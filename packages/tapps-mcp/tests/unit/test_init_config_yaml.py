"""Tests for the comment-preserving .tapps-mcp.yaml writers (TAP-5733).

The point of this module is that a consumer's comments survive a bootstrap
run.  The regression these guard against: ``yaml.safe_load`` → mutate →
``yaml.dump`` rewrites the whole document and silently deletes every comment
in it, including the ones explaining why a setting was overridden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from tapps_mcp.pipeline.init_config_yaml import (
    _ensure_cursor_stop_completion_gate_config,
    _ensure_memory_hooks_config,
    _memory_hooks_defaults_for_engagement,
    _persist_skill_tier,
)

if TYPE_CHECKING:
    from pathlib import Path

COMMENTED_CONFIG = """\
# Why this project raises the stock ceiling: the platform ships 40 skills.
skill_count_max: 60

# Do not remove until TAP-1234 lands; the generated file breaks the build.
upgrade_skip_files:
  - AGENTS.md

quality_preset: standard
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / ".tapps-mcp.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")
    return path


class TestMemoryHooksDefaults:
    def test_high_enables_both(self) -> None:
        defaults = _memory_hooks_defaults_for_engagement("high")
        assert defaults["auto_recall"]["enabled"] is True
        assert defaults["auto_capture"]["enabled"] is True

    def test_medium_enables_recall_only(self) -> None:
        defaults = _memory_hooks_defaults_for_engagement("medium")
        assert defaults["auto_recall"]["enabled"] is True
        assert defaults["auto_capture"]["enabled"] is False

    def test_low_disables_both(self) -> None:
        defaults = _memory_hooks_defaults_for_engagement("low")
        assert defaults["auto_recall"]["enabled"] is False
        assert defaults["auto_capture"]["enabled"] is False

    def test_unknown_level_falls_back_to_disabled(self) -> None:
        assert _memory_hooks_defaults_for_engagement("bogus") == (
            _memory_hooks_defaults_for_engagement("low")
        )


class TestCommentPreservation:
    """The regression this whole module exists to prevent."""

    def test_memory_hooks_keeps_existing_comments(self, tmp_path: Path, config_path: Path) -> None:
        assert _ensure_memory_hooks_config(tmp_path, "high") == "created"
        text = config_path.read_text(encoding="utf-8")
        assert "# Why this project raises the stock ceiling" in text
        assert "# Do not remove until TAP-1234 lands" in text

    def test_cursor_gate_keeps_existing_comments(self, tmp_path: Path, config_path: Path) -> None:
        assert _ensure_cursor_stop_completion_gate_config(tmp_path) == "created"
        text = config_path.read_text(encoding="utf-8")
        assert "# Why this project raises the stock ceiling" in text
        assert "# Do not remove until TAP-1234 lands" in text

    def test_skill_tier_keeps_existing_comments(self, tmp_path: Path, config_path: Path) -> None:
        _persist_skill_tier(tmp_path, "core")
        text = config_path.read_text(encoding="utf-8")
        assert "# Why this project raises the stock ceiling" in text
        assert "# Do not remove until TAP-1234 lands" in text

    def test_untouched_values_survive(self, tmp_path: Path, config_path: Path) -> None:
        _ensure_memory_hooks_config(tmp_path, "high")
        _ensure_cursor_stop_completion_gate_config(tmp_path)
        _persist_skill_tier(tmp_path, "core")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["skill_count_max"] == 60
        assert data["upgrade_skip_files"] == ["AGENTS.md"]
        assert data["quality_preset"] == "standard"
        assert data["skill_tier"] == "core"
        assert data["cursor_stop_completion_gate"] == "warn"
        assert data["memory_hooks"]["auto_capture"]["enabled"] is True


class TestEnsureMemoryHooksConfig:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        assert _ensure_memory_hooks_config(tmp_path, "medium") == "created"
        data = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text(encoding="utf-8"))
        assert data["memory_hooks"]["auto_recall"]["enabled"] is True

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        assert _ensure_memory_hooks_config(tmp_path, "high", dry_run=True) == "skipped"
        assert not (tmp_path / ".tapps-mcp.yaml").exists()

    def test_skips_when_already_complete(self, tmp_path: Path) -> None:
        assert _ensure_memory_hooks_config(tmp_path, "high") == "created"
        assert _ensure_memory_hooks_config(tmp_path, "high") == "skipped"

    def test_fills_missing_subkeys(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("memory_hooks:\n  auto_recall:\n    enabled: true\n", encoding="utf-8")
        assert _ensure_memory_hooks_config(tmp_path, "high") == "updated"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["memory_hooks"]["auto_recall"]["max_results"] == 5
        assert data["memory_hooks"]["auto_capture"]["enabled"] is True

    def test_preserves_user_overrides(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text(
            "memory_hooks:\n  auto_recall:\n    enabled: false\n    max_results: 99\n",
            encoding="utf-8",
        )
        _ensure_memory_hooks_config(tmp_path, "high")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["memory_hooks"]["auto_recall"]["enabled"] is False
        assert data["memory_hooks"]["auto_recall"]["max_results"] == 99

    def test_malformed_yaml_records_warning_and_skips(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("memory_hooks: [unclosed\n", encoding="utf-8")
        warnings: list[str] = []
        assert _ensure_memory_hooks_config(tmp_path, "high", warnings=warnings) == "skipped"
        assert warnings and "memory_hooks" in warnings[0]
        assert path.read_text(encoding="utf-8") == "memory_hooks: [unclosed\n"


class TestEnsureCursorStopCompletionGateConfig:
    def test_creates_warn_when_missing(self, tmp_path: Path) -> None:
        assert _ensure_cursor_stop_completion_gate_config(tmp_path) == "created"
        data = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text(encoding="utf-8"))
        assert data["cursor_stop_completion_gate"] == "warn"

    def test_migrates_block_to_warn(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("cursor_stop_completion_gate: block\n", encoding="utf-8")
        assert _ensure_cursor_stop_completion_gate_config(tmp_path) == "updated"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["cursor_stop_completion_gate"] == "warn"

    def test_skips_when_warn_already_set(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("cursor_stop_completion_gate: warn\n", encoding="utf-8")
        assert _ensure_cursor_stop_completion_gate_config(tmp_path) == "skipped"

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        assert _ensure_cursor_stop_completion_gate_config(tmp_path, dry_run=True) == "skipped"
        assert not (tmp_path / ".tapps-mcp.yaml").exists()

    def test_malformed_yaml_records_warning_and_skips(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("bad: [unclosed\n", encoding="utf-8")
        warnings: list[str] = []
        assert _ensure_cursor_stop_completion_gate_config(tmp_path, warnings=warnings) == "skipped"
        assert warnings and "cursor_stop_completion_gate" in warnings[0]


class TestPersistSkillTier:
    def test_writes_valid_tier(self, tmp_path: Path) -> None:
        _persist_skill_tier(tmp_path, "core")
        data = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text(encoding="utf-8"))
        assert data["skill_tier"] == "core"

    def test_ignores_invalid_tier(self, tmp_path: Path) -> None:
        _persist_skill_tier(tmp_path, "bogus")
        assert not (tmp_path / ".tapps-mcp.yaml").exists()

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        _persist_skill_tier(tmp_path, "full", dry_run=True)
        assert not (tmp_path / ".tapps-mcp.yaml").exists()

    def test_replaces_existing_tier(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("skill_tier: full\nquality_preset: standard\n", encoding="utf-8")
        _persist_skill_tier(tmp_path, "core")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["skill_tier"] == "core"
        assert data["quality_preset"] == "standard"

    def test_malformed_yaml_is_not_destroyed(self, tmp_path: Path) -> None:
        path = tmp_path / ".tapps-mcp.yaml"
        path.write_text("quality_preset: standard\nbroken: [unclosed\n", encoding="utf-8")
        _persist_skill_tier(tmp_path, "core")
        text = path.read_text(encoding="utf-8")
        assert "quality_preset: standard" in text
        assert "skill_tier: core" in text

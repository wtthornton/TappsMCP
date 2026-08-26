"""TAP-6499: invalid ``upgrade_skip_files`` entries must be loud, not inert.

A consumer configured four full file paths (``.claude/skills/<name>/SKILL.md``
and siblings). None are skip tokens, so none protected anything, and two
upgrades rewrote a customized skill without a word of output. The regression
target is the *signal*, not the matching: per-file granularity stays out of
scope, but a path entry now names itself in upgrade output, in the result dict,
and in ``tapps doctor``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.distribution.doctor_platform import check_upgrade_skip_tokens
from tapps_mcp.pipeline import upgrade as upgrade_mod
from tapps_mcp.pipeline.upgrade import upgrade_pipeline
from tapps_mcp.pipeline.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    describe_unknown_skip_token,
    nearest_token,
    unknown_skip_tokens,
)

# The exact shape of the consumer report: a full path to one skill's SKILL.md.
BAD_ENTRY = ".claude/skills/orchestration-prompt/SKILL.md"


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Drop any cached Settings so test-level env tweaks take effect."""
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _python_project(root: Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")


class TestVocabulary:
    def test_single_file_path_is_not_a_token(self) -> None:
        assert BAD_ENTRY not in ALL_SKIP_TOKENS
        assert unknown_skip_tokens([BAD_ENTRY]) == [BAD_ENTRY]

    def test_valid_token_is_not_flagged(self) -> None:
        assert unknown_skip_tokens([".claude/skills", "CLAUDE.md"]) == []

    def test_nearest_token_points_at_the_directory(self) -> None:
        assert nearest_token(BAD_ENTRY) == ".claude/skills"
        assert nearest_token(".claude/hooks/tapps-stop.sh") == ".claude/hooks"
        assert nearest_token("some/unrelated/thing.md") is None

    def test_explanation_names_entry_and_remedy(self) -> None:
        message = describe_unknown_skip_token(BAD_ENTRY)
        assert BAD_ENTRY in message
        assert ".claude/skills" in message
        assert "is not a skip token" in message
        assert "directory granularity" in message

    def test_explanation_for_unrecognized_entry_lists_vocabulary(self) -> None:
        message = describe_unknown_skip_token("not_a_real_token")
        assert "not_a_real_token" in message
        assert "karpathy" in message


class TestUpgradeSignal:
    def test_single_file_path_entry_warns_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The acceptance case: one file-path entry, one unmissable warning."""
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([BAD_ENTRY]))

        logged: list[tuple[str, dict[str, Any]]] = []
        monkeypatch.setattr(
            upgrade_mod.log,
            "warning",
            lambda event, **kw: logged.append((event, kw)),
        )

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert result["unknown_skip_tokens"] == [BAD_ENTRY]
        warnings = result["warnings"]
        assert any(BAD_ENTRY in w and ".claude/skills" in w for w in warnings)
        assert any(event == "upgrade.unknown_skip_tokens" for event, _ in logged)
        assert logged[0][1]["unknown"] == [BAD_ENTRY]

    def test_valid_token_emits_no_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/skills"]))
        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        assert "unknown_skip_tokens" not in result
        assert not [w for w in result.get("warnings", []) if "skip token" in w]

    def test_cli_renders_the_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A warning that never reaches stdout is the bug being fixed."""
        from tapps_mcp.distribution.setup_upgrade_cli import _format_upgrade_result

        _format_upgrade_result(
            {"version": "0.0.0", "warnings": [f"{BAD_ENTRY} is not a skip token"]},
            dry_run=True,
        )
        out = click.unstyle(capsys.readouterr().out)
        assert f"WARNING: {BAD_ENTRY} is not a skip token" in out


class TestDoctorFinding:
    def test_doctor_fails_on_file_path_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([BAD_ENTRY]))
        check = check_upgrade_skip_tokens(tmp_path)
        assert check.severity == "fail"
        assert BAD_ENTRY in check.message
        assert ".claude/skills" in check.detail

    def test_doctor_passes_on_valid_token(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/skills"]))
        check = check_upgrade_skip_tokens(tmp_path)
        assert check.ok
        assert ".claude/skills" in check.message

    def test_doctor_quiet_when_unconfigured(self, tmp_path: Path) -> None:
        check = check_upgrade_skip_tokens(tmp_path)
        assert check.ok
        assert "no skip tokens" in check.message

    def test_check_is_registered_in_the_doctor_run(self) -> None:
        """Registered in the spec list — an unwired check reports nothing."""
        from tapps_mcp.distribution.doctor_runner import _collect_checks

        assert "upgrade_skip_files" in _collect_checks.__code__.co_consts


class TestSettingsDocumentation:
    def test_field_description_states_the_three_facts(self) -> None:
        """Acceptance item 4: fixed tokens, directory granularity, upstream fold."""
        from tapps_core.config.settings import TappsMCPSettings

        description = TappsMCPSettings.model_fields["upgrade_skip_files"].description or ""
        assert "FIXED TOKEN VOCABULARY" in description
        assert "GRANULARITY IS PER-ARTIFACT" in description
        assert "DURABLE ALTERNATIVE" in description

"""Dry-run and live must resolve every component from the same plan (TAP-6913).

Before the split, each host had a ``_dry_run`` twin of its ``_live`` function
and the two drifted silently:

* the preview ignored ``upgrade_skip_files`` for ``python_quality_rule``,
  ``agent_scope_rule``, ``linear_standards_rule`` and ``pipeline_rule`` — a
  consumer who skip-listed a rule was told it would be regenerated;
* ``agent_to_agent_rule`` was missing from the preview entirely, so an artifact
  the live run writes never appeared in the plan.

A preview that disagrees with the run it previews is worse than no preview, so
these assertions compare the two directly rather than pinning literals.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.upgrade import upgrade_pipeline

# Rules whose preview used to ignore the skip token.
PREVIOUSLY_DIVERGENT_RULES = (
    ("python_quality_rule", ".claude/rules/python-quality.md"),
    ("agent_scope_rule", ".claude/rules/agent-scope.md"),
    ("linear_standards_rule", ".claude/rules/linear-standards.md"),
    ("pipeline_rule", ".claude/rules/tapps-pipeline.md"),
)


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """Drop any cached Settings so per-test env tweaks take effect."""
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _python_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / ".claude").mkdir()


def _claude_components(result: dict[str, Any]) -> dict[str, Any]:
    host = next(p for p in result["components"]["platforms"] if p["host"] == "claude-code")
    return host["components"]


class TestSkipTokensApplyToBothModes:
    @pytest.mark.parametrize(("component", "token"), PREVIOUSLY_DIVERGENT_RULES)
    def test_preview_reports_the_skip_the_live_run_performs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        component: str,
        token: str,
    ) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([token]))

        dry = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=True))
        live = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=False))

        assert dry[component] == "skipped (upgrade_skip_files)"
        assert live[component] == "skipped (upgrade_skip_files)"

    @pytest.mark.parametrize(("component", "token"), PREVIOUSLY_DIVERGENT_RULES)
    def test_unskipped_rule_is_planned_and_written(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        component: str,
        token: str,
    ) -> None:
        """Negative control: with no skip list, both modes act on the rule."""
        _python_project(tmp_path)
        monkeypatch.delenv("TAPPS_MCP_UPGRADE_SKIP_FILES", raising=False)

        dry = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=True))
        live = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=False))

        assert dry[component] == "would-regenerate"
        assert live[component]["action"] in {"created", "updated", "unchanged"}
        assert (tmp_path / token).exists()


class TestPreviewCoversEveryLiveComponent:
    def test_dry_run_names_every_component_the_live_run_writes(self, tmp_path: Path) -> None:
        """The plan must not omit an artifact — ``agent_to_agent_rule`` was missing."""
        _python_project(tmp_path)

        dry = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=True))
        live = _claude_components(upgrade_pipeline(tmp_path, platform="claude", dry_run=False))

        # Live-only keys are write-step reports (what the generators did), not
        # plan entries: the preview cannot have migrated a hook or wired one.
        write_step_only = {"retired_hooks", "memory_hooks"}
        missing_from_preview = set(live) - set(dry) - write_step_only
        assert not missing_from_preview, (
            f"dry-run plan omits components the live run writes: {sorted(missing_from_preview)}"
        )
        assert "agent_to_agent_rule" in dry

"""TAP-7054 round 2: skip tokens must be *consumed*, not just recognized.

The vocabulary in ``upgrade_skip_tokens.SKIP_TOKENS`` gained
``cursor_hooks``/``cursor_agents``/``cursor_skills``/``copilot_instructions``
tokens, and ``test_upgrade_skip_token_validation.py`` proved they're valid
tokens. But every ``resolve_component`` call site in
``upgrade_host_cursor.py`` passed ``skip_key=None``, and
``run_github_artifacts`` in ``upgrade_github.py`` never checked
``copilot_instructions`` at all — so pinning ``.cursor/hooks`` in
``upgrade_skip_files`` reported the token as "applied" while the upgrade
still recreated the component. This file proves the component itself is
now skipped, with an unpinned positive control proving the skip is
conditional rather than the component having stopped being generated.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.upgrade import upgrade_pipeline


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _python_project(root: Path) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")


def _cursor_component(result: dict, name: str) -> object:
    platforms = result["components"]["platforms"]
    (cursor,) = [p for p in platforms if p.get("host") == "cursor"]
    return cursor["components"][name]


class TestCursorSkipTokensAreConsumed:
    """Negative control (unpinned) vs. positive control (pinned) per component."""

    @pytest.mark.parametrize(
        "token,component_name,sentinel_rel",
        [
            (".cursor/hooks", "hooks", ".cursor/hooks/sentinel.sh"),
            (".cursor/agents", "agents", ".cursor/agents/sentinel.md"),
            (".cursor/skills", "skills", ".cursor/skills/sentinel/SKILL.md"),
        ],
    )
    def test_pinned_component_is_skipped_and_sentinel_untouched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        token: str,
        component_name: str,
        sentinel_rel: str,
    ) -> None:
        _python_project(tmp_path)
        sentinel = tmp_path / sentinel_rel
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("pinned-content\n", encoding="utf-8")
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([token]))

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)

        assert result["applied_skip_tokens"] == [token]
        assert _cursor_component(result, component_name) == "skipped (upgrade_skip_files)"
        assert sentinel.read_text() == "pinned-content\n"

    @pytest.mark.parametrize(
        "component_name",
        ["hooks", "agents", "skills"],
    )
    def test_unpinned_component_is_created(
        self, tmp_path: Path, component_name: str
    ) -> None:
        """Positive control: without the pin, the component is still generated —
        proving the skip above is conditional, not that generation broke."""
        _python_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)

        assert "applied_skip_tokens" not in result
        component = _cursor_component(result, component_name)
        assert component != "skipped (upgrade_skip_files)"


class TestCopilotInstructionsSkipTokenIsConsumed:
    def test_pinned_copilot_instructions_is_skipped_and_file_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True)
        target = github_dir / "copilot-instructions.md"
        target.write_text("pinned-content\n", encoding="utf-8")
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".github/copilot-instructions.md"])
        )

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        assert result["applied_skip_tokens"] == [".github/copilot-instructions.md"]
        assert result["components"]["github_copilot"] == "skipped (upgrade_skip_files)"
        assert target.read_text() == "pinned-content\n"

    def test_unpinned_copilot_instructions_is_regenerated(self, tmp_path: Path) -> None:
        """Positive control: without the pin, github_copilot still runs."""
        _python_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        assert "applied_skip_tokens" not in result
        assert result["components"]["github_copilot"] != "skipped (upgrade_skip_files)"

    def test_pinned_copilot_instructions_dry_run_reports_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".github/copilot-instructions.md"])
        )

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert result["components"]["github_copilot"] == "skipped (upgrade_skip_files)"

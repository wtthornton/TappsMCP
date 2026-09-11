"""TAP-7425: the ``docs_automation`` skip token must be real on BOTH hosts.

Before this fix, ``docs_automation`` was missing from ``SKIP_TOKENS`` entirely
(Claude host: syntactically guarded but functionally inert — ``skipped()``
fell through ``dict.get(..., frozenset())`` and always returned ``False``) and
``upgrade_host_cursor.py`` passed ``skip_key=None`` (Cursor host: explicitly
unguarded). These are two independent bugs with two independent fixes; a test
that only proves one host is skip-aware would let the other regress silently.

Every positive test here has a paired negative control per the "one thing
that will silently give a wrong result" warning: a non-empty frozenset that
maps to a token nobody would ever configure is indistinguishable from a
correctly-wired guard until you prove the token actually stops the rewrite.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.upgrade import upgrade_pipeline
from tapps_mcp.pipeline.upgrade_report import skipped
from tapps_mcp.pipeline.upgrade_skip_tokens import SKIP_TOKENS


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _docs_project(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["docs-mcp"]\n',
        encoding="utf-8",
    )


def _platform_component(result: dict, host: str, name: str) -> object:
    platforms = result["components"]["platforms"]
    (matched,) = [p for p in platforms if p.get("host") == host]
    return matched["components"][name]


class TestSkipTokenVocabulary:
    """Box 1: the vocabulary entry itself is non-empty and holds a real token."""

    def test_docs_automation_is_a_non_empty_frozenset(self) -> None:
        assert "docs_automation" in SKIP_TOKENS
        assert SKIP_TOKENS["docs_automation"] == frozenset({"docs_automation"})
        assert SKIP_TOKENS["docs_automation"]

    def test_negative_control_unpinned_artifact_is_still_rewritten(
        self, tmp_path: Path
    ) -> None:
        """Without the token configured, the guard must NOT fire — proves the
        guard is conditional, not accidentally always-on."""
        _docs_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        docs_info = _platform_component(result, "claude-code", "docs_automation")
        assert docs_info != "skipped (upgrade_skip_files)"
        assert "applied_skip_tokens" not in result


class TestClaudeHostSkipTokenIsConsumed:
    """Box 2."""

    def test_pinned_docs_automation_is_skipped_on_claude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _docs_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        assert result["applied_skip_tokens"] == ["docs_automation"]
        docs_info = _platform_component(result, "claude-code", "docs_automation")
        assert docs_info == "skipped (upgrade_skip_files)"
        assert not (tmp_path / ".claude" / "skills" / "tapps-docs-refresh").exists()

    def test_negative_control_unpinned_docs_automation_is_created_on_claude(
        self, tmp_path: Path
    ) -> None:
        """Remove the pin: the artifact IS rewritten — the test discriminates."""
        _docs_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        docs_info = _platform_component(result, "claude-code", "docs_automation")
        assert docs_info != "skipped (upgrade_skip_files)"
        assert (tmp_path / ".claude" / "skills" / "tapps-docs-refresh" / "SKILL.md").is_file()


class TestCursorHostSkipTokenIsConsumed:
    """Box 3."""

    def test_pinned_docs_automation_is_skipped_on_cursor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _docs_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)

        assert result["applied_skip_tokens"] == ["docs_automation"]
        docs_info = _platform_component(result, "cursor", "docs_automation")
        assert docs_info == "skipped (upgrade_skip_files)"
        assert not (tmp_path / ".cursor" / "skills" / "tapps-docs-refresh").exists()

    def test_negative_control_unpinned_docs_automation_is_created_on_cursor(
        self, tmp_path: Path
    ) -> None:
        """Same negative control mirrored for the Cursor path."""
        _docs_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)

        docs_info = _platform_component(result, "cursor", "docs_automation")
        assert docs_info != "skipped (upgrade_skip_files)"
        assert (tmp_path / ".cursor" / "skills" / "tapps-docs-refresh" / "SKILL.md").is_file()


class TestBothHostsCoveredInOneCrossHostProof:
    """Box 4: fixing only one host must not pass this test.

    Pinning ``docs_automation`` and running BOTH hosts in the same test body
    means a regression that "fixes" only Claude or only Cursor fails here,
    not in a host-specific file a reviewer might skip.
    """

    def test_docs_automation_token_skips_both_hosts_when_pinned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _docs_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))

        claude_result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        cursor_result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)

        assert (
            _platform_component(claude_result, "claude-code", "docs_automation")
            == "skipped (upgrade_skip_files)"
        )
        assert (
            _platform_component(cursor_result, "cursor", "docs_automation")
            == "skipped (upgrade_skip_files)"
        )


class TestSkippedRaisesOnUnknownArtifact:
    """Box 5.

    ``resolve_component`` short-circuits on ``skip_key is None`` before ever
    calling ``skipped()`` (see ``upgrade_host_context.py``), so a component
    that intentionally has no skip token — e.g. ``cursor_rules`` above, which
    passes ``skip_key=None`` — never reaches this raise. The raise only
    guards against a *typo'd or unregistered* artifact name being passed to
    ``skipped()`` directly, which is exactly the class of bug this lane
    fixes: a guard that looks wired up but can structurally never fire.
    """

    def test_unknown_artifact_name_raises_instead_of_returning_false(self) -> None:
        with pytest.raises(KeyError):
            skipped("totally_unknown_artifact", {"totally_unknown_artifact"})

    def test_known_artifact_still_returns_a_plain_bool(self) -> None:
        assert skipped("docs_automation", {"docs_automation"}) is True
        assert skipped("docs_automation", set()) is False


class TestDryRunStatusReflectsThePin:
    """GAP 1 (box 1): a dry run never writes in EITHER case, so the only
    observable this class of test can assert is the *reported status* —
    not "the file was not rewritten" (that would be true either way and is
    an inert assertion per the lane brief). Each test asserts BOTH
    directions in one body: pinned -> ``skipped (upgrade_skip_files)``,
    unpinned -> the ``would-write-managed-skills`` planning dict. An
    assertion that only checked the pinned half could not tell a working
    guard from a guard that always reports "skipped" regardless of the pin
    (an always-skip bug), which is why both directions live together here.
    """

    def test_claude_dry_run_reports_skipped_when_pinned_and_plan_when_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _docs_project(tmp_path)

        unpinned = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        unpinned_status = _platform_component(unpinned, "claude-code", "docs_automation")
        assert unpinned_status != "skipped (upgrade_skip_files)"
        assert isinstance(unpinned_status, dict)
        assert unpinned_status["action"] == "would-write-managed-skills"

        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))
        pinned = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        pinned_status = _platform_component(pinned, "claude-code", "docs_automation")
        assert pinned_status == "skipped (upgrade_skip_files)"

        # Dry run performed no write in either case -- the discriminator is
        # the reported status above, not filesystem state.
        assert not (tmp_path / ".claude" / "skills" / "tapps-docs-refresh").exists()

    def test_cursor_dry_run_reports_skipped_when_pinned_and_plan_when_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _docs_project(tmp_path)

        unpinned = upgrade_pipeline(tmp_path, platform="cursor", dry_run=True)
        unpinned_status = _platform_component(unpinned, "cursor", "docs_automation")
        assert unpinned_status != "skipped (upgrade_skip_files)"
        assert isinstance(unpinned_status, dict)
        assert unpinned_status["action"] == "would-write-managed-skills"

        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["docs_automation"]))
        pinned = upgrade_pipeline(tmp_path, platform="cursor", dry_run=True)
        pinned_status = _platform_component(pinned, "cursor", "docs_automation")
        assert pinned_status == "skipped (upgrade_skip_files)"

        assert not (tmp_path / ".cursor" / "skills" / "tapps-docs-refresh").exists()

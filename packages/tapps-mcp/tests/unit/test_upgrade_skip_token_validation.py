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
from tapps_mcp.distribution.doctor_skip_drift import check_upgrade_skip_token_drift
from tapps_mcp.pipeline import upgrade_report as upgrade_report_mod
from tapps_mcp.pipeline.platform_bundles import (
    generate_claude_agent_scope_rule,
    generate_claude_autonomy_rule,
)
from tapps_mcp.pipeline.upgrade import upgrade_pipeline
from tapps_mcp.pipeline.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    applied_skip_tokens,
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

    def test_applied_skip_tokens_returns_the_matched_entries(self) -> None:
        assert applied_skip_tokens([".claude/skills", "CLAUDE.md"]) == [
            ".claude/skills",
            "CLAUDE.md",
        ]

    def test_applied_skip_tokens_excludes_unknown_entries(self) -> None:
        assert applied_skip_tokens([BAD_ENTRY, "not_a_real_token"]) == []


class TestCursorAndCopilotTokens:
    """TAP-7054: .cursor/* and .github/copilot-instructions.md were writable
    by upgrade but had no covering skip token, so an operator had no way to
    pin them — the ten uncovered entries this issue's acceptance references."""

    def test_cursor_directories_and_copilot_file_are_known_tokens(self) -> None:
        assert (
            unknown_skip_tokens(
                [
                    ".cursor/hooks",
                    ".cursor/agents",
                    ".cursor/skills",
                    ".github/copilot-instructions.md",
                ]
            )
            == []
        )

    def test_cursor_tokens_cover_every_path_the_upgrade_writes(self) -> None:
        """Acceptance box 4: every path these two modules write is a token."""
        written_paths = {
            ".cursor/hooks",  # platform_hooks.py: generate_cursor_hooks()
            ".github/copilot-instructions.md",  # github_copilot.py
        }
        assert unknown_skip_tokens(written_paths) == []

    def test_entry_inside_cursor_hooks_names_the_directory_token(self) -> None:
        """Acceptance box 3: inside-a-directory-token is distinguished from
        no-covering-token at all — same shape as the pre-existing
        ``.claude/hooks`` case, now extended to the Cursor mirror."""
        bad_entry = ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"
        assert nearest_token(bad_entry) == ".cursor/hooks"
        message = describe_unknown_skip_token(bad_entry)
        assert "directory granularity" in message
        assert ".cursor/hooks" in message

    def test_entry_inside_cursor_skills_names_the_directory_token(self) -> None:
        bad_entry = ".cursor/skills/orchestration-prompt/SKILL.md"
        assert nearest_token(bad_entry) == ".cursor/skills"

    def test_entry_inside_cursor_agents_names_the_directory_token(self) -> None:
        bad_entry = ".cursor/agents/reviewer.md"
        assert nearest_token(bad_entry) == ".cursor/agents"

    def test_unrelated_path_still_has_no_nearest_token(self) -> None:
        """Negative control: an entry outside every directory token still
        reports no-covering-token, proving the distinction isn't vacuous."""
        assert nearest_token(".github/workflows/ci.yml") is None
        message = describe_unknown_skip_token(".github/workflows/ci.yml")
        assert "directory granularity" not in message
        assert "not a recognized skip token" in message


class TestUpgradeSignal:
    def test_single_file_path_entry_warns_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The acceptance case: one file-path entry, one unmissable warning."""
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([BAD_ENTRY]))

        logged: list[tuple[str, dict[str, Any]]] = []
        # TAP-6913: the warning is emitted from the extracted reporting module.
        monkeypatch.setattr(
            upgrade_report_mod.log,
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


class TestAppliedSkipTokens:
    """TAP-6891: a working entry must be confirmable, not just inferred.

    ``_record_unknown_skip_tokens`` already makes a no-op entry loud. Before
    this change, a *working* entry produced identical (silent) output to an
    unconfigured project — "applied" and "not configured" were
    indistinguishable in the run output.
    """

    def test_valid_entries_are_recorded_as_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control: a config of only-valid entries reports them as applied."""
        _python_project(tmp_path)
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/skills", "CLAUDE.md"])
        )
        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert result["applied_skip_tokens"] == [".claude/skills", "CLAUDE.md"]
        assert "unknown_skip_tokens" not in result

    def test_unknown_only_config_reports_none_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: an unknown-only config applies nothing."""
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([BAD_ENTRY]))
        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert "applied_skip_tokens" not in result

    def test_unknown_entry_warning_path_fires_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The existing unknown-entry warning must be byte-unchanged by this change."""
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([BAD_ENTRY]))

        logged: list[tuple[str, dict[str, Any]]] = []
        # TAP-6913: the warning is emitted from the extracted reporting module.
        monkeypatch.setattr(
            upgrade_report_mod.log,
            "warning",
            lambda event, **kw: logged.append((event, kw)),
        )

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert result["unknown_skip_tokens"] == [BAD_ENTRY]
        assert result["warnings"] == [describe_unknown_skip_token(BAD_ENTRY)]
        assert logged == [
            (
                "upgrade.unknown_skip_tokens",
                {"unknown": [BAD_ENTRY], "detail": describe_unknown_skip_token(BAD_ENTRY)},
            )
        ]

    def test_cli_renders_the_applied_tokens(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An applied entry that never reaches stdout is indistinguishable from unset."""
        from tapps_mcp.distribution.setup_upgrade_cli import _format_upgrade_result

        _format_upgrade_result(
            {"version": "0.0.0", "applied_skip_tokens": [".claude/skills", "CLAUDE.md"]},
            dry_run=True,
        )
        out = click.unstyle(capsys.readouterr().out)
        assert ".claude/skills" in out
        assert "CLAUDE.md" in out
        assert "applied" in out.lower()


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


class TestSkipTokenDriftReport:
    """TAP-6600: a skip entry's silence cuts both ways — report which."""

    def test_no_configured_tokens_is_quiet(self, tmp_path: Path) -> None:
        check = check_upgrade_skip_token_drift(tmp_path)
        assert check.ok
        assert "no recognized skip tokens" in check.message

    def test_identical_file_reported_as_removable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        generate_claude_autonomy_rule(tmp_path)
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/rules/autonomy.md"])
        )

        check = check_upgrade_skip_token_drift(tmp_path)

        assert check.ok
        assert check.severity == "pass"
        assert "identical" in check.message
        assert ".claude/rules/autonomy.md" in check.message

    def test_diverged_file_is_reported_not_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        generate_claude_autonomy_rule(tmp_path)
        (tmp_path / ".claude" / "rules" / "autonomy.md").write_text(
            "local customization the operator wants to keep\n", encoding="utf-8"
        )
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/rules/autonomy.md"])
        )

        check = check_upgrade_skip_token_drift(tmp_path)

        # Reported (severity=warn, ok=False) but never blocking (doctor's
        # exit code is driven by fail_count only, not warn_count).
        assert check.severity == "warn"
        assert not check.ok
        assert "diverged" in check.message
        assert ".claude/rules/autonomy.md" in check.message

    def test_missing_path_reported_distinctly_from_diverged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/rules/autonomy.md"])
        )

        check = check_upgrade_skip_token_drift(tmp_path)

        assert check.severity == "warn"
        assert "no longer exists" in check.message
        assert "diverged" not in check.message

    def test_directory_token_reported_as_unsupported_not_guessed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".claude" / "hooks").mkdir(parents=True)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/hooks"]))

        check = check_upgrade_skip_token_drift(tmp_path)

        assert check.ok  # unsupported is not itself a problem
        assert "not yet drift-checkable" in check.message

    def test_multiple_entries_each_get_their_own_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        generate_claude_autonomy_rule(tmp_path)
        generate_claude_agent_scope_rule(tmp_path)
        (tmp_path / ".claude" / "rules" / "autonomy.md").write_text("drifted\n", encoding="utf-8")
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES",
            json.dumps([".claude/rules/autonomy.md", ".claude/rules/agent-scope.md"]),
        )

        check = check_upgrade_skip_token_drift(tmp_path)

        assert "diverged" in check.message
        assert "identical" in check.message
        assert ".claude/rules/autonomy.md" in check.message
        assert ".claude/rules/agent-scope.md" in check.message

    def test_never_writes_to_the_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        generate_claude_autonomy_rule(tmp_path)
        target = tmp_path / ".claude" / "rules" / "autonomy.md"
        before = target.read_bytes()
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps([".claude/rules/autonomy.md"])
        )

        check_upgrade_skip_token_drift(tmp_path)

        assert target.read_bytes() == before

    def test_check_is_registered_in_the_doctor_run(self) -> None:
        from tapps_mcp.distribution.doctor_runner import _collect_checks

        assert "upgrade_skip_files drift" in _collect_checks.__code__.co_consts


class TestClaudeMdDriftReport:
    """TAP-6600 residual: ``claude_md`` reported 'not yet drift-checkable' even
    though it's the issue's own motivating example (nlt-orchestrator's only
    upgrade_skip_files entry). CLAUDE.md isn't a full-overwrite template like
    the ten rule files — most of it is project-specific prose — so drift is
    judged on the marker-wrapped obligations block via the real merge, not a
    whole-file diff."""

    def test_claude_md_drift_reports_identical_for_a_fresh_render(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.pipeline.claude_md import render_fresh_claude_md
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        obligations = load_platform_rules("claude", engagement_level="medium")
        (tmp_path / "CLAUDE.md").write_text(
            render_fresh_claude_md(obligations), encoding="utf-8"
        )
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["CLAUDE.md"]))

        check = check_upgrade_skip_token_drift(tmp_path)

        assert check.ok
        assert check.severity == "pass"
        assert "identical" in check.message
        assert "CLAUDE.md" in check.message
        assert "not yet drift-checkable" not in check.message

    def test_claude_md_drift_reports_diverged_for_a_hand_edit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "<!-- tapps-claude-version: 0.0.1 -->\n# Stale hand-edited content\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["CLAUDE.md"]))

        check = check_upgrade_skip_token_drift(tmp_path)

        assert check.severity == "warn"
        assert not check.ok
        assert "diverged" in check.message
        assert "CLAUDE.md" in check.message

    def test_claude_md_drift_reports_missing_not_unsupported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", json.dumps(["CLAUDE.md"]))

        check = check_upgrade_skip_token_drift(tmp_path)

        assert "no longer exists" in check.message
        assert "not yet drift-checkable" not in check.message


class TestSettingsDocumentation:
    def test_field_description_states_the_three_facts(self) -> None:
        """Acceptance item 4: fixed tokens, directory granularity, upstream fold."""
        from tapps_core.config.settings import TappsMCPSettings

        description = TappsMCPSettings.model_fields["upgrade_skip_files"].description or ""
        assert "FIXED TOKEN VOCABULARY" in description
        assert "GRANULARITY IS PER-ARTIFACT" in description
        assert "DURABLE ALTERNATIVE" in description

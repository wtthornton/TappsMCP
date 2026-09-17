"""Tests for Claude Code plugin bundle generation (Story 12.9).

Verifies that generate_claude_plugin_bundle() creates a complete plugin
directory structure with plugin.json, agents, skills, hooks, .mcp.json,
and README.md.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_generators import (
    generate_claude_plugin_bundle,
)


class TestPluginStructure:
    """Tests for the plugin directory layout."""

    def test_plugin_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / ".claude-plugin" / "plugin.json").exists()

    def test_plugin_json_valid(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
        assert "name" in data
        assert "version" in data
        assert "description" in data

    def test_plugin_json_name(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
        assert data["name"] == "tapps-mcp"

    def test_plugin_json_version_semver(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, version="1.2.3")
        data = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
        assert re.match(r"^\d+\.\d+\.\d+", data["version"])

    def test_agents_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        agents_dir = tmp_path / "agents"
        assert (agents_dir / "tapps-reviewer.md").exists()
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()

    def test_agent_has_name_frontmatter(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "agents" / "tapps-reviewer.md").read_text()
        assert "name:" in content

    def test_skills_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / "skills" / "tapps-finish-task" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-review-pipeline" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-research" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-security" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "tapps-memory" / "SKILL.md").exists()
        assert not (tmp_path / "skills" / "tapps-score" / "SKILL.md").exists()

    def test_hooks_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        hooks_json = tmp_path / "hooks" / "hooks.json"
        assert hooks_json.exists()
        data = json.loads(hooks_json.read_text())
        assert "hooks" in data

    def test_hook_scripts_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / "hooks" / "tapps-stop.sh").exists()

    def test_mcp_json_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        mcp_file = tmp_path / ".mcp.json"
        assert mcp_file.exists()
        data = json.loads(mcp_file.read_text())
        assert "mcpServers" in data
        assert "tapps-mcp" in data["mcpServers"]

    def test_readme_exists(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        readme = tmp_path / "README.md"
        assert readme.exists()
        assert len(readme.read_text()) > 0

    def test_result_dict(self, tmp_path):
        result = generate_claude_plugin_bundle(tmp_path)
        assert "files_created" in result
        assert len(result["files_created"]) > 0
        assert ".claude-plugin/plugin.json" in result["files_created"]
        assert "README.md" in result["files_created"]


class TestPluginManifestExtended:
    """TAP-958: plugin.json carries userConfig and metadata.

    TAP-7758 (Decision A): no `dependencies` key — see
    test_no_dependencies_key below.
    """

    def _load(self, tmp_path, version="3.2.5"):
        generate_claude_plugin_bundle(tmp_path, version=version)
        return json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())

    def test_metadata_fields_present(self, tmp_path):
        data = self._load(tmp_path)
        # `claude plugin validate` (installed CLI, 2.1.258) requires `author`
        # to be an object, not a bare string.
        assert data["author"] == {"name": "TappsMCP Contributors"}
        assert data["license"] == "MIT"
        assert data["homepage"].startswith("https://")
        assert data["repository"].startswith("https://")

    def test_user_config_engagement_level(self, tmp_path):
        data = self._load(tmp_path)
        uc = data["userConfig"]
        assert "engagement_level" in uc
        field = uc["engagement_level"]
        # The installed CLI's userConfig schema has no enum/options/select
        # mechanism (`type` is one of string/number/boolean/directory/file
        # only) — confirmed via `claude plugin validate`, which rejects an
        # `enum` key. `title` is required; allowed values live in the prose.
        assert field["type"] == "string"
        assert field["title"]
        assert field["default"] in {"high", "medium", "low"}
        assert "enum" not in field

    def test_engagement_level_default_configurable(self, tmp_path):
        data = self._load(tmp_path)
        # bare call uses the function's own default
        assert data["userConfig"]["engagement_level"]["default"] == "high"

        low_out = tmp_path / "low"
        generate_claude_plugin_bundle(low_out, engagement_level_default="low")
        low_data = json.loads((low_out / ".claude-plugin" / "plugin.json").read_text())
        assert low_data["userConfig"]["engagement_level"]["default"] == "low"

    def test_user_config_memory_http_url(self, tmp_path):
        data = self._load(tmp_path)
        field = data["userConfig"]["memory_http_url"]
        assert field["type"] == "string"
        assert field["title"]
        assert field["default"].startswith("http")

    def test_user_config_quality_preset(self, tmp_path):
        data = self._load(tmp_path)
        field = data["userConfig"]["quality_preset"]
        assert field["title"]
        assert field["default"] in {"standard", "strict", "framework"}
        assert "enum" not in field

    def test_no_dependencies_key(self, tmp_path):
        # TAP-7758 (Decision A) — the manifest used to declare
        # `dependencies: ["docs-mcp@^{version}"]`, but nothing shipped in
        # this bundle calls `mcp__docs-mcp__` at runtime, and the CLI parses
        # the `@` suffix as a marketplace name rather than a semver range,
        # so that value was unsatisfiable, not merely unpinned: installing
        # the old bundle failed with `Dependency "docs-mcp@tapps-mcp" is not
        # installed`. `dependencies` is optional, so the fix is to omit the
        # key entirely rather than replace it with another value.
        data = self._load(tmp_path, version="3.2.5")
        assert "dependencies" not in data

    def test_mcp_json_substitutes_user_config(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        mcp_data = json.loads((tmp_path / ".mcp.json").read_text())
        env = mcp_data["mcpServers"]["tapps-mcp"]["env"]
        assert env["TAPPS_BRAIN_HTTP_URL"] == "${user_config.memory_http_url}"
        assert env["TAPPS_LLM_ENGAGEMENT_LEVEL"] == "${user_config.engagement_level}"
        assert env["TAPPS_QUALITY_PRESET"] == "${user_config.quality_preset}"


class TestPluginBinShims:
    """TAP-959: bin/ directory carries POSIX + Windows shim scripts so
    consuming projects can invoke `tapps-quick-lint` / `tapps-doctor-cli`
    directly from the Bash tool."""

    def test_posix_shims_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        assert (bin_dir / "tapps-quick-lint").exists()
        assert (bin_dir / "tapps-doctor-cli").exists()

    def test_posix_shims_executable(self, tmp_path):
        import stat as stat_mod

        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        for name in ("tapps-quick-lint", "tapps-doctor-cli"):
            mode = (bin_dir / name).stat().st_mode
            assert mode & stat_mod.S_IXUSR, f"{name} not user-executable"
            assert mode & stat_mod.S_IXGRP, f"{name} not group-executable"

    def test_posix_shims_shebang(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-quick-lint").read_text()
        assert content.startswith("#!/usr/bin/env bash"), content[:40]

    def test_posix_shims_delegate_to_tapps_mcp(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-quick-lint").read_text()
        assert "tapps-mcp validate-changed --quick" in content
        assert "uvx tapps-mcp" in content  # fallback path

    def test_doctor_shim_delegates_to_doctor(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "bin" / "tapps-doctor-cli").read_text()
        assert "tapps-mcp doctor" in content

    def test_windows_cmd_shims_exist(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        bin_dir = tmp_path / "bin"
        assert (bin_dir / "tapps-quick-lint.cmd").exists()
        assert (bin_dir / "tapps-doctor-cli.cmd").exists()

    def test_windows_cmd_has_crlf_and_batch_header(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        # Read as bytes — Path.read_text normalizes CRLF to LF.
        raw = (tmp_path / "bin" / "tapps-quick-lint.cmd").read_bytes()
        assert raw.startswith(b"@echo off"), raw[:40]
        assert b"\r\n" in raw, "Windows .cmd should use CRLF line endings"


class TestPluginMonitors:
    """TAP-960: monitors/monitors.json emitted only when opted in."""

    def test_monitors_absent_by_default(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        assert not (tmp_path / "monitors").exists()

    def test_monitors_absent_when_disabled(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=False)
        assert not (tmp_path / "monitors" / "monitors.json").exists()

    def test_monitors_emitted_when_enabled(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        path = tmp_path / "monitors" / "monitors.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "monitors" in data
        names = {m["name"] for m in data["monitors"]}
        assert {"tapps-brain-health", "quality-gate-watch"} <= names

    def test_monitor_shape(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        data = json.loads((tmp_path / "monitors" / "monitors.json").read_text())
        for m in data["monitors"]:
            assert m["when"] == "always"
            assert "command" in m
            assert "description" in m

    def test_monitor_uses_plugin_root_substitution(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        data = json.loads((tmp_path / "monitors" / "monitors.json").read_text())
        subst_count = sum(1 for m in data["monitors"] if "${CLAUDE_PLUGIN_ROOT}" in m["command"])
        assert subst_count >= 2, "Expected at least 2 monitors to use plugin-root substitution"

    def test_files_created_includes_monitors_when_enabled(self, tmp_path):
        result = generate_claude_plugin_bundle(tmp_path, monitors_enabled=True)
        assert "monitors/monitors.json" in result["files_created"]


class TestHookIfMatchers:
    """TAP-955: every tool-event hook in emitted hooks.json carries `if:`."""

    _TOOL_EVENTS = (
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
    )

    def _hooks(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        return json.loads((tmp_path / "hooks" / "hooks.json").read_text())["hooks"]

    def test_every_tool_event_entry_has_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for event in self._TOOL_EVENTS:
            for entry in hooks.get(event, []):
                assert "if" in entry, (
                    f"{event} entry missing `if:`: {entry}"
                )

    def test_post_edit_if_targets_python_files(self, tmp_path):
        hooks = self._hooks(tmp_path)
        post_edit = next(
            e for e in hooks["PostToolUse"]
            if any("tapps-post-edit" in h["command"] for h in e["hooks"])
        )
        for expr in ("Edit(**/*.py)", "Write(**/*.py)", "MultiEdit(**/*.py)"):
            assert expr in post_edit["if"], f"missing {expr} in {post_edit['if']}"

    def test_non_tool_events_do_not_carry_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for event in ("SessionStart", "Stop", "SessionEnd", "PreCompact"):
            for entry in hooks.get(event, []):
                assert "if" not in entry, (
                    f"{event} should not carry `if:`, got {entry}"
                )

    def test_post_tool_use_failure_has_if(self, tmp_path):
        hooks = self._hooks(tmp_path)
        for entry in hooks["PostToolUseFailure"]:
            # TAP-7753: a plugin-registered server's tools are namespaced
            # mcp__plugin_<pluginName>_<serverKey>__, not the bare
            # mcp__nlt-build__ shape this bundle's `.mcp.json` never
            # registers a server under.
            assert entry["if"] == "mcp__plugin_tapps-mcp_tapps-mcp__*"


def _git_ls_files(repo_root: Path, subdir: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", subdir],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    prefix = subdir.rstrip("/") + "/"
    return {line[len(prefix) :] for line in result.stdout.splitlines() if line}


class TestCommittedBundleMatchesFreshBuild:
    """Regression guard for a defect class that a bare file-COUNT comparison
    cannot catch: `plugin/claude/.mcp.json` was silently dropped by the
    repo's own `.mcp.json` gitignore pattern while `plugin/claude/` still
    carried the same total tracked-file COUNT as a fresh build, because the
    hand-authored `marketplace.json` happened to swap in for the missing
    file one-for-one (54 either way). A count match hid a real, shipped
    defect: every mcp__tapps-mcp__* tool call in the installed plugin would
    fail with no declared MCP server.

    This test compares PATH SETS, not counts, between a fresh build (the
    generator's actual output) and `git ls-files plugin/claude` (what will
    actually reach an installer). The only allowed difference is the small,
    explicitly-named set of hand-authored files that no generator writes
    (mirroring plugin/cursor's own hand-maintained marketplace.json)."""

    #: Files intentionally NOT produced by generate_claude_plugin_bundle —
    #: hand-authored and committed directly, like plugin/cursor/marketplace.json.
    HAND_AUTHORED = frozenset(
        {
            ".claude-plugin/marketplace.json",
            "LICENSE",
            "CHANGELOG.md",
        }
    )

    def test_git_tracked_paths_match_fresh_build_plus_hand_authored(self, tmp_path):
        from tapps_mcp import __version__

        repo_root = Path(__file__).resolve().parents[4]
        committed_dir = repo_root / "plugin" / "claude"
        assert committed_dir.is_dir(), f"expected {committed_dir} to exist"

        tracked = _git_ls_files(repo_root, "plugin/claude")
        assert tracked, "git ls-files returned nothing — the probe itself is broken"

        fresh_out = tmp_path / "fresh-claude-build"
        generate_claude_plugin_bundle(fresh_out, version=__version__)
        fresh_paths = {
            str(p.relative_to(fresh_out)) for p in fresh_out.rglob("*") if p.is_file()
        }
        assert fresh_paths, "fresh build produced nothing — the probe itself is broken"

        expected_tracked = fresh_paths | set(self.HAND_AUTHORED)

        missing_from_git = expected_tracked - tracked
        extra_in_git = tracked - expected_tracked

        assert not missing_from_git, (
            "the generator writes these paths but `git ls-files plugin/claude` "
            f"does not track them (a gitignore pattern silently dropping a "
            f"file?): {sorted(missing_from_git)}"
        )
        assert not extra_in_git, (
            "`git ls-files plugin/claude` tracks these paths but neither the "
            "generator nor HAND_AUTHORED accounts for them (stale file, or a "
            f"newly hand-authored file this test needs to know about): "
            f"{sorted(extra_in_git)}"
        )


class TestClaudePluginSkillFilter:
    """TAP-7753 round 2: `linear-issue` is excluded from the Claude plugin
    bundle at the bundle-WRITER level (every write it performs is gated
    behind a docs-mcp tool this bundle does not ship) — never by deleting
    the key from CLAUDE_SKILLS, which stays the full registry every other
    consumer (`tapps-mcp init`/`upgrade`) relies on."""

    def test_registry_untouched_but_bundle_filtered(self, tmp_path):
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        result = generate_claude_plugin_bundle(tmp_path)
        shipped = [p.name for p in (tmp_path / "skills").iterdir() if p.is_dir()]
        assert (
            "linear-issue" in CLAUDE_SKILLS
            and len(CLAUDE_SKILLS) == 26
            and "linear-issue" not in shipped
            and not any("linear-issue" in f for f in result["files_created"])
            and len(shipped) == len(CLAUDE_SKILLS) - 1 == 25
        )

    def test_bundle_keeps_gracefully_degrading_linear_skills(self, tmp_path):
        """The three skills the operator kept must still ship — the filter
        targets exactly one skill, not the whole Linear family."""
        generate_claude_plugin_bundle(tmp_path)
        kept = ("linear-read", "linear-release-update", "tapps-continue-session")
        assert all((tmp_path / "skills" / name / "SKILL.md").exists() for name in kept), kept


class TestClaudePluginLinearReleaseUpdateDeadGrants:
    """TAP-7753 round 2: `docs_generate_release_update` /
    `docs_validate_release_update` were declared but never invoked in the
    body (which calls `docs_release_gate` instead) — removed as dead grants;
    `docs_release_gate` stays."""

    def test_dead_grants_removed_but_used_grant_kept(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "skills" / "linear-release-update" / "SKILL.md").read_text()
        allowed_tools_line = next(
            line for line in content.splitlines() if line.startswith("allowed-tools:")
        )
        assert (
            "docs_generate_release_update" not in allowed_tools_line
            and "docs_validate_release_update" not in allowed_tools_line
            and "docs_release_gate" in allowed_tools_line
        )


class TestClaudePluginDegradesWithoutSections:
    """TAP-7753 round 2: each skill shipping an unresolved cross-plugin /
    capability-gap reference documents it, in the SAME file, under a
    `## Degrades without` heading — the shape validate-claude-plugin.sh's
    amended part (e) now requires."""

    @pytest.mark.parametrize(
        "skill_name,expected_refs",
        [
            ("linear-read", ("mcp__plugin_linear_linear__",)),
            (
                "linear-release-update",
                ("mcp__nlt-release-ship__docs_release_gate", "mcp__plugin_linear_linear__"),
            ),
            ("tapps-continue-session", ("mcp__plugin_linear_linear__",)),
        ],
    )
    def test_documents_its_own_capability_gap(self, tmp_path, skill_name, expected_refs):
        generate_claude_plugin_bundle(tmp_path)
        content = (tmp_path / "skills" / skill_name / "SKILL.md").read_text()
        parts = content.split("## Degrades without", 1)
        assert len(parts) == 2 and all(ref in parts[1] for ref in expected_refs)

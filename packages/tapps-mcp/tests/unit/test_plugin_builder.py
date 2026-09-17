"""Tests for distribution/plugin_builder.py — Claude Code plugin generation.

``PluginBuilder`` is a thin facade over
``tapps_mcp.pipeline.platform_bundles.generate_claude_plugin_bundle`` (the two
Claude plugin bundlers were unified so `build-plugin` and a direct call to
the generator emit one implementation's output). These tests focus on
delegation: same output shape as the generator, `engagement_level` flowing
into `userConfig`, and a byte-for-byte equivalence guard between the two
public entry points (VAL-08). Exhaustive coverage of the bundle CONTENT
(plugin.json fields, hooks, bin shims, monitors, ...) lives in
test_claude_plugin_bundle.py against generate_claude_plugin_bundle directly —
duplicating it here would just be two copies of the same assertions
drifting apart.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tapps_mcp.distribution.plugin_builder import PluginBuilder


@pytest.fixture()
def plugin_dir(tmp_path: Path) -> Path:
    return tmp_path / "tapps-mcp-plugin"


def _sha256_manifest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


class TestPluginManifest:
    def test_manifest_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists()

    def test_manifest_has_required_fields(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest = json.loads(
            (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["name"] == "tapps-mcp"
        assert "description" in manifest
        assert "version" in manifest
        assert manifest["license"] == "MIT"
        assert "author" in manifest

    def test_version_matches_package(self, plugin_dir: Path) -> None:
        from tapps_mcp import __version__

        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        manifest = json.loads(
            (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["version"] == __version__

    def test_engagement_level_flows_to_user_config_default(self, plugin_dir: Path) -> None:
        """Replaces the retired `rules/python-quality.md` prose: the Claude
        plugin manifest's userConfig field is the machine-read equivalent."""
        builder = PluginBuilder(output_dir=plugin_dir, engagement_level="low")
        builder.build()

        manifest = json.loads(
            (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["userConfig"]["engagement_level"]["default"] == "low"


class TestPluginSkills:
    def test_skills_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        skills_dir = plugin_dir / "skills"
        assert skills_dir.exists()
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert len(skill_dirs) >= 4  # at least core skills

    def test_skill_dirs_match_module(self, plugin_dir: Path) -> None:
        """The bundle ships EXACTLY ``CLAUDE_SKILLS`` minus the plugin-only
        exclusion set -- still an equality, not a subset check.

        TAP-7753 round 2 deliberately made ``dir_names == set(CLAUDE_SKILLS)``
        false by filtering ``linear-issue`` out of the Claude plugin bundle
        (it is gated end-to-end behind docs-mcp tools this bundle cannot
        resolve). The expected set is derived from the two module constants
        rather than restated, so this still fails if a skill goes missing for
        any OTHER reason, if a skill appears that is not in the registry, or
        if the exclusion set silently grows.
        """
        from tapps_mcp.pipeline.platform_bundles import CLAUDE_PLUGIN_EXCLUDED_SKILLS
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        expected = set(CLAUDE_SKILLS.keys()) - set(CLAUDE_PLUGIN_EXCLUDED_SKILLS)
        # Guard the guard: an exclusion set that drifted to cover everything
        # (or nothing it names) would make the equality above vacuous.
        assert not (CLAUDE_PLUGIN_EXCLUDED_SKILLS - set(CLAUDE_SKILLS.keys()))
        assert expected != set(CLAUDE_SKILLS.keys())

        skills_dir = plugin_dir / "skills"
        dir_names = {d.name for d in skills_dir.iterdir() if d.is_dir()}
        assert dir_names == expected
        for d in skills_dir.iterdir():
            if d.is_dir():
                assert (d / "SKILL.md").exists()

    def test_skill_content_nonempty(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        for skill_dir in (plugin_dir / "skills").iterdir():
            if skill_dir.is_dir():
                content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                assert len(content) > 50


class TestPluginAgents:
    def test_agents_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        agents_dir = plugin_dir / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) == 5

    def test_agent_names(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        agents_dir = plugin_dir / "agents"
        names = {f.name for f in agents_dir.glob("*.md")}
        assert "tapps-reviewer.md" in names
        assert "tapps-researcher.md" in names
        assert "tapps-validator.md" in names
        assert "tapps-review-fixer.md" in names


class TestPluginHooks:
    def test_hooks_json_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        hooks_file = plugin_dir / "hooks" / "hooks.json"
        assert hooks_file.exists()

    def test_hooks_json_has_events(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        hooks = json.loads(
            (plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]
        assert "SessionStart" in hooks
        assert "PostToolUse" in hooks

    def test_hook_scripts_are_shipped(self, plugin_dir: Path) -> None:
        """Regression guard: the pre-unification PluginBuilder wrote a
        hooks.json whose commands pointed at `.claude/hooks/*.sh` — a path
        that only exists for a per-project `tapps-mcp init` install — and
        never wrote the scripts into the bundle at all. A plugin installed
        from that output would 404 on every hook invocation. The unified
        builder must ship the referenced scripts alongside hooks.json."""
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        assert (plugin_dir / "hooks" / "tapps-stop.sh").exists()
        assert (plugin_dir / "hooks" / "tapps-session-start.sh").exists()


class TestPluginMCPConfig:
    def test_mcp_config_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        mcp_file = plugin_dir / ".mcp.json"
        assert mcp_file.exists()

    def test_mcp_config_references_tapps(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        mcp = json.loads((plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
        assert "tapps-mcp" in mcp["mcpServers"]
        assert mcp["mcpServers"]["tapps-mcp"]["command"] == "uvx"


class TestPluginReadme:
    def test_readme_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        readme = plugin_dir / "README.md"
        assert readme.exists()
        assert len(readme.read_text(encoding="utf-8")) > 0


class TestPluginResult:
    def test_result_has_version(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()
        assert "version" in builder.result

    def test_result_has_files_created(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()
        assert "files_created" in builder.result
        assert len(builder.result["files_created"]) > 0


class TestPluginDirectoryStructure:
    def test_complete_structure(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()

        assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
        assert (plugin_dir / "skills").is_dir()
        assert (plugin_dir / "agents").is_dir()
        assert (plugin_dir / "hooks" / "hooks.json").exists()
        assert (plugin_dir / ".mcp.json").exists()
        assert (plugin_dir / "README.md").exists()


class TestPluginBinShims:
    """TAP-959: PluginBuilder also emits bin/ shims (parity with
    generate_claude_plugin_bundle)."""

    def test_bin_dir_created(self, plugin_dir: Path) -> None:
        PluginBuilder(output_dir=plugin_dir).build()
        assert (plugin_dir / "bin").is_dir()

    def test_bin_shims_emitted(self, plugin_dir: Path) -> None:
        PluginBuilder(output_dir=plugin_dir).build()
        bin_dir = plugin_dir / "bin"
        for name in (
            "tapps-quick-lint",
            "tapps-doctor-cli",
            "tapps-quick-lint.cmd",
            "tapps-doctor-cli.cmd",
        ):
            assert (bin_dir / name).exists(), f"missing {name}"

    def test_result_records_bin_files(self, plugin_dir: Path) -> None:
        builder = PluginBuilder(output_dir=plugin_dir)
        builder.build()
        bin_files = [f for f in builder.result["files_created"] if f.startswith("bin/")]
        assert len(bin_files) == 4


class TestUnifiedWithGenerateClaudePluginBundle:
    """VAL-08: `build-plugin` (PluginBuilder) and a direct call to
    generate_claude_plugin_bundle() must emit byte-identical trees now that
    PluginBuilder delegates to it, given matching arguments."""

    def test_byte_identical_trees(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.platform_bundles import generate_claude_plugin_bundle

        via_builder = tmp_path / "via-builder"
        via_direct = tmp_path / "via-direct"

        PluginBuilder(output_dir=via_builder, engagement_level="high").build()
        generate_claude_plugin_bundle(
            via_direct, version=__version__, engagement_level_default="high"
        )

        manifest_builder = _sha256_manifest(via_builder)
        manifest_direct = _sha256_manifest(via_direct)
        assert manifest_builder, "builder manifest must not be empty"
        assert manifest_direct, "direct-call manifest must not be empty"
        assert manifest_builder == manifest_direct

    def test_diverges_when_a_file_is_altered(self, tmp_path: Path) -> None:
        """Negative control for the assertion above: altering one file in
        one tree must make the two manifests differ, proving the equality
        check isn't vacuously true (e.g. from both being empty)."""
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.platform_bundles import generate_claude_plugin_bundle

        via_builder = tmp_path / "via-builder"
        via_direct = tmp_path / "via-direct"

        PluginBuilder(output_dir=via_builder, engagement_level="high").build()
        generate_claude_plugin_bundle(
            via_direct, version=__version__, engagement_level_default="high"
        )
        (via_direct / "README.md").write_text("tampered", encoding="utf-8")

        manifest_builder = _sha256_manifest(via_builder)
        manifest_direct = _sha256_manifest(via_direct)
        assert manifest_builder, "builder manifest must not be empty"
        assert manifest_direct, "direct-call manifest must not be empty"
        assert manifest_builder != manifest_direct

"""TAP-410: unit tests for the linear_sdlc template module.

Covers:

* :class:`LinearSDLCConfig` validation
* :func:`render_template` token substitution on each placeholder
* :func:`render_all` emits every path listed in ``TEMPLATE_PATHS``
* Default ``TAP`` prefix produces the expected content in key spots
* Alternate prefix (``LIN``) flows through branches, greps, and commands
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.linear_sdlc import (
    TEMPLATE_PATHS,
    LinearSDLCConfig,
    render_all,
    render_template,
)


class TestLinearSDLCConfig:
    def test_defaults(self) -> None:
        cfg = LinearSDLCConfig()
        assert cfg.issue_prefix == "TAP"
        assert cfg.prefix_lower == "tap"
        assert cfg.agent_name == "claude-sonnet-4-6"
        assert cfg.skill_path == "~/.claude/skills/linear"

    def test_empty_prefix_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            LinearSDLCConfig(issue_prefix="")

    def test_lowercase_prefix_rejected(self) -> None:
        with pytest.raises(ValueError, match="uppercase"):
            LinearSDLCConfig(issue_prefix="tap")


class TestRenderTemplate:
    def test_prefix_and_prefix_lower_substituted(self) -> None:
        text = "Use {{PREFIX}}-123 and branch {{PREFIX_LOWER}}-123-foo"
        result = render_template(text, LinearSDLCConfig(issue_prefix="LIN"))
        assert result == "Use LIN-123 and branch lin-123-foo"

    def test_agent_and_skill_path_substituted(self) -> None:
        text = "Agent: {{AGENT_NAME}}\nSkill: {{SKILL_PATH}}"
        cfg = LinearSDLCConfig(agent_name="claude-opus-4-7", skill_path="/opt/linear")
        result = render_template(text, cfg)
        assert "claude-opus-4-7" in result
        assert "/opt/linear" in result

    def test_prefix_substituted_before_prefix_lower_guard(self) -> None:
        """PREFIX_LOWER must be replaced before PREFIX to avoid 'TAP_LOWER' residue."""
        # If the renderer replaced {{PREFIX}} first, it would turn
        # {{PREFIX_LOWER}} into "TAP_LOWER}}" — verify that doesn't happen.
        text = "{{PREFIX_LOWER}}-123"
        assert render_template(text, LinearSDLCConfig()) == "tap-123"

    def test_no_placeholders_is_passthrough(self) -> None:
        text = "No tokens here."
        assert render_template(text, LinearSDLCConfig()) == text


class TestRenderAll:
    def test_emits_every_declared_path(self) -> None:
        rendered = render_all(LinearSDLCConfig())
        assert set(rendered.keys()) == set(TEMPLATE_PATHS)

    def test_default_tap_prefix_in_workflow(self) -> None:
        rendered = render_all(LinearSDLCConfig())
        workflow = rendered["docs/linear-sdlc/guides/WORKFLOW.md"]
        assert "TAP-prefixed" in workflow
        assert "tap-XXX" in workflow  # branch-naming row
        assert "{{PREFIX}}" not in workflow
        assert "{{PREFIX_LOWER}}" not in workflow

    def test_default_tap_prefix_in_issue_templates(self) -> None:
        rendered = render_all(LinearSDLCConfig())
        templates = rendered["docs/linear-sdlc/guides/ISSUE_TEMPLATES.md"]
        assert "TAP-XXX" in templates
        assert "tap-XXX-short-title" in templates  # branch placeholder
        assert "claude-sonnet-4-6" in templates
        assert "{{" not in templates

    def test_agent_guidance_substitutes_prefix(self) -> None:
        rendered = render_all(LinearSDLCConfig())
        prompt = rendered["docs/linear-sdlc/prompts/linear-sdlc-agent-guidance.md"]
        assert "TAP-prefixed Linear issue" in prompt
        assert "tap-NNN-short-title" in prompt
        assert "{{" not in prompt

    def test_hooks_have_shebang_and_no_tokens(self) -> None:
        rendered = render_all(LinearSDLCConfig())
        post_edit = rendered[".claude/hooks/linear-sdlc-post-edit.sh"]
        post_commit = rendered[".claude/hooks/linear-sdlc-post-commit.sh"]
        assert post_edit.startswith("#!/bin/bash")
        assert post_commit.startswith("#!/bin/bash")
        for body in (post_edit, post_commit):
            assert "{{PREFIX}}" not in body
            assert "{{SKILL_PATH}}" not in body

    def test_post_commit_grep_uses_prefix(self) -> None:
        rendered = render_all(LinearSDLCConfig(issue_prefix="LIN"))
        post_commit = rendered[".claude/hooks/linear-sdlc-post-commit.sh"]
        # The grep pattern must be the concrete prefix, not the placeholder.
        assert "'LIN-[0-9]+'" in post_commit

    def test_alternate_prefix_propagates(self) -> None:
        rendered = render_all(LinearSDLCConfig(issue_prefix="LIN", agent_name="gpt-5"))
        for path, body in rendered.items():
            assert "{{" not in body, f"unrendered tokens in {path}"
            # No residual lowercase/TAP-prefixed strings that should have been LIN.
            # Grep-style: branch placeholders must be lowercase LIN.
        workflow = rendered["docs/linear-sdlc/guides/WORKFLOW.md"]
        assert "LIN-prefixed" in workflow
        assert "lin-XXX" in workflow
        templates = rendered["docs/linear-sdlc/guides/ISSUE_TEMPLATES.md"]
        assert "LIN-XXX" in templates
        assert "gpt-5" in templates

    def test_skill_path_override_lands_in_hooks(self) -> None:
        cfg = LinearSDLCConfig(skill_path="/opt/linear-skill")
        rendered = render_all(cfg)
        post_edit = rendered[".claude/hooks/linear-sdlc-post-edit.sh"]
        post_commit = rendered[".claude/hooks/linear-sdlc-post-commit.sh"]
        assert "/opt/linear-skill" in post_edit
        assert "/opt/linear-skill" in post_commit

    def test_rendered_output_is_deterministic(self) -> None:
        cfg = LinearSDLCConfig()
        first = render_all(cfg)
        second = render_all(cfg)
        assert first == second

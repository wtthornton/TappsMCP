"""Tests for Memory Systems section in AGENTS.md templates (Epic 34.6)."""

from __future__ import annotations

import pytest

import re

from tapps_mcp.prompts.prompt_loader import load_agents_template, load_platform_rules
from tapps_mcp.server_memory_tools import SAVE_SCOPES


class TestMemorySystemsSection:
    """Verify each AGENTS.md template includes memory documentation."""

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_contains_memory_systems_section(self, level: str) -> None:
        """Each engagement-level template must have a '## Memory systems' heading."""
        content = load_agents_template(engagement_level=level)
        assert "## Memory systems" in content

    def test_high_template_contains_required(self) -> None:
        """High engagement template must use REQUIRED language."""
        content = load_agents_template(engagement_level="high")
        assert "REQUIRED" in content.split("## Memory systems")[1].split("##")[0]

    def test_low_template_contains_consider(self) -> None:
        """Low engagement template must use 'Consider' language."""
        content = load_agents_template(engagement_level="low")
        assert "Consider" in content.split("## Memory systems")[1].split("##")[0]

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_mentions_both_memory_systems(self, level: str) -> None:
        """Each template must mention both tapps_memory and MEMORY.md."""
        content = load_agents_template(engagement_level=level)
        memory_section = content.split("## Memory systems")[1].split("##")[0]
        assert "tapps_memory" in memory_section
        assert "MEMORY.md" in memory_section

    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_documents_cross_session_handoff(self, level: str) -> None:
        """Each AGENTS.md template must teach the cross-session handoff pattern.

        Sessions often need to pass tokens, IDs, or short payloads to a later
        session in the same project. The correct path is `tapps_memory(action="save",
        scope="project", ...)`, not stdout. If this guidance disappears from a
        template the next time someone refactors it, agents will fall back to
        printing secrets to stdout — drift catch.
        """
        content = load_agents_template(engagement_level=level)
        assert "Cross-session handoff" in content, (
            f"AGENTS.md template ({level}) is missing the 'Cross-session handoff' "
            "guidance. See packages/tapps-mcp/src/tapps_mcp/prompts/agents_template*.md."
        )
        # Ensure it actually points at the save action with project scope, not just
        # mentioning the phrase in passing.
        assert 'tapps_memory(action="save"' in content
        assert "project" in content.split("Cross-session handoff")[1].split("##")[0]

    # ------------------------------------------------------------------
    # Drift guard: templates must not promise save scopes the API rejects.
    #
    # `tapps_memory(action="save", scope="...")` accepts only the values in
    # SAVE_SCOPES (see server_memory_tools.py). Several templates have
    # historically advertised "shared" as a save scope, which is wrong —
    # `shared` is a federation-publish tier, not a save target. Agents that
    # follow the bad guidance get a confusing failure and fall back to
    # printing handoff payloads to stdout. This test fails loudly if any
    # template's "Scopes:" enumeration drifts back outside SAVE_SCOPES.
    # ------------------------------------------------------------------

    # Words that are scope names in the docstring sense but not SAVE_SCOPES.
    # Listed explicitly so the test fails on each individually with a clear
    # message rather than a silent set-diff.
    _NON_SAVE_SCOPE_NAMES = ("shared", "ephemeral")

    @pytest.mark.parametrize(
        "loader,key",
        [
            (lambda lvl: load_agents_template(engagement_level=lvl), "agents"),
            (lambda lvl: load_platform_rules("claude", engagement_level=lvl), "claude"),
            (lambda lvl: load_platform_rules("cursor", engagement_level=lvl), "cursor"),
        ],
    )
    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_template_does_not_advertise_invalid_save_scopes(
        self, loader, key: str, level: str
    ) -> None:
        """Templates must not list save scopes outside SAVE_SCOPES.

        Looks for ``Scopes:`` enumerations and flags any that name a value
        not in SAVE_SCOPES. Allows ``shared`` / ``ephemeral`` to appear
        elsewhere (e.g. federation prose), but not as an item in a Scopes:
        list, which agents read as "valid for save".
        """
        content = loader(level)
        # Match "Scopes:" or "**Scopes:**" followed by the rest of that line.
        for match in re.finditer(r"\*?\*?Scopes:\*?\*?\s*([^\n]+)", content):
            line = match.group(1)
            for bad in self._NON_SAVE_SCOPE_NAMES:
                # Word-boundary match so "shared (federation)" still trips the test.
                if re.search(rf"\b{bad}\b", line):
                    raise AssertionError(
                        f"{key}/{level}: template lists '{bad}' as a Scopes: "
                        f"value, but SAVE_SCOPES = {sorted(SAVE_SCOPES)}. "
                        f"'{bad}' is not accepted by tapps_memory(action=\"save\"). "
                        f"Offending line: 'Scopes: {line.strip()}'. "
                        f"Either drop '{bad}' from the list or move it out "
                        f"of the Scopes: enumeration into prose that names it "
                        f"as a federation-only tier."
                    )

    def test_save_scopes_constant_is_documented_in_docstring(self) -> None:
        """The SAVE_SCOPES constant must match what the tapps_memory docstring
        promises. If someone edits the docstring without updating the constant
        (or vice versa), the API and the published contract diverge and this
        test catches it before consumers do.
        """
        from tapps_mcp.server_memory_tools import tapps_memory

        docstring = tapps_memory.__doc__ or ""
        # The docstring at line 325 reads:
        #   scope: "project", "branch", or "session" (default: "project").
        # Assert each SAVE_SCOPES value appears as a quoted token in the scope arg's docstring line.
        scope_line_match = re.search(r"scope:\s*([^\n]+)", docstring)
        assert scope_line_match, "tapps_memory docstring missing 'scope:' arg description"
        scope_line = scope_line_match.group(1)
        for s in SAVE_SCOPES:
            assert f'"{s}"' in scope_line, (
                f"SAVE_SCOPES contains {s!r} but the tapps_memory docstring's "
                f"scope: line does not mention it: {scope_line!r}"
            )

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    @pytest.mark.parametrize("level", ["high", "medium", "low"])
    def test_platform_rules_document_cross_session_handoff(
        self, platform: str, level: str
    ) -> None:
        """Each platform-rules template (CLAUDE.md / .cursorrules) must document
        the cross-session handoff pattern. Same drift-catch as the AGENTS.md test."""
        content = load_platform_rules(platform=platform, engagement_level=level)
        assert "Cross-session handoff" in content, (
            f"platform_{platform}_{level}.md is missing 'Cross-session handoff' "
            "guidance. See packages/tapps-mcp/src/tapps_mcp/prompts/platform_*.md."
        )
        assert 'tapps_memory(action="save"' in content

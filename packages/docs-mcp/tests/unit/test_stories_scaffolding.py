"""Tests for docs_mcp.generators.stories -- Gherkin scaffolding and quickstart.

Split from test_stories.py (TAP-5622): covers Gherkin Given/When/Then
derivation, the docs_generate_story quick_start MCP-tool path, and generated
test-name derivation. Human-vs-agent audience rendering (criteria/what
sections, agent-readiness enforcement, the MCP handler audience path) lives
in test_stories_audience.py; content generation itself (section rendering,
styles, markers, empty inputs, auto-populate, expert enrichment) stays in
test_stories.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.helpers import make_settings as _make_settings
from tests.helpers import make_story_config as _make_config

from docs_mcp.generators.stories import StoryGenerator

# ---------------------------------------------------------------------------
# StoryGenerator -- improved Gherkin scaffolding (Story 92.5)
# ---------------------------------------------------------------------------


class TestImprovedGherkinScaffolding:
    """Tests for improved Gherkin Given/When/Then derivation (Story 92.5).

    Verifies that role/want/AC context produces meaningful Gherkin clauses
    and that missing context falls back to bracket placeholders.
    """

    def setup_method(self) -> None:
        self.gen = StoryGenerator()

    # -- _derive_given -------------------------------------------------------

    def test_derive_given_with_role(self) -> None:
        result = StoryGenerator._derive_given("developer")
        assert result == "a developer is ready to perform the action"

    def test_derive_given_empty_role_returns_empty(self) -> None:
        result = StoryGenerator._derive_given("")
        assert result == ""

    def test_derive_given_whitespace_role_returns_empty(self) -> None:
        result = StoryGenerator._derive_given("   ")
        assert result == ""

    # -- _derive_when --------------------------------------------------------

    def test_derive_when_uses_want_field(self) -> None:
        result = StoryGenerator._derive_when("developer", "to validate login credentials", "AC")
        assert result == "the developer validate login credentials"

    def test_derive_when_strips_to_prefix(self) -> None:
        result = StoryGenerator._derive_when("admin", "to manage users", "AC")
        assert result == "the admin manage users"

    def test_derive_when_want_without_to_prefix(self) -> None:
        result = StoryGenerator._derive_when("user", "submits the form", "AC")
        assert result == "the user submits the form"

    def test_derive_when_no_role_uses_the_user(self) -> None:
        result = StoryGenerator._derive_when("", "to validate login", "AC")
        assert result == "the user validate login"

    def test_derive_when_falls_back_to_ac_verb(self) -> None:
        result = StoryGenerator._derive_when("developer", "", "Login validates credentials")
        # First word of AC text as verb
        assert result.startswith("the developer login")

    def test_derive_when_no_want_no_role_uses_ac(self) -> None:
        result = StoryGenerator._derive_when("", "", "Validation rejects empty fields")
        assert result == "the user validation rejects empty fields"

    def test_derive_when_empty_want_and_ac_returns_empty(self) -> None:
        result = StoryGenerator._derive_when("", "", "")
        assert result == ""

    # -- _derive_then --------------------------------------------------------

    def test_derive_then_uses_ac_text(self) -> None:
        result = StoryGenerator._derive_then("Login validates credentials", "")
        assert result == "Login validates credentials successfully"

    def test_derive_then_strips_trailing_punctuation(self) -> None:
        result = StoryGenerator._derive_then("Feature works correctly.", "")
        assert result == "Feature works correctly successfully"

    def test_derive_then_falls_back_to_so_that(self) -> None:
        result = StoryGenerator._derive_then("", "invalid logins are rejected")
        assert result == "invalid logins are rejected"

    def test_derive_then_empty_returns_empty(self) -> None:
        result = StoryGenerator._derive_then("", "")
        assert result == ""

    # -- _render_gherkin_criteria with context --------------------------------

    def test_gherkin_with_role_and_want(self) -> None:
        config = _make_config(
            role="developer",
            want="to validate login credentials",
            acceptance_criteria=["Login validates credentials"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        assert "Given a developer is ready to perform the action" in content
        assert "When the developer validate login credentials" in content
        assert "Login validates credentials successfully" in content

    def test_gherkin_fallback_without_role(self) -> None:
        config = _make_config(
            role="",
            want="",
            acceptance_criteria=["Feature works"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        # Given falls back to bracket (no role)
        assert "Given [describe the precondition]" in content

    def test_gherkin_then_always_derived_from_ac(self) -> None:
        config = _make_config(
            acceptance_criteria=["Rate limit enforced"],
            criteria_format="gherkin",
        )
        content = self.gen.generate(config)
        assert "Then Rate limit enforced successfully" in content

    def test_gherkin_empty_criteria_unchanged(self) -> None:
        """Empty criteria case still renders the example block."""
        config = _make_config(acceptance_criteria=[], criteria_format="gherkin")
        content = self.gen.generate(config)
        assert "Feature: Example" in content
        assert "Given a precondition" in content


# ---------------------------------------------------------------------------
# MCP tool: docs_generate_story -- quick_start
# ---------------------------------------------------------------------------


class TestDocsGenerateStoryQuickStart:
    """Tests for quick_start parameter in ``docs_generate_story`` MCP tool."""

    async def _call(self, **kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_story

        return await docs_generate_story(**kwargs)

    async def test_quick_start_mcp_tool_produces_complete_story(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="Login Validation",
                epic_number=91,
                quick_start=True,
                project_root=str(root),
                audience="human",
                write_to_disk=True,
            )

        assert result["success"] is True
        assert result["data"]["quick_start"] is True
        assert "written_to" in result["data"]
        root = tmp_path / "proj"
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "**As a** developer" in content
        assert "**I want** to login validation" in content
        assert "**Points:** 3" in content
        assert "**Size:** M" in content

    async def test_quick_start_mcp_tool_explicit_role_overrides(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(
                title="Login Validation",
                epic_number=91,
                role="admin",
                quick_start=True,
                project_root=str(root),
                audience="human",
                write_to_disk=True,
            )

        assert result["success"] is True
        assert "written_to" in result["data"]
        root = tmp_path / "proj"
        content = (root / result["data"]["written_to"]).read_text(encoding="utf-8")
        assert "**As a** admin" in content
        assert "**As a** developer" not in content

    async def test_quick_start_false_in_response(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()

        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(root),
        ):
            result = await self._call(title="X", project_root=str(root), audience="human")

        assert result["success"] is True
        assert result["data"]["quick_start"] is False


# ---------------------------------------------------------------------------
# StoryGenerator -- generate_test_name
# ---------------------------------------------------------------------------


class TestGenerateTestName:
    """Tests for StoryGenerator.generate_test_name."""

    def test_long_ac_truncated_to_80_chars(self) -> None:
        long_ac = (
            "The upgrade pipeline calls generate_all_github_templates and generates "
            "CI workflows and governance files and security policies for the project"
        )
        name = StoryGenerator.generate_test_name(long_ac)
        assert len(name) <= 80

    def test_no_mid_word_truncation(self) -> None:
        long_ac = (
            "Results stored in result components github templates and governance "
            "files with proper validation and error handling for edge cases"
        )
        name = StoryGenerator.generate_test_name(long_ac)
        # Every segment between underscores should be a complete word.
        parts = name.split("_")
        for part in parts:
            assert part.isalnum(), f"Part {part!r} is not a complete alphanumeric word"
        assert len(name) <= 80

    def test_valid_python_identifier(self) -> None:
        name = StoryGenerator.generate_test_name("Validation rejects empty fields!")
        assert name.isidentifier()
        assert name.startswith("test_")

    def test_stopwords_removed(self) -> None:
        name = StoryGenerator.generate_test_name(
            "The user should be able to login with a valid password"
        )
        assert "_the_" not in name
        assert "_should_" not in name
        assert "_be_" not in name
        assert "_a_" not in name
        # Key content words should survive.
        assert "user" in name
        assert "login" in name
        assert "valid" in name
        assert "password" in name

    def test_numbered_ac_gets_index_prefix(self) -> None:
        name = StoryGenerator.generate_test_name("Generates templates", index=1)
        assert name.startswith("test_ac1_")
        assert "generates" in name
        assert "templates" in name

    def test_numbered_ac_index_3(self) -> None:
        name = StoryGenerator.generate_test_name("Error handling works", index=3)
        assert name.startswith("test_ac3_")

    def test_empty_ac_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("")
        assert name == "test_story_acceptance"

    def test_empty_ac_with_index_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("", index=2)
        assert name == "test_ac2_story_acceptance"

    def test_whitespace_only_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("   ")
        assert name == "test_story_acceptance"

    def test_all_stopwords_fallback(self) -> None:
        name = StoryGenerator.generate_test_name("the and is are should")
        assert name == "test_story_acceptance"

    def test_special_characters_stripped(self) -> None:
        name = StoryGenerator.generate_test_name("Login (v2) works -- correctly!")
        assert name.isidentifier()
        assert "login" in name
        assert "v2" in name
        assert "works" in name
        assert "correctly" in name
        # No parentheses, dashes, or exclamation marks.
        assert "(" not in name
        assert ")" not in name
        assert "-" not in name
        assert "!" not in name

    def test_only_lowercase_and_underscores(self) -> None:
        name = StoryGenerator.generate_test_name("API Returns JSON Response")
        assert name == name.lower()
        assert re.match(r"^[a-z0-9_]+$", name)

    def test_short_ac_preserved(self) -> None:
        name = StoryGenerator.generate_test_name("Login works")
        assert name == "test_login_works"

    def test_render_test_cases_uses_generate_test_name(self) -> None:
        """Comprehensive style auto-generates test names from AC."""
        gen = StoryGenerator()
        config = _make_config(
            style="comprehensive",
            test_cases=[],
            acceptance_criteria=["Validation rejects empty fields", "Error messages displayed"],
        )
        content = gen.generate(config)
        assert "## Test Cases" in content
        assert "`test_ac1_validation_rejects_empty_fields`" in content
        assert "`test_ac2_error_messages_displayed`" in content

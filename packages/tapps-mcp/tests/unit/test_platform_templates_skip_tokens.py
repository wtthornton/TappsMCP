"""Skip-token vocabulary for the template category (TAP-7423).

Mirrors test_platform_project_scripts_skip_tokens.py's shape for the
analogous project-root, host-agnostic scripts/ category. See that file's
docstring for why both directions (token KEY vs VALUE) are asserted.
"""

from __future__ import annotations

from tapps_mcp.pipeline.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    SKIP_TOKENS,
    describe_unknown_skip_token,
    nearest_token,
    unknown_skip_tokens,
)


class TestSkipTokenVocabulary:
    def test_templates_token_value_is_the_path(self) -> None:
        assert "templates" in SKIP_TOKENS
        assert SKIP_TOKENS["templates"] == frozenset({"docs/templates"})
        assert "docs/templates" in ALL_SKIP_TOKENS

    def test_known_token_not_reported_unknown(self) -> None:
        assert unknown_skip_tokens(["docs/templates"]) == []

    def test_known_bad_control_still_reported_unknown(self) -> None:
        """Negative control: a bad entry must still be flagged."""
        bad_entry = "docs/templates/does-not-exist.html"
        assert unknown_skip_tokens([bad_entry]) == [bad_entry]

    def test_internal_name_is_not_itself_a_valid_token_value(self) -> None:
        """Guards the TAP-6883 failure shape: the KEY must never leak in as
        something a consumer could configure and have it work."""
        assert unknown_skip_tokens(["templates"]) == ["templates"]

    def test_nested_path_suggests_the_directory_token(self) -> None:
        assert nearest_token("docs/templates/one-pager.html") == "docs/templates"

    def test_nested_path_gets_a_helpful_message(self) -> None:
        message = describe_unknown_skip_token("docs/templates/one-pager.html")
        assert "docs/templates" in message

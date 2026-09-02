"""Skip-token vocabulary for project-root scripts (TAP-6884).

Split out from ``test_platform_project_scripts.py`` for gate size — see that
file's module docstring for why.
"""

from __future__ import annotations

from tapps_mcp.pipeline.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    SKIP_TOKENS,
    unknown_skip_tokens,
)


class TestSkipTokenVocabulary:
    """Item 2 of Scope-IN: the token VALUE is the path, the dict KEY is the
    internal name — getting this backwards ships a token nobody can use
    (TAP-6883). Both directions asserted per repo test-quality conventions."""

    def test_measure_script_token_value_is_the_path(self) -> None:
        assert "measure_script" in SKIP_TOKENS
        assert SKIP_TOKENS["measure_script"] == frozenset({"scripts/measure.py"})
        assert "scripts/measure.py" in ALL_SKIP_TOKENS

    def test_gitfacts_script_token_value_is_the_path(self) -> None:
        assert "gitfacts_script" in SKIP_TOKENS
        assert SKIP_TOKENS["gitfacts_script"] == frozenset({"scripts/gitfacts.sh"})
        assert "scripts/gitfacts.sh" in ALL_SKIP_TOKENS

    def test_known_tokens_not_reported_unknown(self) -> None:
        assert unknown_skip_tokens(["scripts/measure.py", "scripts/gitfacts.sh"]) == []

    def test_known_bad_control_still_reported_unknown(self) -> None:
        """Negative control: a bad entry must still be flagged — proves the
        assertions above aren't vacuously true."""
        bad_entry = "scripts/does-not-exist.py"
        assert unknown_skip_tokens([bad_entry]) == [bad_entry]

    def test_internal_name_is_not_itself_a_valid_token_value(self) -> None:
        """Guards the exact TAP-6883 failure shape: the KEY must never leak in
        as something a consumer could configure and have it work."""
        assert unknown_skip_tokens(["measure_script"]) == ["measure_script"]
        assert unknown_skip_tokens(["gitfacts_script"]) == ["gitfacts_script"]

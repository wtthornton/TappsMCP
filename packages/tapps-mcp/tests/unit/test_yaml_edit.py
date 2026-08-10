"""Tests for comment-preserving .tapps-mcp.yaml edits.

Regression origin: `tapps-mcp mcp-bundle set full` in a consumer repo silently
deleted two comment blocks that documented why `skill_count_max` exceeded the
stock ceiling and why three files were in `upgrade_skip_files`. The values
survived; the reasoning did not. These tests pin the comments, not just the data.
"""

from __future__ import annotations

import yaml

from tapps_mcp.common.yaml_edit import update_yaml_preserving_comments

# The real-world file that lost its comments, trimmed to the relevant shape.
_CONSUMER_YAML = """\
cursor_stop_completion_gate: warn
linear_team: TappsCodingAgents
mcp_bundle: full

# Skill inventory intentionally exceeds the stock ceiling of 20.
# Raised rather than pruned per tapps_doctor guidance.
doctor_context_budget:
  skill_count_max: 45

# Locally customized skill files — tapps_upgrade must not overwrite these.
# Drop an entry only after folding the change upstream.
upgrade_skip_files:
  - .claude/skills/orchestration-prompt/SKILL.md
"""


class TestPreservesComments:
    def test_the_original_regression(self) -> None:
        """Setting one key must not delete unrelated comment blocks."""
        out = update_yaml_preserving_comments(_CONSUMER_YAML, {"mcp_transport": "http"})
        assert "Raised rather than pruned per tapps_doctor guidance." in out
        assert "Drop an entry only after folding the change upstream." in out
        assert "Skill inventory intentionally exceeds" in out

    def test_replacing_an_existing_key_keeps_neighbouring_comments(self) -> None:
        out = update_yaml_preserving_comments(_CONSUMER_YAML, {"mcp_bundle": "developer"})
        assert yaml.safe_load(out)["mcp_bundle"] == "developer"
        assert "Skill inventory intentionally exceeds" in out
        assert "Drop an entry only after folding the change upstream." in out

    def test_replacing_a_block_valued_key_keeps_the_comment_after_it(self) -> None:
        """The comment between two blocks belongs to the *next* key, not the replaced one."""
        out = update_yaml_preserving_comments(
            _CONSUMER_YAML, {"doctor_context_budget": {"skill_count_max": 99}}
        )
        assert yaml.safe_load(out)["doctor_context_budget"] == {"skill_count_max": 99}
        assert "Locally customized skill files" in out
        assert "Skill inventory intentionally exceeds" in out


class TestValuesAreCorrect:
    def test_all_other_values_survive_unchanged(self) -> None:
        before = yaml.safe_load(_CONSUMER_YAML)
        after = yaml.safe_load(
            update_yaml_preserving_comments(_CONSUMER_YAML, {"mcp_transport": "http"})
        )
        assert after.pop("mcp_transport") == "http"
        assert after == before

    def test_new_key_is_appended(self) -> None:
        out = update_yaml_preserving_comments(_CONSUMER_YAML, {"brand_new": 7})
        assert yaml.safe_load(out)["brand_new"] == 7

    def test_multiple_updates_at_once(self) -> None:
        out = update_yaml_preserving_comments(
            _CONSUMER_YAML, {"mcp_bundle": "developer", "mcp_transport": "http"}
        )
        loaded = yaml.safe_load(out)
        assert loaded["mcp_bundle"] == "developer"
        assert loaded["mcp_transport"] == "http"

    def test_key_order_is_stable_for_existing_keys(self) -> None:
        out = update_yaml_preserving_comments(_CONSUMER_YAML, {"mcp_bundle": "developer"})
        keys = [line.split(":")[0] for line in out.splitlines() if line and not line[:1].isspace()]
        keys = [k for k in keys if not k.startswith("#") and not k.startswith("-")]
        assert keys.index("mcp_bundle") < keys.index("doctor_context_budget")

    def test_nested_and_list_values_round_trip(self) -> None:
        out = update_yaml_preserving_comments(
            _CONSUMER_YAML, {"upgrade_skip_files": ["a.md", "b.md"]}
        )
        assert yaml.safe_load(out)["upgrade_skip_files"] == ["a.md", "b.md"]


class TestEdgeCases:
    def test_empty_document_renders_fresh(self) -> None:
        out = update_yaml_preserving_comments("", {"mcp_bundle": "full"})
        assert yaml.safe_load(out) == {"mcp_bundle": "full"}

    def test_whitespace_only_document_renders_fresh(self) -> None:
        out = update_yaml_preserving_comments("\n  \n", {"mcp_bundle": "full"})
        assert yaml.safe_load(out) == {"mcp_bundle": "full"}

    def test_no_updates_returns_input_unchanged(self) -> None:
        assert update_yaml_preserving_comments(_CONSUMER_YAML, {}) == _CONSUMER_YAML

    def test_commented_out_key_is_not_treated_as_the_key(self) -> None:
        """`# mcp_bundle: developer` must not be mistaken for the real setting."""
        text = "# mcp_bundle: developer\nother: 1\n"
        out = update_yaml_preserving_comments(text, {"mcp_bundle": "full"})
        assert "# mcp_bundle: developer" in out
        assert yaml.safe_load(out)["mcp_bundle"] == "full"

    def test_nested_key_of_the_same_name_is_not_matched(self) -> None:
        """An indented `mcp_bundle:` belongs to a parent block, not the document."""
        text = "memory_hooks:\n  mcp_bundle: nested\ntop: 1\n"
        out = update_yaml_preserving_comments(text, {"mcp_bundle": "full"})
        loaded = yaml.safe_load(out)
        assert loaded["memory_hooks"] == {"mcp_bundle": "nested"}
        assert loaded["mcp_bundle"] == "full"

    def test_trailing_comment_at_end_of_file_survives(self) -> None:
        text = "mcp_bundle: full\n\n# trailing note\n"
        out = update_yaml_preserving_comments(text, {"mcp_bundle": "developer"})
        assert "# trailing note" in out

    def test_file_without_trailing_newline(self) -> None:
        out = update_yaml_preserving_comments("mcp_bundle: full", {"mcp_transport": "http"})
        loaded = yaml.safe_load(out)
        assert loaded == {"mcp_bundle": "full", "mcp_transport": "http"}
        assert out.endswith("\n")

    def test_quoted_key_is_matched(self) -> None:
        out = update_yaml_preserving_comments(
            '"mcp_bundle": full\nother: 1\n', {"mcp_bundle": "developer"}
        )
        assert yaml.safe_load(out)["mcp_bundle"] == "developer"

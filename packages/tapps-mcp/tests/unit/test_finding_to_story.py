"""Tests for the TAP-2717 deterministic finding-to-story converter.

Covers:
  - finding_to_story: title generation, 5-section body, file anchor normalisation
  - P0/P1/P2/P3 severity variants
  - Edge cases: long recommendations, bare file paths, empty parent_id
  - Validation: returned body passes docs_validate_linear_issue(agent_ready=true)
  - tapps_finding_to_story handler: pass / error paths
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tapps_mcp.tools.finding_to_story import (
    FindingStory,
    _derive_estimate,
    _make_title,
    _normalise_file_anchor,
    _render_acceptance,
    _render_refs,
    _render_where,
    finding_to_story,
)

# ---------------------------------------------------------------------------
# _normalise_file_anchor
# ---------------------------------------------------------------------------


class TestNormaliseFileAnchor:
    def test_preserves_existing_line_ref(self) -> None:
        assert _normalise_file_anchor("src/foo.py:10-25") == "src/foo.py:10-25"

    def test_preserves_single_line_ref(self) -> None:
        assert _normalise_file_anchor("src/foo.py:42") == "src/foo.py:42"

    def test_appends_one_to_bare_path(self) -> None:
        assert _normalise_file_anchor("src/foo.py") == "src/foo.py:1"

    def test_strips_whitespace(self) -> None:
        assert _normalise_file_anchor("  src/foo.py:5  ") == "src/foo.py:5"

    def test_bare_path_stripped_gets_suffix(self) -> None:
        assert _normalise_file_anchor("  src/bar.ts  ") == "src/bar.ts:1"


# ---------------------------------------------------------------------------
# _make_title
# ---------------------------------------------------------------------------


class TestMakeTitle:
    def test_basic_pattern(self) -> None:
        title = _make_title("security", "Fix SQL injection in query builder")
        assert title == "security: Fix SQL injection in query builder"

    def test_title_at_most_80_chars(self) -> None:
        long_rec = "A" * 100
        title = _make_title("style", long_rec)
        assert len(title) <= 80

    def test_long_title_ends_with_ellipsis(self) -> None:
        long_rec = "word " * 20
        title = _make_title("correctness", long_rec)
        assert title.endswith("\u2026")

    def test_truncated_title_within_limit(self) -> None:
        title = _make_title("docs", "short")
        assert len(title) <= 80

    def test_category_lowercased(self) -> None:
        title = _make_title("SECURITY", "fix it")
        assert title.startswith("security: ")

    def test_recommendation_stripped(self) -> None:
        title = _make_title("style", "  fix whitespace  ")
        assert title == "style: fix whitespace"


# ---------------------------------------------------------------------------
# _render_where
# ---------------------------------------------------------------------------


class TestRenderWhere:
    def test_single_file_with_line_ref(self) -> None:
        result = _render_where(["src/foo.py:1-50"])
        assert "1. `src/foo.py:1-50`" in result

    def test_bare_file_gets_colon_one(self) -> None:
        result = _render_where(["src/bar.py"])
        assert "1. `src/bar.py:1`" in result

    def test_multiple_files_numbered(self) -> None:
        result = _render_where(["a.py:1", "b.py:2-10"])
        lines = result.splitlines()
        assert lines[0].startswith("1.")
        assert lines[1].startswith("2.")

    def test_file_anchor_in_backticks(self) -> None:
        result = _render_where(["src/x.py:5"])
        assert "`src/x.py:5`" in result


# ---------------------------------------------------------------------------
# _render_acceptance
# ---------------------------------------------------------------------------


class TestRenderAcceptance:
    def test_always_has_checkbox(self) -> None:
        for sev in ("P0", "P1", "P2", "P3"):
            result = _render_acceptance(sev)
            assert "- [ ]" in result

    def test_p0_has_extra_review_item(self) -> None:
        result = _render_acceptance("P0")
        assert "reviewed" in result.lower() or "review" in result.lower()

    def test_p1_has_regression_test_item(self) -> None:
        result = _render_acceptance("P1")
        assert "regression" in result.lower()

    def test_p2_has_no_extra_items(self) -> None:
        p2 = _render_acceptance("P2")
        p3 = _render_acceptance("P3")
        assert p2 == p3  # P2 and P3 share the same base template

    def test_tapps_quick_check_mentioned(self) -> None:
        for sev in ("P0", "P1", "P2", "P3"):
            assert "tapps_quick_check" in _render_acceptance(sev)


# ---------------------------------------------------------------------------
# _render_refs
# ---------------------------------------------------------------------------


class TestRenderRefs:
    def test_contains_severity(self) -> None:
        result = _render_refs("P0", "security", "")
        assert "**P0**" in result

    def test_contains_category(self) -> None:
        result = _render_refs("P1", "correctness", "")
        assert "**correctness**" in result

    def test_parent_id_included_when_set(self) -> None:
        result = _render_refs("P1", "security", "TAP-2040")
        assert "TAP-2040" in result

    def test_parent_id_omitted_when_empty(self) -> None:
        result = _render_refs("P2", "style", "")
        assert "session" not in result or "Audit session" not in result


# ---------------------------------------------------------------------------
# finding_to_story — P0/P1/P2/P3 coverage
# ---------------------------------------------------------------------------


_SAMPLE_FILES = ["packages/tapps-mcp/src/tapps_mcp/server.py:200-250"]
_SAMPLE_EVIDENCE = "bandit B608: possible SQL injection at server.py:220 via user input"
_SAMPLE_REC = "Use parameterised queries instead of string interpolation"


class TestFindingToStoryP0:
    def setup_method(self) -> None:
        self.story = finding_to_story(
            severity="P0",
            category="security",
            files=_SAMPLE_FILES,
            evidence=_SAMPLE_EVIDENCE,
            recommendation=_SAMPLE_REC,
            parent_id="TAP-2040",
        )

    def test_returns_finding_story(self) -> None:
        assert isinstance(self.story, FindingStory)

    def test_title_le_80_chars(self) -> None:
        assert len(self.story.title) <= 80

    def test_title_contains_category(self) -> None:
        assert "security" in self.story.title

    def test_body_has_five_sections(self) -> None:
        for section in ("## What", "## Where", "## Why", "## Acceptance", "## Refs"):
            assert section in self.story.body

    def test_body_contains_recommendation(self) -> None:
        assert _SAMPLE_REC in self.story.body

    def test_body_contains_evidence(self) -> None:
        assert _SAMPLE_EVIDENCE in self.story.body

    def test_body_contains_file_anchor(self) -> None:
        # Must have a file anchor matching the linter regex
        anchor_re = re.compile(r"[\w./\\-]+\.py:\d+(?:-\d+)?")
        assert anchor_re.search(self.story.body)

    def test_body_has_checkbox(self) -> None:
        assert "- [ ]" in self.story.body

    def test_parent_id_in_refs(self) -> None:
        assert "TAP-2040" in self.story.body

    def test_body_ends_with_newline(self) -> None:
        assert self.story.body.endswith("\n")


class TestFindingToStoryP1:
    def test_regression_test_in_acceptance(self) -> None:
        story = finding_to_story(
            severity="P1",
            category="correctness",
            files=["src/module.py:1-100"],
            evidence="missing null check at line 42",
            recommendation="Add None guard before dereferencing",
        )
        assert "regression" in story.body.lower()


class TestFindingToStoryP2:
    def test_body_passes_basic_structure(self) -> None:
        story = finding_to_story(
            severity="P2",
            category="style",
            files=["src/utils.py:10-30"],
            evidence="unused import `os` at line 1 (vulture)",
            recommendation="Remove unused import",
        )
        assert "## Acceptance" in story.body
        assert "- [ ]" in story.body


class TestFindingToStoryP3:
    def test_body_has_all_sections(self) -> None:
        story = finding_to_story(
            severity="P3",
            category="docs",
            files=["src/api.py:1"],
            evidence="public function has no docstring",
            recommendation="Add docstring describing parameters and return value",
        )
        for section in ("## What", "## Where", "## Why", "## Acceptance", "## Refs"):
            assert section in story.body


# ---------------------------------------------------------------------------
# finding_to_story — file anchor edge cases
# ---------------------------------------------------------------------------


class TestFileAnchorNormalisation:
    def test_bare_path_becomes_valid_anchor(self) -> None:
        story = finding_to_story(
            severity="P2",
            category="style",
            files=["src/module.py"],  # no :LINE
            evidence="some finding",
            recommendation="fix it",
        )
        # The linter needs `file.py:N`
        assert "src/module.py:1" in story.body

    def test_multiple_files_all_anchored(self) -> None:
        story = finding_to_story(
            severity="P1",
            category="correctness",
            files=["a.py:1", "b.py", "c.ts:5-10"],
            evidence="cross-file issue",
            recommendation="align types across modules",
        )
        assert "a.py:1" in story.body
        assert "b.py:1" in story.body
        assert "c.ts:5-10" in story.body


# ---------------------------------------------------------------------------
# finding_to_story — label assertions (TAP-2719)
# ---------------------------------------------------------------------------


class TestFindingStoryLabels:
    """TAP-2719: generated fix stories must carry the audit-fix label."""

    def test_default_label_is_audit_fix(self) -> None:
        story = finding_to_story(
            severity="P0",
            category="security",
            files=["src/auth.py:1-50"],
            evidence="sql injection at line 20",
            recommendation="use parameterised queries",
        )
        assert "audit-fix" in story.labels

    @pytest.mark.parametrize("severity", ["P0", "P1", "P2", "P3"])
    def test_all_severities_have_audit_fix_label(self, severity: str) -> None:
        story = finding_to_story(
            severity=severity,
            category="correctness",
            files=["src/mod.py:1"],
            evidence="finding evidence",
            recommendation="apply fix",
        )
        assert "audit-fix" in story.labels

    def test_label_is_tuple(self) -> None:
        story = finding_to_story(
            severity="P1",
            category="style",
            files=["src/utils.py:5-10"],
            evidence="unused import",
            recommendation="remove unused import",
        )
        assert isinstance(story.labels, tuple)

    def test_audit_fix_label_not_empty(self) -> None:
        story = finding_to_story(
            severity="P2",
            category="docs",
            files=["src/api.py:1"],
            evidence="missing docstring",
            recommendation="add docstring",
        )
        assert len(story.labels) >= 1


# ---------------------------------------------------------------------------
# tapps_finding_to_story handler — label in response (TAP-2719)
# ---------------------------------------------------------------------------


class TestTappsFindingToStoryHandlerLabels:
    @pytest.mark.asyncio()
    async def test_handler_returns_labels_field(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P1",
            category="security",
            files=["src/auth.py:10-50"],
            evidence="missing auth check at line 20",
            recommendation="Add authentication guard before privileged operation",
        )
        assert "labels" in result["data"]
        assert "audit-fix" in result["data"]["labels"]

    @pytest.mark.asyncio()
    async def test_handler_labels_is_list(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P0",
            category="security",
            files=["src/x.py:1-10"],
            evidence="sql injection",
            recommendation="use parameterised queries",
        )
        assert isinstance(result["data"]["labels"], list)


# ---------------------------------------------------------------------------
# finding_to_story — validation against docs-mcp validator
# ---------------------------------------------------------------------------


class TestAgentReadyValidation:
    """Verify the converter is truly agent_ready by construction."""

    @pytest.mark.parametrize(
        "severity,category",
        [
            ("P0", "security"),
            ("P1", "correctness"),
            ("P2", "style"),
            ("P3", "docs"),
        ],
    )
    def test_returned_body_is_agent_ready(self, severity: str, category: str) -> None:
        from docs_mcp.validators.linear_issue import validate_issue

        story = finding_to_story(
            severity=severity,
            category=category,
            files=["packages/tapps-mcp/src/tapps_mcp/server.py:1-100"],
            evidence=f"finding evidence for {severity}/{category} test",
            recommendation=f"apply the {category} fix",
            parent_id="TAP-9999",
        )
        report = validate_issue(title=story.title, description=story.body)
        assert report.agent_ready, (
            f"Story for {severity}/{category} is NOT agent_ready: {report.missing}"
        )


# ---------------------------------------------------------------------------
# finding_to_story — error paths
# ---------------------------------------------------------------------------


class TestFindingToStoryErrors:
    def test_raises_on_empty_files(self) -> None:
        with pytest.raises(ValueError, match="files"):
            finding_to_story("P1", "security", [], "ev", "rec")

    def test_raises_on_blank_evidence(self) -> None:
        with pytest.raises(ValueError, match="evidence"):
            finding_to_story("P1", "security", ["f.py:1"], "   ", "rec")

    def test_raises_on_blank_recommendation(self) -> None:
        with pytest.raises(ValueError, match="recommendation"):
            finding_to_story("P1", "security", ["f.py:1"], "ev", "   ")


# ---------------------------------------------------------------------------
# tapps_finding_to_story handler
# ---------------------------------------------------------------------------


class TestTappsFindingToStoryHandler:
    @pytest.fixture()
    def mock_settings(self, tmp_path: Path) -> MagicMock:
        s = MagicMock()
        s.project_root = tmp_path
        return s

    @pytest.mark.asyncio()
    async def test_valid_finding_returns_title_and_body(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P1",
            category="security",
            files=["src/auth.py:10-50"],
            evidence="missing auth check at line 20",
            recommendation="Add authentication guard before privileged operation",
        )
        assert result["data"]["title"]
        assert "## What" in result["data"]["body"]
        assert result["data"]["severity"] == "P1"

    @pytest.mark.asyncio()
    async def test_invalid_severity_returns_error(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="CRITICAL",
            category="security",
            files=["src/f.py:1"],
            evidence="ev",
            recommendation="rec",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_severity"

    @pytest.mark.asyncio()
    async def test_invalid_category_returns_error(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P0",
            category="unknown_cat",
            files=["src/f.py:1"],
            evidence="ev",
            recommendation="rec",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_category"

    @pytest.mark.asyncio()
    async def test_empty_files_returns_error(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P2",
            category="style",
            files=[],
            evidence="ev",
            recommendation="rec",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "missing_files"

    @pytest.mark.asyncio()
    async def test_next_steps_include_validate(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P0",
            category="security",
            files=["src/x.py:1-10"],
            evidence="sql injection",
            recommendation="use parameterised queries",
        )
        next_steps = result["data"].get("next_steps", [])
        assert any("docs_validate_linear_issue" in s for s in next_steps)

    @pytest.mark.asyncio()
    async def test_severity_case_insensitive(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="p1",
            category="correctness",
            files=["src/x.py:5"],
            evidence="null deref",
            recommendation="add guard",
        )
        assert result["success"] is True
        assert result["data"]["severity"] == "P1"

    @pytest.mark.asyncio()
    async def test_category_case_insensitive(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P2",
            category="STYLE",
            files=["src/x.py:1"],
            evidence="unused import",
            recommendation="remove it",
        )
        assert result["success"] is True
        assert result["data"]["category"] == "style"


# ---------------------------------------------------------------------------
# TAP-2720: priority mapping and estimate derivation
# ---------------------------------------------------------------------------


class TestSeverityPriorityMapping:
    """TAP-2720: severity → Linear priority (1=Urgent … 3=Normal)."""

    @pytest.mark.parametrize(
        "severity,expected_priority",
        [
            ("P0", 1),  # Urgent
            ("P1", 2),  # High
            ("P2", 3),  # Normal
            ("P3", 3),  # Normal
        ],
    )
    def test_priority_from_severity(self, severity: str, expected_priority: int) -> None:
        story = finding_to_story(
            severity=severity,
            category="correctness",
            files=["src/mod.py:1"],
            evidence="finding evidence",
            recommendation="apply fix",
        )
        assert story.priority == expected_priority

    def test_unknown_severity_defaults_to_normal(self) -> None:
        # _SEVERITY_PRIORITY.get(unknown, 3) → 3
        from tapps_mcp.tools.finding_to_story import _SEVERITY_PRIORITY

        assert _SEVERITY_PRIORITY.get("P9", 3) == 3

    def test_priority_field_is_int(self) -> None:
        story = finding_to_story(
            severity="P1",
            category="security",
            files=["src/auth.py:1"],
            evidence="missing check",
            recommendation="add guard",
        )
        assert isinstance(story.priority, int)


class TestEstimateDerivation:
    """TAP-2720: story-point estimate derivation (Fibonacci-aligned)."""

    def test_p0_base_estimate_is_8(self) -> None:
        est = _derive_estimate("P0", ["f.py:1"], 0.0)
        assert est == 8

    def test_p1_base_estimate_is_5(self) -> None:
        est = _derive_estimate("P1", ["f.py:1"], 0.0)
        assert est == 5

    def test_p2_base_estimate_is_2(self) -> None:
        est = _derive_estimate("P2", ["f.py:1"], 0.0)
        assert est == 2

    def test_p3_base_estimate_is_1(self) -> None:
        est = _derive_estimate("P3", ["f.py:1"], 0.0)
        assert est == 1

    def test_file_bonus_adds_one_per_three_extra_files(self) -> None:
        # 4 files: base=2 (P2), bonus = (4-1)//3 = 1 → 3
        est = _derive_estimate("P2", ["f.py:1"] * 4, 0.0)
        assert est == 3

    def test_file_bonus_not_fractional(self) -> None:
        # 3 files: bonus = (3-1)//3 = 0 → no bonus
        est_three = _derive_estimate("P2", ["f.py:1"] * 3, 0.0)
        est_one = _derive_estimate("P2", ["f.py:1"], 0.0)
        assert est_three == est_one

    def test_complexity_bonus_above_10_adds_one(self) -> None:
        base = _derive_estimate("P2", ["f.py:1"], 0.0)
        with_complexity = _derive_estimate("P2", ["f.py:1"], 15.0)
        assert with_complexity == base + 1

    def test_complexity_bonus_above_20_adds_two(self) -> None:
        base = _derive_estimate("P2", ["f.py:1"], 0.0)
        with_complexity = _derive_estimate("P2", ["f.py:1"], 25.0)
        assert with_complexity == base + 2

    def test_complexity_at_exactly_10_no_bonus(self) -> None:
        est_zero = _derive_estimate("P2", ["f.py:1"], 0.0)
        est_ten = _derive_estimate("P2", ["f.py:1"], 10.0)
        assert est_ten == est_zero

    def test_estimate_capped_at_13(self) -> None:
        # P0 base=8 + many files + high complexity → cap at 13
        many_files = ["f.py:1"] * 20  # bonus = 19//3 = 6 → 8+6+2=16 → capped
        est = _derive_estimate("P0", many_files, 25.0)
        assert est == 13

    def test_estimate_minimum_is_1(self) -> None:
        est = _derive_estimate("P3", ["f.py:1"], 0.0)
        assert est >= 1

    def test_finding_to_story_returns_estimate(self) -> None:
        story = finding_to_story(
            severity="P2",
            category="style",
            files=["src/utils.py:1-30"],
            evidence="unused import",
            recommendation="remove unused import",
        )
        assert isinstance(story.estimate, int)
        assert story.estimate >= 1

    def test_avg_complexity_param_propagates(self) -> None:
        story_low = finding_to_story(
            severity="P2",
            category="correctness",
            files=["src/mod.py:1"],
            evidence="complexity issue",
            recommendation="refactor function",
            avg_complexity=0.0,
        )
        story_high = finding_to_story(
            severity="P2",
            category="correctness",
            files=["src/mod.py:1"],
            evidence="complexity issue",
            recommendation="refactor function",
            avg_complexity=25.0,
        )
        assert story_high.estimate > story_low.estimate


class TestTappsFindingToStoryHandlerEstimateAndPriority:
    """TAP-2720: handler exposes estimate and priority in response data."""

    @pytest.mark.asyncio()
    async def test_handler_returns_estimate_field(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P1",
            category="security",
            files=["src/auth.py:10-50"],
            evidence="missing auth check",
            recommendation="add authentication guard",
        )
        assert "estimate" in result["data"]
        assert isinstance(result["data"]["estimate"], int)

    @pytest.mark.asyncio()
    async def test_handler_returns_priority_field(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result = await tapps_finding_to_story(
            severity="P0",
            category="security",
            files=["src/x.py:1-10"],
            evidence="sql injection",
            recommendation="use parameterised queries",
        )
        assert "priority" in result["data"]
        assert result["data"]["priority"] == 1  # P0 → Urgent

    @pytest.mark.asyncio()
    async def test_handler_avg_complexity_increases_estimate(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_finding_to_story

        result_low = await tapps_finding_to_story(
            severity="P2",
            category="correctness",
            files=["src/mod.py:1"],
            evidence="issue",
            recommendation="fix",
            avg_complexity=0.0,
        )
        result_high = await tapps_finding_to_story(
            severity="P2",
            category="correctness",
            files=["src/mod.py:1"],
            evidence="issue",
            recommendation="fix",
            avg_complexity=25.0,
        )
        assert result_high["data"]["estimate"] > result_low["data"]["estimate"]

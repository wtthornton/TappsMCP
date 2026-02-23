"""Tests for scoring.dead_code - dead code penalty and suggestion logic."""

from __future__ import annotations

import pytest

from tapps_mcp.scoring.dead_code import (
    DEAD_CODE_MAX_PENALTY,
    DEAD_CODE_PENALTY_PER_FINDING,
    UNREACHABLE_CODE_PENALTY,
    calculate_dead_code_penalty,
    suggest_dead_code_fixes,
)
from tapps_mcp.tools.vulture import DeadCodeFinding


def _make_finding(
    *,
    finding_type: str = "function",
    name: str = "helper",
    confidence: int = 100,
    line: int = 42,
) -> DeadCodeFinding:
    """Create a DeadCodeFinding for testing."""
    return DeadCodeFinding(
        file_path="mod.py",
        line=line,
        name=name,
        finding_type=finding_type,
        confidence=confidence,
        message=f"unused {finding_type} '{name}' ({confidence}% confidence)",
    )


# ---------------------------------------------------------------------------
# calculate_dead_code_penalty
# ---------------------------------------------------------------------------
class TestCalculateDeadCodePenalty:
    def test_no_findings(self) -> None:
        maint, struct = calculate_dead_code_penalty([])
        assert maint == 0.0
        assert struct == 0.0

    def test_single_finding_100_confidence(self) -> None:
        findings = [_make_finding(confidence=100)]
        maint, struct = calculate_dead_code_penalty(findings)
        # penalty = 1.0 * 2.0 = 2.0
        # maintainability = 2.0 * 0.6 = 1.2
        # structure = 2.0 * 0.4 = 0.8
        assert maint == pytest.approx(1.2)
        assert struct == pytest.approx(0.8)

    def test_confidence_weighted(self) -> None:
        findings = [_make_finding(confidence=50)]
        maint, struct = calculate_dead_code_penalty(findings)
        # penalty = 0.5 * 2.0 = 1.0
        # maintainability = 1.0 * 0.6 = 0.6
        # structure = 1.0 * 0.4 = 0.4
        assert maint == pytest.approx(0.6)
        assert struct == pytest.approx(0.4)

    def test_unreachable_code_extra_penalty(self) -> None:
        findings = [_make_finding(finding_type="unreachable_code", confidence=100)]
        maint, struct = calculate_dead_code_penalty(findings)
        # base penalty = 1.0 * 2.0 = 2.0
        # maintainability = 2.0 * 0.6 + 5.0 (unreachable) = 6.2
        # structure = 2.0 * 0.4 = 0.8
        assert maint == pytest.approx(6.2)
        assert struct == pytest.approx(0.8)

    def test_cap_maintainability(self) -> None:
        # Create enough findings to exceed the cap
        findings = [_make_finding(confidence=100, line=i) for i in range(20)]
        maint, _struct = calculate_dead_code_penalty(findings)
        assert maint == DEAD_CODE_MAX_PENALTY

    def test_cap_structure(self) -> None:
        findings = [_make_finding(confidence=100, line=i) for i in range(30)]
        _maint, struct = calculate_dead_code_penalty(findings)
        assert struct == DEAD_CODE_MAX_PENALTY

    def test_multiple_findings_accumulate(self) -> None:
        findings = [
            _make_finding(confidence=100, name="a", line=1),
            _make_finding(confidence=80, name="b", line=2),
        ]
        maint, struct = calculate_dead_code_penalty(findings)
        # penalty = (1.0 * 2.0) + (0.8 * 2.0) = 3.6
        # maintainability = 3.6 * 0.6 = 2.16
        # structure = 3.6 * 0.4 = 1.44
        assert maint == pytest.approx(2.16)
        assert struct == pytest.approx(1.44)

    def test_higher_confidence_higher_penalty(self) -> None:
        low = [_make_finding(confidence=20)]
        high = [_make_finding(confidence=100)]
        maint_low, struct_low = calculate_dead_code_penalty(low)
        maint_high, struct_high = calculate_dead_code_penalty(high)
        assert maint_high > maint_low
        assert struct_high > struct_low

    def test_constants_are_sensible(self) -> None:
        assert DEAD_CODE_PENALTY_PER_FINDING > 0
        assert DEAD_CODE_MAX_PENALTY > DEAD_CODE_PENALTY_PER_FINDING
        assert UNREACHABLE_CODE_PENALTY > 0


# ---------------------------------------------------------------------------
# suggest_dead_code_fixes
# ---------------------------------------------------------------------------
class TestSuggestDeadCodeFixes:
    def test_empty_findings(self) -> None:
        assert suggest_dead_code_fixes([]) == []

    def test_unused_function(self) -> None:
        findings = [_make_finding(finding_type="function", name="helper", line=42, confidence=90)]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unused function 'helper'" in suggestions[0]
        assert "line 42" in suggestions[0]
        assert "90% confidence" in suggestions[0]

    def test_unused_import(self) -> None:
        findings = [_make_finding(finding_type="import", name="os", line=1, confidence=90)]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unused import 'os'" in suggestions[0]
        assert "line 1" in suggestions[0]
        assert "90% confidence" in suggestions[0]

    def test_unreachable_code(self) -> None:
        findings = [
            _make_finding(
                finding_type="unreachable_code",
                name="dead_branch",
                line=100,
                confidence=60,
            )
        ]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unreachable code 'dead_branch'" in suggestions[0]
        assert "line 100" in suggestions[0]
        assert "60% confidence" in suggestions[0]

    def test_unused_class(self) -> None:
        findings = [_make_finding(finding_type="class", name="OldManager", line=25, confidence=80)]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unused class 'OldManager'" in suggestions[0]

    def test_unused_variable(self) -> None:
        findings = [_make_finding(finding_type="variable", name="tmp", line=55, confidence=60)]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unused variable 'tmp'" in suggestions[0]

    def test_unused_attribute(self) -> None:
        findings = [
            _make_finding(finding_type="attribute", name="legacy_flag", line=70, confidence=80)
        ]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 1
        assert "Remove unused attribute 'legacy_flag'" in suggestions[0]

    def test_multiple_findings(self) -> None:
        findings = [
            _make_finding(finding_type="function", name="fn1", line=10, confidence=90),
            _make_finding(finding_type="import", name="sys", line=1, confidence=90),
            _make_finding(finding_type="unreachable_code", name="dead", line=50, confidence=60),
        ]
        suggestions = suggest_dead_code_fixes(findings)
        assert len(suggestions) == 3
        assert "fn1" in suggestions[0]
        assert "sys" in suggestions[1]
        assert "unreachable code" in suggestions[2]

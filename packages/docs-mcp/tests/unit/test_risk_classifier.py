"""Tests for docs_mcp.generators.risk_classifier -- Risk auto-classification.

Covers keyword-based impact/probability classification, ISO 31000 risk matrix
scoring, mitigation derivation, and word-boundary matching.
"""

from __future__ import annotations

from docs_mcp.generators.risk_classifier import RiskClassifier

# ---------------------------------------------------------------------------
# Impact classification
# ---------------------------------------------------------------------------


class TestImpactClassification:
    """Tests for keyword-driven impact classification."""

    def setup_method(self) -> None:
        self.clf = RiskClassifier()

    def test_security_keywords_high_impact(self) -> None:
        _prob, impact, _score = self.clf.classify("encrypt key rotation")
        assert impact == "High"

    def test_auth_keyword_high_impact(self) -> None:
        _prob, impact, _score = self.clf.classify("auth bypass risk")
        assert impact == "High"

    def test_ui_keywords_low_impact(self) -> None:
        _prob, impact, _score = self.clf.classify("button label alignment")
        assert impact == "Low"

    def test_deploy_keywords_medium_impact(self) -> None:
        _prob, impact, _score = self.clf.classify("CI pipeline failure")
        assert impact == "Medium"

    def test_default_medium(self) -> None:
        prob, impact, _score = self.clf.classify("update helper module")
        assert prob == "Medium"
        assert impact == "Medium"


# ---------------------------------------------------------------------------
# Probability classification
# ---------------------------------------------------------------------------


class TestProbabilityClassification:
    """Tests for keyword-driven probability classification."""

    def setup_method(self) -> None:
        self.clf = RiskClassifier()

    def test_complex_keyword_high_probability(self) -> None:
        prob, _impact, _score = self.clf.classify("complex legacy migration")
        assert prob == "High"


# ---------------------------------------------------------------------------
# Risk matrix scoring
# ---------------------------------------------------------------------------


class TestRiskMatrixScoring:
    """Tests for ISO 31000 3x3 risk matrix score computation."""

    def setup_method(self) -> None:
        self.clf = RiskClassifier()

    def test_risk_matrix_low_low(self) -> None:
        score = self.clf._compute_score("Low", "Low")
        assert score == 1

    def test_risk_matrix_high_high(self) -> None:
        score = self.clf._compute_score("High", "High")
        assert score == 9

    def test_risk_matrix_medium_high(self) -> None:
        score = self.clf._compute_score("Medium", "High")
        assert score == 6


# ---------------------------------------------------------------------------
# Mitigation derivation
# ---------------------------------------------------------------------------


class TestMitigationDerivation:
    """Tests for derive_mitigation from expert advice."""

    def setup_method(self) -> None:
        self.clf = RiskClassifier()

    def test_mitigation_from_expert_advice(self) -> None:
        mitigation = self.clf.derive_mitigation(
            "SQL injection risk",
            expert_advice="Use input validation against SQL injection. Also sanitize outputs.",
        )
        assert mitigation == "Use input validation against SQL injection."

    def test_mitigation_no_expert(self) -> None:
        mitigation = self.clf.derive_mitigation("some risk", expert_advice=None)
        assert "Mitigation required" in mitigation

    def test_mitigation_empty_expert(self) -> None:
        mitigation = self.clf.derive_mitigation("some risk", expert_advice="")
        assert "Mitigation required" in mitigation


# ---------------------------------------------------------------------------
# Word-boundary matching
# ---------------------------------------------------------------------------


class TestWordBoundaryMatching:
    """Tests for keyword word-boundary awareness."""

    def test_matches_keywords_word_boundary(self) -> None:
        # "ci" should NOT match inside "special" -- word boundary required.
        assert not RiskClassifier._matches_keywords("special", ["ci"])

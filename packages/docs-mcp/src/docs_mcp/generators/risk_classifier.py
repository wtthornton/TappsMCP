"""Risk auto-classification from keywords with ISO 31000 3x3 matrix scoring."""

from __future__ import annotations

import re
from typing import ClassVar

import structlog

logger = structlog.get_logger(__name__)


class RiskClassifier:
    """Classifies risk probability and impact from textual risk descriptions.

    Uses keyword matching against domain-specific patterns to assign
    probability/impact levels, then computes an ISO 31000-aligned risk score.
    """

    LEVELS: ClassVar[list[str]] = ["Low", "Medium", "High"]

    # Keywords that indicate high-impact risks.
    _HIGH_IMPACT_KEYWORDS: ClassVar[list[str]] = [
        "encrypt",
        "auth",
        "credential",
        "secret",
        "token",
        "password",
        "certificate",
        "oauth",
        "jwt",
        "session",
        "permission",
        "rbac",
        "migration",
        "schema",
        "database",
        "backup",
        "data loss",
        "production",
        "downtime",
        "outage",
    ]

    # Keywords that indicate medium-impact risks.
    _MEDIUM_IMPACT_KEYWORDS: ClassVar[list[str]] = [
        "deploy",
        "docker",
        "ci",
        "pipeline",
        "infrastructure",
        "api",
        "endpoint",
        "integration",
        "cache",
        "queue",
        "config",
        "performance",
        "latency",
        "scale",
    ]

    # Keywords that indicate low-impact risks.
    _LOW_IMPACT_KEYWORDS: ClassVar[list[str]] = [
        "ui",
        "display",
        "format",
        "label",
        "color",
        "font",
        "typo",
        "rename",
        "refactor",
        "comment",
        "docs",
        "style",
        "lint",
        "cosmetic",
    ]

    # Keywords that indicate higher probability.
    _HIGH_PROBABILITY_KEYWORDS: ClassVar[list[str]] = [
        "complex",
        "legacy",
        "untested",
        "fragile",
        "manual",
        "third-party",
        "external",
        "dependency",
        "migration",
    ]

    # Risk score matrix: (probability_index, impact_index) -> score 1-9.
    # Index 0=Low, 1=Medium, 2=High.
    _RISK_MATRIX: ClassVar[dict[tuple[int, int], int]] = {
        (0, 0): 1,
        (0, 1): 2,
        (0, 2): 3,
        (1, 0): 2,
        (1, 1): 4,
        (1, 2): 6,
        (2, 0): 3,
        (2, 1): 6,
        (2, 2): 9,
    }

    def classify(self, risk_text: str) -> tuple[str, str, int]:
        """Classify a risk description into probability, impact, and score.

        Args:
            risk_text: Free-text risk description.

        Returns:
            Tuple of (probability, impact, risk_score) where probability and
            impact are "Low", "Medium", or "High" and risk_score is 1-9.
        """
        text_lower = risk_text.lower()
        impact = self._classify_impact(text_lower)
        probability = self._classify_probability(text_lower)
        score = self._compute_score(probability, impact)
        return probability, impact, score

    def derive_mitigation(
        self,
        risk_text: str,
        expert_advice: str | None = None,
    ) -> str:
        """Derive a mitigation strategy from expert advice or flag the gap.

        Args:
            risk_text: The risk description (used for context if needed).
            expert_advice: Expert-provided advice text, if available.

        Returns:
            Mitigation text — either derived from expert advice or a warning.
        """
        if expert_advice and expert_advice.strip():
            # Take the first sentence of expert advice as mitigation.
            first_sentence = expert_advice.strip().split(". ")[0]
            if not first_sentence.endswith("."):
                first_sentence += "."
            return first_sentence
        return "Warning: Mitigation required - no automated recommendation available"

    def _classify_impact(self, text: str) -> str:
        """Classify impact level from keywords in text."""
        if self._matches_keywords(text, self._HIGH_IMPACT_KEYWORDS):
            return "High"
        if self._matches_keywords(text, self._MEDIUM_IMPACT_KEYWORDS):
            return "Medium"
        if self._matches_keywords(text, self._LOW_IMPACT_KEYWORDS):
            return "Low"
        return "Medium"  # default

    def _classify_probability(self, text: str) -> str:
        """Classify probability level from keywords in text."""
        if self._matches_keywords(text, self._HIGH_PROBABILITY_KEYWORDS):
            return "High"
        return "Medium"  # default

    def _compute_score(self, probability: str, impact: str) -> int:
        """Compute ISO 31000 risk score from probability and impact levels."""
        p_idx = self.LEVELS.index(probability)
        i_idx = self.LEVELS.index(impact)
        return self._RISK_MATRIX[(p_idx, i_idx)]

    @staticmethod
    def _matches_keywords(text: str, keywords: list[str]) -> bool:
        """Check if text contains any of the keywords (word-boundary aware)."""
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", text):
                return True
        return False

"""Tests for adaptive domain detection wiring in engine._resolve_domain().

Verifies that the expert engine integrates the AdaptiveDomainDetector when
adaptive learning is enabled and has sufficient outcome data, and falls
back to the static DomainDetector otherwise.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tapps_core.experts.adaptive_domain_detector import DomainSuggestion
from tapps_core.experts.engine import (
    _ADAPTIVE_MIN_CONFIDENCE,
    _resolve_domain,
    _try_adaptive_detection,
    consult_expert,
)
from tapps_core.experts.models import ConsultationResult, DomainMapping


class TestResolvedDomainAdaptiveFlag:
    """Verify _ResolvedDomain.adaptive_domain_used is propagated correctly."""

    def test_explicit_domain_does_not_use_adaptive(self) -> None:
        resolved = _resolve_domain("any question", domain="security")
        assert resolved.adaptive_domain_used is False

    def test_static_fallback_does_not_set_adaptive_flag(self) -> None:
        with patch(
            "tapps_core.experts.engine._try_adaptive_detection",
            return_value=(None, []),
        ):
            resolved = _resolve_domain("How to prevent SQL injection?", domain=None)
            assert resolved.adaptive_domain_used is False

    @patch("tapps_core.experts.engine._try_adaptive_detection")
    def test_adaptive_domain_sets_flag_true(self, mock_adaptive: MagicMock) -> None:
        mock_adaptive.return_value = (
            "security",
            [
                DomainMapping(
                    domain="security",
                    confidence=0.8,
                    signals=["adaptive:prompt"],
                    reasoning="Adaptive: prompt",
                )
            ],
        )
        resolved = _resolve_domain("How to prevent SQL injection?", domain=None)
        assert resolved.adaptive_domain_used is True
        assert resolved.domain == "security"


class TestTryAdaptiveDetection:
    """Tests for _try_adaptive_detection helper.

    Imports inside _try_adaptive_detection are lazy (inside the function body),
    so patches target the source modules, not tapps_core.experts.engine.
    """

    def test_returns_none_when_adaptive_disabled(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = False
        with patch(
            "tapps_core.config.settings.load_settings",
            return_value=mock_settings,
        ):
            domain, detected = _try_adaptive_detection("test question")
            assert domain is None
            assert detected == []

    def test_returns_none_when_insufficient_outcomes(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 5
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = [1, 2]  # only 2, need 5

        with (
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
        ):
            domain, detected = _try_adaptive_detection("test question")
            assert domain is None
            assert detected == []

    def test_returns_domain_when_high_confidence(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 5
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = list(range(10))

        suggestion = DomainSuggestion(
            domain="testing",
            confidence=0.8,
            source="prompt",
            evidence=["Keyword match: testing"],
        )

        async def fake_detect_domains(**kwargs: object) -> list[DomainSuggestion]:
            return [suggestion]

        mock_detector = MagicMock()
        mock_detector.detect_domains = fake_detect_domains

        with (
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
            patch(
                "tapps_core.experts.adaptive_domain_detector.AdaptiveDomainDetector",
                return_value=mock_detector,
            ),
        ):
            domain, detected = _try_adaptive_detection("How to test?")
            assert domain == "testing"
            assert len(detected) == 1
            assert detected[0].domain == "testing"
            assert detected[0].confidence == 0.8

    def test_returns_none_when_low_confidence(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 5
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = list(range(10))

        suggestion = DomainSuggestion(
            domain="testing",
            confidence=0.2,  # Below _ADAPTIVE_MIN_CONFIDENCE (0.4)
            source="prompt",
            evidence=["Weak match"],
        )

        async def fake_detect_domains(**kwargs: object) -> list[DomainSuggestion]:
            return [suggestion]

        mock_detector = MagicMock()
        mock_detector.detect_domains = fake_detect_domains

        with (
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
            patch(
                "tapps_core.experts.adaptive_domain_detector.AdaptiveDomainDetector",
                return_value=mock_detector,
            ),
        ):
            domain, detected = _try_adaptive_detection("test?")
            assert domain is None
            assert detected == []

    def test_returns_none_when_no_suggestions(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 5
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = list(range(10))

        async def fake_detect_domains(**kwargs: object) -> list[DomainSuggestion]:
            return []

        mock_detector = MagicMock()
        mock_detector.detect_domains = fake_detect_domains

        with (
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
            patch(
                "tapps_core.experts.adaptive_domain_detector.AdaptiveDomainDetector",
                return_value=mock_detector,
            ),
        ):
            domain, detected = _try_adaptive_detection("random question")
            assert domain is None
            assert detected == []

    def test_catches_exceptions_gracefully(self) -> None:
        with patch(
            "tapps_core.config.settings.load_settings",
            side_effect=RuntimeError("config error"),
        ):
            domain, detected = _try_adaptive_detection("test")
            assert domain is None
            assert detected == []


class TestConsultExpertAdaptiveIntegration:
    """Integration tests for adaptive wiring through consult_expert."""

    def test_consultation_result_has_adaptive_field(self) -> None:
        result = consult_expert("How to prevent SQL injection?")
        assert isinstance(result, ConsultationResult)
        assert hasattr(result, "adaptive_domain_used")
        assert isinstance(result.adaptive_domain_used, bool)

    def test_default_adaptive_domain_used_is_false(self) -> None:
        result = consult_expert("How to prevent SQL injection?")
        assert result.adaptive_domain_used is False

    @patch("tapps_core.experts.engine._try_adaptive_detection")
    def test_adaptive_domain_used_true_in_result(
        self, mock_adaptive: MagicMock
    ) -> None:
        mock_adaptive.return_value = (
            "security",
            [
                DomainMapping(
                    domain="security",
                    confidence=0.9,
                    signals=["adaptive:prompt"],
                    reasoning="Adaptive: prompt",
                )
            ],
        )
        result = consult_expert("How to prevent SQL injection?")
        assert result.adaptive_domain_used is True
        assert result.domain == "security"


class TestDomainSuggestionConversion:
    """Verify DomainSuggestion → DomainMapping conversion in _try_adaptive_detection."""

    def test_suggestion_converts_to_domain_mapping(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 1
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = list(range(5))

        suggestions = [
            DomainSuggestion(
                domain="oauth2",
                confidence=0.65,
                source="prompt",
                evidence=["Keyword match: oauth", "Keyword match: refresh token"],
            ),
            DomainSuggestion(
                domain="authentication",
                confidence=0.5,
                source="code_pattern",
                evidence=["Pattern match: login"],
            ),
        ]

        async def fake_detect(**kwargs: object) -> list[DomainSuggestion]:
            return suggestions

        mock_detector = MagicMock()
        mock_detector.detect_domains = fake_detect

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
            patch(
                "tapps_core.experts.adaptive_domain_detector.AdaptiveDomainDetector",
                return_value=mock_detector,
            ),
        ):
            domain, detected = _try_adaptive_detection("oauth2 refresh token flow")
            assert domain == "oauth2"
            # Conversion caps at 3 suggestions
            assert len(detected) <= 3
            # First mapping matches best suggestion
            assert isinstance(detected[0], DomainMapping)
            assert detected[0].domain == "oauth2"
            assert detected[0].confidence == 0.65
            assert "adaptive:prompt" in detected[0].signals
            assert "Keyword match: oauth" in detected[0].reasoning

    def test_conversion_caps_at_three_mappings(self) -> None:
        mock_settings = MagicMock()
        mock_settings.adaptive.enabled = True
        mock_settings.adaptive.min_outcomes = 1
        mock_settings.project_root = MagicMock()

        mock_tracker = MagicMock()
        mock_tracker.load_outcomes.return_value = list(range(5))

        suggestions = [
            DomainSuggestion(domain=f"domain-{i}", confidence=0.9 - i * 0.1, source="prompt")
            for i in range(5)
        ]

        async def fake_detect(**kwargs: object) -> list[DomainSuggestion]:
            return suggestions

        mock_detector = MagicMock()
        mock_detector.detect_domains = fake_detect

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch(
                "tapps_core.adaptive.persistence.FileOutcomeTracker",
                return_value=mock_tracker,
            ),
            patch(
                "tapps_core.experts.adaptive_domain_detector.AdaptiveDomainDetector",
                return_value=mock_detector,
            ),
        ):
            _, detected = _try_adaptive_detection("complex question")
            assert len(detected) == 3


class TestFeedbackToAdaptiveOutcomes:
    """Verify feedback records bridge to adaptive training data."""

    def test_to_adaptive_outcomes_produces_records(self, tmp_path: MagicMock) -> None:
        from tapps_core.metrics.feedback import FeedbackTracker

        tracker = FeedbackTracker(tmp_path)
        tracker.record("tapps_score_file", helpful=True, context="good scores")
        tracker.record("tapps_quality_gate", helpful=False, context="too strict")
        tracker.record("tapps_consult_expert", helpful=True, context="irrelevant")

        outcomes = tracker.to_adaptive_outcomes()
        # Only scoring tools produce outcomes
        assert len(outcomes) == 2
        assert outcomes[0]["first_pass_success"] is True
        assert outcomes[1]["first_pass_success"] is False
        assert outcomes[0]["source"] == "feedback"

    def test_non_scoring_tools_excluded(self, tmp_path: MagicMock) -> None:
        from tapps_core.metrics.feedback import FeedbackTracker

        tracker = FeedbackTracker(tmp_path)
        tracker.record("tapps_consult_expert", helpful=True)
        tracker.record("tapps_lookup_docs", helpful=True)

        outcomes = tracker.to_adaptive_outcomes()
        assert len(outcomes) == 0


class TestAdaptiveMinConfidenceConstant:
    """Verify the threshold constant is correct."""

    def test_threshold_value(self) -> None:
        assert _ADAPTIVE_MIN_CONFIDENCE == 0.4

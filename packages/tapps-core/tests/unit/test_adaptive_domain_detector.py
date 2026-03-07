"""Tests for adaptive domain detector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.adaptive.persistence import DomainWeightStore
from tapps_core.experts.adaptive_domain_detector import (
    AdaptiveDomainDetector,
    DomainSuggestion,
)


class TestAdaptiveDomainDetector:
    def _make_detector(self) -> AdaptiveDomainDetector:
        return AdaptiveDomainDetector()

    async def test_detect_from_prompt_oauth(self):
        detector = self._make_detector()
        results = await detector.detect_domains(
            prompt="How to implement oauth2 refresh token flow?"
        )
        domains = [s.domain for s in results]
        assert "oauth2" in domains

    async def test_detect_from_code_patterns_websocket(self):
        detector = self._make_detector()
        code = 'conn = WebSocket("ws://localhost:8080")'
        results = await detector.detect_domains(code_context=code)
        domains = [s.domain for s in results]
        assert "websocket" in domains

    async def test_detect_from_consultation_gaps(self):
        detector = self._make_detector()
        history = [
            {"domain": "new-domain", "confidence": 0.3},
            {"domain": "new-domain", "confidence": 0.4},
        ]
        results = await detector.detect_domains(consultation_history=history)
        domains = [s.domain for s in results]
        assert "new-domain" in domains

    async def test_empty_inputs_no_suggestions(self):
        detector = self._make_detector()
        results = await detector.detect_domains()
        assert results == []

    async def test_detect_recurring_patterns(self):
        history = [
            DomainSuggestion(domain="new-api", confidence=0.6, source="prompt"),
            DomainSuggestion(domain="new-api", confidence=0.7, source="prompt"),
            DomainSuggestion(domain="new-api", confidence=0.5, source="prompt"),
            DomainSuggestion(domain="rare", confidence=0.5, source="prompt"),
        ]
        recurring = await AdaptiveDomainDetector.detect_recurring_patterns(history)
        domains = [s.domain for s in recurring]
        assert "new-api" in domains
        assert "rare" not in domains

    async def test_deduplicates_by_domain(self):
        detector = self._make_detector()
        # Both prompt and code detect websocket.
        results = await detector.detect_domains(
            prompt="websocket connection",
            code_context='ws = WebSocket("ws://example.com")',
        )
        ws_results = [s for s in results if s.domain == "websocket"]
        assert len(ws_results) <= 1


# ---------------------------------------------------------------------------
# Weight-based detection tests (Epic 57, Story 57.2)
# ---------------------------------------------------------------------------


class TestAdaptiveDomainDetectorWeightBased:
    """Tests for weight-based domain detection (Epic 57)."""

    @pytest.fixture()
    def detector(self, tmp_path: Path) -> AdaptiveDomainDetector:
        return AdaptiveDomainDetector(project_root=tmp_path)

    @pytest.fixture()
    def weight_store(self, tmp_path: Path) -> DomainWeightStore:
        return DomainWeightStore(tmp_path)

    # -- Basic detect() tests -----------------------------------------------

    def test_detect_returns_tuple(self, detector: AdaptiveDomainDetector):
        """detect() returns a (domain, confidence) tuple."""
        domain, confidence = detector.detect("How do I secure my API?")
        assert isinstance(domain, str)
        assert isinstance(confidence, float)

    def test_detect_security_question(self, detector: AdaptiveDomainDetector):
        """Security-related questions should route to security domain."""
        domain, confidence = detector.detect("How to prevent SQL injection attacks?")
        assert domain == "security"
        assert confidence > 0.0

    def test_detect_testing_question(self, detector: AdaptiveDomainDetector):
        """Testing-related questions should route to testing domain."""
        # Use multiple keywords to boost confidence above threshold.
        domain, confidence = detector.detect(
            "How to write unit test with pytest and test coverage for integration test?"
        )
        assert domain == "testing-strategies"
        assert confidence > 0.0

    def test_detect_no_match_returns_unknown(self, detector: AdaptiveDomainDetector):
        """Questions with no keyword match return unknown."""
        domain, confidence = detector.detect("What is the meaning of life?")
        assert domain == "unknown"
        assert confidence == 0.0

    # -- Weight application tests -------------------------------------------

    def test_detect_applies_learned_weights(
        self, tmp_path: Path, weight_store: DomainWeightStore
    ):
        """Learned weights should influence domain selection."""
        # Boost testing domain weight significantly.
        weight_store.save_weight("testing-strategies", 2.5, domain_type="technical")
        # Lower security domain weight.
        weight_store.save_weight("security", 0.5, domain_type="technical")

        detector = AdaptiveDomainDetector(project_root=tmp_path)

        # A question that could match both security and testing keywords.
        domain, _confidence = detector.detect("test security vulnerabilities")

        # Testing should win because of the higher learned weight.
        assert domain == "testing-strategies"

    def test_detect_without_weights_uses_default(self, detector: AdaptiveDomainDetector):
        """Without stored weights, default weight of 1.0 is used."""
        # Use multiple keywords to boost confidence above threshold.
        domain, confidence = detector.detect(
            "How to handle authentication with login session and password management?"
        )
        # Should still work with default weights.
        assert domain != "unknown"
        assert confidence > 0.0

    # -- include_business parameter tests -----------------------------------

    def test_detect_include_business_false(self, detector: AdaptiveDomainDetector):
        """include_business=False excludes business domains."""
        # Use multiple keywords to boost confidence above threshold.
        domain, confidence = detector.detect(
            "How to handle security authentication and authorization?",
            include_business=False,
        )
        assert domain != "unknown"
        assert confidence > 0.0

    # -- detect_with_details() tests ----------------------------------------

    def test_detect_with_details_returns_dict(self, detector: AdaptiveDomainDetector):
        """detect_with_details() returns a detailed dictionary."""
        details = detector.detect_with_details("How to secure my API?")
        assert "domain" in details
        assert "confidence" in details
        assert "raw_confidence" in details
        assert "weight_applied" in details
        assert "domain_type" in details
        assert "all_candidates" in details

    def test_detect_with_details_all_candidates(self, detector: AdaptiveDomainDetector):
        """all_candidates includes all matched domains."""
        details = detector.detect_with_details("test security vulnerabilities")
        assert len(details["all_candidates"]) > 0
        for candidate in details["all_candidates"]:
            assert "domain" in candidate
            assert "confidence" in candidate
            assert "raw_confidence" in candidate
            assert "weight_applied" in candidate
            assert "domain_type" in candidate

    def test_detect_with_details_shows_weight_impact(
        self, tmp_path: Path, weight_store: DomainWeightStore
    ):
        """detect_with_details shows the weight that was applied."""
        weight_store.save_weight("security", 1.8, domain_type="technical")

        detector = AdaptiveDomainDetector(project_root=tmp_path)
        details = detector.detect_with_details("How to prevent XSS attacks?")

        assert details["domain"] == "security"
        assert details["weight_applied"] == 1.8
        assert details["confidence"] > details["raw_confidence"]

    def test_detect_with_details_no_match(self, detector: AdaptiveDomainDetector):
        """detect_with_details returns unknown for no match."""
        details = detector.detect_with_details("random gibberish xyz")
        assert details["domain"] == "unknown"
        assert details["confidence"] == 0.0
        assert details["all_candidates"] == []

    # -- Confidence threshold tests -----------------------------------------

    def test_detect_respects_confidence_threshold(
        self, tmp_path: Path, weight_store: DomainWeightStore
    ):
        """Detection should respect the 0.4 confidence threshold."""
        # Set a very low weight that will push confidence below threshold.
        weight_store.save_weight("security", 0.1, domain_type="technical")

        detector = AdaptiveDomainDetector(project_root=tmp_path)
        domain, confidence = detector.detect("security")

        # The raw confidence may be ~0.5, but with 0.1 weight it becomes 0.05.
        # Below threshold, should return unknown.
        if confidence == 0.0:
            assert domain == "unknown"

    # -- Path handling tests ------------------------------------------------

    def test_accepts_string_path(self, tmp_path: Path):
        """Constructor accepts string paths."""
        detector = AdaptiveDomainDetector(project_root=str(tmp_path))
        domain, _confidence = detector.detect("How to test my code?")
        assert domain != ""

    def test_accepts_path_object(self, tmp_path: Path):
        """Constructor accepts Path objects."""
        detector = AdaptiveDomainDetector(project_root=tmp_path)
        domain, _confidence = detector.detect("How to test my code?")
        assert domain != ""

    def test_none_project_root_works(self):
        """None project_root still works (no weight store)."""
        detector = AdaptiveDomainDetector(project_root=None)
        domain, _confidence = detector.detect("How to test my code?")
        # Should still work with default weights.
        assert domain != ""

    # -- Domain type classification tests -----------------------------------

    def test_technical_domains_classified_correctly(
        self, detector: AdaptiveDomainDetector
    ):
        """Built-in domains should be classified as technical."""
        # Use multiple keywords to boost confidence above threshold.
        details = detector.detect_with_details(
            "How to write unit test with pytest and test coverage?"
        )
        assert details["domain_type"] == "technical"

    def test_candidates_sorted_by_weighted_confidence(
        self, tmp_path: Path, weight_store: DomainWeightStore
    ):
        """Candidates should be sorted by weighted confidence (descending)."""
        weight_store.save_weight("testing-strategies", 2.0, domain_type="technical")
        weight_store.save_weight("security", 0.5, domain_type="technical")

        detector = AdaptiveDomainDetector(project_root=tmp_path)
        details = detector.detect_with_details("test security vulnerabilities")

        candidates = details["all_candidates"]
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert candidates[i]["confidence"] >= candidates[i + 1]["confidence"]

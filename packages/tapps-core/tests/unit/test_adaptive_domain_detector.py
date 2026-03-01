"""Tests for adaptive domain detector."""

from __future__ import annotations

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

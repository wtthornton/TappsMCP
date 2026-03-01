"""Unit tests for documentation providers (LlmsTxtProvider, etc.)."""

from __future__ import annotations

from tapps_core.knowledge.providers.base import DocumentationProvider
from tapps_core.knowledge.providers.llms_txt_provider import LlmsTxtProvider


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProviderProtocolCompliance:
    def test_llms_txt_satisfies_protocol(self) -> None:
        assert isinstance(LlmsTxtProvider(), DocumentationProvider)


# ---------------------------------------------------------------------------
# LlmsTxtProvider
# ---------------------------------------------------------------------------


class TestLlmsTxtProvider:
    def test_is_available_always_true(self) -> None:
        assert LlmsTxtProvider().is_available() is True

    def test_name(self) -> None:
        assert LlmsTxtProvider().name() == "llms_txt"

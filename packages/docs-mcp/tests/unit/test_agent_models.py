"""Tests for agent configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.agents.models import AgentConfig, MemoryProfile


class TestMemoryProfile:
    """Test MemoryProfile enum."""

    def test_values(self) -> None:
        assert MemoryProfile.FULL == "full"
        assert MemoryProfile.READONLY == "readonly"
        assert MemoryProfile.NONE == "none"

    def test_from_string(self) -> None:
        assert MemoryProfile("full") == MemoryProfile.FULL
        assert MemoryProfile("readonly") == MemoryProfile.READONLY
        assert MemoryProfile("none") == MemoryProfile.NONE


class TestAgentConfig:
    """Test AgentConfig model."""

    def test_minimal(self) -> None:
        config = AgentConfig(name="test-agent")
        assert config.name == "test-agent"
        assert config.description == ""
        assert config.keywords == []
        assert config.capabilities == []
        assert config.memory_profile == MemoryProfile.FULL
        assert config.deprecated is False
        assert config.source_path is None

    def test_full_config(self) -> None:
        config = AgentConfig(
            name="weather",
            description="Provides weather forecasts",
            keywords=["weather", "forecast", "temperature"],
            capabilities=["weather_lookup", "forecast_7day"],
            memory_profile=MemoryProfile.READONLY,
            deprecated=False,
            system_prompt_path=Path("/agents/weather/AGENT.md"),
        )
        assert config.name == "weather"
        assert len(config.keywords) == 3
        assert config.memory_profile == MemoryProfile.READONLY

    def test_name_required(self) -> None:
        with pytest.raises(Exception):
            AgentConfig()  # type: ignore[call-arg]

    def test_name_min_length(self) -> None:
        with pytest.raises(Exception):
            AgentConfig(name="")

    def test_embedding_text(self) -> None:
        config = AgentConfig(
            name="code-review",
            description="Reviews Python code quality",
            keywords=["python", "review", "quality"],
            capabilities=["lint", "type-check"],
        )
        text = config.embedding_text()
        assert "code-review" in text
        assert "Reviews Python code quality" in text
        assert "python" in text
        assert "lint" in text

    def test_embedding_text_minimal(self) -> None:
        config = AgentConfig(name="minimal")
        text = config.embedding_text()
        assert text == "minimal"

    def test_deprecated_default_false(self) -> None:
        config = AgentConfig(name="test")
        assert config.deprecated is False

    def test_memory_profile_default_full(self) -> None:
        config = AgentConfig(name="test")
        assert config.memory_profile == MemoryProfile.FULL

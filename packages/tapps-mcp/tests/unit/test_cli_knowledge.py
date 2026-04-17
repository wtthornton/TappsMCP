"""Tests for lookup-docs, research, and consult-expert CLI commands (Epic 53)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _mock_lookup_result(
    success: bool = True,
    content: str = "# FastAPI Routing\n\nUse `@app.get()` for GET endpoints.",
    source: str = "cache",
    library: str = "fastapi",
    topic: str = "routing",
    error: str | None = None,
    warning: str | None = None,
) -> MagicMock:
    result = MagicMock()
    result.success = success
    result.content = content
    result.source = source
    result.library = library
    result.topic = topic
    result.error = error
    result.warning = warning
    return result


def _mock_consultation_result(
    domain: str = "security",
    expert_name: str = "Security Expert",
    confidence: float = 0.85,
    answer: str = "## Security Expert\n\nUse parameterized queries to prevent SQL injection.",
    sources: list[str] | None = None,
    recommendation: str = "Expert guidance is high-confidence.",
) -> MagicMock:
    result = MagicMock()
    result.domain = domain
    result.expert_name = expert_name
    result.confidence = confidence
    result.answer = answer
    result.sources = sources or ["security/sql_injection.md"]
    result.recommendation = recommendation
    result.model_dump.return_value = {
        "domain": domain,
        "expert_name": expert_name,
        "confidence": confidence,
        "answer": answer,
        "sources": sources or ["security/sql_injection.md"],
        "recommendation": recommendation,
    }
    return result


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.project_root = MagicMock()
    settings.project_root.__truediv__ = MagicMock(return_value=MagicMock())
    return settings


class TestLookupDocs:
    def test_lookup_success(self, runner: CliRunner) -> None:
        mock_result = _mock_lookup_result()
        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=mock_result)
        mock_engine.close = AsyncMock()

        with (
            patch("tapps_core.config.settings.load_settings", return_value=_mock_settings()),
            patch("tapps_core.knowledge.cache.KBCache"),
            patch("tapps_core.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            result = runner.invoke(
                main, ["lookup-docs", "--library", "fastapi", "--topic", "routing"]
            )
        assert result.exit_code == 0
        assert "fastapi" in result.output
        assert "routing" in result.output
        assert "FastAPI Routing" in result.output

    def test_lookup_failure(self, runner: CliRunner) -> None:
        mock_result = _mock_lookup_result(
            success=False, content=None, error="No documentation found."
        )
        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=mock_result)
        mock_engine.close = AsyncMock()

        with (
            patch("tapps_core.config.settings.load_settings", return_value=_mock_settings()),
            patch("tapps_core.knowledge.cache.KBCache"),
            patch("tapps_core.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            result = runner.invoke(main, ["lookup-docs", "--library", "nonexistent"])
        assert result.exit_code == 1
        assert "No documentation found" in result.output

    def test_lookup_truncation(self, runner: CliRunner) -> None:
        long_content = "x" * 3000
        mock_result = _mock_lookup_result(content=long_content)
        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=mock_result)
        mock_engine.close = AsyncMock()

        with (
            patch("tapps_core.config.settings.load_settings", return_value=_mock_settings()),
            patch("tapps_core.knowledge.cache.KBCache"),
            patch("tapps_core.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            result = runner.invoke(main, ["lookup-docs", "--library", "fastapi"])
        assert result.exit_code == 0
        assert "truncated" in result.output

    def test_lookup_raw_no_truncation(self, runner: CliRunner) -> None:
        long_content = "x" * 3000
        mock_result = _mock_lookup_result(content=long_content)
        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=mock_result)
        mock_engine.close = AsyncMock()

        with (
            patch("tapps_core.config.settings.load_settings", return_value=_mock_settings()),
            patch("tapps_core.knowledge.cache.KBCache"),
            patch("tapps_core.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            result = runner.invoke(main, ["lookup-docs", "--library", "fastapi", "--raw"])
        assert result.exit_code == 0
        assert "truncated" not in result.output

    def test_lookup_with_warning(self, runner: CliRunner) -> None:
        mock_result = _mock_lookup_result(warning="Stale content returned.")
        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=mock_result)
        mock_engine.close = AsyncMock()

        with (
            patch("tapps_core.config.settings.load_settings", return_value=_mock_settings()),
            patch("tapps_core.knowledge.cache.KBCache"),
            patch("tapps_core.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            result = runner.invoke(main, ["lookup-docs", "--library", "fastapi"])
        assert result.exit_code == 0
        assert "Stale content returned" in result.output


# Note: TestConsultExpert and TestResearch were removed when the
# `consult-expert` and `research` CLI commands were deleted (EPIC-94).

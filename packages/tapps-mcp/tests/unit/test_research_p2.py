"""Tests for P2 research enhancements: always-on docs + file context."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.experts.models import ConfidenceFactors, ConsultationResult
from tapps_mcp.knowledge.models import LookupResult


def _make_consultation_result(
    confidence: float = 0.9,
    chunks_used: int = 3,
    suggested_library: str | None = None,
) -> ConsultationResult:
    """Create a mock ConsultationResult with sensible defaults."""
    return ConsultationResult(
        domain="security",
        expert_id="expert-security",
        expert_name="Security Expert",
        answer="Expert answer here.",
        confidence=confidence,
        factors=ConfidenceFactors(
            rag_quality=0.8,
            domain_relevance=1.0,
            source_count=2,
            chunk_coverage=0.7,
        ),
        sources=["source1.md"],
        chunks_used=chunks_used,
        suggested_library=suggested_library,
    )


def _make_lookup_result(success: bool = True, content: str | None = "Doc content") -> LookupResult:
    return LookupResult(success=success, content=content, source="cache")


def _settings_mock() -> MagicMock:
    s = MagicMock()
    s.project_root = MagicMock()
    s.project_root.__truediv__ = MagicMock(return_value=MagicMock())
    s.context7_api_key = ""
    s.expert_fallback_max_chars = 5000
    s.memory.write_rules.max_value_length = 4096
    s.memory.write_rules.min_value_length = 20
    s.memory.enabled = True
    return s


class TestDocsAlwaysFetched:
    """Docs are always supplemented regardless of expert confidence."""

    async def test_docs_always_fetched_regardless_of_confidence(self) -> None:
        """Even with high confidence and chunks, docs lookup is still called."""
        result = _make_consultation_result(confidence=0.9, chunks_used=5)
        lookup_result = _make_lookup_result()
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch("tapps_mcp.experts.engine.consult_expert", return_value=result),
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp: dict[str, Any] = await tapps_research(
                question="How to prevent SQL injection?",
                domain="security",
            )

        assert resp["success"] is True
        assert resp["data"]["docs_supplemented"] is True
        mock_engine.lookup.assert_awaited_once()


class TestFileContextInference:
    """file_context parameter infers library from imports."""

    async def test_file_context_infers_library(self) -> None:
        result = _make_consultation_result(suggested_library=None)
        lookup_result = _make_lookup_result()
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch("tapps_mcp.experts.engine.consult_expert", return_value=result),
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.knowledge.import_analyzer.extract_external_imports",
                return_value=["pydantic"],
            ),
            patch("tapps_mcp.server._validate_file_path", return_value=MagicMock()),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp = await tapps_research(
                question="How to use pydantic?",
                domain="security",
                file_context="/some/file.py",
            )

        assert resp["success"] is True
        # The lookup should have used "pydantic" as the library
        call_kwargs = mock_engine.lookup.call_args
        assert call_kwargs.kwargs.get("library") == "pydantic" or (
            call_kwargs.args and call_kwargs.args[0] == "pydantic"
        )

    async def test_file_context_invalid_path_graceful(self) -> None:
        """Invalid file_context should not crash the function."""
        result = _make_consultation_result(suggested_library=None)
        lookup_result = _make_lookup_result(success=False, content=None)
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch("tapps_mcp.experts.engine.consult_expert", return_value=result),
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.server._validate_file_path",
                side_effect=FileNotFoundError("not found"),
            ),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp = await tapps_research(
                question="Some question?",
                domain="security",
                file_context="/nonexistent/file.py",
            )

        # Should still return successfully
        assert resp["success"] is True


class TestTechStackInference:
    """When no library or file_context, infer from tech stack."""

    async def test_tech_stack_inference_when_no_file_context(self) -> None:
        result = _make_consultation_result(suggested_library=None)
        lookup_result = _make_lookup_result()
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        session_ctx = {
            "project_profile": {
                "tech_stack": {
                    "context7_priority": ["fastapi", "pydantic"],
                    "libraries": ["fastapi"],
                }
            }
        }

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch("tapps_mcp.experts.engine.consult_expert", return_value=result),
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.server_helpers.get_session_context",
                return_value=session_ctx,
            ),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp = await tapps_research(
                question="How to handle routes?",
                domain="security",
            )

        assert resp["success"] is True
        call_kwargs = mock_engine.lookup.call_args
        assert call_kwargs.kwargs.get("library") == "fastapi" or (
            call_kwargs.args and call_kwargs.args[0] == "fastapi"
        )

    async def test_fallback_to_python_when_no_tech_stack(self) -> None:
        result = _make_consultation_result(suggested_library=None)
        lookup_result = _make_lookup_result()
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch("tapps_mcp.experts.engine.consult_expert", return_value=result),
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.server_helpers.get_session_context",
                return_value={},
            ),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp = await tapps_research(
                question="General python question?",
                domain="security",
            )

        assert resp["success"] is True
        call_kwargs = mock_engine.lookup.call_args
        assert call_kwargs.kwargs.get("library") == "python" or (
            call_kwargs.args and call_kwargs.args[0] == "python"
        )


class TestInputSanitization:
    """Question length and file_context sanitization."""

    async def test_question_length_5000_accepted(self) -> None:
        """A 5000-char question should not be truncated."""
        long_question = "How to do X? " * 385  # ~5005 chars, truncated to 5000
        result = _make_consultation_result()
        lookup_result = _make_lookup_result(success=False, content=None)
        settings = _settings_mock()

        mock_engine = AsyncMock()
        mock_engine.lookup = AsyncMock(return_value=lookup_result)
        mock_engine.close = AsyncMock()

        with (
            patch(
                "tapps_mcp.server_metrics_tools.load_settings", return_value=settings
            ),
            patch(
                "tapps_mcp.experts.engine.consult_expert", return_value=result
            ) as mock_consult,
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=MagicMock()),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
            patch(
                "tapps_mcp.server._record_call", return_value=None
            ),
            patch(
                "tapps_mcp.server._record_execution", return_value=None
            ),
            patch(
                "tapps_mcp.server._with_nudges",
                side_effect=lambda _name, resp: resp,
            ),
        ):
            from tapps_mcp.server_metrics_tools import tapps_research

            resp = await tapps_research(
                question=long_question,
                domain="security",
            )

        assert resp["success"] is True
        # The question passed to consult_expert should be up to 5000 chars
        called_question = mock_consult.call_args.kwargs.get(
            "question"
        ) or mock_consult.call_args.args[0]
        assert len(called_question) <= 5000
        assert len(called_question) > 2000  # Would have been truncated at 2000 before

    async def test_file_context_sanitized(self) -> None:
        """A file_context longer than 500 chars is truncated."""
        from tapps_mcp.server_metrics_tools import _sanitize_param

        long_ctx = "x" * 1000
        sanitized = _sanitize_param(long_ctx, max_len=500)
        assert len(sanitized) == 500

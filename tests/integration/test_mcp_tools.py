"""Integration test: MCP tool handlers end-to-end.

Tests the full MCP tool flow: tool call → validation → execution → response.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.server import (
    tapps_checklist,
    tapps_lookup_docs,
    tapps_quality_gate,
    tapps_score_file,
    tapps_security_scan,
    tapps_validate_config,
)
from tapps_mcp.tools.checklist import CallTracker
from tapps_mcp.tools.parallel import ParallelResults

SAMPLE_CODE = '"""Module."""\n\ndef f() -> int:\n    return 1\n'


@pytest.mark.integration
class TestMCPScoreFileTool:
    """End-to-end tests for tapps_score_file MCP tool."""

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / ".git").mkdir()
        f = tmp_path / "app.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    @pytest.mark.asyncio
    async def test_score_file_quick_response_shape(self, project: Path):
        """Quick mode returns well-formed response envelope."""
        with (
            patch("tapps_mcp.scoring.scorer.run_ruff_check", return_value=[]),
            patch("tapps_mcp.server._validate_file_path", return_value=project),
        ):
            result = await tapps_score_file(str(project), quick=True)

        assert result["tool"] == "tapps_score_file"
        assert result["success"] is True
        assert isinstance(result["elapsed_ms"], int)
        assert "data" in result
        assert "overall_score" in result["data"]
        assert "categories" in result["data"]
        assert "file_path" in result["data"]

    @pytest.mark.asyncio
    async def test_score_file_full_response_shape(self, project: Path):
        """Full mode returns well-formed response with degraded info."""
        parallel = ParallelResults()
        with (
            patch(
                "tapps_mcp.scoring.scorer.run_all_tools",
                new_callable=AsyncMock,
                return_value=parallel,
            ),
            patch("tapps_mcp.server._validate_file_path", return_value=project),
        ):
            result = await tapps_score_file(str(project))

        assert result["success"] is True
        assert "degraded" in result
        assert "lint_issue_count" in result["data"]
        assert "type_issue_count" in result["data"]
        assert "security_issue_count" in result["data"]

    @pytest.mark.asyncio
    async def test_score_file_path_denied(self):
        """Path outside project root is denied."""
        result = await tapps_score_file("/etc/passwd")
        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"


@pytest.mark.integration
class TestMCPSecurityScanTool:
    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        f = tmp_path / "app.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    def test_security_scan_response_shape(self, project: Path):
        """Security scan returns well-formed response."""
        with (
            patch("tapps_mcp.server._validate_file_path", return_value=project),
            patch("tapps_mcp.security.security_scanner._is_bandit_available", return_value=False),
        ):
            result = tapps_security_scan(str(project))

        assert result["tool"] == "tapps_security_scan"
        assert result["success"] is True
        assert "data" in result
        assert "passed" in result["data"]
        assert "total_issues" in result["data"]
        assert "bandit_available" in result["data"]

    def test_security_scan_path_denied(self):
        result = tapps_security_scan("/etc/shadow")
        assert result["success"] is False


@pytest.mark.integration
class TestMCPQualityGateTool:
    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / ".git").mkdir()
        f = tmp_path / "app.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    @pytest.mark.asyncio
    async def test_quality_gate_response_shape(self, project: Path):
        """Quality gate returns well-formed response."""
        parallel = ParallelResults(
            radon_cc=[{"name": "f", "complexity": 1}],
            radon_mi=90.0,
        )
        with (
            patch(
                "tapps_mcp.scoring.scorer.run_all_tools",
                new_callable=AsyncMock,
                return_value=parallel,
            ),
            patch("tapps_mcp.server._validate_file_path", return_value=project),
        ):
            result = await tapps_quality_gate(str(project))

        assert result["tool"] == "tapps_quality_gate"
        assert result["success"] is True
        assert "data" in result
        assert "passed" in result["data"]
        assert "preset" in result["data"]
        assert "scores" in result["data"]
        assert "thresholds" in result["data"]
        assert "failures" in result["data"]

    @pytest.mark.asyncio
    async def test_quality_gate_path_denied(self):
        result = await tapps_quality_gate("/etc/passwd")
        assert result["success"] is False


@pytest.mark.integration
class TestMCPChecklistTool:
    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_checklist_response_shape(self):
        """Checklist returns well-formed response."""
        result = await tapps_checklist("review")
        assert result["tool"] == "tapps_checklist"
        assert result["success"] is True
        data = result["data"]
        assert "task_type" in data
        assert "called" in data
        assert "missing_required" in data
        assert "missing_required_hints" in data
        assert "complete" in data
        assert "total_calls" in data
        # Hints are lists of { tool, reason }
        for hint in data.get("missing_required_hints", []):
            assert "tool" in hint
            assert "reason" in hint

    @pytest.mark.asyncio
    async def test_checklist_tracks_session(self):
        """Checklist tracks calls across a session."""
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")

        result = await tapps_checklist("review")
        data = result["data"]
        assert data["complete"] is True
        # tapps_checklist itself is recorded by the tool
        assert "tapps_checklist" in data["called"]

    @pytest.mark.asyncio
    async def test_checklist_different_task_types(self):
        """Different task types have different requirements."""
        feature_result = await tapps_checklist("feature")
        security_result = await tapps_checklist("security")

        feat_req = feature_result["data"]["missing_required"]
        sec_req = security_result["data"]["missing_required"]

        # Feature needs score_file + quality_gate
        assert "tapps_score_file" in feat_req
        # Security needs security_scan + quality_gate
        assert "tapps_security_scan" in sec_req


@pytest.mark.integration
class TestMCPLookupDocsTool:
    """End-to-end tests for tapps_lookup_docs MCP tool."""

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_lookup_cache_hit_response_shape(self, tmp_path: Path):
        """Lookup with cached content returns well-formed response."""
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.lookup import LookupEngine
        from tapps_mcp.knowledge.models import CacheEntry

        cache = KBCache(cache_dir=tmp_path / "cache")
        cache.put(CacheEntry(library="fastapi", topic="overview", content="# FastAPI"))

        # Pre-compute the expected result using a real engine
        engine = LookupEngine(cache)
        result_obj = await engine.lookup("fastapi")
        await engine.close()

        # Now call the MCP tool handler with mocked internals
        mock_engine = AsyncMock()
        mock_engine.lookup.return_value = result_obj

        with (
            patch("tapps_mcp.server.load_settings") as mock_settings,
            patch("tapps_mcp.knowledge.cache.KBCache", return_value=cache),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.context7_api_key = None

            result = await tapps_lookup_docs("fastapi")

        assert result["tool"] == "tapps_lookup_docs"
        assert result["success"] is True
        assert isinstance(result["elapsed_ms"], int)
        assert "data" in result
        assert "library" in result["data"]
        assert "source" in result["data"]
        assert "cache_hit" in result["data"]

    @pytest.mark.asyncio
    async def test_lookup_no_api_key_response(self, tmp_path: Path):
        """Lookup without API key and no cache returns error response."""
        from tapps_mcp.knowledge.models import LookupResult

        error_result = LookupResult(
            success=False,
            library="unknown-lib",
            topic="overview",
            error="No Context7 API key configured. Cache miss.",
        )

        mock_engine = AsyncMock()
        mock_engine.lookup.return_value = error_result

        with (
            patch("tapps_mcp.server.load_settings") as mock_settings,
            patch("tapps_mcp.knowledge.cache.KBCache"),
            patch("tapps_mcp.knowledge.lookup.LookupEngine", return_value=mock_engine),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.context7_api_key = None

            result = await tapps_lookup_docs("unknown-lib")

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "api_key_missing"


@pytest.mark.integration
class TestMCPValidateConfigTool:
    """End-to-end tests for tapps_validate_config MCP tool."""

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        CallTracker.reset()
        yield
        CallTracker.reset()

    @pytest.fixture
    def dockerfile(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / ".git").mkdir()
        f = tmp_path / "Dockerfile"
        f.write_text("FROM python:3.12\nCOPY . /app\n", encoding="utf-8")
        return f

    def test_validate_config_response_shape(self, dockerfile: Path):
        """Validate config returns well-formed response."""
        with patch("tapps_mcp.server._validate_file_path", return_value=dockerfile):
            result = tapps_validate_config(str(dockerfile))

        assert result["tool"] == "tapps_validate_config"
        assert result["success"] is True
        assert isinstance(result["elapsed_ms"], int)
        data = result["data"]
        assert "file_path" in data
        assert "config_type" in data
        assert data["config_type"] == "dockerfile"
        assert "valid" in data
        assert "findings" in data
        assert "suggestions" in data
        assert "finding_count" in data
        assert "critical_count" in data
        assert "warning_count" in data

    def test_validate_config_path_denied(self):
        """Path outside project root is denied."""
        result = tapps_validate_config("/etc/passwd")
        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    def test_validate_config_explicit_type(self, dockerfile: Path):
        """Explicit config_type overrides auto-detection."""
        with patch("tapps_mcp.server._validate_file_path", return_value=dockerfile):
            result = tapps_validate_config(str(dockerfile), config_type="dockerfile")

        assert result["data"]["config_type"] == "dockerfile"

    def test_validate_config_findings_populated(self, dockerfile: Path):
        """Dockerfile with issues produces findings."""
        with patch("tapps_mcp.server._validate_file_path", return_value=dockerfile):
            result = tapps_validate_config(str(dockerfile))

        data = result["data"]
        # Dockerfile missing USER and HEALTHCHECK should have suggestions
        assert len(data["suggestions"]) > 0

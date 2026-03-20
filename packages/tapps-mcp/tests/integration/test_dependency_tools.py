"""Integration tests for tapps_dependency_scan and tapps_dependency_graph MCP handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker
from tapps_mcp.tools.dependency_scan_cache import (
    clear_dependency_cache,
    get_dependency_findings,
    set_dependency_findings,
)
from tapps_mcp.tools.pip_audit import DependencyAuditResult, VulnerabilityFinding


def _sample_audit_result(
    *,
    findings: list[VulnerabilityFinding] | None = None,
    error: str | None = None,
) -> DependencyAuditResult:
    if findings is None:
        findings = [
            VulnerabilityFinding(
                package="requests",
                installed_version="2.28.0",
                fixed_version="2.31.0",
                vulnerability_id="CVE-2024-12345",
                severity="high",
            ),
        ]
    return DependencyAuditResult(
        findings=findings,
        scanned_packages=10,
        vulnerable_packages=len({f.package for f in findings}),
        scan_source="environment",
        error=error,
    )


@pytest.mark.integration
@pytest.mark.slow
class TestDependencyScanTool:
    """End-to-end tests for tapps_dependency_scan MCP tool."""

    @pytest.fixture(autouse=True)
    def reset(self):
        CallTracker.reset()
        clear_dependency_cache()
        yield
        CallTracker.reset()
        clear_dependency_cache()

    @pytest.mark.asyncio
    async def test_response_shape(self):
        """Response has correct envelope structure."""
        from tapps_mcp.server import tapps_dependency_scan

        mock_result = _sample_audit_result()

        with patch(
            "tapps_mcp.tools.pip_audit.run_pip_audit_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await tapps_dependency_scan()

        assert result["tool"] == "tapps_dependency_scan"
        assert result["success"] is True
        assert isinstance(result["elapsed_ms"], int)
        data = result["data"]
        assert "scanned_packages" in data
        assert "total_findings" in data
        assert "by_severity" in data
        assert "severity_counts" in data
        assert "summary" in data

    @pytest.mark.asyncio
    async def test_cache_populated(self):
        """Successful scan populates the dependency scan cache."""
        from tapps_mcp.server import tapps_dependency_scan

        mock_result = _sample_audit_result()

        with patch(
            "tapps_mcp.tools.pip_audit.run_pip_audit_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await tapps_dependency_scan()

        # Cache should now have the findings
        from tapps_mcp.config.settings import load_settings

        settings = load_settings()
        cached = get_dependency_findings(str(settings.project_root))
        assert len(cached) == 1
        assert cached[0].package == "requests"

    @pytest.mark.asyncio
    async def test_error_does_not_populate_cache(self):
        """Scan with error does not populate cache."""
        from tapps_mcp.server import tapps_dependency_scan

        mock_result = _sample_audit_result(
            findings=[],
            error="pip-audit not installed",
        )

        with patch(
            "tapps_mcp.tools.pip_audit.run_pip_audit_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await tapps_dependency_scan()

        assert "error" in result["data"]

        from tapps_mcp.config.settings import load_settings

        settings = load_settings()
        cached = get_dependency_findings(str(settings.project_root))
        assert cached == []

    @pytest.mark.asyncio
    async def test_disabled_returns_early(self):
        """When dependency_scan_enabled=False, tool returns without running."""
        from tapps_mcp.server import tapps_dependency_scan

        with patch("tapps_mcp.server_analysis_tools.load_settings") as mock_load:
            settings = mock_load.return_value
            settings.dependency_scan_enabled = False

            result = await tapps_dependency_scan()

        data = result["data"]
        assert data["scan_source"] == "disabled"
        assert data["total_findings"] == 0

    @pytest.mark.asyncio
    async def test_source_setting_passed(self):
        """The dependency_scan_source setting is forwarded to pip-audit."""
        from tapps_mcp.server import tapps_dependency_scan

        mock_audit = AsyncMock(return_value=_sample_audit_result())

        with (
            patch("tapps_mcp.tools.pip_audit.run_pip_audit_async", mock_audit),
            patch("tapps_mcp.server_analysis_tools.load_settings") as mock_load,
        ):
            settings = mock_load.return_value
            settings.dependency_scan_enabled = True
            settings.dependency_scan_source = "requirements"
            settings.dependency_scan_severity_threshold = "medium"
            settings.dependency_scan_ignore_ids = []
            settings.project_root = Path("/fake")

            await tapps_dependency_scan()

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs.kwargs.get("source") == "requirements"


@pytest.mark.integration
@pytest.mark.slow
class TestDependencyGraphTool:
    """End-to-end tests for tapps_dependency_graph MCP tool."""

    @pytest.fixture(autouse=True)
    def reset(self):
        CallTracker.reset()
        clear_dependency_cache()
        yield
        CallTracker.reset()
        clear_dependency_cache()

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        """Create a minimal Python project for graph analysis."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("from mypkg.b import helper\n")
        (pkg / "b.py").write_text("def helper(): pass\n")
        return tmp_path

    @pytest.mark.asyncio
    async def test_response_shape(self, project: Path):
        """Graph tool returns well-formed response envelope."""
        from tapps_mcp.server import tapps_dependency_graph

        result = await tapps_dependency_graph(project_root=str(project))

        assert result["tool"] == "tapps_dependency_graph"
        assert result["success"] is True
        data = result["data"]
        assert "total_modules" in data
        assert "total_edges" in data
        assert "cycles" in data
        assert "coupling" in data

    @pytest.mark.asyncio
    async def test_cycles_detected(self, tmp_path: Path):
        """Circular imports are detected and reported."""
        from tapps_mcp.server import tapps_dependency_graph

        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("from mypkg.b import X\n")
        (pkg / "b.py").write_text("from mypkg.a import Y\n")

        result = await tapps_dependency_graph(project_root=str(tmp_path))
        data = result["data"]

        assert data["cycles"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_cross_tool_integration_with_cache(self, project: Path):
        """When dep scan cache has findings and graph has external imports,
        vulnerability_impact is included."""
        from tapps_mcp.server import tapps_dependency_graph

        # Write a file that imports an external package
        pkg = project / "mypkg"
        (pkg / "c.py").write_text("import requests\n")

        # Pre-populate the cache with a vulnerability for 'requests'
        set_dependency_findings(
            str(project),
            [
                VulnerabilityFinding(
                    package="requests",
                    installed_version="2.28.0",
                    fixed_version="2.31.0",
                    vulnerability_id="CVE-2024-12345",
                    severity="high",
                ),
            ],
        )

        result = await tapps_dependency_graph(project_root=str(project))
        data = result["data"]

        assert "vulnerability_impact" in data
        assert data["vulnerability_impact"]["total_vulnerable_imports"] >= 1

    @pytest.mark.asyncio
    async def test_no_vulnerability_impact_without_cache(self, project: Path):
        """Without cached findings, vulnerability_impact is absent."""
        from tapps_mcp.server import tapps_dependency_graph

        result = await tapps_dependency_graph(project_root=str(project))
        data = result["data"]

        assert "vulnerability_impact" not in data

    @pytest.mark.asyncio
    async def test_without_cycles(self, project: Path):
        """Can disable cycle detection."""
        from tapps_mcp.server import tapps_dependency_graph

        result = await tapps_dependency_graph(
            project_root=str(project), detect_cycles=False
        )
        data = result["data"]

        assert "cycles" not in data
        assert "coupling" in data

    @pytest.mark.asyncio
    async def test_without_coupling(self, project: Path):
        """Can disable coupling analysis."""
        from tapps_mcp.server import tapps_dependency_graph

        result = await tapps_dependency_graph(
            project_root=str(project), include_coupling=False
        )
        data = result["data"]

        assert "coupling" not in data
        assert "cycles" in data

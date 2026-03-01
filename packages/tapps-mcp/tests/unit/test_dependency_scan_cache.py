"""Tests for the dependency scan session cache."""

from __future__ import annotations

from unittest.mock import patch

from tapps_mcp.tools.dependency_scan_cache import (
    clear_dependency_cache,
    get_dependency_findings,
    set_dependency_findings,
)
from tapps_mcp.tools.pip_audit import VulnerabilityFinding


def _make_finding(
    package: str = "requests",
    severity: str = "high",
) -> VulnerabilityFinding:
    return VulnerabilityFinding(
        package=package,
        installed_version="2.28.0",
        fixed_version="2.31.0",
        vulnerability_id="CVE-2024-12345",
        severity=severity,
    )


class TestSetAndGetDependencyFindings:
    def test_round_trip(self):
        """Stored findings are retrievable."""
        findings = [_make_finding()]
        set_dependency_findings("/project", findings)

        result = get_dependency_findings("/project")
        assert len(result) == 1
        assert result[0].package == "requests"

    def test_empty_findings_stored(self):
        """Empty list is distinct from 'no entry'."""
        set_dependency_findings("/project", [])
        result = get_dependency_findings("/project")
        assert result == []

    def test_different_projects_isolated(self):
        """Findings for different project roots are independent."""
        set_dependency_findings("/project-a", [_make_finding("pkg-a")])
        set_dependency_findings("/project-b", [_make_finding("pkg-b")])

        a = get_dependency_findings("/project-a")
        b = get_dependency_findings("/project-b")
        assert len(a) == 1
        assert a[0].package == "pkg-a"
        assert len(b) == 1
        assert b[0].package == "pkg-b"

    def test_missing_project_returns_empty(self):
        """Querying an unknown project root returns empty list."""
        result = get_dependency_findings("/nonexistent")
        assert result == []


class TestTTLExpiry:
    def test_fresh_entry_returned(self):
        """Entry within TTL is returned."""
        set_dependency_findings("/project", [_make_finding()])
        result = get_dependency_findings("/project", ttl=300)
        assert len(result) == 1

    def test_expired_entry_returns_empty(self):
        """Entry past TTL is evicted and returns empty."""
        set_dependency_findings("/project", [_make_finding()])

        # Simulate time passing beyond TTL
        with patch("tapps_mcp.tools.dependency_scan_cache.time") as mock_time:
            mock_time.monotonic.return_value = 99999999.0
            result = get_dependency_findings("/project", ttl=300)

        assert result == []


class TestClearDependencyCache:
    def test_clear_specific_project(self):
        """Clearing one project leaves others intact."""
        set_dependency_findings("/project-a", [_make_finding("a")])
        set_dependency_findings("/project-b", [_make_finding("b")])

        clear_dependency_cache("/project-a")

        assert get_dependency_findings("/project-a") == []
        assert len(get_dependency_findings("/project-b")) == 1

    def test_clear_all(self):
        """Clearing without project root empties entire cache."""
        set_dependency_findings("/project-a", [_make_finding("a")])
        set_dependency_findings("/project-b", [_make_finding("b")])

        clear_dependency_cache()

        assert get_dependency_findings("/project-a") == []
        assert get_dependency_findings("/project-b") == []

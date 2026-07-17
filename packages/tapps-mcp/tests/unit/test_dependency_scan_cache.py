"""Tests for the dependency scan session cache."""

from __future__ import annotations

import threading
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

    def test_missing_project_returns_none(self):
        """Querying an unknown project root returns None (cache miss)."""
        result = get_dependency_findings("/nonexistent")
        assert result is None

    def test_empty_hit_distinct_from_miss(self):
        """Cached empty list is a hit; unknown project is a miss."""
        set_dependency_findings("/clean-project", [])
        assert get_dependency_findings("/clean-project") == []
        assert get_dependency_findings("/never-scanned") is None

    def test_get_returns_copy(self):
        """Mutating the returned list must not corrupt the cache."""
        set_dependency_findings("/project", [_make_finding()])
        result = get_dependency_findings("/project")
        assert result is not None
        result.clear()
        assert len(get_dependency_findings("/project") or []) == 1


class TestTTLExpiry:
    def test_fresh_entry_returned(self):
        """Entry within TTL is returned."""
        set_dependency_findings("/project", [_make_finding()])
        result = get_dependency_findings("/project", ttl=300)
        assert len(result) == 1

    def test_expired_entry_returns_empty(self):
        """Entry past TTL is evicted and returns None (miss)."""
        set_dependency_findings("/project", [_make_finding()])

        # Simulate time passing beyond TTL
        with patch("tapps_mcp.tools.dependency_scan_cache.time") as mock_time:
            mock_time.monotonic.return_value = 99999999.0
            result = get_dependency_findings("/project", ttl=300)

        assert result is None


    def test_concurrent_expiry_no_exception(self) -> None:
        """Two concurrent reads on an expired entry never raise KeyError (TAP-1745).

        Regression test for the check-then-del race: the first coroutine that
        detects expiry should evict the key atomically so a concurrent second
        reader finds nothing rather than raising KeyError.
        """
        from tapps_mcp.tools.dependency_scan_cache import _cache as dep_cache

        # Plant an already-expired entry (ts=0.0 is always past any ttl > 0).
        dep_cache["/race-test"] = ([], 0.0)

        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def _reader() -> None:
            barrier.wait()  # maximise overlap between the two reads
            try:
                get_dependency_findings("/race-test", ttl=1)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_reader) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not any(t.is_alive() for t in threads), "Threads did not complete"
        assert errors == [], f"Concurrent expiry raised exceptions: {errors}"


class TestClearDependencyCache:
    def test_clear_specific_project(self):
        """Clearing one project leaves others intact."""
        set_dependency_findings("/project-a", [_make_finding("a")])
        set_dependency_findings("/project-b", [_make_finding("b")])

        clear_dependency_cache("/project-a")

        assert get_dependency_findings("/project-a") is None
        assert len(get_dependency_findings("/project-b") or []) == 1

    def test_clear_all(self):
        """Clearing without project root empties entire cache."""
        set_dependency_findings("/project-a", [_make_finding("a")])
        set_dependency_findings("/project-b", [_make_finding("b")])

        clear_dependency_cache()

        assert get_dependency_findings("/project-a") is None
        assert get_dependency_findings("/project-b") is None

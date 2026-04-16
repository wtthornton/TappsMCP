"""Tests for memory contradiction detection (Epic 24.3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tapps_mcp.memory.contradictions import ContradictionDetector
from tapps_mcp.memory.models import MemoryEntry, MemoryScope, MemorySource, MemoryTier
from tapps_mcp.project.models import ProjectProfile, TechStack


def _make_entry(
    *,
    key: str = "test-key",
    value: str = "test value",
    tags: list[str] | None = None,
    tier: MemoryTier = MemoryTier.pattern,
    scope: MemoryScope = MemoryScope.project,
    branch: str | None = None,
) -> MemoryEntry:
    """Helper to create a MemoryEntry for testing."""
    return MemoryEntry(
        key=key,
        value=value,
        tier=tier,
        source=MemorySource.agent,
        tags=tags or [],
        scope=scope,
        branch=branch,
    )


def _make_profile(
    *,
    libraries: list[str] | None = None,
    frameworks: list[str] | None = None,
    test_frameworks: list[str] | None = None,
    package_managers: list[str] | None = None,
) -> ProjectProfile:
    """Helper to create a ProjectProfile for testing."""
    return ProjectProfile(
        tech_stack=TechStack(
            languages=["python"],
            libraries=libraries or ["ruff", "mypy", "pydantic"],
            frameworks=frameworks or ["fastapi"],
        ),
        test_frameworks=test_frameworks or ["pytest"],
        package_managers=package_managers or ["uv"],
    )


class TestTechStackDrift:
    def test_detects_unknown_library(self, tmp_path: Path) -> None:
        """Memory claiming a library not in the tech stack is flagged."""
        entry = _make_entry(
            value="We use sqlalchemy for database access.",
            tags=["library", "database"],
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 1
        assert "sqlalchemy" in results[0].reason

    def test_no_contradiction_when_library_present(self, tmp_path: Path) -> None:
        """Memory mentioning a known library is NOT flagged."""
        entry = _make_entry(
            value="We use pydantic for validation.",
            tags=["library"],
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0

    def test_no_flag_without_tech_tags(self, tmp_path: Path) -> None:
        """Memory without tech-related tags is not checked for tech drift."""
        entry = _make_entry(
            value="We use sqlalchemy for database access.",
            tags=["note"],
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0


class TestFileExistence:
    def test_detects_missing_file(self, tmp_path: Path) -> None:
        """Memory referencing a non-existent file is flagged."""
        entry = _make_entry(
            value="The config lives at config/settings.yaml",
            tags=["file", "config"],
        )
        detector = ContradictionDetector(tmp_path)
        profile = _make_profile()

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 1
        assert "settings.yaml" in results[0].reason

    def test_no_flag_for_existing_file(self, tmp_path: Path) -> None:
        """Memory referencing an existing file is NOT flagged."""
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.yaml").write_text("key: value")

        entry = _make_entry(
            value="The config lives at config/settings.yaml",
            tags=["file"],
        )
        detector = ContradictionDetector(tmp_path)
        profile = _make_profile()

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0

    def test_no_flag_without_file_tags(self, tmp_path: Path) -> None:
        """Memory without file-related tags is not checked for file existence."""
        entry = _make_entry(
            value="Look at nonexistent/file.py for details.",
            tags=["note"],
        )
        detector = ContradictionDetector(tmp_path)
        profile = _make_profile()

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0


class TestTestFrameworkDrift:
    def test_detects_wrong_test_framework(self, tmp_path: Path) -> None:
        """Memory mentioning a test framework not in the project is flagged."""
        entry = _make_entry(
            value="We run tests with jest.",
            tags=["test"],
        )
        profile = _make_profile(test_frameworks=["pytest"])
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 1
        assert "jest" in results[0].reason

    def test_no_flag_for_correct_framework(self, tmp_path: Path) -> None:
        """Memory mentioning the correct test framework is NOT flagged."""
        entry = _make_entry(
            value="We run tests with pytest.",
            tags=["test"],
        )
        profile = _make_profile(test_frameworks=["pytest"])
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0


class TestPackageManagerDrift:
    def test_detects_wrong_package_manager(self, tmp_path: Path) -> None:
        """Memory mentioning wrong package manager is flagged."""
        entry = _make_entry(
            value="Install deps with poetry.",
            tags=["package-manager"],
        )
        profile = _make_profile(package_managers=["uv"])
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 1
        assert "poetry" in results[0].reason

    def test_no_flag_for_correct_manager(self, tmp_path: Path) -> None:
        """Memory mentioning the correct package manager is NOT flagged."""
        entry = _make_entry(
            value="Install deps with uv.",
            tags=["package-manager"],
        )
        profile = _make_profile(package_managers=["uv"])
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0


class TestBranchExistence:
    def test_detects_deleted_branch(self, tmp_path: Path) -> None:
        """Memory scoped to a deleted branch is flagged."""
        entry = _make_entry(
            value="Feature work on this branch.",
            tags=["branch"],
            scope=MemoryScope.branch,
            branch="feature/deleted-branch",
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "  main\n  develop\n"
            mock_run.return_value.stderr = ""
            results = detector.detect_contradictions([entry], profile)

        assert len(results) == 1
        assert "feature/deleted-branch" in results[0].reason

    def test_no_flag_for_existing_branch(self, tmp_path: Path) -> None:
        """Memory scoped to an existing branch is NOT flagged."""
        entry = _make_entry(
            value="Feature work on this branch.",
            tags=["branch"],
            scope=MemoryScope.branch,
            branch="main",
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "  main\n  develop\n"
            mock_run.return_value.stderr = ""
            results = detector.detect_contradictions([entry], profile)

        assert len(results) == 0

    def test_no_flag_without_branch(self, tmp_path: Path) -> None:
        """Memory without a branch field is not checked for branch existence."""
        entry = _make_entry(
            value="Some branch info.",
            tags=["branch"],
        )
        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 0


class TestIdempotency:
    def test_already_contradicted_memory_still_detected(self, tmp_path: Path) -> None:
        """A previously contradicted memory is still returned by detection.

        The caller (store integration) handles idempotent confidence halving.
        """
        entry = _make_entry(
            value="We use sqlalchemy for ORM.",
            tags=["library"],
        )
        # Simulate already contradicted
        object.__setattr__(entry, "contradicted", True)
        object.__setattr__(entry, "contradiction_reason", "previously detected")

        profile = _make_profile()
        detector = ContradictionDetector(tmp_path)

        results = detector.detect_contradictions([entry], profile)
        assert len(results) == 1

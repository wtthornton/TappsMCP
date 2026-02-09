"""Project profiler - combines tech-stack, type, and environment detection.

This is the main entry point for Story 4.1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.project.models import ProjectProfile
from tapps_mcp.project.tech_stack import TechStackDetector
from tapps_mcp.project.type_detector import detect_project_type

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# CI detection
# ---------------------------------------------------------------------------

_CI_SIGNALS: dict[str, list[str]] = {
    "github-actions": [".github/workflows"],
    "gitlab-ci": [".gitlab-ci.yml"],
    "jenkins": ["Jenkinsfile"],
    "circleci": [".circleci"],
    "travis": [".travis.yml"],
    "azure-pipelines": ["azure-pipelines.yml"],
}


def _detect_ci(root: Path) -> list[str]:
    found: list[str] = []
    for name, paths in _CI_SIGNALS.items():
        if any((root / p).exists() for p in paths):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Test framework detection
# ---------------------------------------------------------------------------

_TEST_SIGNALS: dict[str, list[str]] = {
    "pytest": ["pytest.ini", "pyproject.toml", "conftest.py", "tests"],
    "jest": ["jest.config.js", "jest.config.ts"],
    "mocha": [".mocharc.yml", ".mocharc.json"],
    "go-test": ["go.mod"],
    "cargo-test": ["Cargo.toml"],
}


def _detect_test_frameworks(root: Path) -> list[str]:
    found: list[str] = []
    for name, paths in _TEST_SIGNALS.items():
        if any((root / p).exists() for p in paths):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Package-manager detection
# ---------------------------------------------------------------------------

_PM_SIGNALS: dict[str, list[str]] = {
    "uv": ["uv.lock"],
    "pip": ["requirements.txt"],
    "poetry": ["poetry.lock"],
    "npm": ["package-lock.json"],
    "yarn": ["yarn.lock"],
    "pnpm": ["pnpm-lock.yaml"],
    "cargo": ["Cargo.lock"],
    "go-mod": ["go.sum"],
}


def _detect_package_managers(root: Path) -> list[str]:
    found: list[str] = []
    for name, paths in _PM_SIGNALS.items():
        if any((root / p).exists() for p in paths):
            found.append(name)
    # Fallback: if pyproject.toml exists but no lock file detected, assume pip
    if not found and (root / "pyproject.toml").exists():
        found.append("pip")
    return found


# ---------------------------------------------------------------------------
# Quality recommendations
# ---------------------------------------------------------------------------


def _quality_recommendations(profile: ProjectProfile) -> list[str]:
    recs: list[str] = []

    if not profile.has_ci:
        recs.append("Add CI/CD pipeline (e.g. GitHub Actions) for automated testing.")
    if not profile.has_docker and profile.project_type in (
        "api-service", "microservice", "web-app",
    ):
        recs.append("Add Dockerfile for consistent deployment environments.")
    if not profile.has_tests:
        recs.append("Add a test suite (pytest for Python, jest for JS/TS).")
    if "python" in profile.tech_stack.languages:
        if "ruff" not in profile.tech_stack.libraries:
            recs.append("Add ruff for fast Python linting.")
        if "mypy" not in profile.tech_stack.libraries:
            recs.append("Add mypy for type checking.")
    if profile.project_type == "library" and not profile.package_managers:
        recs.append("Publish via PyPI or npm for discoverability.")

    return recs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_project_profile(project_root: Path) -> ProjectProfile:
    """Detect a comprehensive :class:`ProjectProfile` for *project_root*.

    Combines tech-stack detection, project type detection, CI/Docker/test
    signals, and quality recommendations.
    """
    logger.info("profile_detection_start", project_root=str(project_root))

    # Tech stack
    detector = TechStackDetector(project_root)
    tech_stack = detector.detect_all()

    # Project type
    ptype, pconf, preason = detect_project_type(project_root)

    # Signals
    ci_systems = _detect_ci(project_root)
    test_fws = _detect_test_frameworks(project_root)
    pkg_mgrs = _detect_package_managers(project_root)
    has_docker = (project_root / "Dockerfile").exists() or (
        project_root / "docker-compose.yml"
    ).exists()

    profile = ProjectProfile(
        tech_stack=tech_stack,
        project_type=ptype,
        project_type_confidence=pconf,
        project_type_reason=preason,
        has_ci=bool(ci_systems),
        ci_systems=ci_systems,
        has_docker=has_docker,
        has_tests=bool(test_fws),
        test_frameworks=test_fws,
        package_managers=pkg_mgrs,
    )

    profile.quality_recommendations = _quality_recommendations(profile)

    logger.info(
        "profile_detection_complete",
        project_type=ptype,
        languages=tech_stack.languages,
        frameworks=tech_stack.frameworks,
    )

    return profile

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


def _detect_signals(root: Path, signals: dict[str, list[str]]) -> list[str]:
    """Detect which signal groups are present under *root*."""
    return [name for name, paths in signals.items() if any((root / p).exists() for p in paths)]


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


# ---------------------------------------------------------------------------
# Quality recommendations
# ---------------------------------------------------------------------------


def _quality_recommendations(profile: ProjectProfile) -> list[str]:
    is_python = "python" in profile.tech_stack.languages
    checks: list[tuple[bool, str]] = [
        (not profile.has_ci, "Add CI/CD pipeline (e.g. GitHub Actions) for automated testing."),
        (
            not profile.has_docker
            and profile.project_type in ("api-service", "microservice", "web-app"),
            "Add Dockerfile for consistent deployment environments.",
        ),
        (not profile.has_tests, "Add a test suite (pytest for Python, jest for JS/TS)."),
        (
            is_python and "ruff" not in profile.tech_stack.libraries,
            "Add ruff for fast Python linting.",
        ),
        (
            is_python and "mypy" not in profile.tech_stack.libraries,
            "Add mypy for type checking.",
        ),
        (
            profile.project_type == "library" and not profile.package_managers,
            "Publish via PyPI or npm for discoverability.",
        ),
    ]
    return [rec for condition, rec in checks if condition]


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
    ci_systems = _detect_signals(project_root, _CI_SIGNALS)
    test_fws = _detect_signals(project_root, _TEST_SIGNALS)
    pkg_mgrs = _detect_signals(project_root, _PM_SIGNALS)
    if not pkg_mgrs and (project_root / "pyproject.toml").exists():
        pkg_mgrs.append("pip")
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

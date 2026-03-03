"""Tests for docs_mcp.integrations.tapps -- TappsMCP integration layer.

Covers:
- Model defaults and full construction (TappsQualityScore, TappsProjectProfile,
  TappsDependencyData, TappsEnrichment)
- TappsIntegration.is_available property
- load_enrichment (valid export, missing dir, missing file, malformed JSON,
  version mismatch, partial data, dependency data)
- load_project_profile (valid, missing dir, missing key)
- load_quality_scores (valid, missing dir)
- generate_quality_badge (high/medium/low colour thresholds, boundary values)
- generate_gate_badge (pass/fail)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from docs_mcp.integrations.tapps import (
    TappsDependencyData,
    TappsEnrichment,
    TappsIntegration,
    TappsProjectProfile,
    TappsQualityScore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_EXPORT: dict[str, Any] = {
    "version": "1.0",
    "quality_scores": [
        {
            "file_path": "src/app.py",
            "overall_score": 85.0,
            "category_scores": {"security": 90},
        },
        {
            "file_path": "src/utils.py",
            "overall_score": 55.0,
            "category_scores": {},
        },
    ],
    "project_profile": {
        "project_type": "python-library",
        "tech_stack": {"language": "python"},
        "has_ci": True,
        "test_frameworks": ["pytest"],
        "package_managers": ["uv"],
    },
    "dependency_data": {
        "total_modules": 10,
        "total_edges": 15,
        "cycles": [],
        "coupling": [],
    },
    "overall_project_score": 72.5,
}


def _write_export(root: Path, data: dict[str, Any]) -> Path:
    """Write a docsmcp-export.json under root/.tapps-mcp/."""
    tapps_dir = root / ".tapps-mcp"
    tapps_dir.mkdir(parents=True, exist_ok=True)
    export_path = tapps_dir / "docsmcp-export.json"
    export_path.write_text(json.dumps(data), encoding="utf-8")
    return export_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tapps_project(tmp_path: Path) -> Path:
    """Create a project with a valid .tapps-mcp/docsmcp-export.json."""
    root = tmp_path / "project"
    root.mkdir()
    _write_export(root, _VALID_EXPORT)
    return root


@pytest.fixture()
def bare_project(tmp_path: Path) -> Path:
    """Create a project with no .tapps-mcp directory."""
    root = tmp_path / "bare"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# TestTappsQualityScoreModel
# ---------------------------------------------------------------------------


class TestTappsQualityScoreModel:
    """TappsQualityScore Pydantic model defaults and construction."""

    def test_defaults(self) -> None:
        score = TappsQualityScore(file_path="src/app.py", overall_score=80.0)
        assert score.file_path == "src/app.py"
        assert score.overall_score == 80.0
        assert score.category_scores == {}

    def test_full_construction(self) -> None:
        score = TappsQualityScore(
            file_path="src/main.py",
            overall_score=92.5,
            category_scores={"security": 95.0, "complexity": 88.0},
        )
        assert score.file_path == "src/main.py"
        assert score.overall_score == 92.5
        assert score.category_scores["security"] == 95.0
        assert score.category_scores["complexity"] == 88.0


# ---------------------------------------------------------------------------
# TestTappsProjectProfileModel
# ---------------------------------------------------------------------------


class TestTappsProjectProfileModel:
    """TappsProjectProfile Pydantic model defaults and construction."""

    def test_defaults(self) -> None:
        profile = TappsProjectProfile()
        assert profile.project_type == ""
        assert profile.tech_stack == {}
        assert profile.has_ci is False
        assert profile.ci_systems == []
        assert profile.has_docker is False
        assert profile.has_tests is False
        assert profile.test_frameworks == []
        assert profile.package_managers == []

    def test_full_construction(self) -> None:
        profile = TappsProjectProfile(
            project_type="python-library",
            tech_stack={"language": "python"},
            has_ci=True,
            ci_systems=["github_actions"],
            has_docker=True,
            has_tests=True,
            test_frameworks=["pytest", "unittest"],
            package_managers=["uv", "pip"],
        )
        assert profile.project_type == "python-library"
        assert profile.has_ci is True
        assert profile.has_docker is True
        assert profile.has_tests is True
        assert "github_actions" in profile.ci_systems
        assert "pytest" in profile.test_frameworks
        assert "uv" in profile.package_managers


# ---------------------------------------------------------------------------
# TestTappsDependencyDataModel
# ---------------------------------------------------------------------------


class TestTappsDependencyDataModel:
    """TappsDependencyData Pydantic model defaults and construction."""

    def test_defaults(self) -> None:
        dep = TappsDependencyData()
        assert dep.total_modules == 0
        assert dep.total_edges == 0
        assert dep.cycles == []
        assert dep.coupling == []

    def test_full_construction(self) -> None:
        dep = TappsDependencyData(
            total_modules=10,
            total_edges=15,
            cycles=[["a.py", "b.py", "a.py"]],
            coupling=[{"module": "a.py", "afferent": 3}],
        )
        assert dep.total_modules == 10
        assert dep.total_edges == 15
        assert len(dep.cycles) == 1
        assert dep.cycles[0] == ["a.py", "b.py", "a.py"]
        assert dep.coupling[0]["module"] == "a.py"


# ---------------------------------------------------------------------------
# TestTappsEnrichmentModel
# ---------------------------------------------------------------------------


class TestTappsEnrichmentModel:
    """TappsEnrichment Pydantic model defaults and construction."""

    def test_defaults(self) -> None:
        enrichment = TappsEnrichment()
        assert enrichment.available is False
        assert enrichment.quality_scores == []
        assert enrichment.project_profile is None
        assert enrichment.dependency_data is None
        assert enrichment.overall_project_score is None

    def test_full_construction(self) -> None:
        enrichment = TappsEnrichment(
            available=True,
            quality_scores=[
                TappsQualityScore(file_path="a.py", overall_score=80.0),
            ],
            project_profile=TappsProjectProfile(project_type="app"),
            dependency_data=TappsDependencyData(total_modules=5),
            overall_project_score=78.0,
        )
        assert enrichment.available is True
        assert len(enrichment.quality_scores) == 1
        assert enrichment.project_profile is not None
        assert enrichment.project_profile.project_type == "app"
        assert enrichment.dependency_data is not None
        assert enrichment.dependency_data.total_modules == 5
        assert enrichment.overall_project_score == 78.0


# ---------------------------------------------------------------------------
# TestTappsAvailability
# ---------------------------------------------------------------------------


class TestTappsAvailability:
    """is_available property detects .tapps-mcp directory."""

    def test_not_available_when_no_dir(self, bare_project: Path) -> None:
        integration = TappsIntegration(bare_project)
        assert integration.is_available is False

    def test_available_when_dir_exists(self, tapps_project: Path) -> None:
        integration = TappsIntegration(tapps_project)
        assert integration.is_available is True


# ---------------------------------------------------------------------------
# TestLoadEnrichment
# ---------------------------------------------------------------------------


class TestLoadEnrichment:
    """load_enrichment reads and parses the export JSON."""

    def test_returns_unavailable_when_dir_does_not_exist(
        self, bare_project: Path
    ) -> None:
        integration = TappsIntegration(bare_project)
        enrichment = integration.load_enrichment()
        assert enrichment.available is False

    def test_returns_unavailable_when_export_file_missing(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "nofile"
        root.mkdir()
        (root / ".tapps-mcp").mkdir()
        # Directory exists, but no export file inside
        integration = TappsIntegration(root)
        enrichment = integration.load_enrichment()
        assert enrichment.available is False

    def test_returns_unavailable_when_json_malformed(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "malformed"
        root.mkdir()
        tapps_dir = root / ".tapps-mcp"
        tapps_dir.mkdir()
        (tapps_dir / "docsmcp-export.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )
        integration = TappsIntegration(root)
        enrichment = integration.load_enrichment()
        assert enrichment.available is False

    def test_returns_unavailable_when_version_mismatch(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "badver"
        root.mkdir()
        _write_export(root, {"version": "99.0", "quality_scores": []})
        integration = TappsIntegration(root)
        enrichment = integration.load_enrichment()
        assert enrichment.available is False

    def test_loads_quality_scores_from_valid_export(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        enrichment = integration.load_enrichment()
        assert enrichment.available is True
        assert len(enrichment.quality_scores) == 2
        assert enrichment.quality_scores[0].file_path == "src/app.py"
        assert enrichment.quality_scores[0].overall_score == 85.0
        assert enrichment.quality_scores[0].category_scores == {"security": 90}
        assert enrichment.quality_scores[1].file_path == "src/utils.py"
        assert enrichment.quality_scores[1].overall_score == 55.0

    def test_loads_project_profile_from_valid_export(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        enrichment = integration.load_enrichment()
        assert enrichment.available is True
        assert enrichment.project_profile is not None
        assert enrichment.project_profile.project_type == "python-library"
        assert enrichment.project_profile.has_ci is True
        assert "pytest" in enrichment.project_profile.test_frameworks
        assert "uv" in enrichment.project_profile.package_managers

    def test_loads_dependency_data_from_valid_export(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        enrichment = integration.load_enrichment()
        assert enrichment.available is True
        assert enrichment.dependency_data is not None
        assert enrichment.dependency_data.total_modules == 10
        assert enrichment.dependency_data.total_edges == 15
        assert enrichment.dependency_data.cycles == []
        assert enrichment.dependency_data.coupling == []

    def test_returns_overall_project_score(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        enrichment = integration.load_enrichment()
        assert enrichment.overall_project_score == 72.5

    def test_partial_export_no_profile_or_deps(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "partial"
        root.mkdir()
        _write_export(root, {"version": "1.0", "quality_scores": []})
        integration = TappsIntegration(root)
        enrichment = integration.load_enrichment()
        assert enrichment.available is True
        assert enrichment.quality_scores == []
        assert enrichment.project_profile is None
        assert enrichment.dependency_data is None
        assert enrichment.overall_project_score is None


# ---------------------------------------------------------------------------
# TestLoadProjectProfile
# ---------------------------------------------------------------------------


class TestLoadProjectProfile:
    """load_project_profile returns TappsProjectProfile or None."""

    def test_returns_none_when_dir_does_not_exist(
        self, bare_project: Path
    ) -> None:
        integration = TappsIntegration(bare_project)
        assert integration.load_project_profile() is None

    def test_returns_none_when_no_profile_in_export(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "noprofile"
        root.mkdir()
        _write_export(root, {"version": "1.0", "quality_scores": []})
        integration = TappsIntegration(root)
        assert integration.load_project_profile() is None

    def test_returns_profile_with_correct_fields(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        profile = integration.load_project_profile()
        assert profile is not None
        assert profile.project_type == "python-library"
        assert profile.tech_stack == {"language": "python"}
        assert profile.has_ci is True
        assert "pytest" in profile.test_frameworks
        assert "uv" in profile.package_managers


# ---------------------------------------------------------------------------
# TestLoadQualityScores
# ---------------------------------------------------------------------------


class TestLoadQualityScores:
    """load_quality_scores returns list[TappsQualityScore] or empty."""

    def test_returns_empty_when_dir_does_not_exist(
        self, bare_project: Path
    ) -> None:
        integration = TappsIntegration(bare_project)
        assert integration.load_quality_scores() == []

    def test_loads_scores_from_valid_export(
        self, tapps_project: Path
    ) -> None:
        integration = TappsIntegration(tapps_project)
        scores = integration.load_quality_scores()
        assert len(scores) == 2
        assert scores[0].file_path == "src/app.py"
        assert scores[0].overall_score == 85.0
        assert scores[0].category_scores == {"security": 90}
        assert scores[1].file_path == "src/utils.py"
        assert scores[1].overall_score == 55.0
        assert scores[1].category_scores == {}


# ---------------------------------------------------------------------------
# TestGenerateQualityBadge
# ---------------------------------------------------------------------------


class TestGenerateQualityBadge:
    """generate_quality_badge shields.io colour thresholds."""

    def test_score_above_80_is_brightgreen(self) -> None:
        badge = TappsIntegration.generate_quality_badge(90.0)
        assert "brightgreen" in badge

    def test_score_exactly_80_is_brightgreen(self) -> None:
        badge = TappsIntegration.generate_quality_badge(80.0)
        assert "brightgreen" in badge

    def test_score_between_60_and_79_is_yellow(self) -> None:
        badge = TappsIntegration.generate_quality_badge(65.0)
        assert "yellow" in badge

    def test_score_exactly_60_is_yellow(self) -> None:
        badge = TappsIntegration.generate_quality_badge(60.0)
        assert "yellow" in badge

    def test_score_below_60_is_red(self) -> None:
        badge = TappsIntegration.generate_quality_badge(40.0)
        assert "red" in badge

    def test_badge_contains_quality_text(self) -> None:
        badge = TappsIntegration.generate_quality_badge(85.0)
        assert "quality" in badge

    def test_badge_contains_shields_io_url(self) -> None:
        badge = TappsIntegration.generate_quality_badge(85.0)
        assert "img.shields.io" in badge

    def test_badge_contains_encoded_score(self) -> None:
        badge = TappsIntegration.generate_quality_badge(82.3)
        # Score formatted as integer with percent sign (URL-encoded)
        assert "82%" in badge


# ---------------------------------------------------------------------------
# TestGenerateGateBadge
# ---------------------------------------------------------------------------


class TestGenerateGateBadge:
    """generate_gate_badge pass/fail colours."""

    def test_passed_true_shows_passing_green(self) -> None:
        badge = TappsIntegration.generate_gate_badge(passed=True)
        assert "passing" in badge
        assert "green" in badge

    def test_passed_false_shows_failing_red(self) -> None:
        badge = TappsIntegration.generate_gate_badge(passed=False)
        assert "failing" in badge
        assert "red" in badge

    def test_gate_badge_contains_shields_io_url(self) -> None:
        badge = TappsIntegration.generate_gate_badge(passed=True)
        assert "img.shields.io" in badge

    def test_gate_badge_markdown_image_format(self) -> None:
        badge = TappsIntegration.generate_gate_badge(passed=True)
        assert badge.startswith("![Quality Gate]")

"""Tests for TECH_STACK.md rendering in the bootstrap pipeline (TAP-5733)."""

from __future__ import annotations

from tapps_mcp.pipeline.init_tech_stack import (
    _render_infrastructure_section,
    _render_list_section,
    _render_tech_stack_md,
)
from tapps_mcp.project.models import ProjectProfile, TechStack


class TestRenderListSection:
    def test_renders_one_bullet_per_item(self) -> None:
        assert _render_list_section("Languages", ["python", "typescript"]) == [
            "",
            "## Languages",
            "- python",
            "- typescript",
        ]

    def test_uses_default_fallback_for_none(self) -> None:
        assert _render_list_section("Frameworks", None) == [
            "",
            "## Frameworks",
            "- (none detected)",
        ]

    def test_uses_default_fallback_for_empty_list(self) -> None:
        assert _render_list_section("Frameworks", []) == [
            "",
            "## Frameworks",
            "- (none detected)",
        ]

    def test_uses_custom_fallback(self) -> None:
        assert _render_list_section("Recommendations", [], fallback="(none)") == [
            "",
            "## Recommendations",
            "- (none)",
        ]


class TestRenderInfrastructureSection:
    def test_renders_detected_infrastructure(self) -> None:
        profile = ProjectProfile(
            has_ci=True,
            ci_systems=["github-actions", "circleci"],
            has_docker=True,
            has_tests=True,
            test_frameworks=["pytest"],
            package_managers=["uv", "pip"],
        )
        assert _render_infrastructure_section(profile) == [
            "",
            "## Infrastructure",
            "- **CI:** Yes (github-actions, circleci)",
            "- **Docker:** Yes",
            "- **Tests:** Yes (pytest)",
            "- **Package managers:** uv, pip",
        ]

    def test_renders_absent_infrastructure(self) -> None:
        assert _render_infrastructure_section(ProjectProfile()) == [
            "",
            "## Infrastructure",
            "- **CI:** No",
            "- **Docker:** No",
            "- **Tests:** No",
            "- **Package managers:** N/A",
        ]


def _confident_profile(confidence: float = 0.9) -> ProjectProfile:
    return ProjectProfile(
        tech_stack=TechStack(
            languages=["python"],
            frameworks=["fastapi"],
            libraries=["httpx"],
            domains=["backend"],
            context7_priority=["fastapi", "httpx"],
        ),
        project_type="api-service",
        project_type_confidence=confidence,
        project_type_reason="pyproject.toml with fastapi dependency",
        has_ci=True,
        ci_systems=["github-actions"],
        has_tests=True,
        test_frameworks=["pytest"],
        package_managers=["uv"],
        quality_recommendations=["Add mypy --strict"],
    )


class TestRenderTechStackMd:
    def test_renders_every_section(self) -> None:
        md = _render_tech_stack_md(_confident_profile())
        assert md.startswith("# Tech Stack\n")
        assert "- **Type:** api-service" in md
        assert "- **Confidence:** 0.90" in md
        assert "- **Reason:** pyproject.toml with fastapi dependency" in md
        for heading in (
            "## Languages",
            "## Frameworks",
            "## Libraries",
            "## Domains",
            "## Context7 Priority (for doc lookups)",
            "## Infrastructure",
            "## Recommendations",
        ):
            assert heading in md
        assert md.endswith("\n")

    def test_omits_low_confidence_banner_above_threshold(self) -> None:
        assert "**Low confidence:**" not in _render_tech_stack_md(_confident_profile())

    def test_omits_low_confidence_banner_at_threshold(self) -> None:
        md = _render_tech_stack_md(_confident_profile(confidence=0.6))
        assert "**Low confidence:**" not in md

    def test_includes_low_confidence_banner_below_threshold(self) -> None:
        md = _render_tech_stack_md(_confident_profile(confidence=0.59))
        assert "> **Low confidence:**" in md
        assert md.splitlines()[2].startswith("> **Low confidence:**")

    def test_unknown_project_type_falls_back(self) -> None:
        md = _render_tech_stack_md(ProjectProfile())
        assert "- **Type:** unknown" in md
        assert "- **Confidence:** 0.00" in md
        assert "- **Reason:** N/A" in md

    def test_empty_context7_priority_renders_no_bullets(self) -> None:
        md = _render_tech_stack_md(ProjectProfile())
        lines = md.splitlines()
        idx = lines.index("## Context7 Priority (for doc lookups)")
        assert lines[idx + 1] == ""
        assert lines[idx + 2] == "## Infrastructure"

    def test_empty_profile_uses_list_fallbacks(self) -> None:
        md = _render_tech_stack_md(ProjectProfile())
        assert md.count("- (none detected)") == 4
        assert "- (none)" in md

"""TECH_STACK.md rendering for the bootstrap pipeline.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.project.models import ProjectProfile


def _render_list_section(
    heading: str, items: list[str] | None, fallback: str = "(none detected)"
) -> list[str]:
    """Render a markdown section with a heading and bullet list."""
    lines = ["", f"## {heading}"]
    lines.extend(f"- {item}" for item in items or [fallback])
    return lines


def _render_infrastructure_section(profile: ProjectProfile) -> list[str]:
    """Render the Infrastructure section of TECH_STACK.md."""
    ci_str = "Yes (" + ", ".join(profile.ci_systems) + ")" if profile.has_ci else "No"
    tests_str = "Yes (" + ", ".join(profile.test_frameworks) + ")" if profile.has_tests else "No"
    docker_str = "Yes" if profile.has_docker else "No"
    pkg_str = ", ".join(profile.package_managers) or "N/A"
    return [
        "",
        "## Infrastructure",
        f"- **CI:** {ci_str}",
        f"- **Docker:** {docker_str}",
        f"- **Tests:** {tests_str}",
        f"- **Package managers:** {pkg_str}",
    ]


_TECH_STACK_LOW_CONFIDENCE_THRESHOLD = 0.6


def _render_tech_stack_md(profile: ProjectProfile) -> str:
    """Render TECH_STACK.md content from project profile."""
    ts = profile.tech_stack
    low_conf = profile.project_type_confidence < _TECH_STACK_LOW_CONFIDENCE_THRESHOLD
    lines = [
        "# Tech Stack",
        "",
    ]
    if low_conf:
        lines.extend(
            [
                "> **Low confidence:** Auto-detected project type may be wrong (e.g. docs-only root "
                "with code in a subfolder). Confirm or edit sections below; optionally add "
                "`pyproject.toml` / `package.json` where the real code lives.",
                "",
            ]
        )
    lines.extend(
        [
            "## Project Type",
            f"- **Type:** {profile.project_type or 'unknown'}",
            f"- **Confidence:** {profile.project_type_confidence:.2f}",
            f"- **Reason:** {profile.project_type_reason or 'N/A'}",
        ]
    )
    lines.extend(_render_list_section("Languages", ts.languages))
    lines.extend(_render_list_section("Frameworks", ts.frameworks))
    lines.extend(_render_list_section("Libraries", ts.libraries))
    lines.extend(_render_list_section("Domains", ts.domains))
    # Context7 priority renders no fallback text when empty
    lines.extend(["", "## Context7 Priority (for doc lookups)"])
    lines.extend(f"- {p}" for p in ts.context7_priority or [])
    lines.extend(_render_infrastructure_section(profile))
    lines.extend(
        _render_list_section("Recommendations", profile.quality_recommendations, fallback="(none)")
    )
    lines.append("")
    return "\n".join(lines)

"""Regression tests for the shared CI install-step renderer.

tapps-mcp is not published to PyPI. The generated CI workflows must
install tapps-brain, tapps-core, and tapps-mcp directly from git URLs.
If a future refactor drops these URLs (or reintroduces
`pip install tapps-mcp`), every consuming project's CI silently breaks
again — the tests below exist to catch that regression at PR time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp import __version__
from tapps_mcp.pipeline.ci_install import (
    TAPPS_BRAIN_REPO,
    TAPPS_BRAIN_REV,
    TAPPS_MCP_REPO,
    render_install_step,
)
from tapps_mcp.pipeline.github_ci import (
    generate_enhanced_ci_workflow,
    generate_reusable_quality_workflow,
)
from tapps_mcp.pipeline.github_copilot import generate_agentic_workflow
from tapps_mcp.pipeline.platform_bundles import generate_ci_workflow


def _expected_urls() -> tuple[str, str, str]:
    tag = f"v{__version__}"
    return (
        f"{TAPPS_BRAIN_REPO}@{TAPPS_BRAIN_REV}",
        f"{TAPPS_MCP_REPO}@{tag}#subdirectory=packages/tapps-core",
        f"{TAPPS_MCP_REPO}@{tag}#subdirectory=packages/tapps-mcp",
    )


def test_render_install_step_includes_all_three_git_urls() -> None:
    rendered = render_install_step()
    brain_url, core_url, mcp_url = _expected_urls()
    assert brain_url in rendered
    assert core_url in rendered
    assert mcp_url in rendered
    assert "pip install" in rendered


def test_render_install_step_never_emits_bare_pypi_install() -> None:
    """`pip install tapps-mcp` alone would fail — it must always use a URL."""
    rendered = render_install_step()
    for line in rendered.splitlines():
        stripped = line.strip()
        if stripped.startswith("pip install") and "@ git+" not in stripped:
            assert stripped == "pip install --upgrade pip" or stripped.endswith("\\"), (
                f"found pip install without git URL: {stripped!r}"
            )


def test_render_install_step_omits_checkers_when_requested() -> None:
    rendered = render_install_step(include_checkers=False)
    assert "ruff mypy bandit radon vulture" not in rendered


@pytest.mark.parametrize(
    "generator_name",
    [
        "tapps-quality.yml",
        "tapps-quality-reusable.yml",
        "agentic-pr-review.yml",
    ],
)
def test_generated_workflow_contains_git_urls(generator_name: str, tmp_path: Path) -> None:
    generators = {
        "tapps-quality.yml": generate_enhanced_ci_workflow,
        "tapps-quality-reusable.yml": generate_reusable_quality_workflow,
        "agentic-pr-review.yml": generate_agentic_workflow,
    }
    generators[generator_name](tmp_path)

    workflow_text = (tmp_path / ".github" / "workflows" / generator_name).read_text()
    brain_url, core_url, mcp_url = _expected_urls()
    assert brain_url in workflow_text
    assert core_url in workflow_text
    assert mcp_url in workflow_text
    assert "--preset" not in workflow_text
    assert "validate-changed --full" in workflow_text


def test_platform_bundles_ci_workflow_contains_git_urls(tmp_path: Path) -> None:
    generate_ci_workflow(tmp_path)
    workflow_text = (tmp_path / ".github" / "workflows" / "tapps-quality.yml").read_text()
    brain_url, core_url, mcp_url = _expected_urls()
    assert brain_url in workflow_text
    assert core_url in workflow_text
    assert mcp_url in workflow_text
    assert "--preset" not in workflow_text
    assert "validate-changed --full" in workflow_text

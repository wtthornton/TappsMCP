"""Regression tests for the shared CI install-step renderer.

tapps-mcp is not published to PyPI. Any generated CI workflow that installs
tapps-brain / tapps-core / tapps-mcp must do so from git URLs, not a bare
`pip install tapps-mcp`. These tests lock the renderer's output shape so a
future refactor that silently drops the git URL — or reintroduces a PyPI
install — fails loudly at PR time.

As of the GitHub Actions simplification (only CodeQL remains), no workflow
currently calls `render_install_step`. The helper is retained so the
shape-lock is still meaningful if a consumer opts a workflow back in.
"""

from __future__ import annotations

from tapps_mcp import __version__
from tapps_mcp.pipeline.ci_install import (
    TAPPS_BRAIN_REPO,
    TAPPS_BRAIN_REV,
    TAPPS_MCP_REPO,
    render_install_step,
)


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

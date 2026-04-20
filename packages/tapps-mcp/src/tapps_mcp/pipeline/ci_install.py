"""Shared install-step renderer for generated GitHub CI workflows.

tapps-mcp is not published to PyPI. Consumers installing via `pip install
tapps-mcp` fail at dependency resolution. This module renders a pip install
step that points at the three source repositories directly (tapps-brain,
tapps-core, tapps-mcp) with pinned refs matching the current release.

The generator modules (github_ci, github_copilot, platform_bundles) splice
the rendered block into their workflow templates at write-time so the pins
track the installed tapps-mcp version.

Keep ``TAPPS_BRAIN_REV`` in sync with the ``rev`` declared for tapps-brain
in the workspace ``pyproject.toml`` (root ``[tool.uv.sources]`` table).
"""

from __future__ import annotations

from tapps_mcp import __version__

TAPPS_BRAIN_REV = "a3654693df32d64f65cd3d97e7e28b2499a5308b"
"""tapps-brain commit SHA matching ``[tool.uv.sources]`` in the root pyproject."""

TAPPS_MCP_REPO = "https://github.com/wtthornton/TappsMCP.git"
TAPPS_BRAIN_REPO = "https://github.com/wtthornton/tapps-brain.git"


def render_install_step(
    *,
    indent: str = "      ",
    step_name: str = "Install TappsMCP and checkers",
    include_checkers: bool = True,
) -> str:
    """Return a GitHub Actions ``steps:`` entry that installs tapps-mcp.

    The entry is emitted at the given indent (default 6 spaces, matching
    the existing templates' ``jobs.<id>.steps:`` depth). It installs
    tapps-brain, tapps-core, and tapps-mcp from git URLs pinned to the
    current release, because none are published to PyPI.

    ``include_checkers`` controls whether the quality checker packages
    (ruff, mypy, bandit, radon, vulture) are installed in the same pip
    invocation. Disable for workflows that install checkers separately.
    """
    tag = f"v{__version__}"
    core_url = f"tapps-core @ git+{TAPPS_MCP_REPO}@{tag}#subdirectory=packages/tapps-core"
    mcp_url = f"tapps-mcp @ git+{TAPPS_MCP_REPO}@{tag}#subdirectory=packages/tapps-mcp"
    brain_url = f"tapps-brain @ git+{TAPPS_BRAIN_REPO}@{TAPPS_BRAIN_REV}"

    lines = [
        f"{indent}- name: {step_name}",
        f"{indent}  run: |",
        f"{indent}    pip install --upgrade pip",
        f"{indent}    pip install \\",
        f'{indent}      "{brain_url}" \\',
        f'{indent}      "{core_url}" \\',
    ]
    if include_checkers:
        lines.append(f'{indent}      "{mcp_url}" \\')
        lines.append(f"{indent}      ruff mypy bandit radon vulture")
    else:
        lines.append(f'{indent}      "{mcp_url}"')
    return "\n".join(lines) + "\n"

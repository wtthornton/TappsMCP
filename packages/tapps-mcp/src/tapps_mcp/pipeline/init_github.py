"""GitHub scaffolding steps for the bootstrap pipeline.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733).  Each function
delegates to a dedicated generator module and records its result on the
shared state, downgrading any generator failure to a recorded error so one
broken generator cannot abort the whole bootstrap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.pipeline.init_state import _BootstrapState


def _setup_github_templates(state: _BootstrapState) -> None:
    """Generate GitHub Issue forms and PR template."""
    try:
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        result = generate_all_github_templates(state.project_root)
        state.result["github_templates"] = result
    except Exception as exc:
        state.errors.append(f"GitHub templates: {exc}")
        state.result["github_templates"] = {"error": str(exc)}


def _setup_github_ci(state: _BootstrapState) -> None:
    """Generate enhanced CI workflows."""
    try:
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result = generate_all_ci_workflows(state.project_root)
        state.result["ci_workflows"] = result
    except Exception as exc:
        state.errors.append(f"CI workflows: {exc}")
        state.result["ci_workflows"] = {"error": str(exc)}


def _setup_github_copilot(state: _BootstrapState) -> None:
    """Generate Copilot agent profiles and path-scoped instructions."""
    try:
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        result = generate_all_copilot_config(state.project_root)
        state.result["github_copilot"] = result
    except Exception as exc:
        state.errors.append(f"Copilot config: {exc}")
        state.result["github_copilot"] = {"error": str(exc)}


def _setup_github_governance(state: _BootstrapState) -> None:
    """Generate governance files (SECURITY.md, CODEOWNERS, rulesets, guide)."""
    try:
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        result = generate_all_governance(state.project_root)
        state.result["governance"] = result
    except Exception as exc:
        state.errors.append(f"Governance: {exc}")
        state.result["governance"] = {"error": str(exc)}

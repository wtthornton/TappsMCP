"""MCP tool handler for tapps_release_update (TAP-1112).

Orchestrates release update document generation: sources body from
CHANGELOG or git log, calls docs-mcp generator and validator APIs
directly (same uv workspace), and returns a validated body ready for
the linear-release-update skill to post via save_document.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.server_helpers import error_response, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from mcp.types import ToolAnnotations

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _record_call(tool_name: str) -> None:
    from tapps_mcp.server import _record_call as _rc

    _rc(tool_name)


async def tapps_release_update(
    version: str,
    prev_version: str,
    bump_type: str = "",
    team: str = "",
    project: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate and validate a release update document body.

    Sources content from CHANGELOG.md (preferred) or git log, builds the
    document via docs-mcp generators, validates it, and returns the body
    ready for the linear-release-update skill to post via save_document.

    With ``dry_run=True``, returns the body without requiring agent_ready.

    Args:
        version: New release version, e.g. "1.5.0".
        prev_version: Previous version, e.g. "1.4.2".
        bump_type: "patch", "minor", or "major". Inferred from semver if blank.
        team: Linear team name/ID (from .tapps-mcp.yaml or passed by agent).
        project: Linear project name/slug (from .tapps-mcp.yaml or agent).
        dry_run: When True, return body regardless of validation result.
    """
    _record_call("tapps_release_update")
    start = time.perf_counter_ns()

    if not version.strip():
        return error_response("tapps_release_update", "MISSING_VERSION", "Parameter 'version' is required.")
    if not prev_version.strip():
        return error_response("tapps_release_update", "MISSING_PREV_VERSION", "Parameter 'prev_version' is required.")

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        project_root = Path(settings.project_root)
        effective_team = team.strip() or settings.linear_team
        effective_project = project.strip() or settings.linear_project
    except Exception:
        project_root = Path.cwd()
        effective_team = team.strip()
        effective_project = project.strip()

    # Source content
    try:
        from tapps_mcp.tools.release_update import build_release_content

        content = build_release_content(
            version=version.strip(),
            prev_version=prev_version.strip(),
            bump_type=bump_type.strip(),
            project_root=project_root,
        )
    except Exception as exc:
        return error_response(
            "tapps_release_update",
            "CONTENT_SOURCE_ERROR",
            f"Failed to source release content: {exc}",
        )

    # Generate body via docs-mcp Python API
    try:
        from docs_mcp.generators.release_update import ReleaseUpdateConfig, ReleaseUpdateGenerator

        config = ReleaseUpdateConfig(
            version=content["version"],
            prev_version=content["prev_version"],
            bump_type=content["bump_type"],
            highlights=content["highlights"],
            issues_closed=content["issues_closed"],
        )
        body = ReleaseUpdateGenerator().generate(config)
    except Exception as exc:
        return error_response(
            "tapps_release_update",
            "GENERATION_ERROR",
            f"docs-mcp generator failed: {exc}",
        )

    # Validate
    try:
        from docs_mcp.validators.release_update import validate_release_update

        report = validate_release_update(body)
    except Exception as exc:
        return error_response(
            "tapps_release_update",
            "VALIDATION_ERROR",
            f"docs-mcp validator failed: {exc}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    if not dry_run and not report.agent_ready:
        return error_response(
            "tapps_release_update",
            "VALIDATION_FAILED",
            "Release update body failed validation. Fix the findings before posting.",
            extra={
                "agent_ready": False,
                "score": report.score,
                "findings": [f.model_dump() for f in report.findings],
                "body": body,
            },
        )

    return success_response(
        "tapps_release_update",
        elapsed_ms,
        {
            "body": body,
            "version": content["version"],
            "prev_version": content["prev_version"],
            "bump_type": content["bump_type"],
            "team": effective_team,
            "project": effective_project,
            "agent_ready": report.agent_ready,
            "score": report.score,
            "findings": [f.model_dump() for f in report.findings],
            "dry_run": dry_run,
            "source": "changelog" if content.get("changelog_body") else "git_log",
            "document_title": f"Release v{content['version']} — {_today()}",
        },
    )


def _today() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d")


def register(mcp_instance: "FastMCP", allowed_tools: frozenset[str]) -> None:
    """Register release update tool on the shared mcp instance."""
    if "tapps_release_update" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_release_update)

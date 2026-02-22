"""MCP elicitation helpers for interactive user input.

MCP elicitation is a protocol extension that allows servers to request
structured input from the user via the host's native UI during tool
execution.  Currently only Cursor implements this extension.

On unsupported clients the helpers degrade gracefully — they return
``None`` instead of raising, so callers can fall back to defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context


# ---------------------------------------------------------------------------
# Pydantic models for elicitation schemas
# ---------------------------------------------------------------------------


class PresetElicitation(BaseModel):
    """Schema for quality gate preset selection."""

    preset: str = Field(
        description="Quality gate preset",
        json_schema_extra={
            "enum": ["development", "staging", "production"],
            "enumNames": [
                "Development (lenient — score >= 60)",
                "Staging (moderate — score >= 75)",
                "Production (strict — score >= 90)",
            ],
        },
    )


class InitConfirmation(BaseModel):
    """Schema for tapps_init confirmation."""

    confirm: bool = Field(
        description="Confirm TappsMCP initialization",
    )


# ---------------------------------------------------------------------------
# Elicitation helpers
# ---------------------------------------------------------------------------


async def elicit_preset(ctx: Context) -> str | None:  # type: ignore[type-arg]
    """Ask the user to select a quality gate preset via elicitation.

    Returns the selected preset string (e.g. ``"staging"``) if the user
    accepted, or ``None`` if declined, cancelled, or unsupported.
    """
    try:
        result = await ctx.elicit(
            message="Which quality gate preset should be applied?",
            schema=PresetElicitation,
        )
        if result.action == "accept" and result.data is not None:
            return result.data.preset
        return None
    except Exception:  # pragma: no cover — graceful degradation
        return None


async def elicit_init_confirmation(
    ctx: Context,  # type: ignore[type-arg]
    project_root: str,
) -> bool | None:
    """Ask the user to confirm tapps_init before writing files.

    Returns ``True`` if confirmed, ``False`` if explicitly declined,
    or ``None`` if unsupported/cancelled.
    """
    try:
        result = await ctx.elicit(
            message=(
                f"TappsMCP will write configuration files to {project_root}. "
                "This includes .claude/settings.json, .mcp.json, CLAUDE.md, "
                "and AGENTS.md. Proceed?"
            ),
            schema=InitConfirmation,
        )
        if result.action == "accept" and result.data is not None:
            return result.data.confirm
        return None
    except Exception:  # pragma: no cover — graceful degradation
        return None

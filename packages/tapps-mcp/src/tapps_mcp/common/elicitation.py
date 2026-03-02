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
# Wizard elicitation schemas (Epic 37.1)
# ---------------------------------------------------------------------------


class WizardQualityPreset(BaseModel):
    """Schema for wizard quality preset selection."""

    preset: str = Field(
        description="Quality standard",
        json_schema_extra={
            "enum": ["standard", "strict", "framework"],
            "enumNames": [
                "Standard (70+ score, recommended for most projects)",
                "Strict (80+ score, for production codebases)",
                "Framework (75+ score, for library/framework development)",
            ],
        },
    )


class WizardEngagementLevel(BaseModel):
    """Schema for wizard engagement level selection."""

    level: str = Field(
        description="Engagement level",
        json_schema_extra={
            "enum": ["high", "medium", "low"],
            "enumNames": [
                "High (mandatory enforcement — blocks without validation)",
                "Medium (balanced — reminders and nudges)",
                "Low (optional guidance — minimal intervention)",
            ],
        },
    )


class WizardAgentTeams(BaseModel):
    """Schema for wizard agent teams selection."""

    enabled: bool = Field(description="Enable agent team hooks")


class WizardSkillTier(BaseModel):
    """Schema for wizard skill tier selection."""

    tier: str = Field(
        description="Skill tier",
        json_schema_extra={
            "enum": ["core", "full"],
            "enumNames": [
                "Core only (score, gate, validate, security — 4 skills)",
                "Full (all 7 skills including research, memory, review pipeline)",
            ],
        },
    )


class WizardPromptHooks(BaseModel):
    """Schema for wizard prompt hooks selection."""

    enabled: bool = Field(description="Enable AI-powered quality judgment")


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


# ---------------------------------------------------------------------------
# Wizard flow (Epic 37.1)
# ---------------------------------------------------------------------------


class WizardResult:
    """Aggregated answers from the interactive first-run wizard."""

    __slots__ = (
        "agent_teams",
        "completed",
        "engagement_level",
        "prompt_hooks",
        "quality_preset",
        "skill_tier",
    )

    def __init__(self) -> None:
        self.quality_preset: str = "standard"
        self.engagement_level: str = "medium"
        self.agent_teams: bool = False
        self.skill_tier: str = "full"
        self.prompt_hooks: bool = False
        self.completed: bool = False


async def run_init_wizard(ctx: Context) -> WizardResult:  # type: ignore[type-arg]
    """Run the 5-question interactive wizard via MCP elicitation.

    Returns a :class:`WizardResult` with the user's selections.
    If elicitation is unsupported or the user cancels, returns defaults
    with ``completed=False``.
    """
    result = WizardResult()
    try:
        # 1. Quality preset
        r1 = await ctx.elicit(
            message="Which quality standard should TappsMCP enforce?",
            schema=WizardQualityPreset,
        )
        if r1.action == "accept" and r1.data is not None:
            result.quality_preset = r1.data.preset
        elif r1.action == "decline":
            return result

        # 2. Engagement level
        r2 = await ctx.elicit(
            message="How actively should TappsMCP guide the coding agent?",
            schema=WizardEngagementLevel,
        )
        if r2.action == "accept" and r2.data is not None:
            result.engagement_level = r2.data.level
        elif r2.action == "decline":
            return result

        # 3. Agent teams
        r3 = await ctx.elicit(
            message=(
                "Will you use Claude Code Agent Teams for parallel work? "
                "(Generates TeammateIdle and TaskCompleted hooks)"
            ),
            schema=WizardAgentTeams,
        )
        if r3.action == "accept" and r3.data is not None:
            result.agent_teams = r3.data.enabled

        # 4. Skill tier
        r4 = await ctx.elicit(
            message="Which TappsMCP skills should be installed?",
            schema=WizardSkillTier,
        )
        if r4.action == "accept" and r4.data is not None:
            result.skill_tier = r4.data.tier

        # 5. Prompt hooks
        r5 = await ctx.elicit(
            message=(
                "Enable AI-powered quality judgment? "
                "(Uses Haiku, ~$0.001/check)"
            ),
            schema=WizardPromptHooks,
        )
        if r5.action == "accept" and r5.data is not None:
            result.prompt_hooks = r5.data.enabled

        result.completed = True
    except Exception:  # noqa: S110 — graceful degradation for unsupported clients
        pass
    return result

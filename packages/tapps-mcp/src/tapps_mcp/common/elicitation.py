"""MCP elicitation helpers for interactive user input.

MCP elicitation is a protocol extension that allows servers to request
structured input from the user via the host's native UI during tool
execution.  Currently only Cursor implements this extension.

On unsupported clients the helpers degrade gracefully — they return
``None`` instead of raising, so callers can fall back to defaults.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

# Timeout for elicitation calls.  Non-interactive clients that don't support
# the ``elicitation/create`` method will never respond, so we cap the wait
# to avoid blocking the server indefinitely.
_ELICITATION_TIMEOUT_SEC = 30

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


class WizardOtherMcps(BaseModel):
    """Schema for wizard 'add other MCPs' prompt."""

    enabled: bool = Field(
        description="Show guidance on adding complementary MCPs (GitHub, YouTube, etc.)",
    )


class WizardConfigScope(BaseModel):
    """Schema for wizard config scope selection (Epic 47)."""

    scope: str = Field(
        description="Config scope",
        json_schema_extra={
            "enum": ["project", "user"],
            "enumNames": [
                "Project scope — .mcp.json in project root (recommended)",
                "User scope — ~/.claude.json (global, affects all projects)",
            ],
        },
    )


# ---------------------------------------------------------------------------
# Elicitation helpers
# ---------------------------------------------------------------------------


def _client_supports_elicitation(ctx: Context) -> bool:  # type: ignore[type-arg]
    """Return ``True`` if the connected MCP client advertises elicitation.

    Falls back to ``True`` (optimistic) if capabilities cannot be inspected
    so that supported clients aren't accidentally excluded.
    """
    try:
        session = getattr(ctx, "session", None)
        if session is None:
            return True
        caps = getattr(session, "client_capabilities", None) or getattr(
            session, "_client_capabilities", None
        )
        if caps is None:
            return True
        # The MCP spec uses ``elicitation`` as a capability key.
        if hasattr(caps, "elicitation"):
            return caps.elicitation is not None
        # Dict-style fallback
        if isinstance(caps, dict):
            return caps.get("elicitation") is not None
        return True
    except Exception:
        return True


async def elicit_preset(ctx: Context) -> str | None:  # type: ignore[type-arg]
    """Ask the user to select a quality gate preset via elicitation.

    Returns the selected preset string (e.g. ``"staging"``) if the user
    accepted, or ``None`` if declined, cancelled, or unsupported.
    """
    if not _client_supports_elicitation(ctx):
        return None
    try:
        result = await asyncio.wait_for(
            ctx.elicit(
                message="Which quality gate preset should be applied?",
                schema=PresetElicitation,
            ),
            timeout=_ELICITATION_TIMEOUT_SEC,
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
    or ``None`` if unsupported/cancelled/timed out.
    """
    if not _client_supports_elicitation(ctx):
        return None
    try:
        result = await asyncio.wait_for(
            ctx.elicit(
                message=(
                    f"TappsMCP will write configuration files to {project_root}. "
                    "This includes .claude/settings.json, .mcp.json, CLAUDE.md, "
                    "and AGENTS.md. Proceed?"
                ),
                schema=InitConfirmation,
            ),
            timeout=_ELICITATION_TIMEOUT_SEC,
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
        "add_other_mcps",
        "agent_teams",
        "completed",
        "config_scope",
        "engagement_level",
        "prompt_hooks",
        "quality_preset",
        "skill_tier",
    )

    def __init__(self) -> None:
        self.quality_preset: str = "standard"
        self.engagement_level: str = "medium"
        self.config_scope: str = "project"
        self.agent_teams: bool = False
        self.skill_tier: str = "full"
        self.prompt_hooks: bool = False
        self.add_other_mcps: bool = False
        self.completed: bool = False


async def run_init_wizard(
    ctx: Context,
    *,
    claude_code_detected: bool = True,
) -> WizardResult:
    """Run the interactive wizard via MCP elicitation.

    Returns a :class:`WizardResult` with the user's selections.
    If elicitation is unsupported or the user cancels, returns defaults
    with ``completed=False``.

    Args:
        ctx: MCP context for elicitation.
    """
    result = WizardResult()
    if not _client_supports_elicitation(ctx):
        return result

    _t = _ELICITATION_TIMEOUT_SEC

    async def _ask(message: str, schema: type) -> Any:
        return await asyncio.wait_for(
            ctx.elicit(message=message, schema=schema),
            timeout=_t,
        )

    try:
        # 1. Quality preset
        r1 = await _ask(
            "Which quality standard should TappsMCP enforce?",
            WizardQualityPreset,
        )
        if r1.action == "accept" and r1.data is not None:
            result.quality_preset = r1.data.preset
        elif r1.action == "decline":
            return result

        # 2. Engagement level
        r2 = await _ask(
            "How actively should TappsMCP guide the coding agent?",
            WizardEngagementLevel,
        )
        if r2.action == "accept" and r2.data is not None:
            result.engagement_level = r2.data.level
        elif r2.action == "decline":
            return result

        # 2b. Config scope (only for Claude Code - Epic 47)
        if claude_code_detected:
            r_scope = await _ask(
                "Where should TappsMCP config be stored? "
                "Project scope keeps config in this repo only.",
                WizardConfigScope,
            )
            if r_scope.action == "accept" and r_scope.data is not None:
                result.config_scope = r_scope.data.scope
            elif r_scope.action == "decline":
                return result

        # 3. Agent teams
        r3 = await _ask(
            "Will you use Claude Code Agent Teams for parallel work? "
            "(Generates TeammateIdle and TaskCompleted hooks)",
            WizardAgentTeams,
        )
        if r3.action == "accept" and r3.data is not None:
            result.agent_teams = r3.data.enabled

        # 4. Skill tier
        r4 = await _ask(
            "Which TappsMCP skills should be installed?",
            WizardSkillTier,
        )
        if r4.action == "accept" and r4.data is not None:
            result.skill_tier = r4.data.tier

        # 5. Prompt hooks
        r5 = await _ask(
            "Enable AI-powered quality judgment? (Uses Haiku, ~$0.001/check)",
            WizardPromptHooks,
        )
        if r5.action == "accept" and r5.data is not None:
            result.prompt_hooks = r5.data.enabled

        # 6. Other MCPs
        r6 = await _ask(
            "Get guidance on adding other MCPs (GitHub, YouTube, Sentry) "
            "alongside TappsMCP? See docs/MCP_COMPOSITION.md for details.",
            WizardOtherMcps,
        )
        if r6.action == "accept" and r6.data is not None:
            result.add_other_mcps = r6.data.enabled

        result.completed = True
    except Exception:
        pass
    return result

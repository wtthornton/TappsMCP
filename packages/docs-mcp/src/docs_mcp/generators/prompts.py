"""Prompt artifact generation (Epic 75). PromptConfig + PromptGenerator for LLM-facing prompt docs."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Models (aligned with docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md §5)
# ---------------------------------------------------------------------------


class ContextFileEntry(BaseModel):
    """A single context file: path and short description."""

    path: str
    description: str = ""


class SuccessBrief(BaseModel):
    """Success brief: output type, recipient reaction, does_not_sound_like, success_means."""

    output_type: str = ""
    recipient_reaction: str = ""
    does_not_sound_like: str = ""
    success_means: str = ""


class PromptConfig(BaseModel):
    """Configuration for prompt artifact generation.

    All sections from the design doc (task, context files, success brief,
    rules, conversation, plan, alignment, allowed tools, output format, don't)
    are representable. Purpose & Intent is required for all artifacts.
    """

    name: str
    when_to_use: str = ""
    purpose_and_intent: str = ""  # Required per design doc §2
    task: str = ""
    success_criteria: str = ""
    context_files: list[ContextFileEntry] = []
    reference_notes: str = ""
    success_brief: SuccessBrief | None = None
    rules: str = ""
    conversation_first: bool = False
    plan_steps: int | bool = False  # int = number of steps, False = omit
    alignment_required: bool = False
    allowed_tools: list[str] = []
    output_format: str = ""
    dont: list[str] = []
    style: str = "standard"  # "standard" or "comprehensive"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class PromptGenerator:
    """Generates prompt artifact markdown with docsmcp section markers.

    Renders sections: Purpose & Intent (required), task, context files,
    reference (optional), success brief, rules, conversation (optional),
    plan (optional), alignment (optional), allowed tools, output format, don't.
    """

    VALID_STYLES: ClassVar[frozenset[str]] = frozenset({"standard", "comprehensive"})

    def generate(
        self,
        config: PromptConfig,
        *,
        project_root: Path | None = None,
        auto_populate: bool = False,
    ) -> str:
        """Generate a prompt document.

        Args:
            config: PromptConfig with name, when_to_use, purpose_and_intent, task, etc.
            project_root: Optional project root (for future auto_populate).
            auto_populate: If True, could call consult_expert for rules enrichment;
                not implemented in this version.

        Returns:
            Markdown string with docsmcp markers.
        """
        _ = project_root, auto_populate
        sections: list[str] = []

        # Identity
        sections.append(_section("metadata", f"# Prompt: {config.name}\n\n**When to use:** {config.when_to_use or '(not specified)'}"))

        # Purpose & Intent (required)
        p_intent = config.purpose_and_intent.strip() or "This prompt is for the given task so that success criteria are met."
        sections.append(_section("purpose-intent", f"## Purpose & Intent\n\n{p_intent}"))

        # Task
        if config.task or config.success_criteria:
            task_block = []
            if config.task:
                task_block.append(f"**Task:** {config.task}")
            if config.success_criteria:
                task_block.append(f"**Success criteria:** {config.success_criteria}")
            sections.append(_section("task", "## Task\n\n" + "\n\n".join(task_block)))

        # Context files
        if config.context_files:
            lines = ["## Context files\n\nRead these files completely before responding:\n"]
            for cf in config.context_files:
                lines.append(f"- `{cf.path}` — {cf.description or '(no description)'}")
            sections.append(_section("context-files", "\n".join(lines)))

        # Reference (optional)
        if config.reference_notes:
            sections.append(_section("reference", f"## Reference\n\n{config.reference_notes}"))

        # Success brief
        if config.success_brief and any([
            config.success_brief.output_type,
            config.success_brief.recipient_reaction,
            config.success_brief.does_not_sound_like,
            config.success_brief.success_means,
        ]):
            sb = config.success_brief
            lines = ["## Success brief\n"]
            if sb.output_type:
                lines.append(f"- **Output type:** {sb.output_type}")
            if sb.recipient_reaction:
                lines.append(f"- **Recipient reaction:** {sb.recipient_reaction}")
            if sb.does_not_sound_like:
                lines.append(f"- **Does NOT sound like:** {sb.does_not_sound_like}")
            if sb.success_means:
                lines.append(f"- **Success means:** {sb.success_means}")
            sections.append(_section("success-brief", "\n".join(lines)))

        # Rules
        if config.rules:
            sections.append(_section("rules", f"## Rules\n\n{config.rules}"))

        # Conversation (optional)
        if config.conversation_first:
            sections.append(_section("conversation", "## Conversation\n\nDo not start executing yet; ask clarifying questions to refine approach step by step."))

        # Plan (optional)
        if config.plan_steps is not False:
            n = config.plan_steps if isinstance(config.plan_steps, int) else 5
            sections.append(_section("plan", f"## Plan\n\nBefore writing: list the key rules from context that matter most; then give execution plan ({n} steps max)."))

        # Alignment (optional)
        if config.alignment_required:
            sections.append(_section("alignment", "## Alignment\n\nOnly begin work once we've aligned."))

        # Allowed tools
        if config.allowed_tools:
            tools_list = "\n".join(f"- {t}" for t in config.allowed_tools)
            sections.append(_section("allowed-tools", f"## Allowed tools\n\n{tools_list}"))

        # Output format
        if config.output_format:
            sections.append(_section("output-format", f"## Output format\n\n{config.output_format}"))

        # Don't (out of scope)
        if config.dont:
            lines = ["## Don't\n\n"] + [f"- {d}" for d in config.dont]
            sections.append(_section("dont", "\n".join(lines)))

        return "\n\n---\n\n".join(sections) + "\n"

    def generate_compact(self, config: PromptConfig) -> str:
        """Generate a compact LLM view (≤~1.5K tokens target).

        Format: identity, purpose/goal, success criteria, steps, rules, don't.
        No narrative, no full section prose. For use as token-efficient context
        (Epic 75.4). Full doc remains source of truth for humans.
        """
        lines: list[str] = []
        # Identity
        lines.append(f"# {config.name}")
        if config.when_to_use:
            lines.append(f"When: {config.when_to_use}")
        lines.append("")
        # Purpose / goal (single paragraph)
        p_intent = (
            config.purpose_and_intent.strip()
            or "This prompt is for the given task so that success criteria are met."
        )
        lines.append("## Purpose")
        lines.append(p_intent)
        lines.append("")
        # Success criteria (bulleted)
        if config.task or config.success_criteria:
            lines.append("## Success criteria")
            if config.task:
                lines.append(f"- Task: {config.task}")
            if config.success_criteria:
                lines.append(f"- {config.success_criteria}")
            if config.success_brief and config.success_brief.success_means:
                lines.append(f"- Success means: {config.success_brief.success_means}")
            lines.append("")
        # Steps / instructions (bulleted: task + allowed tools)
        steps: list[str] = []
        if config.task:
            steps.append(config.task)
        if config.allowed_tools:
            steps.extend(config.allowed_tools)
        if steps:
            lines.append("## Steps")
            for s in steps:
                lines.append(f"- {s}")
            lines.append("")
        # Rules / constraints (bulleted)
        if config.rules:
            lines.append("## Rules")
            for raw_line in config.rules.strip().splitlines():
                stripped = raw_line.strip()
                if stripped:
                    lines.append(f"- {stripped}")
            lines.append("")
        # Don't (bulleted)
        if config.dont:
            lines.append("## Don't")
            for d in config.dont:
                lines.append(f"- {d}")
        return "\n".join(lines).strip() + "\n"


def _section(name: str, content: str) -> str:
    """Wrap content in docsmcp markers."""
    return f"<!-- docsmcp:start:{name} -->\n{content}\n<!-- docsmcp:end:{name} -->"


def estimate_tokens(text: str) -> int:
    """Estimate token count for English text (~1.35 tokens/word, ~4 chars/token).

    Used for compact LLM view budget checks (Epic 75.4). Not exact; for
    validation only. Target compact view ≤~1.5K tokens; test under 2K.
    """
    if not text or not text.strip():
        return 0
    # Conservative: words * 1.35 (English) and chars/4 as upper bound
    words = len(text.split())
    chars = len(text)
    return min(int(words * 1.35), chars // 4 + 1)


# Target and hard cap for compact view (Epic 75.4)
COMPACT_VIEW_TARGET_TOKENS = 1500
COMPACT_VIEW_MAX_TOKENS = 2000

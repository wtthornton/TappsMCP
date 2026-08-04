"""Planning-document DocsMCP generation tools.

Epics, user stories, and reusable prompt templates — the handlers that
feed the Linear issue flow. Split out of ``server_gen_tools.py`` under
TAP-5608 — that module is now a registration facade that re-exports
these handlers.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.server_gen_helpers import (
    _split_criteria_list,
    _split_csv,
    _strip_wire_tags,
)
from docs_mcp.server_gen_helpers import (
    get_settings as _get_settings,
)
from docs_mcp.server_gen_helpers import (
    record_call as _record_call,
)
from docs_mcp.server_helpers import (
    error_response,
    finalize_output,
    safe_slug,
    success_response,
)

logger = structlog.get_logger(__name__)


async def docs_generate_epic(
    title: str,
    number: int = 0,
    purpose_and_intent: str = "",
    goal: str = "",
    motivation: str = "",
    status: str = "Proposed",
    priority: str = "",
    estimated_loe: str = "",
    dependencies: str = "",
    blocks: str = "",
    acceptance_criteria: str = "",
    stories: str = "",
    technical_notes: str = "",
    risks: str = "",
    non_goals: str = "",
    success_metrics: str = "",
    stakeholders: str = "",
    references: str = "",
    files: str = "",
    link_stories: bool = False,
    style: str = "standard",
    auto_populate: bool = False,
    quick_start: bool = False,
    output_path: str = "",
    write_to_disk: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    """Generate an Epic planning document with stories and acceptance criteria.

    Creates a structured epic document following agile best practices with
    metadata block, goal, motivation, acceptance criteria (checkbox list),
    numbered story stubs, technical notes, and out-of-scope items.

    The ``comprehensive`` style adds success metrics, stakeholders, references,
    implementation order, risk assessment with auto-classification, and files
    affected table with aggregated paths from stories.

    When ``auto_populate=True``, enriches sections from project analyzers
    (module map, tech stack, git history).

    When ``files`` is provided, generates a detailed Files Affected table
    with per-file analysis (line counts, recent git commits, public symbols)
    and a Related Epics section cross-referencing existing epics that mention
    the same files.

    Args:
        title: Epic title (e.g. "User Authentication System").
        number: Epic number for story numbering (e.g. 23 gives stories 23.1, 23.2).
        purpose_and_intent: Required per Epic 75.3. One paragraph: "We are doing this so that …".
        goal: One-paragraph description of what the epic achieves.
        motivation: Why this work matters.
        status: Epic status - "Proposed", "In Progress", "Complete",
            "Blocked", or "Cancelled".
        priority: Priority label (e.g. "P0 - Critical", "P1 - High").
        estimated_loe: Level of effort estimate (e.g. "~2-3 weeks (1 developer)").
        dependencies: Comma-separated list of dependencies (e.g. "Epic 0, Epic 4").
        blocks: Comma-separated list of epics this blocks.
        acceptance_criteria: Newline-separated acceptance criteria (TAP-5357).
            Commas inside a criterion are preserved; do not use commas as
            delimiters. Optional leading ``- [ ]`` markers are stripped.
        stories: JSON array of story objects with keys: title, points, description,
            tasks, ac_count.
            Example: [{"title": "Data Models", "points": 3}]
        technical_notes: Comma-separated list of technical notes.
        risks: Comma-separated list of risks (comprehensive style only).
        non_goals: Comma-separated list of out-of-scope items.
        success_metrics: Comma-separated or pipe-delimited success metrics
            (comprehensive only). Example: "MTTR|4h|1h|PagerDuty"
        stakeholders: Comma-separated or pipe-delimited stakeholders
            (comprehensive only). Example: "Owner|Alice|Implementation"
        references: Comma-separated OKR/roadmap references (comprehensive only).
        files: Comma-separated file paths the epic affects. When provided with
            auto_populate, generates per-file analysis (line counts, git history,
            public symbols) and cross-references related epics.
        link_stories: When True, story stubs link to full story files.
        style: Epic style - "minimal", "standard", "comprehensive", or "auto".
            "auto" selects the style based on input complexity (stories, risks,
            files, success_metrics).
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata, etc).
            Default False. On large projects this adds latency (module map
            walk, 8 expert consultations, git history). A 15 s wall-clock
            budget is enforced; steps that exceed it are skipped and partial
            results returned.
        quick_start: When True, infer defaults from the title alone -- goal,
            motivation, 3 story stubs, acceptance criteria, and priority are
            filled in automatically. Explicit parameters always override
            quick-start defaults. Style defaults to "auto" in quick-start mode.
        output_path: Virtual or filesystem path label (relative to project root).
            When empty, defaults to ``linear/epic/EPIC-{number}.md`` (metadata
            only unless ``write_to_disk=True``; slug-derived when ``number`` unset).
        write_to_disk: When False (the default, TAP-1413), the epic body is
            returned inline (or via FileManifest for large bodies) and no
            file is written. Linear is the canonical store for epics, so
            disk drafts are opt-in via ``write_to_disk=True``.
        project_root: Override project root path (default: configured root).

    Returns:
        On success, ``data`` includes ``timing_ms`` (per-phase milliseconds:
        ``render_ms``, ``total_ms``, and when ``auto_populate=True``,
        ``metadata_ms``, ``module_map_ms``, ``git_ms``, ``experts_ms``,
        ``auto_populate_ms``).
    """
    _record_call("docs_generate_epic")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_epic",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.epics import EpicConfig, EpicGenerator, EpicStoryStub

    # Parse comma-separated lists
    dep_list = _split_csv(dependencies)
    blocks_list = _split_csv(blocks)
    ac_list = _split_criteria_list(acceptance_criteria)
    notes_list = _split_csv(technical_notes)
    risks_list = _split_csv(risks)
    ng_list = _split_csv(non_goals)
    sm_list = _split_csv(success_metrics)
    sh_list = _split_csv(stakeholders)
    ref_list = _split_csv(references)

    # Parse stories JSON
    story_list: list[EpicStoryStub] = []
    if stories:
        try:
            story_list = EpicGenerator.parse_stories_json(stories)
        except ValueError as exc:
            return error_response(
                "docs_generate_epic",
                "INVALID_STORIES",
                str(exc),
            )

    # Parse files list (TAP-1552: strip wire-format tags per item)
    files_list = _split_csv(files)

    config = EpicConfig(
        title=_strip_wire_tags(title),
        number=number,
        purpose_and_intent=_strip_wire_tags(purpose_and_intent.strip()),
        goal=_strip_wire_tags(goal),
        motivation=_strip_wire_tags(motivation),
        status=status,
        priority=priority,
        estimated_loe=estimated_loe,
        dependencies=dep_list,
        blocks=blocks_list,
        acceptance_criteria=ac_list,
        stories=story_list,
        technical_notes=notes_list,
        risks=risks_list,
        non_goals=ng_list,
        success_metrics=sm_list,
        stakeholders=sh_list,
        references=ref_list,
        files=files_list,
        link_stories=link_stories,
        style=style,
    )

    generator = EpicGenerator()

    # Pass project_root when auto_populate or files are provided
    needs_root = auto_populate or bool(files_list)

    try:
        content, timing_ms = generator.generate_with_timing(
            config,
            project_root=root if needs_root else None,
            auto_populate=auto_populate,
            quick_start=quick_start,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_epic",
            "GENERATION_ERROR",
            f"Failed to generate epic: {exc}",
        )

    # Auto-compute output_path when not provided
    if output_path.strip():
        target = output_path.strip()
    elif number:
        target = f"linear/epic/EPIC-{number}.md"
    else:
        slug = safe_slug(title) or "untitled"
        target = f"linear/epic/EPIC-{slug}.md"

    # Three-tier output: write-first / inline / manifest.
    # TAP-1413: default write_to_disk=False — Linear is canonical for epics,
    # so don't litter the repo with .md drafts unless the caller opts in.
    out = await finalize_output(
        "docs_generate_epic",
        content,
        target,
        root,
        description=f"Epic planning document: {title}",
        write_to_disk=write_to_disk,
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "number": number,
        "style": style,
        "story_count": len(story_list),
        "auto_populated": auto_populate,
        "quick_start": quick_start,
        "timing_ms": timing_ms,
        **out,
    }

    return success_response(
        "docs_generate_epic",
        elapsed_ms,
        data,
        next_steps=[
            "Use data.content as the epic body — validate with docs_validate_linear_issue, "
            "then save via docs_save_linear_issue → save_issue (Linear is canonical).",
            "Use docs_generate_story to expand individual story stubs into full documents.",
            "Do not write local epic markdown unless write_to_disk=true.",
        ],
    )


async def docs_generate_story(
    title: str,
    epic_number: int = 0,
    story_number: int = 0,
    purpose_and_intent: str = "",
    role: str = "",
    want: str = "",
    so_that: str = "",
    description: str = "",
    points: int = 0,
    size: str = "",
    tasks: str = "",
    acceptance_criteria: str = "",
    assertions: str = "",
    test_cases: str = "",
    dependencies: str = "",
    files: str = "",
    technical_notes: str = "",
    criteria_format: str = "checkbox",
    style: str = "standard",
    inherit_context: bool = True,
    epic_path: str = "",
    auto_populate: bool = False,
    quick_start: bool = False,
    output_path: str = "",
    write_to_disk: bool = False,
    project_root: str = "",
    audience: str = "agent",
) -> dict[str, Any]:
    """Generate a User Story document with acceptance criteria and task breakdown.

    **Default audience is ``"agent"``** (STORY-104.1): the output is the
    5-section Linear-issue template from ``docs/linear/AGENT_ISSUES.md``
    (``## What`` / ``## Where`` / ``## Why`` / ``## Acceptance`` / ``## Refs``)
    and passes ``docs_validate_linear_issue`` with ``agent_ready=true`` by
    construction. Required inputs: ``title`` (≤80 chars), ``files`` with at
    least one ``path/to/file.ext:LINE-RANGE`` anchor, and non-empty
    ``acceptance_criteria``. Optional ``assertions`` (newline-separated
    ``VAL-…`` IDs) adds a ``## Assertions`` section (TAP-5541). Missing required
    inputs produce a structured error.

    Pass ``audience="human"`` for the legacy product-review shape: "As a /
    I want / So that" statement, sizing, task checklist, standard /
    comprehensive styles, INVEST checklist, etc. The ``style``,
    ``criteria_format``, ``auto_populate``, and comprehensive-only params
    apply only to ``audience="human"``.

    When ``auto_populate=True`` (human mode), enriches sections from project analyzers.
    When ``quick_start=True``, infers defaults from the title alone (both modes).

    Args:
        title: Story title (e.g. "Add login form validation").
        epic_number: Parent epic number (e.g. 23 for story numbering as 23.1).
        story_number: Story number within the epic (e.g. 1 for 23.1).
        purpose_and_intent: Required per Epic 75.3. One paragraph: "This story exists so that …".
        role: User role for the story statement (e.g. "developer").
        want: Desired capability (e.g. "to validate login credentials").
        so_that: Benefit/reason (e.g. "invalid logins are rejected").
        description: Detailed description of the story.
        points: Story points estimate.
        size: T-shirt size - "S", "M", "L", or "XL".
        tasks: JSON array of task objects with keys: description, file_path.
            Example: [{"description": "Create model", "file_path": "src/models.py"}]
        acceptance_criteria: Newline-separated acceptance criteria (TAP-5357).
            Commas inside a criterion are preserved; do not use commas as
            delimiters. Optional leading ``- [ ]`` markers are stripped.
        assertions: Optional newline-separated validation-contract IDs
            (``VAL-AREA-###``) for a ``## Assertions`` section (TAP-5541).
        test_cases: Comma-separated list of test cases (comprehensive style only).
        dependencies: Comma-separated list of dependencies.
        files: Comma-separated list of affected file paths.
        technical_notes: Comma-separated list of technical notes.
        criteria_format: Acceptance criteria format - "checkbox" or "gherkin".
        style: Story style - "standard" or "comprehensive".
        inherit_context: When True, skip project metadata in story (inherit from epic).
        epic_path: Parent epic reference for cross-linking (e.g. ``TAP-####`` or
            a relative path when ``write_to_disk=true``).
        auto_populate: Enrich from project analyzers (ModuleMap, Metadata).
        quick_start: When True, infer defaults from the title alone -- role, want,
            so_that, points, size, tasks, and acceptance criteria are filled in
            automatically. Explicit parameters always override quick-start defaults.
        output_path: Virtual or filesystem path label (relative to project root).
            When empty, defaults to
            ``linear/story/STORY-{epic}.{story}.md`` (metadata only unless
            ``write_to_disk=True``; slug-derived when numbers are unset).
        write_to_disk: When False (the default, TAP-1413), the story body is
            returned inline (or via FileManifest for large bodies) and no
            file is written. Linear is the canonical store for stories, so
            disk drafts are opt-in via ``write_to_disk=True``.
        project_root: Override project root path (default: configured root).
        audience: Output target — ``"agent"`` (default) emits the 5-section
            Linear-issue template with validation enforcement;
            ``"human"`` emits the full product-review shape.
    """
    _record_call("docs_generate_story")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_story",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    import json as json_mod

    from docs_mcp.generators.stories import StoryConfig, StoryGenerator, StoryTask

    # Parse list params — AC is newline-split (TAP-5357); others stay CSV.
    ac_list = _split_criteria_list(acceptance_criteria)
    assertion_list = _split_criteria_list(assertions)
    tc_list = _split_csv(test_cases)
    dep_list = _split_csv(dependencies)
    file_list = _split_csv(files)
    notes_list = _split_csv(technical_notes)

    # Parse tasks JSON (or pre-parsed list from MCP clients)
    task_list: list[StoryTask] = []
    if tasks:
        try:
            raw: Any = tasks if isinstance(tasks, list) else json_mod.loads(tasks)
            if not isinstance(raw, list):
                return error_response(
                    "docs_generate_story",
                    "INVALID_TASKS",
                    "Tasks JSON must be a list of objects",
                )
            task_list.extend(
                StoryTask(
                    description=str(item.get("description", "")),
                    file_path=str(item.get("file_path", "")),
                )
                for item in raw
                if isinstance(item, dict)
            )
        except json_mod.JSONDecodeError as exc:
            return error_response(
                "docs_generate_story",
                "INVALID_TASKS",
                f"Invalid JSON for tasks: {exc}",
            )

    config = StoryConfig(
        title=_strip_wire_tags(title),
        epic_number=epic_number,
        story_number=story_number,
        purpose_and_intent=_strip_wire_tags(purpose_and_intent.strip()),
        role=_strip_wire_tags(role),
        want=_strip_wire_tags(want),
        so_that=_strip_wire_tags(so_that),
        description=_strip_wire_tags(description),
        points=points,
        size=size,
        tasks=task_list,
        acceptance_criteria=ac_list,
        assertions=assertion_list,
        test_cases=tc_list,
        dependencies=dep_list,
        files=file_list,
        technical_notes=notes_list,
        criteria_format=criteria_format,
        style=style,
        inherit_context=inherit_context,
        epic_path=epic_path,
        audience=audience,
    )

    generator = StoryGenerator()

    try:
        content = generator.generate(
            config,
            project_root=root if auto_populate else None,
            auto_populate=auto_populate,
            quick_start=quick_start,
            output_path=output_path or "",
        )
    except ValueError as exc:
        # STORY-104.1: agent audience raises ValueError on template violations.
        # Surface these as a structured INPUT_INVALID error so the caller gets
        # actionable guidance (which field failed and how to fix it).
        return error_response(
            "docs_generate_story",
            "INPUT_INVALID",
            str(exc),
        )
    except Exception as exc:
        return error_response(
            "docs_generate_story",
            "GENERATION_ERROR",
            f"Failed to generate story: {exc}",
        )

    # Auto-compute output_path when not provided
    if output_path.strip():
        target = output_path.strip()
    elif epic_number and story_number:
        target = f"linear/story/STORY-{epic_number}.{story_number}.md"
    else:
        slug = safe_slug(title) or "untitled"
        target = f"linear/story/STORY-{slug}.md"

    # Three-tier output: write-first / inline / manifest.
    # TAP-1413: default write_to_disk=False — Linear is canonical for stories,
    # so don't litter the repo with .md drafts unless the caller opts in.
    out = await finalize_output(
        "docs_generate_story",
        content,
        target,
        root,
        description=f"User story: {title}",
        write_to_disk=write_to_disk,
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "title": title,
        "epic_number": epic_number,
        "story_number": story_number,
        "audience": audience,
        "style": style,
        "criteria_format": criteria_format,
        "task_count": len(task_list),
        "auto_populated": auto_populate,
        "quick_start": quick_start,
        **out,
    }

    return success_response(
        "docs_generate_story",
        elapsed_ms,
        data,
        next_steps=[
            "Use data.content as the story description — validate with "
            "docs_validate_linear_issue, then save via docs_save_linear_issue → save_issue.",
            "Use docs_generate_epic to create the parent epic in Linear if not yet filed.",
            "Do not write local story markdown unless write_to_disk=true.",
        ],
    )


async def docs_generate_prompt(
    name: str,
    when_to_use: str = "",
    purpose_and_intent: str = "",
    task: str = "",
    success_criteria: str = "",
    context_files: str = "",
    reference_notes: str = "",
    rules: str = "",
    conversation_first: bool = False,
    plan_steps: int = 0,
    alignment_required: bool = False,
    allowed_tools: str = "",
    output_format: str = "",
    dont: str = "",
    style: str = "standard",
    compact_llm_view: bool = False,
    output_path: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate a prompt artifact (Epic 75). LLM-facing prompt doc with docsmcp markers.

    Creates a structured prompt with Purpose & Intent (required), task, context files,
    success brief, rules, optional conversation/plan/alignment, allowed tools, output format.
    When compact_llm_view=True, emits a token-efficient view (goal + criteria + steps + rules)
    targeting ≤~1.5K tokens (Epic 75.4).

    Args:
        name: Prompt name (e.g. "quality-gate-workflow").
        when_to_use: When and why this prompt is used.
        purpose_and_intent: Required. One paragraph: "This prompt is for … so that …".
        task: "I want to [TASK] so that [SUCCESS CRITERIA]."
        success_criteria: Definition of success.
        context_files: JSON array of {"path": "...", "description": "..."}.
        reference_notes: Optional reference / blueprint notes.
        rules: Standards, constraints, landmines.
        conversation_first: If True, add "ask clarifying questions first" section.
        plan_steps: Number of plan steps (0 = omit plan section).
        alignment_required: If True, add "Only begin once we've aligned" section.
        allowed_tools: Comma-separated list of MCP tool names.
        output_format: Expected output format (e.g. JSON schema, markdown structure).
        dont: Comma-separated list of "don't" items.
        style: "standard" or "comprehensive".
        compact_llm_view: When True, generate compact view only (≤~1.5K tokens) for LLM context.
        output_path: File path to write (relative to project root). Empty = docs/prompts/{name}.md.
        project_root: Override project root.
    """
    _record_call("docs_generate_prompt")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_prompt",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    import json as json_mod

    from docs_mcp.generators.prompts import (
        ContextFileEntry,
        PromptConfig,
        PromptGenerator,
    )

    if not name.strip():
        return error_response(
            "docs_generate_prompt",
            "INVALID_NAME",
            "name is required",
        )

    purpose = (
        purpose_and_intent.strip()
        or "This prompt is for the given task so that success criteria are met."
    )

    cf_list: list[ContextFileEntry] = []
    if context_files:
        try:
            raw = json_mod.loads(context_files) if isinstance(context_files, str) else context_files
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        cf_list.append(
                            ContextFileEntry(
                                path=item.get("path", ""), description=item.get("description", "")
                            )
                        )
                    else:
                        cf_list.append(ContextFileEntry(path=str(item), description=""))
        except (json_mod.JSONDecodeError, TypeError):
            pass

    tools_list = [t.strip() for t in allowed_tools.split(",") if t.strip()] if allowed_tools else []
    dont_list = [d.strip() for d in dont.split(",") if d.strip()] if dont else []

    config = PromptConfig(
        name=name.strip(),
        when_to_use=when_to_use.strip(),
        purpose_and_intent=purpose,
        task=task.strip(),
        success_criteria=success_criteria.strip(),
        context_files=cf_list,
        reference_notes=reference_notes.strip(),
        success_brief=None,
        rules=rules.strip(),
        conversation_first=conversation_first,
        plan_steps=plan_steps or False,
        alignment_required=alignment_required,
        allowed_tools=tools_list,
        output_format=output_format.strip(),
        dont=dont_list,
        style=style if style in ("standard", "comprehensive") else "standard",
    )

    gen = PromptGenerator()
    content = gen.generate_compact(config) if compact_llm_view else gen.generate(config)

    # Auto-compute output_path when not provided
    slug = name.strip().replace(" ", "-").lower()
    if not slug.endswith(".md"):
        slug += ".md"
    rel = output_path.strip() or f"docs/prompts/{slug}"
    if not rel.endswith(".md"):
        rel += ".md"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_prompt",
        content,
        rel,
        root,
        description=f"Prompt template: {name}",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data: dict[str, Any] = {
        "name": name,
        "style": style,
        **out,
    }

    return success_response(
        "docs_generate_prompt",
        elapsed_ms,
        data,
        next_steps=[
            "Review the generated prompt and refine Purpose & Intent and rules.",
            "Use as context for the LLM or register as an MCP prompt template.",
        ],
    )

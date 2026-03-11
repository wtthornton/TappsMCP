# LLM Artifact Structure: Common, Epic, Story, Prompt

**Status:** Proposed  
**Date:** 2026-03-11  
**Purpose:** Unified schema and MCP tool/data guidance for epic, story, and prompt artifacts so they share a common structure and consistent TappsMCP/DocsMCP usage.

---

## 1. Design principles

- **Common** = shared sections and fields across all three artifact types; the LLM always sees a consistent shape.
- **Purpose & Intent (required)** = every epic, story, and prompt artifact MUST include a **Purpose & Intent** section that states why we are doing this (epic) or why this story/prompt exists (story/prompt). This reduces drift and aligns humans and tooling on the same rationale.
- **Epic / Story / Prompt** = each adds type-specific sections on top of Common.
- **Pre-approved .md** = all three are written out as markdown (and optionally registered as MCP prompts where applicable); they become context for the LLM.
- **Tool and data** = for each type we specify which TappsMCP and DocsMCP tools to call and what data to use or produce.

---

## 2. Common structure (shared by all)

All artifacts include these conceptual sections. Field names and rendering may vary by type.

| Section | Description | Example content |
|--------|-------------|-----------------|
| **Identity** | Title, optional id, status | `Epic 74`, `Story 74.1`, `Prompt: quality-gate-workflow` |
| **Purpose & Intent** | **Required.** Why we are doing this (epic) or why this story/prompt exists. Single paragraph. | Epic: "We are doing this so that …" Story: "This story exists so that …" Prompt: "This prompt is for … so that …" |
| **Purpose / Goal** | What we want and why (task + success) | "I want to [TASK] so that [SUCCESS CRITERIA]" or goal + motivation |
| **Context / Constraints** | Audience, scope, standards, "read these first" | Context files list, rules, non-goals, technical notes |
| **Success / Done** | Definition of done, acceptance or completion criteria | Checklist or list of criteria; "success means …" |
| **Steps / Scope** | Ordered work items or instructions | Epic: child stories; Story: tasks; Prompt: instructions or tool sequence |
| **Out of scope / Don't** | What not to do | Non-goals, "does NOT sound like", landmines |
| **Expert enrichment** | Domain guidance (security, architecture, testing, etc.) | Optional; from TappsMCP experts or DocsMCP/TappsMCP integration |
| **Markers** | SmartMerger / tooling | `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->` for machine-readable sections |

**Purpose & Intent convention:**

- **Epics:** Include a `## Purpose & Intent` section wrapped in `<!-- docsmcp:start:purpose-intent -->` … `<!-- docsmcp:end:purpose-intent -->`. One paragraph starting with "We are doing this so that …" followed by the intent and outcomes.
- **Stories:** Include a `## Purpose & Intent` heading and one paragraph starting with "This story exists so that …" (or equivalent) explaining why the story exists and what it enables.
- **Prompts:** Include a `## Purpose & Intent` (or equivalent) stating when and why the prompt is used (e.g. "This prompt is for … so that …"). Required so generated prompt artifacts carry the same rationale as epics and stories.

**Data used (common):**

- **tapps_project_profile** — project root, tech stack, constraints (for context/constraints).
- **tapps_consult_expert** (or tapps_core `consult_expert`) — domain guidance for security, architecture, testing, api-design, code-quality, etc.; used to fill expert enrichment.
- **tapps_list_experts** — optional; to choose which domains to consult.

**DocsMCP (common):**

- **docs_session_start** — project type, doc inventory (optional; when generating in a session).
- **docs_module_map** — optional; project structure summary for technical notes / context.

---

## 3. Epic structure (Common + epic-specific)

**Common:** Identity (title, number, status, priority, LOE), **Purpose & Intent (required)**, Purpose (goal, motivation), Success (acceptance criteria), Context (dependencies, blocks, technical notes), Out of scope (non-goals), Expert enrichment. Epics MUST include a Purpose & Intent section with docsmcp markers (see §2).

**Epic-specific:**

| Section | Description |
|--------|-------------|
| **Stories** | Child story stubs (title, points, optional description/tasks) |
| **Success metrics** | Optional; measurable outcomes (comprehensive style) |
| **Stakeholders / References** | Optional; links and refs (comprehensive) |
| **Implementation order** | Optional; suggested story order |
| **Risk assessment** | Optional; risks and mitigations (comprehensive) |
| **Files affected** | Optional; file hints and related epics (when `files` provided) |

**TappsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **tapps_project_profile** | `project_root` → tech stack, project type; feed into context/technical notes. |
| **tapps_consult_expert** | For epic title/goal: security, architecture, testing, performance, devops, code-quality, api-design, observability; store in expert enrichment. |
| **tapps_list_experts** | Optional; to list domains before consult. |
| **tapps_validate_changed** | Not typically for generating epic text; use when validating implementation of this epic (e.g. changed files under epic scope). |
| **tapps_checklist** | Not for generation; use when closing work that implemented this epic. |

**DocsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **docs_generate_epic** | Primary generator: EpicConfig (title, goal, motivation, acceptance_criteria, stories, technical_notes, risks, non_goals, style, files, …). Uses internal analyzers (metadata, module_map, git_history) and expert enrichment. |
| **docs_project_scan** | Optional; doc inventory and completeness for context. |
| **docs_git_summary** | Optional; recent commits for motivation / scope. |
| **docs_module_map** | Optional; when `files` provided, for file hints and related epics. |

**Output:** One epic .md file (e.g. `EPIC-NN-NAME.md`) with docsmcp markers; can reference story stubs and link to `docs_generate_story` for expansion.

---

## 4. Story structure (Common + story-specific)

**Common:** Identity (title, epic.story number, role/want/so_that), **Purpose & Intent (required)**, Purpose (user story statement, description), Success (acceptance criteria, definition of done), Context (technical notes, dependencies), Steps (tasks), Expert enrichment. Stories MUST include a `## Purpose & Intent` section (see §2).

**Story-specific:**

| Section | Description |
|--------|-------------|
| **User story statement** | "As a [role], I want [want] so that [so_that]." |
| **Sizing** | Points, S/M/L/XL |
| **Tasks** | Ordered implementation tasks (description, optional file_path) |
| **Test cases** | Optional (comprehensive) |
| **INVEST checklist** | Optional; auto-assessed from story content (comprehensive) |
| **Files** | Optional; files touched by this story |
| **Epic link** | Optional; epic_path or parent epic id for context |

**TappsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **tapps_project_profile** | Project context for technical notes and constraints. |
| **tapps_consult_expert** | Same domains as epic; question built from story title/description; feed into technical notes / expert recommendations. |
| **tapps_impact_analysis** | Optional; when story touches existing modules (file_path from story tasks). |
| **tapps_lookup_docs** | Optional; when story involves specific libraries (library names from description/tasks). |

**DocsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **docs_generate_story** | Primary generator: StoryConfig (title, epic_number, story_number, role, want, so_that, description, points, size, tasks, acceptance_criteria, test_cases, dependencies, files, technical_notes, criteria_format, style, inherit_context, epic_path). Uses expert enrichment and optional module_map for project structure. |
| **docs_module_map** | Optional; for technical notes when not inheriting from epic. |
| **docs_generate_epic** | When parent epic does not exist yet; create epic first then story. |

**Output:** One story .md file (e.g. `story-NN.M-NAME.md`) with docsmcp markers; may reference parent epic.

---

## 5. Prompt structure (Common + prompt-specific)

**Common:** Identity (name, when_to_use), **Purpose & Intent (required)**, Purpose (task + success), Context (context files, rules), Success (completion criteria, expected output), Out of scope (don't), Expert enrichment (optional). Prompt artifacts MUST include a Purpose & Intent section so that generated prompts carry the same rationale as epics and stories (see §2).

**Prompt-specific (aligned with "Anatomy of a Claude prompt"):**

| Section | Description |
|--------|-------------|
| **Purpose & Intent** | **Required.** One paragraph: when and why this prompt is used (e.g. "This prompt is for … so that …"). |
| **Task** | "I want to [TASK] so that [SUCCESS CRITERIA]." |
| **Context files** | "First, read these files completely before responding." List: `[filename.md] — [what it contains]`. |
| **Reference** | Optional; "[Upload reference or paste here]; reverse-engineer blueprint: patterns, tone, structure, rules as Always/Never statements." |
| **Success brief** | Output type + length; recipient reaction; "does NOT sound like"; "success means" (sign/approve/reply/action). |
| **Rules** | "My context file contains standards, constraints, landmines. Read fully before starting. If you're about to break a rule, stop and tell me." |
| **Conversation** | Optional; "Do not start executing yet; ask clarifying questions (e.g. AskUserQuestion) to refine approach step by step." |
| **Plan** | Optional; "Before writing: list the 3 rules from my context file that matter most; then give execution plan (5 steps max)." |
| **Alignment** | Optional; "Only begin work once we've aligned." |
| **Allowed tools** | Optional; explicit MCP tool list and order (e.g. tapps_session_start → tapps_quick_check → tapps_validate_changed). |
| **Output format** | Optional; e.g. JSON schema, markdown structure, or "return X with keys Y, Z." |

**TappsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **tapps_project_profile** | Project root and constraints; inject into "Rules" or "Context files" when prompt is project-scoped. |
| **tapps_consult_expert** | Optional; when prompt needs domain rules (e.g. security, code-quality); add as "Always/Never" or rules block. |
| **tapps_list_experts** | Optional; to pick domains for rule enrichment. |
| **tapps_server_info** | Optional; to list available tools and capabilities for "Allowed tools" section. |
| **tapps_session_start** | Not for generating prompt text; use at runtime when this prompt is executed. |
| **tapps_workflow** / **tapps_pipeline** (prompts) | Reference existing workflow prompts when building "Allowed tools" or "Plan" for a new prompt artifact. |

**DocsMCP calls and data:**

| Tool | When / data used |
|------|-------------------|
| **docs_generate_prompt** | **Proposed.** Primary generator: PromptConfig (name, when_to_use, purpose_and_intent, task, success_criteria, context_files, reference_notes, success_brief, rules, conversation_first, plan_steps, alignment_required, allowed_tools, output_format, dont, style). Would reuse Common + prompt-specific sections and docsmcp markers; purpose_and_intent is required. |
| **docs_project_scan** | Optional; to suggest context files (e.g. existing epic/story .md, README, ADRs). |
| **docs_module_map** | Optional; when prompt is tied to code structure (e.g. "implement in modules X, Y"). |

**Output:** One prompt .md file (e.g. `prompt-quality-gate-workflow.md`) with docsmcp markers; can be loaded as context for the LLM or (future) registered as an MCP prompt template.

**Note:** `docs_generate_prompt` does not exist today; this structure defines the contract for a future tool in DocsMCP (or TappsMCP).

---

## 6. Summary: tools and data by artifact

| Artifact | Primary generator | TappsMCP (data/tools used) | DocsMCP (data/tools used) |
|----------|-------------------|----------------------------|----------------------------|
| **Common** | — | project_profile, consult_expert, list_experts | session_start (optional), module_map (optional) |
| **Epic** | docs_generate_epic | project_profile, consult_expert (multi-domain) | generate_epic (EpicConfig + analyzers), project_scan, git_summary, module_map (optional) |
| **Story** | docs_generate_story | project_profile, consult_expert, impact_analysis (optional), lookup_docs (optional) | generate_story (StoryConfig + enrichment), module_map (optional), generate_epic if parent missing |
| **Prompt** | docs_generate_prompt (proposed) | project_profile, consult_expert (optional), server_info (optional), workflow/pipeline prompts as reference | generate_prompt (PromptConfig), project_scan (optional), module_map (optional) |

---

## 7. Data flow (high level)

```
                    ┌─────────────────────────────────────────────────┐
                    │              Common data sources                 │
                    │  tapps_project_profile, tapps_consult_expert     │
                    │  docs_session_start, docs_module_map (optional)  │
                    └─────────────────────┬───────────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         ▼                                ▼                                ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│ Epic            │            │ Story           │            │ Prompt          │
│ docs_generate_  │            │ docs_generate_  │            │ docs_generate_  │
│ epic(EpicConfig)│            │ story(StoryConfig)            │ prompt(PromptConfig)│
│ + analyzers     │            │ + enrichment    │            │ (proposed)      │
│ + experts       │            │ + experts       │            │ + experts (opt) │
└────────┬────────┘            └────────┬────────┘            └────────┬────────┘
         │                              │                              │
         ▼                              ▼                              ▼
   EPIC-NN.md                    story-N.M.md                 prompt-name.md
   (stories as stubs)            (tasks, AC, DoD)              (task, context, rules,
                                                                 success brief, plan)
```

---

## 8. Compact LLM view (Epic 75.4)

An optional **compact LLM view** is available for prompt artifacts (and can be extended to epic/story). It emits only: identity, purpose/goal, success criteria, steps, rules, don’t—targeting **≤~1.5K tokens** so context stays within recommended limits (see [2026-LLM-PROMPT-CONTEXT-RESEARCH.md](research/2026-LLM-PROMPT-CONTEXT-RESEARCH.md)). Use `docs_generate_prompt(..., compact_llm_view=True)` to generate the compact view; the full .md remains the source of truth for humans.

---

## 9. Common schema reference

A single **Common schema** table and config mapping is maintained in [LLM-ARTIFACT-COMMON-SCHEMA.md](LLM-ARTIFACT-COMMON-SCHEMA.md). It lists: Identity, Purpose & Intent (required), Purpose/Goal, Success/Done, Context/Constraints, Steps/Scope, Out of scope/Don't, Expert enrichment, and maps each to EpicConfig, StoryConfig, and PromptConfig. Use it when aligning or extending epic, story, or prompt generators.

---

## 10. Next steps

1. **Implement PromptConfig + PromptGenerator** in DocsMCP (or TappsMCP) with the prompt-specific sections above; emit .md with docsmcp markers.
2. **Add docs_generate_prompt** MCP tool that accepts PromptConfig (or equivalent params) and writes the prompt artifact.
3. **Optionally** register generated prompt .md as an MCP prompt (e.g. by path or by name) so clients can request it by name.
4. **Reuse expert_utils** (and same domain list as epic/story) for prompt expert enrichment when "Rules" or "Reference" are populated from experts.
5. **Document** this structure in AGENTS.md and planning epics so LLM and human authors use the same Common + type-specific sections and tool calls.

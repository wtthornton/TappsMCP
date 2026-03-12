# Story 75.3: Common schema documentation and epic/story alignment

**Epic:** [EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION](../EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION.md)  
**Priority:** P2 | **LOE:** 1–2 days

## Problem

The Common schema (identity, purpose, success, constraints, steps, out-of-scope, expert enrichment) is described in the design doc but not yet reflected in a single place that epic, story, and prompt generators can reference. Epic and story generators may use slightly different section names or ordering; we should document the common shape and align naming where it helps.

## Purpose & Intent

This story exists so that **everyone (humans and tooling) shares one mental model** of what epic, story, and prompt artifacts contain. A single documented Common schema and explicit mapping to configs reduces drift, makes generators easier to extend, and gives AGENTS.md a clear pointer for when to use which tools when generating artifacts.

## Tasks

- [x] Add a short “Common schema” section or table to the design doc (or to a new docs/planning/LLM-ARTIFACT-COMMON-SCHEMA.md) that lists: Identity, Purpose/Goal, Success/Done, Context/Constraints, Steps/Scope, Out of scope/Don’t, Expert enrichment. Map each to EpicConfig, StoryConfig, and PromptConfig field names.
- [x] Ensure the documented Common schema explicitly requires **Purpose & Intent** for epic, story, and prompt (see design doc §2); generators must emit this section.
- [x] Review EpicGenerator and StoryGenerator section order and names; if any section is missing a docsmcp marker or is named inconsistently, add a one-line note in the design doc (no mandatory code change unless trivial).
- [x] In AGENTS.md or docs/MCP_TOOL_REFERENCE.md (if present), add a pointer to the LLM artifact structure doc for “when generating epic, story, or prompt artifacts” and list recommended TappsMCP/DocsMCP calls (tapps_project_profile, tapps_consult_expert, docs_generate_epic, docs_generate_story, docs_generate_prompt).

## Acceptance criteria

- [x] Common schema is documented with explicit mapping to Epic/Story/Prompt configs, and **Purpose & Intent** is required for all three artifact types (epic, story, prompt) with generators emitting it.
- [x] Epic and story generator section names are either aligned or the delta is documented.
- [x] AGENTS.md or equivalent references the artifact structure and tool guidance.

## Files

- `docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md` (or new LLM-ARTIFACT-COMMON-SCHEMA.md)
- `AGENTS.md` or docs in packages/docs-mcp
- `packages/docs-mcp/src/docs_mcp/generators/epics.py`, `stories.py` (review section order/names only)

## Dependencies

- Stories 75.1 and 75.2 not required; this is doc + alignment. Can run in parallel with 75.2.

## References

- Design doc: docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md §2 Common structure

# LLM Artifact Common Schema

**Status:** Active (Epic 75.3)  
**Date:** 2026-03-11  
**Purpose:** Single reference for the shared structure of epic, story, and prompt artifacts. All three generators (EpicGenerator, StoryGenerator, PromptGenerator) align to this schema so that section names and required sections are consistent.

---

## Common schema (shared by all three)

Every artifact type includes these conceptual sections. **Purpose & Intent is required for all three** (see [LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md](LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md) §2).

| Common section       | Description                    | EpicConfig field(s)     | StoryConfig field(s)     | PromptConfig field(s)   |
|----------------------|--------------------------------|--------------------------|---------------------------|--------------------------|
| **Identity**         | Title, id, status              | title, number, status   | title, epic_number, story_number | name, when_to_use |
| **Purpose & Intent** | **Required.** Why we are doing this / why this story/prompt exists. One paragraph. | purpose_and_intent (new in 75.3) | purpose_and_intent (new in 75.3) | purpose_and_intent |
| **Purpose / Goal**   | What we want and why           | goal, motivation        | role, want, so_that, description | task, success_criteria |
| **Success / Done**   | Definition of done, acceptance criteria | acceptance_criteria | acceptance_criteria, definition_of_done (rendered) | success_brief, success_criteria |
| **Context / Constraints** | Audience, scope, standards | technical_notes, dependencies | technical_notes, dependencies | context_files, rules |
| **Steps / Scope**    | Ordered work or instructions  | stories (child stubs)   | tasks                     | (plan_steps, allowed_tools) |
| **Out of scope / Don't** | What not to do            | non_goals               | (implicit in DoD)         | dont                    |
| **Expert enrichment** | Domain guidance (optional)   | technical_notes (expert block) | technical_notes (expert block) | rules (optional expert) |
| **Markers**          | Machine-readable sections     | `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->` | Same | Same |

---

## Purpose & Intent (required)

- **Epic:** Section heading `## Purpose & Intent`, marker `purpose-intent`. One paragraph starting with "We are doing this so that …". Emitted by EpicGenerator when `purpose_and_intent` is set (or placeholder if empty for backward compat).
- **Story:** Section heading `## Purpose & Intent`, marker `purpose-intent`. One paragraph starting with "This story exists so that …". Emitted by StoryGenerator when `purpose_and_intent` is set (or placeholder if empty).
- **Prompt:** Section heading `## Purpose & Intent`, marker `purpose-intent`. One paragraph "This prompt is for … so that …". Emitted by PromptGenerator (already implemented).

---

## Generator section order (reference)

**Epic:** metadata → **purpose-intent** → goal → motivation → acceptance-criteria → stories → technical-notes → non-goals → (comprehensive: success-metrics, stakeholders, references, implementation-order, risk-assessment, files-affected).

**Story:** title → user-story → sizing → **purpose-intent** → description → files → tasks → acceptance-criteria → definition-of-done → (comprehensive: test-cases, technical-notes, dependencies, invest).

**Prompt:** metadata → purpose-intent → task → context-files → reference → success-brief → rules → conversation → plan → alignment → allowed-tools → output-format → dont.

---

## References

- Design doc: [LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md](LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md)
- Epic generator: `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- Story generator: `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- Prompt generator: `packages/docs-mcp/src/docs_mcp/generators/prompts.py`

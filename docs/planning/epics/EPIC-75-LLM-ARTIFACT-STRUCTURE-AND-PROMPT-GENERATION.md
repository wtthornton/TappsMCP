# Epic 75: LLM Artifact Structure & Prompt Generation

<!-- docsmcp:start:metadata -->
- **Status:** Proposed
- **Priority:** P2
- **Estimated LOE:** ~3–4 weeks (1 developer)
- **Dependencies:** DocsMCP epics (generate_epic, generate_story), design doc LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md
- **Blocks:** None
- **Source:** docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md, 2026 prompt/context research
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Implement a unified LLM-facing artifact schema (Common, Epic, Story, Prompt) and add a prompt generator so that epic, story, and prompt artifacts share consistent structure and can be generated with aligned TappsMCP/DocsMCP tool usage. Deliver `docs_generate_prompt` (or equivalent) and optional compact “LLM view” for token-efficient context.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

1. **Consistency:** Epic and story generators already overlap (goal, acceptance criteria, technical notes, experts). Adding a first-class “prompt” artifact type with the same conceptual sections (purpose, success, constraints, steps) gives LLMs a single, predictable shape for all three.
2. **Prompt as artifact:** Prompts that become LLM context (e.g. “Anatomy of a Claude prompt”) are today written by hand or in code. A generator that emits prompt .md (task, context files, success brief, rules, plan, alignment) supports pre-approved, versioned prompt docs.
3. **Token efficiency:** 2026 research recommends core instructions ≤~1.5K tokens and critical content at start/end. A “compact LLM view” for epic/story/prompt (goal + criteria + steps + rules) supports that without changing the full human-readable doc.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that **epic, story, and prompt artifacts share one predictable shape** and can be generated and consumed by LLMs and tooling in a consistent way. Today epic and story generators exist but prompts are ad hoc; LLMs see inconsistent sections and no single "prompt as artifact" path. By defining a Common schema and adding a first-class prompt generator we enable: (1) versioned, pre-approved prompt docs that can be injected as context; (2) aligned TappsMCP/DocsMCP tool usage so the same data sources (project profile, experts) feed all three artifact types; and (3) optional token-efficient views so context stays within recommended limits. The intent is to make planning and execution artifacts first-class, generator-driven, and LLM-optimized—reducing drift and improving reliability when humans and agents collaborate on epics, stories, and prompts.
<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [ ] Prompt artifact type is defined with a config model (PromptConfig) and sections aligned to the design doc (task, context files, success brief, rules, conversation, plan, alignment, allowed tools, output format).
- [ ] `docs_generate_prompt` MCP tool exists (DocsMCP or TappsMCP) and writes prompt .md with docsmcp markers; optional expert enrichment reuses epic/story domain list.
- [ ] Common schema (identity, **purpose & intent (required for all three)**, purpose, success, constraints, steps, out-of-scope, expert enrichment) is documented and reflected in epic/story/prompt generator section names where missing; all generated artifacts include a Purpose & Intent section per design doc §2.
- [ ] Optional: compact “LLM view” generator or flag for epic/story/prompt that emits ≤~1.5K tokens (goal + criteria + steps + rules) for use as LLM context.
- [ ] TappsMCP/DocsMCP tool and data guidance from the design doc is documented in AGENTS.md or a dedicated doc; no breaking changes to existing docs_generate_epic or docs_generate_story.
- [ ] New/updated tests for prompt generator; existing epic/story tests pass.
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE |
|-------|--------|----------|-----|
| [75.1](EPIC-75/story-75.1-prompt-config-and-schema.md) | PromptConfig model and prompt schema | P2 | 2–3 days |
| [75.2](EPIC-75/story-75.2-prompt-generator-and-docs-generate-prompt.md) | PromptGenerator and docs_generate_prompt tool | P2 | 3–4 days |
| [75.3](EPIC-75/story-75.3-common-schema-docs-and-alignment.md) | Common schema documentation and epic/story alignment | P2 | 1–2 days |
| [75.4](EPIC-75/story-75.4-compact-llm-view.md) | Optional compact LLM view for epic/story/prompt | P3 | 2–3 days |

<!-- docsmcp:end:stories -->

## Implementation notes

| Item | Location |
|------|----------|
| PromptConfig / PromptGenerator | `packages/docs-mcp/src/docs_mcp/generators/prompts.py` (new) |
| docs_generate_prompt tool | `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (add handler alongside docs_generate_epic, docs_generate_story) |
| Epic/Story config models | `packages/docs-mcp/src/docs_mcp/generators/epics.py` (EpicConfig), `stories.py` (StoryConfig) |
| Docsmcp markers | `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->`; section names per design doc |
| Tests | `packages/docs-mcp/tests/unit/test_prompts.py` (new); extend test_gen_tools for docs_generate_prompt |
| Tool registration | DocsMCP server auto-loads server_gen_tools; ensure new tool is exported and listed in server tool list |

**Story order:** 75.1 → 75.2 (PromptConfig required for generator and tool); 75.3 and 75.4 can run in parallel after 75.2.

## References

- **Design:** docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md
- **Research:** docs/planning/research/2026-LLM-PROMPT-CONTEXT-RESEARCH.md
- **Existing:** docs_generate_epic (EpicConfig), docs_generate_story (StoryConfig) in packages/docs-mcp; server_gen_tools.py

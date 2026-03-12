# Story 75.1: PromptConfig model and prompt schema

**Epic:** [EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION](../EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION.md)  
**Priority:** P2 | **LOE:** 2–3 days

## Problem

There is no first-class config model or schema for a “prompt” artifact. The design doc defines prompt-specific sections (task, context files, reference, success brief, rules, conversation, plan, alignment, allowed tools, output format). We need a Pydantic model and a clear section list so the generator and MCP tool can accept structured input.

## Purpose & Intent

This story exists so that **prompts become a first-class, schema-driven artifact** like epics and stories. Without PromptConfig, we cannot generate or validate prompt docs consistently; this story is the foundation for docs_generate_prompt and for shared tool/data guidance across all three artifact types.

## Tasks

- [ ] Add `PromptConfig` (or equivalent) in docs-mcp generators (e.g. `generators/prompts.py` or alongside epics.py) with fields: name, when_to_use, task, success_criteria, context_files (list of (path, description)), reference_notes, success_brief (output type, recipient reaction, does_not_sound_like, success_means), rules, conversation_first (bool), plan_steps (bool/int), alignment_required (bool), allowed_tools (list), output_format, dont (list), style (standard/comprehensive).
- [ ] Document the schema in the design doc or in the module docstring; ensure field names match LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md.
- [ ] Add unit tests that build PromptConfig with minimal and full payloads and assert validation (required vs optional).

## Acceptance criteria

- [ ] PromptConfig exists and is used as the single source of truth for prompt generation input.
- [ ] All sections from the design doc (task, context files, success brief, rules, conversation, plan, alignment, allowed tools, output format, don’t) are representable.
- [ ] Tests cover at least: minimal config (name + task + success_criteria), full config, invalid values rejected.

## Files

- `packages/docs-mcp/src/docs_mcp/generators/prompts.py` (new) or equivalent
- `packages/docs-mcp/tests/unit/test_prompts.py` (new)
- `docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md` (optional small update)

## References

- Design doc §4 Prompt structure: docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md
- Existing config models: `packages/docs-mcp/src/docs_mcp/generators/epics.py` (EpicConfig), `stories.py` (StoryConfig) for field style

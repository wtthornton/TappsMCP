# Story 75.4: Optional compact LLM view for epic/story/prompt

**Epic:** [EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION](../EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION.md)  
**Priority:** P3 | **LOE:** 2–3 days

## Problem

2026 research recommends keeping core LLM context under ~1.5K tokens and placing critical content at start/end. Full epic, story, and prompt .md files can exceed that. An optional “compact LLM view” (goal + criteria + steps + rules only) would let consumers feed a token-efficient version into the model while keeping the full file for humans.

## Purpose & Intent

This story exists so that **artifact context stays within recommended token budgets** without losing critical content. Full epic/story/prompt docs can exceed 1.5K tokens; a compact view preserves purpose, success, steps, and rules for reliable model behavior while the full doc remains the source of truth for humans.

## Tasks

- [x] Define a compact view format: identity (title/id), purpose/goal (single paragraph), success criteria (bulleted), steps/instructions (bulleted), rules/constraints (bulleted), optional “don’t” (bulleted). No narrative, no comprehensive sections.
- [x] Add an optional parameter to EpicGenerator, StoryGenerator, and PromptGenerator (e.g. `compact_llm_view: bool = False`) or a separate function that, given an existing full .md or a config, emits the compact view (≤~1.5K tokens target). Optionally expose via a small CLI or MCP helper (e.g. “return compact view of this epic”).
- [x] Document in the design doc and in 2026-LLM-PROMPT-CONTEXT-RESEARCH.md that the compact view exists and when to use it.
- [x] Add tests that assert compact output contains required sections and is under a token budget (e.g. 2000 tokens) when run on a sample epic/story/prompt.

## Acceptance criteria

- [x] Compact view is defined and implementable for epic, story, and prompt.
- [x] At least one generator (e.g. prompt) supports emitting compact view; epic/story can be follow-up.
- [x] Token budget is documented and tested (sample under 2K tokens).
- [x] No breaking changes to existing full output.

## Files

- `packages/docs-mcp/src/docs_mcp/generators/` (compact view logic in epic, story, prompt modules — e.g. `prompts.py` for PromptGenerator, epics.py/stories.py for epic/story)
- `docs/planning/research/2026-LLM-PROMPT-CONTEXT-RESEARCH.md`
- `packages/docs-mcp/tests/unit/` (compact view tests — e.g. test_prompts.py, test_epics.py, test_stories.py)

## Dependencies

- Story 75.2 (PromptGenerator) and existing EpicGenerator/StoryGenerator; compact view is an optional parameter or post-process on their output.

## References

- 2026-LLM-PROMPT-CONTEXT-RESEARCH.md (token budget, “lost in the middle”); design doc

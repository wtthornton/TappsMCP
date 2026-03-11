# Story 75.2: PromptGenerator and docs_generate_prompt tool

**Epic:** [EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION](../EPIC-75-LLM-ARTIFACT-STRUCTURE-AND-PROMPT-GENERATION.md)  
**Priority:** P2 | **LOE:** 3–4 days

## Problem

There is no generator that renders a prompt artifact from PromptConfig, and no MCP tool that exposes it. We need a PromptGenerator (similar to EpicGenerator/StoryGenerator) that outputs markdown with docsmcp section markers, and a `docs_generate_prompt` tool that accepts parameters and writes the file.

## Purpose & Intent

This story exists so that **prompts can be generated and versioned like epics and stories**, with the same section markers and optional expert enrichment. Delivering the MCP tool makes prompt artifacts part of the standard DocsMCP workflow and completes the epic/story/prompt triad for LLM-facing planning and execution.

## Tasks

- [ ] Implement `PromptGenerator` with a `generate(config: PromptConfig, project_root=None, auto_populate=False)` method that returns markdown. Render sections: task, context files, reference (optional), success brief, rules, conversation (optional), plan (optional), alignment (optional), allowed tools, output format, don’t. Use `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->` markers.
- [ ] Optional: call tapps_core `consult_expert` for rules enrichment (reuse expert_utils and domain list from epic/story) when auto_populate or a flag is set.
- [ ] Add `docs_generate_prompt` to DocsMCP server_gen_tools (or equivalent): accept PromptConfig-like params (name, when_to_use, task, success_criteria, context_files, …), call PromptGenerator, write to project output_dir (e.g. docs/prompts/ or configurable), return path and summary.
- [ ] Register the tool in server.json and document in DocsMCP AGENTS.md/CLAUDE.md.
- [ ] Add unit tests for PromptGenerator (minimal and full config, section presence, marker presence) and for the MCP handler (success path, validation error path).

## Acceptance criteria

- [ ] PromptGenerator produces valid markdown with all requested sections and docsmcp markers.
- [ ] `docs_generate_prompt` is callable via MCP and writes a prompt .md file; response includes path and success.
- [ ] Expert enrichment is optional and does not break when tapps_core is unavailable.
- [ ] Tests cover generator and tool; existing DocsMCP tests pass.

## Files

- `packages/docs-mcp/src/docs_mcp/generators/prompts.py` (extend from 75.1 with PromptGenerator class)
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (add `async def docs_generate_prompt(...)` alongside docs_generate_epic ~line 1051; same pattern: _record_call, validation, call generator, write file, return path/summary)
- `packages/docs-mcp/tests/unit/test_prompts.py`, `test_server_gen_tools.py` or equivalent for new tool
- DocsMCP `server.json` (if tool list is explicit) and AGENTS.md / CLAUDE.md for tool documentation

## Dependencies

- Story 75.1 (PromptConfig) must be done first; generator and tool consume PromptConfig.

## References

- Design doc §4 Prompt structure: docs/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md
- Existing tool pattern: docs_generate_epic in server_gen_tools.py

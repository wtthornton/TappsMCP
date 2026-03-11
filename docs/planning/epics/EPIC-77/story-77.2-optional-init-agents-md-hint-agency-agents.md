# Story 77.2: Optional init/AGENTS.md hint for agency-agents

**Epic:** [EPIC-77-AGENCY-AGENTS-INTEGRATION](../EPIC-77-AGENCY-AGENTS-INTEGRATION.md)  
**Priority:** P3 | **LOE:** 0.5 day

## Problem

After `tapps_init`, users who want more specialized agents (e.g. Frontend Developer, Reality Checker) may not know about agency-agents. A one-sentence hint in init success output or in the generated AGENTS.md improves discoverability.

## Purpose & Intent

This story exists so that **users who want more agents discover agency-agents at the right moment** (right after init or when reading AGENTS.md) without us coupling code to agency-agents. A single optional hint increases adoption of the broader agent ecosystem while keeping the main workflow focused on TappsMCP.

## Tasks

- [ ] **Option A (init success message):** In `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`, after the init success summary is built (e.g. where `state.created` / `state.skipped` are reported), append one line to the success message or to the CLI output: e.g. “For more specialized agents (e.g. Frontend Developer, Reality Checker), see https://github.com/msitarzewski/agency-agents and run their install script for your platform.”
- [ ] **Option B (AGENTS.md template):** In the template used for AGENTS.md (e.g. in `packages/tapps-mcp/src/tapps_mcp/pipeline/` or prompts/ — locate via grep for “AGENTS.md” or “agents_template”), add one sentence in an “Optional” or “See also” subsection: same text as above, with markdown link `[agency-agents](https://github.com/msitarzewski/agency-agents)`.
- [ ] Implement either A or B (or both); document which in the epic. Do not add both if it would be redundant (e.g. if AGENTS.md is always created and already shown to user, template alone may suffice).
- [ ] Ensure the hint is clearly optional (“For more…”, “Optional: …”) so it does not imply agency-agents is required.

## Acceptance criteria

- [ ] Init success output or generated AGENTS.md includes a single sentence linking to agency-agents for “more specialized agents (e.g. Frontend Developer, Reality Checker).”
- [ ] Wording is optional; no implication that agency-agents is required for TappsMCP.

## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (if Option A — success message)
- AGENTS.md template: `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_medium.md` (and `agents_template.md`, `agents_template_high.md`, `agents_template_low.md` if hint should appear in all engagement levels); template is loaded via `prompt_loader.load_agents_template(engagement_level)` from `init.py` and `setup_generator.py`

## Dependencies

- Story 77.1 recommended first so the full “Agent ecosystem” section exists; 77.2 can ship standalone.

## References

- Epic 77; https://github.com/msitarzewski/agency-agents

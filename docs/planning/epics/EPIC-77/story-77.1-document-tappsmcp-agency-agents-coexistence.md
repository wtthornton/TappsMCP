# Story 77.1: Document TappsMCP + agency-agents coexistence

**Epic:** [EPIC-77-AGENCY-AGENTS-INTEGRATION](../EPIC-77-AGENCY-AGENTS-INTEGRATION.md)  
**Priority:** P3 | **LOE:** 1–2 days

## Problem

Users may not know that TappsMCP’s four subagents and platform rules can coexist with the optional [agency-agents](https://github.com/msitarzewski/agency-agents) roster. Without a single place that explains install order and paths, they may assume conflict or miss the option to add specialized personas (Frontend Developer, Reality Checker, etc.).

## Purpose & Intent

This story exists so that **users have one authoritative place** to understand how TappsMCP and agency-agents fit together. Clear install order and path clarification reduce support questions and enable users to confidently combine quality automation (TappsMCP) with optional domain personas (agency-agents) without conflict.

## Tasks

- [ ] Add a short section **“Agent ecosystem”** or **“Using TappsMCP with other agent libraries”** in one of: `AGENTS.md` (project root), `README.md`, or `docs/TAPPS_MCP_SETUP_AND_USE.md`. If adding to AGENTS.md, use a collapsible or clearly labeled subsection so the main workflow stays primary.
- [ ] Section content must include: (1) TappsMCP creates 4 quality subagents (tapps-reviewer, tapps-researcher, tapps-validator, tapps-review-fixer) and platform rules + skills; (2) agency-agents is an optional add-on with 120+ personas (Frontend Developer, Reality Checker, etc.); (3) recommended install order: configure MCP → run `tapps_init` → optionally run agency-agents `./scripts/install.sh --tool claude-code` or `--tool cursor`; (4) path clarification: Cursor — agency-agents writes to `.cursor/rules/`, TappsMCP writes to `.cursor/agents/` and `.cursor/rules/` (no conflict); Claude — both can use agents dir (project `.claude/agents/` and/or user `~/.claude/agents/`); (5) link to `docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md`.
- [ ] Ensure the research doc is reachable from the new section (relative or absolute path as appropriate for where the section lives).

## Acceptance criteria

- [ ] A dedicated doc or section explains TappsMCP’s 4 subagents + rules + skills and optional agency-agents.
- [ ] Install order and path behavior are stated explicitly; no path conflict is clearly called out.
- [ ] Research reference is linked; readers can find 2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md.

## Files

- `AGENTS.md` and/or `README.md` and/or `docs/TAPPS_MCP_SETUP_AND_USE.md` (choose one primary location; cross-link if duplicated elsewhere)
- `docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md` (existing; linked only)

## References

- Epic 77; docs/reviews/AGENCY-AGENTS-REPO-DEEP-DIVE.md; https://github.com/msitarzewski/agency-agents

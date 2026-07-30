# ADR-0031: Always-on context budget (doctor → upgrade → init)

**Status:** Accepted  
**Date:** 2026-07-29  
**Deciders:** TappsMCP maintainers

## Context

TappsMCP already budgets eager MCP tools (`doctor_tool_budget_limit`) but shipped large always-on markdown surfaces: fat `AGENTS.md` / `CLAUDE.md`, Claude `alwaysApply` rules, and ~30 skills. Anthropic-style context engineering for Claude 5-class models favors thin always-on indexes, progressive disclosure via skills, and right-sizing inventories. Wizard collected `skill_tier` but generation ignored it.

## Decision

1. **`tapps_doctor` WARN checks** (non-blocking) for CLAUDE.md / AGENTS.md size, alwaysApply rule weight, skill inventory (count, orphans, oversized SKILL.md without companions), and dual Karpathy installs. Ceilings live under `doctor_context_budget` in `.tapps-mcp.yaml`.
2. **`skill_tier: core | full`** (default `full`) is persisted by init and honored by upgrade. Core deploys a fixed essential set; upgrade may prune managed non-core registry skills when `skill_tier: core`. Unknown user skills are never deleted.
3. **Karpathy single-home:** install/refresh prefers `AGENTS.md` when present, else `CLAUDE.md`. Dual installs WARN in doctor; upgrade `--force` strips the secondary copy.
4. **Templates / Claude rules:** AGENTS templates keep essentials and point at `tapps-tool-reference` / `tapps-memory`; `linear-standards` and `integration-hygiene` ship with `alwaysApply: false`.

## Consequences

- Greenfield medium AGENTS templates stay under the default 24 KiB ceiling.
- Existing full-skill fleets are unchanged until they set `skill_tier: core`.
- Doctor noise on fat monorepos is intentional; raise ceilings or slim content.

## Alternatives considered

- Hard-fail quality gate on context size — rejected; advisory WARNs match MCP tool budget precedent.
- Transcript-based unused-skill pruning (Claude `/doctor`) — deferred; host-specific and non-deterministic across IDEs.

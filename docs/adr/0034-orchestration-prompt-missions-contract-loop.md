# 34. orchestration-prompt ships Missions-inspired contract + expected-fail loops

Date: 2026-08-04

## Status

Accepted (TAP-5552 / TAP-5538).

## Context

Factory Missions ([talk](https://youtu.be/ow1we5PzK-o), [architecture](https://factory.ai/news/missions-architecture)) shows that long-running agent quality comes from: (1) a **validation contract** written before features, (2) **creator ≠ verifier**, (3) **serial writes**, (4) **structured handoffs**, and (5) an **expected-fail fix loop** with an attempt cap.

TappsMCP already ships `/orchestration-prompt` as a multi-file, smart-merged platform skill (init / upgrade / doctor). It had strong harness pieces (independent verifier, model tiers, cold-start, diagnose-don't-repeat) but did not force contract-before-features or treat first-pass validation failure as normal.

We do **not** want a Missions product runtime (Mission Control UI, multi-day orchestrator, computer-use fleets) inside tapps-mcp. Consumers need the *control loop* in every generated orchestration prompt.

## Decision

1. Extend `platform_skill_orchestration.py` (SKILL body + `assets/prompt-template.md` + `references/claude-feature-map.md`) so emitted prompts carry:
   - validation contract (when changing software behavior) before execution sub-goals
   - creator ≠ verifier (verifier reports; does not implement fixes)
   - expected-fail fix loop with default ≤3 validation rounds and structured handoffs
   - serial writes / parallel reads guidance
2. Ship via existing paths: `tapps_init` / `tapps_upgrade` refresh the managed block + companions; `learnings.md` stays create-once.
3. Doctor `check_orchestration_prompt_skill_current` fails deployed hosts whose skill/template lack `validation contract` + `expected-fail` fingerprints, with remediation `tapps-mcp upgrade --force`.

## Consequences

- All full-tier consumers get the better skill on next init/upgrade; doctor nags until upgraded.
- Core-tier (`skill_tier: core`) still omits orchestration-prompt (unchanged).
- No new MCP tool or Missions runtime. Wayfind (TAP-5492) remains the fog/planning gate; this ADR covers the clear-route harness.

## Alternatives considered

- **New MCP `tapps_mission_*` tools** — rejected: product surface duplication; prompts+skills are enough for v1.
- **Embed full Factory Missions prompts** — rejected: host-locked, non-portable, fights TAPPS deterministic gates.
- **Doctor opt-in only (no content fingerprint)** — rejected: stale companions would stay "current" forever after a one-time deploy.

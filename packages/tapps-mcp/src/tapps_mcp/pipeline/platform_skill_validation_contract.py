"""Platform ``tapps-validation-contract`` skill — body + companion files.

Forces contract-first correctness (Factory Missions ordering): write behavioral
assertions before implementation, map features to assertion IDs, forbid
post-hoc-only tests as the sole done signal. Ships via smart-merge on
init/upgrade (TAP-5541 / ADR-0034).
"""

from __future__ import annotations

VALIDATION_CONTRACT_SKILL_FRONTMATTER = """\
---
name: tapps-validation-contract
user-invocable: true
disable-model-invocation: true
description: >-
  Write a finite validation contract (behavioral assertion IDs) before
  implementing software behavior, map features to those IDs, and keep tests
  shaped by the contract — not by the code. Use when starting a feature,
  bugfix with observable effect, or migration; when /orchestration-prompt
  needs a contract; or when the user invokes /tapps-validation-contract.
argument-hint: "[draft | claim <VAL-id> | mark-verified]"
---
"""

VALIDATION_CONTRACT_SKILL_BODY = (
    VALIDATION_CONTRACT_SKILL_FRONTMATTER
    + r"""
# tapps-validation-contract

You produce a **validation contract** — a finite checklist of testable behavioral
assertions with stable IDs — **before** implementation. This is the Factory
Missions ordering that stops post-hoc tests from ratifying whatever the
implementer already built.

You do **not** implement the feature here. Hand off to normal coding or
`/orchestration-prompt` once the contract is written and claimed.

## When to use

- Starting feature / bugfix / migration work with observable behavior
- Before `/orchestration-prompt` for software-behavior goals
- When `usage_gaps` shows `contract_assertions_unverified`

Skip for pure research, triage, docs-only, or decision tickets (wayfind).

## Contract rules

1. **Assertions first.** Write the contract *before* code and before feature
   decomposition that would bias the assertions toward a planned implementation.
2. **Behavioral, not structural.** Each assertion is what a user/API/CLI observes
   — not "module X has function Y" or "tests pass."
3. **Stable IDs.** Use `VAL-<AREA>-###` (e.g. `VAL-AUTH-001`). IDs never change
   meaning mid-mission; add new IDs instead of rewriting old ones.
4. **Fulfills coverage.** Every feature/story claims which IDs it fulfills.
   Coverage must be complete: no orphan IDs, no duplicate claims.
5. **Tests follow the contract.** Prefer tests (or smoke scripts) written to the
   assertion. Post-hoc tests alone are **not** a done signal.
6. **Independent verify.** A fresh verifier checks assertions; the implementer
   does not self-grade. See `/tapps-finish-task` creator-verifier step.

## Invocation

### Draft

User: `/tapps-validation-contract draft <goal>`

1. Clarify observable done (ask if foggy — or send to `/tapps-wayfind`).
2. Write `.tapps-mcp/validation-contract.md` using `assets/contract-template.md`.
3. Optionally attach assertion IDs to Linear stories via `linear-issue`
   (Assertions section from docs-mcp).
4. Stop — do not implement.

### Claim

User: `/tapps-validation-contract claim VAL-…`

Map one or more pending features/stories to assertion IDs (`fulfills`). Update
the contract Coverage table. Reject claims that leave orphans/duplicates.

### Mark-verified

After an independent verifier confirms all claimed IDs for this session's work:

```bash
uv run tapps-mcp pipeline-mark contract-verified
```

This clears `contract_assertions_unverified` in `tapps_checklist` `usage_gaps`.

## Guardrails

- Never invent green by weakening assertions to match broken code.
- Never treat coverage % or "tests exist" as contract satisfaction.
- Serial writes when implementing claimed features; parallel research OK.
- Prefer `/orchestration-prompt` for multi-step harness loops that already
  embed a Validation contract section.
"""
)

_CONTRACT_TEMPLATE = r"""# Validation contract

> Write **before** implementation. Each assertion is behavioral and testable.

## Assertions

| ID | Behavioral assertion | Evidence (how to prove) |
|----|----------------------|-------------------------|
| VAL-AREA-001 | <user-visible / API / CLI outcome> | <pytest / smoke / curl / screenshot> |

## Coverage (fulfills)

| Feature / story | Fulfills IDs |
|-----------------|--------------|
| <name or TAP-###> | VAL-AREA-001 |

**Coverage rule:** every assertion ID appears in exactly one fulfills cell.
"""

_ASSERTION_SCHEMA = r"""# Assertion ID schema

- Format: `VAL-<AREA>-###` where AREA is a short SCREAMING slug (AUTH, API, UI, …)
  and ### is a zero-padded integer starting at 001.
- IDs are stable for the life of the mission/epic. Do not reuse IDs for different
  meaning; add VAL-AREA-002 instead.
- Evidence tools: prefer deterministic commands whose output can be pasted
  (`pytest -q`, `curl -sS`, smoke scripts). LLM narration is not evidence.
"""

_WHEN_TO_USE = r"""# When to use tapps-validation-contract

| Situation | Action |
|-----------|--------|
| New feature / observable bugfix / migration | Draft contract first |
| Orchestration prompt for software behavior | Embed contract table (skill already required) |
| `contract_assertions_unverified` in usage_gaps | Draft or mark-verified |
| Pure docs / research / wayfind decision | Skip |
"""

VALIDATION_CONTRACT_COMPANION_FILES: dict[str, str] = {
    "assets/contract-template.md": _CONTRACT_TEMPLATE,
    "references/assertion-schema.md": _ASSERTION_SCHEMA,
    "references/when-to-use.md": _WHEN_TO_USE,
}

__all__ = [
    "VALIDATION_CONTRACT_COMPANION_FILES",
    "VALIDATION_CONTRACT_SKILL_BODY",
]

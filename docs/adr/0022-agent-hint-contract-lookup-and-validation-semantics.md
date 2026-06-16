# 22. Agent hint contract — lookup timing and validation semantics

Date: 2026-06-16

## Status

accepted

## Context

The 2026 agent-contract audit found contradictory hints across hooks, skills,
rules, usage gaps, and subagent templates (matrix X1–X10). Phase 1 introduced
`agent_contract.py` as a shared string source and aligned post-edit hooks,
finish-task skills, and Cursor pipeline rules.

Remaining ambiguity:

1. **Lookup timing (X1, X2)** — AGENTS Rule 2 says lookup *before write*;
   finish-task step 3 allows *retrospective* MCP lookups to clear telemetry
   gaps. Post-edit hooks said “before complete” vs “before writing more code.”
2. **Validation semantics (X3, X9)** — Stop-hook telemetry treats
   `tapps_quick_check` as gate activity; `/tapps-finish-task` requires
   `tapps_validate_changed` for the edited set. Docs sometimes implied Stop
   hooks *block* completion; default is warn-only telemetry.
3. **Memory narrative (X4, X5)** — SubagentStart listed `tapps_memory` on the
   legacy server id; skills/rules now document CLI bridge + `nlt-memory`
   facade (TAP-3895).

Without a single contract, agents over-trust retrospective lookups for
knowledge, skip pre-code lookups, or call removed MCP routes.

## Decision

### Single source: `agent_contract.py`

All cross-surface hint strings for lookup timing, validation semantics,
session-start gaps, stop followups, subagent awareness, and finish-task
blocks live in `packages/tapps-mcp/src/tapps_mcp/pipeline/agent_contract.py`.
Generated artifacts import or echo these constants — no divergent copy in
hooks, `usage.py`, or skills.

### Lookup timing rule (ADR-0022)

| When | Action | Clears |
|------|--------|--------|
| **Before first use** of an external library in a session | `tapps_lookup_docs(library, topic)` | Hallucination risk; preferred path |
| **After edits** (post-edit hook) | Advisory: lookup before using detected imports | Nudge only |
| **End of task** (finish-task step 3) | Retrospective lookup per listed library | Telemetry gap + CallTracker; cache hit OK (ADR-0021) |
| **CLI warmup** | `tapps-mcp lookup-docs` | `.lookup-docs-events.jsonl` + cache; SessionStart hints (ADR-0021) |

**Invariant:** retrospective lookup clears **telemetry**, not the need to have
read docs before relying on APIs in future sessions.

### Validation semantics

| Tool | Role | Counts as “gate” in Stop telemetry |
|------|------|-----------------------------------|
| `tapps_quick_check` | Per-file during edits | Yes |
| `tapps_validate_changed` | Batch before done | Yes |
| `/tapps-finish-task` | Orchestrates validate + checklist (+ optional memory) | Yes (via those tools) |

**Invariant:** declaring work complete requires batch validation on the edited
set (`tapps_validate_changed` with explicit `file_paths` or finish-task skill).
Stop / TaskCompleted hooks are **warn-only** unless opt-in gates
(`install_git_hooks`, `linear_enforce_cache_gate=block`, etc.).

### Memory narrative (TAP-3895)

- Default consumer path: `uv run tapps-mcp memory …` (BrainBridge).
- When `nlt-memory` is in the MCP bundle, `tapps_memory` is a **slim facade** on
  that server — not a second brain connection.
- SubagentStart and doctor checks must not route agents at
  `mcp__tapps-mcp__tapps_memory`.

### Verification

- Unit tests: `test_agent_contract.py`, `test_hint_string_consistency.py`
- CI: `validate-skills`, `check-agents-md-stamp`, agent-contract pytest job
- Doctor: `check_tapps_memory_skill` requires CLI + nlt-memory facade markers

## Consequences

- **Positive:** One remediation string per gap ID; hosts stay aligned after
  `tapps-mcp upgrade --force`.
- **Positive:** ADR-0021 telemetry/cache behavior documented alongside timing.
- **Tradeoff:** Edits to agent-facing copy require touching `agent_contract.py`
  and regenerating scaffolds — intentional friction to prevent drift.

## Alternatives considered

1. **Document-only** — Update AGENTS.md without code constants. Rejected: drift
   recurs on the next `platform_skills.py` edit.
2. **Block Stop hook on gaps** — Hard enforcement by default. Rejected: breaks
   long sessions and conflicts with engagement-level design (X9).
3. **Remove retrospective lookup from finish-task** — Would leave telemetry gaps
   stuck after cache-only warmups. Rejected; ADR-0021 needs both channels.

# 37. Session-handoff slots and an ownership guard

Date: 2026-09-01

## Status

Accepted

## Context

`.tapps-mcp/session-handoff.md` was a single constant path and a single flat brain key
(`session-handoff`), written with a blind `path.write_text(...)` — no read of what was already
there, no lock, no backup. In a repo that routinely runs several concurrent programs (e.g.
nlt-orchestrator with 3-4 concurrent sessions), the last `/tapps-handoff-session` silently
replaced every other program's cold-start channel — file *and* brain row — and the read side had
no way to detect it, because nothing in the artifact identified which program had written it.

The servers are shared across sessions and scoped per request by `X-Tapps-Project-Root`; there is
no per-session identity on the wire, and `.tapps-mcp/agent.id` is one id per repo, not per
session. Inventing session-id plumbing to solve this was rejected as unnecessary — the identity a
program can state about itself (a `**Program:**` line it writes into its own handoff) is enough,
and does not require any new transport-level concept.

## Decision

Two mechanisms, both required, land together:

1. **Slots.** `handoff_path(project_root, slot=None)` becomes the single naming site for the
   handoff file path; `handoff_memory_key(slot=None)` is the single naming site for the brain key.
   No slot reproduces the pre-existing path (`.tapps-mcp/session-handoff.md`) and key
   (`session-handoff`) exactly, so the default behaviour for any caller that never passes `slot=`
   is unchanged. A slot namespaces both halves: file `.tapps-mcp/handoffs/<slot>.md`, brain key
   `session-handoff.<slot>`. The slot separator in the brain key is a **dot, not a colon** — the
   brain validates every `MemoryEntry.key` against a slug pattern (`^[a-z0-9][a-z0-9._-]{0,127}$`)
   that excludes `:`; a colon-separated key is rejected server-side by every real `save`, not
   merely non-idiomatic. This was caught only by exercising a live save against the pinned brain
   dependency — a test asserting the key as a returned *string* stayed green while every
   production write would have failed.
2. **Ownership guard.** Every write reads the incumbent file first (if any) and fingerprints it as
   `{program, updated, linear_p0, title}` from its `**Program:**` header (new schema field) and
   title. The incoming write is fingerprinted the same way. A write whose program differs from a
   *recent* incumbent's (inside `handoff_conflict_window_hours`, default 12) is `foreign`; an
   incumbent whose ownership cannot be established at all reports `"unknown"` rather than passing
   silently as "no conflict." The incumbent is **archived on every write, conflict or not** — moved
   to `.tapps-mcp/handoffs/archive/<UTC>-<slot|default>.md`, pruned to the newest 20 — and the
   replacement is promoted **atomically**: written to a temp file in the target's own directory,
   `fsync`'d, then `os.replace`'d onto the target path, with the parent directory `fsync`'d after.
   A new `handoff_conflict_mode` setting (`off` / `warn` / `block`, default `warn`) controls
   whether a conflict is reported (`warn`) or refused outright with a structured
   `handoff_owner_conflict` error naming the retry (`block`); `force=true` overrides `block` and
   still archives first.

## Consequences

**Positive:**

- The 2026-09-01 incident this was filed against — one program's `/tapps-handoff-session`
  silently replacing another's — cannot recur silently: the write is reported (`warn`) or refused
  (`block`), and the replaced handoff is always recoverable from the archive.
- Two or more programs can coexist in one repo by passing distinct `slot=` values, without any
  change to the ~35 other repos that never pass one.
- A crash between archiving the incumbent and promoting the replacement can no longer leave a
  truncated handoff on disk — the previous blind `write_text` could.

**Negative:**

- Every handoff written **before** this change carries no `**Program:**` header. Its identity
  cannot be established, so a write over it always classifies as `foreign: "unknown"` — reported
  and **archived, not blocked**. Retro-fitting the header onto historical handoffs is explicitly
  out of scope; every legacy repo continues writing its ordinary handoff without ever tripping a
  refusal it cannot satisfy.
- Slots multiply brain rows against the per-project entry cap. The `context` tier ages entries out
  in 14 days, so an abandoned slot's row self-expires; this is a property of the existing tier
  policy, not a new mechanism this ADR introduces.
- Mutual exclusion between two writers racing inside the same second is still not guaranteed —
  the atomic promote makes the *result* always a complete file, but it does not serialize
  concurrent writers. Advisory locking (`flock`) and a content-hash compare-and-swap were
  considered and explicitly deferred (see Alternatives) — reopen only if the archive shows two
  writes landing inside the same second in practice.

## Alternatives considered

**Session-id plumbing** (a per-session identifier threaded through the MCP request) was rejected:
the wire already carries no per-session identity, only `X-Tapps-Project-Root`, and adding one
would require new transport-level state for a problem the artifact's own `**Program:**` header
already solves without it.

**Colon-separated brain key** (`session-handoff:<slot>`) was the original design and was rejected
after a live rejection from the brain's own key validator — see Decision §1.

**Advisory file locking + content-hash compare-and-swap** were considered as a stronger
concurrency guarantee. Deferred: the archive-and-atomic-promote pair already converts a silent,
unrecoverable loss into a recoverable, visible one, which is the actual defect being closed;
locking addresses a narrower race (two writes in the same second) that has not been observed.

## Refs

- `packages/tapps-mcp/src/tapps_mcp/tools/handoff_guard.py` — guard, archive/prune, atomic promote.
- `packages/tapps-mcp/src/tapps_mcp/tools/handoff_schema.py` — naming sites, slot validation,
  `**Program:**` parsing.
- `packages/tapps-core/src/tapps_core/config/settings.py` — `handoff_conflict_mode` /
  `handoff_conflict_window_hours`.
- Linear: TAP-6868 (epic), TAP-6870, TAP-6871, TAP-6872, TAP-6873, TAP-6874, TAP-6875.

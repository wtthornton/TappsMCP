# Handoff → tapps-brain: wayfind resume pack (B1)

**Status:** requested by tapps-mcp 2026-08-04 (TAP-5499 / parent TAP-5492).
These are **tapps-brain** changes — do **not** file or edit Linear issues for
tapps-brain from this repo (see `.cursor/rules/tapps-agent-scope.mdc`). Copy
the epic stub below into the **tapps-brain** Linear project from that checkout.

## Source of truth

| Concern | Owner |
|---|---|
| Ticket status, assignee, frontier, map children | **Linear** (always) |
| Resume rationale, charting notes, decision transcripts | **tapps-brain** memory (+ optional KG) |

Brain must **not** become a second tracker. Wayfind skills read Linear for
status and write brain only for cross-session resume hints.

## B1 — convention pack (required)

### Memory group

- `memory_group=wayfind` on all resume saves from `/tapps-wayfind` / orchestration fog gate.

### Key schema (suggested)

| Key pattern | Tier | Value |
|---|---|---|
| `wayfind:map:<linear-issue-id>` | `procedural` (30d) | Map snapshot: destination summary, last chart note, child ticket ids |
| `wayfind:decision:<linear-issue-id>` | `context` (14d) | Question text + recorded answer when closed |
| `wayfind:session:<session-id>` | `context` (14d) | Pointer to active map id for cold-start recall |

Use `project_id` / `X-Project-Id` = consumer slug (same as other brain tenants).
Do not store Linear workflow state (Backlog / In Progress) in brain.

### KG predicates (optional B1.5)

If brain KG is available:

- `(:WayfindMap)-[:INDEXES]->(:LinearIssue)` where map id ↔ Linear parent id
- `(:Decision)-[:RESOLVES]->(:WayfindMap)` when a decision ticket closes

Keep predicates advisory — Linear links remain authoritative.

## B2 — document plane (optional follow-ons)

File separately in tapps-brain if B1 lands:

1. Document store attachments for large grilling transcripts linked by map id
2. TTL / GC policy for stale `wayfind:*` keys when Linear map is Done/Canceled
3. Operator endpoint to list orphan wayfind keys with no matching Linear id

## Copy-paste epic stub (file in tapps-brain Linear project)

```markdown
## Purpose & Intent
We are doing this so tapps-mcp wayfind / orchestration can resume foggy maps
across sessions without treating brain as a second ticket tracker.

## Goal
Implement B1 wayfind memory_group + key schema (+ optional KG predicates) so
tapps-mcp agents can save/recall `wayfind:map:*` / `wayfind:decision:*` safely.

## Motivation
TAP-5492 ships wayfind skills in tapps-mcp; resume packs must live in brain
with Linear as SoT for status (TAP-5499 handoff).

## Acceptance
- [ ] `memory_group=wayfind` keys persist and recall under the consumer tenant
- [ ] Docs state Linear remains SoT for status/frontier
- [ ] No API that writes Linear ticket status from brain

## Out of Scope
Mirroring Linear workflow states; Missions product UI; MCP tools in tapps-mcp

## Refs
TAP-5492 / TAP-5499 (tapps-mcp Platform); docs/handoff/BRAIN-wayfind-resume-pack.md
```

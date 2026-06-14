# 16. Needs-based NLT MCP taxonomy (Build / Memory / Setup)

Date: 2026-06-13

## Status

Accepted (2026-06-13; TAP-3889 / TAP-3892)

## Context

Epic 109 split the monolithic tapps-mcp surface into five NLT servers by **product
workflow** (`nlt-code-quality`, `nlt-platform-admin`, `nlt-linear-issues`,
`nlt-project-docs`, `nlt-release-ship`). Daily coding still loaded Platform Admin
(~11 eager tools across two servers) because bootstrap and session-lifecycle tools
shared the admin profile.

[TAP-1994](https://linear.app/tappscodingagents/issue/TAP-1994) removed the full
`tapps_memory` MCP catalog (42 actions) in favor of CLI + brain bridge. Agents lost
MCP recall/save unless they enabled extra servers or used shell fallbacks. Checklist
and skills still implied memory search at session start.

Operators need a **needs-based** taxonomy: what task am I doing → which 1–3 servers
to enable — not which internal team owns the code.

## Decision

Replace the workflow-oriented **Build + Admin** default with three core tapps-mcp
profiles plus unchanged situational servers.

### Core profiles (tapps-mcp `--profile`)

| Profile | MCP server ID | Purpose | Eager tools (approx) |
|---------|---------------|---------|----------------------|
| **Build** | `nlt-build` | Score, gate, validate, docs lookup, import/impact graph | 9 |
| **Memory** | `nlt-memory` | Slim `tapps_memory` (search/save/get/health/related) + session continuity | 2 |
| **Setup** | `nlt-setup` | Bootstrap, upgrade, doctor, engagement, pipeline, stats | 2 |

**Legacy aliases (one release):** `--profile nlt-code-quality` → Build;
`--profile nlt-platform-admin` → Setup. MCP config migration maps old server keys
to new IDs on `tapps_upgrade`.

### Situational servers (unchanged)

| Server | When to enable |
|--------|----------------|
| `nlt-linear-issues` | Planning, Linear writes, audit close loop |
| `nlt-project-docs` | Doc generation / drift audits |
| `nlt-release-ship` | Release notes, changelog, release gate |

### Session bundles

Documented in `docs/architecture/nlt-mcp-plugin-spec.yaml`:

| Bundle | Enabled servers | Use case |
|--------|-----------------|----------|
| `developer` | `nlt-build`, `nlt-memory`, `nlt-linear-issues` | Daily implementation (default after init; ~18 eager) |
| `minimal` | `nlt-build` | Token-tight coding (build-only; ~9 eager) |
| `memory` | `nlt-build`, `nlt-memory` | Coding + recall/save/handoff (no Linear) |
| `planning` | `nlt-build`, `nlt-linear-issues` | Backlog / issue workflow (no Memory MCP) |
| `docs` | `nlt-build`, `nlt-project-docs` | Documentation pass |
| `release` | `nlt-build`, `nlt-release-ship` | Ship day |
| `security` | `nlt-build` | File + CVE scan (`dependency_scan` deferred on Build) |
| `audit` | `nlt-build`, `nlt-linear-issues` | Audit campaign + finding→story |
| `full` | all six | Escape hatch; doctor WARN |

`tapps_init` writes the **`developer`** bundle: `nlt-build`, `nlt-memory`, and
`nlt-linear-issues`. Use `--bundle minimal` for build-only. `nlt-setup`, docs, and
release servers remain commented opt-in blocks in `mcp.json`.

### Zero-duplication rules

1. Each tool name registers on **exactly one** NLT profile (unchanged from Epic 109).
2. `tapps_memory` returns only on `nlt-memory` with a **bounded action set** (~5
   actions), not the retired 42-action catalog ([TAP-1994](https://linear.app/tappscodingagents/issue/TAP-1994)).
3. Session lifecycle (`tapps_session_notes`, `tapps_session_end`, `tapps_handoff_save`)
   live on **Memory**, not Setup.
4. `tapps_checklist` treats required tools on **disabled** servers as optional with
   an explicit hint (server-aware resolution).
5. Three graph concepts stay distinct (see `tool-budget.md`): **import graph**
   (`tapps_impact_analysis`, Python-only), **package CVE graph**
   (`tapps_dependency_scan` / `tapps_dependency_graph`), **brain KG**
   (`tapps_memory` action `related` on Memory server).

### Relationship to Epic 109

Epic 109 established zero-duplication splits and partial enablement. ADR-0016 **renames
and refines** the two always-on tapps-mcp servers; it does not change docs-mcp or
tapps-platform profile boundaries for Linear/Release.

## Consequences

### Positive

- Default coding sessions load ~18 eager tools (Build + Memory + Linear), within the
  doctor partial-enablement budget; use `minimal` for ~9 eager build-only.
- Memory recall/save is a deliberate opt-in (`nlt-memory`) without restoring MCP bloat.
- Setup is clearly bootstrap/diagnostics, not a junk drawer for session tools.
- Checklist `complete=true` is achievable on partial server enablement.

### Negative / migration

- Consumers must run `tapps_upgrade` to rename MCP server keys and refresh skills
  (`mcp__nlt-build__*`, `mcp__nlt-memory__*` prefixes).
- One release of legacy `--profile` aliases; remove after downstream migration.
- Skills and AGENTS.md must document Build vs Build+Memory session modes.

## Alternatives considered

1. **Keep Platform Admin always on** — Rejected: violates partial-enablement assumption
   and wastes ~2 eager tools daily.
2. **Restore full `tapps_memory` on Build** — Rejected: recreates TAP-1994 catalog bloat.
3. **CLI-only memory forever** — Rejected: IDE agents cannot call shell from tool loop
   reliably; slim MCP facade is the compromise.

## References

- [nlt-mcp-plugin-spec.yaml](../architecture/nlt-mcp-plugin-spec.yaml)
- [TAP-3889](https://linear.app/tappscodingagents/issue/TAP-3889) parent epic
- [TAP-1994](https://linear.app/tappscodingagents/issue/TAP-1994) memory MCP removal
- Epic 109 research: `docs/archive/planning/research/2026-NLT-MCP-PLUGIN-SPLIT-RESEARCH.md`

# 17. Function-level call graph (Python-first)

Date: 2026-06-15

## Status

Accepted (2026-06-15; TAP-4056 / [TAP-4049](https://linear.app/tappscodingagents/issue/TAP-4049))

## Context

TappsMCP ships **module-level** import-graph impact analysis via `tapps_impact_analysis`
(`impact_analyzer.py`). Agents refactoring a function still grep for callers, miss
indirect chains, and cannot tie edits to **which tests** exercise a symbol.

2026 research (RepoScope ICSE, TDAD Mar 2026) shows function-level call-chain context
improves repo-level codegen and cuts test regressions. Epic 114 ([TAP-4049](https://linear.app/tappscodingagents/issue/TAP-4049))
adds deterministic Python **CALLS** edges and MCP queries without violating
[ADR-0004](0004-deterministic-tools-only-contract.md) (no LLM in the tool chain).

ADR-0016 defines three graph types (import, CVE, brain KG). Call graph is a **fourth**
concept — function/symbol edges inside a repo, distinct from module imports.

## Decision

Ship a **Python-first**, **AST-only**, **deterministic** call graph on `nlt-build`,
integrated with — not replacing — `tapps_impact_analysis`.

### Tier roadmap

| Tier | Stories | Deliverable | Agent value |
|------|---------|-------------|-------------|
| **A** | TAP-4053 | `call_graph.py` indexer: `CALLS` edges from `ast` | Offline index; no new MCP tool yet |
| **B** | TAP-4050, TAP-4051 | `tapps_call_graph` (callers, callees, token-budgeted chains); symbol blast radius on `tapps_impact_analysis` | Replace grep for who-calls-whom; pre-refactor symbol scope |
| **C** | TAP-4052, TAP-4054, TAP-4055 | TDAD-style `TESTS` edges (`test_linker.py`); `tapps_diff_impact` affected tests; `resolution_gaps` for unresolved dispatch | Regression-aware edits; honest limits on dynamic calls |
| **Stretch** | TAP-4057 | Git co-change enrichment | Optional ranking signal; not required for epic acceptance |

Implementation order: **A → B → C**; stretch is post-epic.

### Tool surface (Tier B+)

| Tool | Profile | When to use |
|------|---------|-------------|
| `tapps_impact_analysis` | `nlt-build` (existing) | **Module/file** blast radius: direct + transitive importers, heuristic test overlap |
| `tapps_call_graph` | `nlt-build` (new, deferred until Tier B) | **Symbol-level** callers, callees, bounded call chains for one qualified name |
| `tapps_diff_impact` | `nlt-build` (new, deferred until Tier C) | Changed symbols → affected tests via `TESTS` edges |

`tool_descriptions.py` and `tapps_checklist` `refactor` task type treat
`tapps_impact_analysis` as **recommended** today; `tapps_call_graph` becomes
**recommended** once Tier B ships (optional until then).

### Token budget for chains

Call-chain responses must cap serialized output (default **~4k tokens** of graph
payload, configurable). Depth-first expansion stops at the budget; response includes
`truncated: true` and `resolution_gaps` when edges cannot be resolved.

### Resolution model

- **Resolved:** static `ast` call sites where callee module + name resolve in-repo.
- **Unresolved (`resolution_gaps`):** `getattr`, `eval`, dynamic imports, C extensions,
  monkey-patched bindings, and cross-repo calls — reported explicitly, never guessed.

### Relationship to existing graphs

| Graph | Tool(s) | Granularity |
|-------|---------|-------------|
| Import / impact | `tapps_impact_analysis`, `tapps_dependency_graph` | Module / file |
| **Call graph** | `tapps_call_graph`, extended `tapps_impact_analysis` | Function / method |
| Package CVE | `tapps_dependency_scan` | Installed packages |
| Brain KG | `tapps_memory(action="related")` | Cross-session entities |

Polyglot **scoring** (TS/Go/Rust) does not imply polyglot call graphs in v1 — Python only,
matching import-graph scope in ADR-0016.

## Consequences

### Positive

- Agents get deterministic caller/callee answers without grep false positives.
- `tapps_impact_analysis` stays the entry point for file-level edits; call graph
  deepens symbol-level refactors.
- `resolution_gaps` preserves ADR-0004 honesty when static analysis cannot resolve.

### Negative / constraints

- Dynamic dispatch and metaclass magic remain blind spots until explicitly modeled.
- Index build adds cold-start cost on first query per project root (cache on disk under
  `.tapps-mcp/`).
- Tier B adds one eager tool on Build — stays within doctor budget if other deferred
  tools unchanged; monitor via `tapps_doctor`.

## Non-goals (Epic 114 out of scope)

- Cross-repo service graphs and runtime telemetry graphs
- Full CFG, DFG, or program slicing
- SCIP / LSP universal indexing
- PageRank or ML risk scoring
- Replacing `tapps_impact_analysis` module-level reports

## Alternatives considered

1. **Extend grep/heuristics only** — Rejected: high false-positive rate; fails epic acceptance.
2. **SCIP/LSP indexer** — Rejected for v1: heavy external deps; violates simple deterministic AST contract.
3. **LLM-summarized impact** — Rejected: violates ADR-0004.
4. **Separate MCP server for call graph** — Rejected: belongs on Build alongside `tapps_impact_analysis`; same session mode.

## References

- [TAP-4049](https://linear.app/tappscodingagents/issue/TAP-4049) Epic 114
- [TAP-4053](https://linear.app/tappscodingagents/issue/TAP-4053) AST indexer
- [TAP-4050](https://linear.app/tappscodingagents/issue/TAP-4050) callers/callees/chains
- [TAP-4051](https://linear.app/tappscodingagents/issue/TAP-4051) symbol blast radius
- [ADR-0004](0004-deterministic-tools-only-contract.md) deterministic tools
- [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) graph taxonomy
- `docs/architecture/tool-budget.md`

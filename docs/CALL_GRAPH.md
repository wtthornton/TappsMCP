# Call graph tools (consumer guide)

TappsMCP v3.12.31+ ships **function-level call graph** tools for Python projects (Epic 114, [ADR-0017](adr/0017-function-level-call-graph-python-first.md)). Use them before refactors to see callers, callees, and affected tests — without grepping the repo.

---

## Tools

| Tool | When |
|------|------|
| `tapps_call_graph(symbol, query=callers\|callees\|chain\|all)` | Who calls this function? What does it call? |
| `tapps_impact_analysis(file_path, symbol=..., granularity=symbol\|both)` | Blast radius at file or symbol level |
| `tapps_diff_impact` | Git-changed files → ranked affected tests |

Module-level import impact remains `tapps_impact_analysis` without `symbol`. Call-graph tools complement import graphs; they do not replace them.

---

## Review path: `diff_impact` blast radius (TAP-4526)

`tapps_validate_changed(include_impact=true)` — the reviewer's batch entry point —
attaches a `diff_impact` block to its response. For each changed Python **symbol**
it reports, reusing the existing call graph (no new analysis, no LLM, no network,
per [ADR-0004](adr/0004-deterministic-tools-only-contract.md)):

- `callers` — in-repo functions/methods that call the symbol (from static CALLS edges).
- `affected_tests` — ranked `{test_file, test_symbol}` pairs that exercise it (TESTS edges).

Shape:

```json
"diff_impact": {
  "cache_status": "ready",
  "degraded": false,
  "symbols": {
    "pkg.mod.changed_fn": {
      "callers": ["pkg.mod.caller_a", "pkg.other.caller_b"],
      "affected_tests": [{"test_file": "tests/test_mod.py", "test_symbol": "test_changed_fn"}]
    }
  },
  "changed_files": ["pkg/mod.py"]
}
```

**Graceful degradation:** when the call-graph cache is missing or stale, the block
is still present with `degraded: true` and a `note` (empty `symbols`) rather than
raising. Rebuild via `tapps_call_graph` or `tapps_diff_impact(force_rebuild=true)`,
then re-review. This is distinct from the flat, cross-change-set `affected_tests`
block: `diff_impact` is keyed **per symbol** and adds each symbol's callers.

### `blast_radius_caveat` — incomplete-impact trust signal (TAP-4528)

When a reviewed change lands in a region where the call graph is **materially
incomplete**, the review verdict carries a top-level `blast_radius_caveat` so
agents know the impact analysis (callers / affected tests) may be partial:

```json
"blast_radius_caveat": {
  "degraded": true,
  "in_repo_gap_rate": 0.42,
  "parse_failures": 0,
  "reason": "high_in_repo_gap_rate",
  "note": "In-repo call-graph gap rate is 42% (threshold 10%) — many in-repo references are unresolved, so this change's blast radius may be incomplete."
}
```

- **`reason`** is one of `cache_not_ready` (cache missing / stale / unreadable —
  impact could not be computed), `parse_failures` (≥ 1 file failed to parse), or
  `high_in_repo_gap_rate` (in-repo gap rate `>=` the 10% threshold).
- The caveat is **derived from `summarize_call_graph_cache` output** — it is a
  read of the same health metrics below, not a new analysis pass (deterministic,
  ADR-0004: no LLM / no network).
- **Healthy / low-gap regions produce no caveat** — the field is absent, so
  clean reviews stay clean (no false alarms). A handful of stray unresolved
  external references (below the 10% in-repo threshold, zero parse failures) is
  normal and does **not** trip it.

The field sits beside `diff_impact` on `tapps_validate_changed` output when
`include_impact=true` and source (non-test) Python files are in the change set.

---

## Local cache (not in git)

The index is written to:

```text
.tapps-mcp/call-graph-index.json
```

This file is **gitignored** by design. It is rebuilt automatically when:

- You first call `tapps_call_graph` or `tapps_diff_impact`
- Source files change (git-aware fingerprint when `.git` exists)
- `INDEX_VERSION` bumps after a tapps-mcp upgrade

Check status anytime via `tapps_session_start` (`call_graph` block) or `tapps_doctor`.

**Rebuild manually:** any `tapps_call_graph` or `tapps_diff_impact` call rebuilds when stale; use `force_rebuild=true` only to bypass a matching cache you do not trust.

---

## Health metrics (read these, not raw gap counts)

| Metric | Meaning |
|--------|---------|
| `gap_rate` | `resolution_gaps / edges` — total unresolved call sites |
| `in_repo_gap_rate` | Actionable in-repo unresolved calls / edges — primary trust signal |
| `external_gaps` | Stdlib, builtin, and expected dynamic dispatch (not graph breakage) |
| `in_repo_gaps` | Unresolved calls that may be fixable via better static analysis |
| `gap_reasons` | Taxonomy: `unresolved_static_call`, `dynamic_dispatch`, `callback_opaque`, `framework_hof`, … |
| `in_repo_gap_reasons` | Gap reasons counted only for in-repo gaps |
| `parse_failures` | Files with syntax/decode errors omitted from the graph |
| `degraded` | Tool response flag when in-repo gaps or parse failures exist |

High total `gap_rate` on dynamic codebases is **expected** — most gaps are stdlib/builtin calls.
Use `in_repo_gap_rate` to judge whether the graph is trustworthy for refactor workflows.
Static analysis cannot resolve all Python dispatch. Gaps are honest uncertainty — prefer them over silent wrong edges ([ADR-0004](adr/0004-deterministic-tools-only-contract.md)).

---

## `tapps_dead_code` — GA, with an `in_repo_gap_rate` trust caveat (TAP-4527)

`tapps_dead_code` (vulture-backed unused-code detection) is **GA** — a supported tool, no longer Preview.

It reports unused functions, classes, imports, and variables with per-finding confidence and line numbers. Because vulture resolves references **statically**, it shares the same blind spot as the call graph: dynamic dispatch (`getattr`, plugin entry points, CLI/registry lookups, reflective calls) can hide a symbol's only callers, so a live symbol may be reported as **unused** — a false "unused" positive.

Use `in_repo_gap_rate` (above) as the trust signal: when a repo's in-repo gap rate is high, the call graph cannot resolve many in-repo callers, which is exactly the condition under which vulture's dead-code output is least reliable. Treat dead-code findings from high-gap repos as **advisory** — cross-check before deleting, and raise `min_confidence` to trim the noise floor.

---

## TDAD static test map (optional)

Export a grep-friendly test map without MCP at runtime:

```python
from pathlib import Path
from tapps_mcp.project.diff_impact import export_test_map

export_test_map(Path("."))  # writes ./test_map.txt
```

Format: `code_symbol<TAB>test_file<TAB>test_symbol` — useful for CI scripts and pre-commit targeting.

---

## Recommended agent workflow

1. **Session start** — confirm `call_graph.ready` or wait for background rebuild (`rebuild_scheduled`).
2. **Before editing a function** — `tapps_call_graph(symbol="handler_name", query="callers")`.
3. **After editing Python files** — `tapps_diff_impact` or `tapps_validate_changed(include_impact=true)`.
4. **Before deleting a symbol** — `tapps_impact_analysis(..., symbol="...", granularity="both")`.

---

## Non-goals

- Cross-repo service graphs
- Runtime / telemetry call graphs
- SCIP/LSP indexing by default
- Committing `call-graph-index.json` to git
- Eliminating all `resolution_gaps`

See [ADR-0017](adr/0017-function-level-call-graph-python-first.md) for scope and alternatives.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `call_graph.status: missing` | Run any graph tool once to warm the cache |
| `stale: true` after edits | `force_rebuild=true` or wait for fingerprint invalidation |
| `index_version_mismatch` | Rebuild after tapps-mcp upgrade (schema bump) |
| Huge gap count | Check `gap_reasons`; audit dynamic dispatch hotspots |

Fleet / MCP deploy: [operations/FLEET-MAINTENANCE.md](operations/FLEET-MAINTENANCE.md). Upgrade notes: [UPGRADE_FOR_CONSUMERS.md](UPGRADE_FOR_CONSUMERS.md).

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
| `gap_rate` | `resolution_gaps / edges` — primary health signal |
| `gap_reasons` | Taxonomy: `unresolved_static_call`, `dynamic_dispatch`, `callback_opaque`, `framework_hof`, … |
| `parse_failures` | Files with syntax/decode errors omitted from the graph |
| `degraded` | Tool response flag when gaps or parse failures exist |

High `gap_rate` on dynamic codebases is **expected**. Static analysis cannot resolve all Python dispatch. Gaps are honest uncertainty — prefer them over silent wrong edges ([ADR-0004](adr/0004-deterministic-tools-only-contract.md)).

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

1. **Session start** — confirm `call_graph.ready` or follow the rebuild hint.
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

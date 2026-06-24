# State Files Reference

Documents the files and directories that TappsMCP creates at runtime in
the project root, and the outcome of any audit / cleanup decisions.

## Active directories

| Path | Writer | Purpose |
|---|---|---|
| `.tapps-mcp/` | `tapps_init` / `bootstrap_pipeline` | Root runtime state directory |
| `.tapps-mcp-cache/` | Various tools | Cache: Linear snapshots, doc warm, validate-ok markers |
| `.tapps-mcp-cache/linear-snapshots/` | Cache gate hooks | Linear issue snapshot JSON files |

## Deprecated / removed directories

### `.tapps-mcp/learning/` — **REMOVED (TAP-2001 / TAP-2023)**

**Audit date:** 2026-05-23

**Finding:** Cargo-cult artifact. The directory was created by
`FileOutcomeTracker` and `FilePerformanceTracker` in
`tapps-core/adaptive/persistence.py`, but **neither class is instantiated
in production code** — they are re-exported as backward-compat shims only.
A `rg -e 'learning[/\\]' --type py` scan found zero call-sites in
`tapps-mcp` or `tapps-core` production paths; hits were docstrings in
`persistence.py` and references in `tapps-core` tests only.

**Action:** `tapps_init` / `bootstrap_pipeline` never created this
directory explicitly (confirmed: no reference in `pipeline/init.py`).
`_cleanup_legacy_learning_dir` in `session_start_helpers.py` removes the
directory on the next session start for any project that had it created by
an earlier test or manual run. Only removes files that match the expected
pattern (`outcomes.jsonl`, `expert_performance.jsonl`); logs a warning if
unknown files are present and leaves them alone.

## Active files

| Path | Writer | Purpose |
|---|---|---|
| `.tapps-mcp/session-handoff.md` | `tapps-handoff-session` skill (or manual) | Cross-session continue block; read by `tapps-continue-session` on next chat. Brain mirror via `tapps-mcp memory save --key session-handoff`. |
| `.tapps-mcp/metrics/tool_calls_*.jsonl` | TappsMCP tool handlers | Daily execution metrics (local leg of `dual` storage). Feeds `tapps_dashboard` / `tapps_stats` including `docs_metrics` and `session_funnel` sections. |
| `.tapps-mcp/session-capture.json` | legacy (pre-TAP-1999) | Session summary from the removed `tapps-memory-capture.sh` Stop hook. Superseded by `call_memory_index_session_start` (TAP-1999); the hook, its templates, and the `tapps_init(memory_capture=)` opt-in were removed. `tapps_session_start` still reads a stale file if present, for backward compat. |
| `.tapps-mcp/.linear-validate-sentinel` | `tapps-post-docs-validate.sh` | Confirms `docs_validate_linear_issue` ran before `save_issue` |
| `.tapps-mcp/.linear-snapshot-sentinel-*` | `tapps-post-linear-snapshot-get.sh` | Per-key unlock for Linear list-issues cache gate |
| `.tapps-mcp/.bypass-log.jsonl` | Hook bypass paths | Audit log of guarded-operation bypasses |
| `.tapps-mcp/.cache-gate-violations.jsonl` | `tapps-pre-linear-list.sh` | Linear cache-gate violation log |
| `.tapps-mcp/.push-test-log` | `.githooks/pre-push` | Tier-2 background test results |
| `.tapps-mcp/.validation-marker` | `tapps_validate_changed` | Marks a successful validation run |

## Session handoff funnel (dashboard)

`tapps_dashboard` section `session_funnel` (and matching recommendations) reports:

| Signal | Source | Meaning |
|---|---|---|
| `session_start_calls` | execution metrics JSONL (+ brain merge) | Sessions bootstrapped via `tapps_session_start` (proxy for continue-session volume). |
| `session_end_calls` | execution metrics | Handoff writes proxy — `/tapps-handoff-session` calls `tapps_session_end`. |
| `checklist_calls` | execution metrics | Pipeline completion proxy — `tapps_checklist` invocations. |
| `checklist_per_session_start` | derived ratio | Drop-off when many sessions start but few run checklist. |
| `handoff_file.updated_at` / `age_days` | `.tapps-mcp/session-handoff.md` mtime | Last persisted handoff; `stale` when older than 7 days. |

When gaps are detected (`low_checklist_completion`, `low_handoff_writes`, `missing_handoff_file`, `stale_handoff_file`), the dashboard `recommendations` section suggests `/tapps-handoff-session` or `tapps_checklist` as appropriate.

DocsMCP tool calls appear in the separate `docs_metrics` dashboard section (and `docs_tools` slice on `tapps_stats` when present), aggregated from the same JSONL/brain read path with `docs_*` tool names normalized from `mcp__docs-mcp__*` prefixes.

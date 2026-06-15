# Dogfood Retest Checklist (EPIC-113 / TAP-4026)

Run this checklist on the **tapps-mcp dev repo** after CallMcpTool unwrap (TAP-4017), rolling-stats filter (TAP-4025), and developer NLT bundle trim (TAP-4021/3963) ship. Goal: prove stop-hook telemetry and doctor recommendations reflect real pipeline compliance.

**Parent epic:** [TAP-4016](https://linear.app/tappscodingagents/issue/TAP-4016)

---

## Preconditions

1. **Reload MCP** after regenerating host configs:
   ```bash
   # Consumer dogfood retest — developer bundle (3 servers, doctor NLT PASS)
   uv run tapps-mcp init --host cursor --force --allow-package-init --no-uv
   uv run tapps-mcp init --host claude-code --force --allow-package-init --no-uv
   uv run tapps-mcp init --host vscode --force --allow-package-init --no-uv

   # Platform dev repo (tapps-mcp itself) — all six servers for full tool surface
   uv run tapps-mcp init --host cursor --force --allow-package-init --no-uv --bundle full
   ```
   Restart Cursor (or reload window) after init. **Consumer retest** expects the **developer bundle** (`nlt-build`, `nlt-memory`, `nlt-linear-issues`). The **tapps-mcp dev repo** normally runs **`--bundle full`** (doctor NLT WARN is acceptable here).

2. **Git hooks** (TAP-4023):
   ```bash
   git config --get core.hooksPath   # expect: .githooks
   test -x .githooks/pre-commit
   ```

3. **Source install** (dev repo uses global CLI via `.cursor/bin/*-serve.sh` after code changes):
   ```bash
   uv tool install --reinstall --from packages/tapps-mcp tapps-mcp
   ```

---

## Retest procedure

### A. Doctor baseline

```bash
uv run tapps-mcp doctor --quick
```

| Check | Pass criteria |
|-------|----------------|
| NLT partial enablement | PASS — ≤3 servers, combined eager ≤20 |
| Deprecated wrapper skills | PASS — no `tapps-score/gate/validate/report` on disk |
| Cursor loop-metrics telemetry | PASS or actionable detail — `callmcptool_unwrap=active` |
| Pipeline enforcement | `gate_skip_rate` uses **reliable** edit loops (`is_reliable_edit_loop_row`) |

### B. Automated stop-hook contract

```bash
uv run pytest packages/tapps-mcp/tests/unit/test_cursor_stop_completion_gate.py -q
uv run pytest packages/tapps-mcp/tests/unit/test_loop_metrics.py -k "callmcptool or legacy" -q
```

Expect: CallMcpTool unwrap prevents `QUALITY_GATE_SKIP` when `tapps_validate_changed` + `tapps_checklist` ran; `/tmp` edits excluded from gate scope.

### C. One compliant Cursor coding session

During a real agent session that edits Python under `packages/`:

1. `tapps_session_start` at session start
2. `tapps_quick_check` after each Python edit
3. `tapps_validate_changed(file_paths=...)` with **explicit paths** before declaring done
4. `tapps_checklist(task_type=...)`

**Pass:** No new row appended to `.tapps-mcp/.completion-gate-violations.jsonl` for that session (warn mode logs only when gate/checklist missing).

### D. Rolling metrics (7d window)

```bash
uv run python3 -c "
from pathlib import Path
import json
from tapps_mcp.tools.loop_metrics import compute_rolling_stats, compute_recent_edit_loop_stats
r = Path('.')
print(json.dumps({'rolling_7d': compute_rolling_stats(r), 'recent_edits': compute_recent_edit_loop_stats(r)}, indent=2))
"
```

| Metric | Pass criteria |
|--------|----------------|
| `gate_skip_rate` (reliable 7d) | **< 0.30** (30%) |
| `legacy_unparsed_callmcptool` | Doctor reports count; rows excluded from rate |
| Recent edit loops (last 10) | `gate_skip_rate` reflects current behavior, not legacy jsonl |

---

## Retest run — 2026-06-15

**Operator:** Cursor agent session (Tier-1 implementation + retest)  
**Git:** dirty working tree on `master` @ post TAP-4021/4025/3960 fixes

### Results

| Step | Result | Evidence |
|------|--------|----------|
| A. Doctor NLT | **PASS** | 3 servers; combined eager=18 |
| A. Deprecated skills | **PASS** | No wrapper skills in `.cursor/skills/` |
| A. Cursor telemetry | **PASS** | `callmcptool_unwrap=active`; 148 legacy rows noted |
| A. Pipeline enforcement | **PASS** | `7d gate_skip_rate=0%` (216 loops, reliable filter) |
| B. Stop-hook tests | **PASS** | 7/7 `test_cursor_stop_completion_gate` + doctor telemetry tests |
| C. Compliant session | **PASS** | This session called `session_start`, `quick_check`, `validate_changed`, `checklist`; no new completion-gate violation attributed to in-repo Python edits |
| D. Rolling metrics | **PASS** | `gate_skip_rate=0.0`; recent 10 edit loops `gate_skip_rate=0.0` |

### Notes

- **Legacy jsonl:** 148 pre-TAP-4017 `CallMcpTool` rows remain in `.tapps-mcp/loop-metrics.jsonl` but are excluded from doctor enforcement via `is_reliable_edit_loop_row`.
- **Historical violations:** `.completion-gate-violations.jsonl` still contains 88 prior entries (mostly `/tmp` script edits and pre-fix sessions). Retest criterion is **zero new violations** on compliant sessions going forward.
- **Host configs:** Doctor failed NLT check until `.mcp.json` and `.vscode/mcp.json` were regenerated (only `.cursor/mcp.json` had been trimmed initially). Consumer retest requires the developer bundle on all three host configs; the platform dev repo may use `--bundle full` afterward.

### Verdict

**EPIC-113 dogfood retest: PASS** — telemetry trustworthy for Cursor; doctor NLT check passes; reliable `gate_skip_rate` below 30%.

**Follow-up (non-blocking):** TAP-4024 — expand `docs/TROUBLESHOOTING.md` Cursor vs Claude transcript section; optional 7-day calendar watch as legacy rows age out of the jsonl window.

---

## Quick re-run (copy/paste)

```bash
cd /path/to/tapps-mcp
uv run tapps-mcp doctor --quick | rg -i "NLT partial|Cursor loop|gate_skip|Deprecated"
uv run pytest packages/tapps-mcp/tests/unit/test_cursor_stop_completion_gate.py -q
uv run python3 -c "from pathlib import Path; from tapps_mcp.tools.loop_metrics import compute_rolling_stats; import json; print(json.dumps(compute_rolling_stats(Path('.')), indent=2))"
```

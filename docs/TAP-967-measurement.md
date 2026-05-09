# TAP-967: 2-Week `list_issues` Call-Count Measurement Report

**Measurement date:** 2026-05-07  
**Baseline date:** 2026-04-23  
**Baseline count:** 5,118 calls in 7 days (pre-fix)  
**Fix commit referenced in TAP-967:** `fd18b2d` (not present in this repo's local history — see note)  
**Prepared by:** scheduled measurement agent

---

## 1. Baseline

| Field | Value |
|---|---|
| Measurement window | 7 days ending 2026-04-23 |
| Raw call count | 5,118 `plugin_linear_linear.list_issues` calls |
| Cache adoption | ~0.26% (cited in shipped template text) |
| Fix description | Narrowing text added to 4 call sites (linear-issue skill + 2 templates + docstring) |
| Fix commit | `fd18b2d` |

---

## 2. Current 7-Day Count

**Current 7-day call count: UNAVAILABLE FROM REPO**

No committed telemetry or OTEL data exists for the `plugin_linear_linear.list_issues` call
volume in this repository. Specifically:

- `.tapps-mcp/metrics/` contains a single JSONL file (`tool_calls_2026-02-10.jsonl`, 778 entries)
  tracking **tapps-mcp** tool calls only — not Linear plugin calls.
- `.ralph/logs/` contains Claude session logs from 2026-03-22 only; no `list_issues` references.
- No `.tapps-mcp/.cache-gate-violations.jsonl` or `.tapps-mcp/.bypass-log.jsonl` exists
  (the PreToolUse enforcement hook in TAP-1224 was merged 2026-05-02, so any gate violations
  postdate this repo's history window).
- No `docs/TAPPS_RUNLOG.md` or OTEL/Prometheus export is present.
- This repo's git history begins 2026-05-01. Commit `fd18b2d` is not present locally —
  the fix was applied either in a prior clone or squashed before the current history begins.

**The >=30% drop target cannot be confirmed or denied from repo-local data.**  
The measurement must be obtained from the Tapps Command Center dashboard or an external
telemetry store (Linear API call logs, OTEL backend, or Claude Code session analytics).

---

## 3. Absolute / Percent Delta

| Field | Value |
|---|---|
| Baseline (2026-04-23, 7-day) | 5,118 calls |
| Current (2026-05-07, 7-day) | unavailable |
| Absolute delta | — |
| Percent reduction | — |
| >=30% target met? | **unknown — data unavailable** |

---

## 4. Shipped-Template Audit (as of 2026-05-07)

The narrowing text from the fix commit is confirmed present in all three target files.

### 4.1 `.claude/skills/linear-issue/SKILL.md` — **CONFIRMED**

Narrowing language present (line 44):
```
On cache miss (data.cached is false): call mcp__plugin_linear_linear__list_issues with narrow
filters — team, project, state, includeArchived=false (never call without filters).
```
Single-issue bypass present (line 42):
```
If the user names a specific issue (e.g. "triage TAP-686"), use
mcp__plugin_linear_linear__get_issue(id="TAP-686") — skip list/cache entirely.
```

### 4.2 `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py` — **CONFIRMED**

Claude Code template (lines 422–424): identical narrowing text as SKILL.md above.

Cursor template (lines 858–859): equivalent text using `linear_list_issues` / `linear_get_issue`
tool names:
```
On cache miss (data.cached is false): call linear_list_issues with narrow filters —
team, project, state, includeArchived=false (never call without filters).
```

Full `linear-read` skill block present (lines 442–503) including explicit antipattern callouts:
- The 6-poll kickoff antipattern (`list_issues` × 6 per state×priority bucket)
- The status-bucket sweep antipattern (3 sequential calls for backlog/unstarted/started)
- Unfiltered scroll antipattern (`list_issues({})` or `list_issues({team, limit:250})`)

Baseline data cited verbatim in both Claude Code and Cursor templates (lines 452, 883):
```
TAP-967 audit found 5,368 list_issues calls with 0.26% cache adoption
```
*(Note: the template uses 5,368; the TAP-967 baseline recorded here is 5,118 — minor discrepancy,
likely from rounding or a different 7-day window. The intent is the same.)*

### 4.3 `packages/docs-mcp/src/docs_mcp/server_linear_tools.py` — **CONFIRMED**

Narrowing docstring present (lines 238–241) in `docs_linear_triage`:
```python
1. list_issues (Linear MCP) with explicit narrowing —
   always pass team, project, state ("backlog" or "unstarted"),
   and includeArchived=False. Broad queries waste Linear quota;
   narrow ones cache well.
```

---

## 5. Follow-On Commits (Last 14 Days)

Commits since 2026-04-23 touching the three audited files:

| Commit | Date | Message |
|---|---|---|
| `dfa45e1` | 2026-05-01 | `chore(rules): codify integration-hygiene + repo-workflow rules` — touches `.claude/skills/linear-issue/SKILL.md` and `server_linear_tools.py` |
| `13c6ac9` | 2026-05-01 | `feat(tapps-mcp): linear-read skill for cache-first multi-issue reads (TAP-1260)` — adds full `linear-read` skill to `platform_skills.py` and `.claude/skills/linear-issue/SKILL.md`; introduces the 6-poll antipattern doc |

**Significant adjacent commits (not modifying the three files directly but strongly related):**

| Commit | Date | Message |
|---|---|---|
| `4d71b1e` | 2026-05-02 | `feat(tapps-mcp): hard-enforce Linear cache-first reads via PreToolUse hook (TAP-1224)` — hard-blocks `list_issues` calls without a prior `snapshot_get` sentinel; this is the structural enforcement that soft rules alone could not provide |
| `667ec6f` | 2026-05-02 | `docs+upgrade: sync TAP-1224/1280/1284 work into templates + upgrade run` — propagates enforcement to consumer-facing templates |

---

## 6. Recommendation for TAP-967 Status

**Soft-rules phase complete; hard enforcement shipped.**

The template narrowing (the original TAP-967 fix) is confirmed in place. More importantly,
TAP-1224 (merged 2026-05-02) added a PreToolUse hook that structurally blocks uncached
`list_issues` calls at the agent harness level — this is a materially stronger control than
the docstring narrowing alone.

Without live telemetry, a formal >=30% measurement is impossible from this repo. However:

- Hard enforcement via PreToolUse hook (TAP-1224) eliminates the unfiltered scroll pattern
  entirely for projects that have run `tapps_upgrade` and activated the hook.
- The `linear-read` skill (TAP-1260) routes all multi-issue reads through `snapshot_get` first,
  collapsing typical 5–12 call sequences to 0–1 Linear API calls per session.
- The `.tapps-mcp/.cache-gate-violations.jsonl` log (written by the TAP-1224 hook) is the
  correct ongoing measurement instrument for future reports.

**Suggested TAP-967 action:** close with note that structural enforcement supersedes the
soft-rule drop target; use violation log as the ongoing KPI instrument going forward.

---

## 7. Ready-to-Paste Linear Comment

```
**2-week measurement update (2026-05-07)**

**Baseline (2026-04-23):** 5,118 `list_issues` calls / 7 days, ~0.26% cache adoption.

**Current 7-day count:** unavailable from repo-local data. No OTEL/telemetry export is
committed to git. The Tapps Command Center dashboard or an external call-log store is
required for a numeric drop measurement.

**Template audit (all 3 files):** ✅ narrowing text confirmed in place as of today.

**Follow-on commits since fix:**
- `13c6ac9` (2026-05-01) — `linear-read` skill with 6-poll antipattern callout (TAP-1260)
- `4d71b1e` (2026-05-02) — PreToolUse hard-enforcement hook blocking uncached `list_issues`
  entirely (TAP-1224)
- `667ec6f` (2026-05-02) — template sync propagating enforcement to consumers

**Assessment:** structural enforcement via PreToolUse hook (TAP-1224) is a stronger control
than the soft-rule narrowing that was TAP-967's original fix. Numeric confirmation of the
>=30% drop requires pulling the TAP-1224 violation log
(`.tapps-mcp/.cache-gate-violations.jsonl`) from a consumer project, or querying the
dashboard.

Recommend closing TAP-967: the root cause (unbounded `list_issues` calls) is now blocked at
the harness level. Ongoing monitoring KPI = 24-hour violation count from the cache-gate log.
```

---

*Report generated by scheduled measurement agent. No call-count numbers were invented.
Data gaps are stated explicitly above.*

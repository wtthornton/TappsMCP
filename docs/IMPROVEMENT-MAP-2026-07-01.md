# TappsMCP Improvement Map — 2026-07-01

Full-system review of the tapps-mcp project: the six nlt-* MCP servers, init/upgrade/doctor
lifecycle, installed skills and .md scaffolding, memory (BrainBridge), research (Context7),
caching, and code-graph tooling. Reviewed from the position of the actual consumer — an LLM
coding in Claude Code — with live telemetry, not just code reading.

**Version reviewed:** 3.12.49 (tapps-mcp + docs-mcp, blue/green current `3.12.49-19819af`)

## Evidence base

| Source | What it provided |
|---|---|
| Live `tapps_server_info` / `tapps_stats(period=all)` / `tapps_usage(30d)` / `tapps_doctor(quick)` | 3,044 recorded calls (AgentForge MetricsHub), gate/skip rates, cache state, 73 doctor checks |
| Cross-project loop metrics (`.tapps-mcp/loop-metrics.jsonl`, 5 projects) | 3,729 stop-event records, per-tool usage across AgentForge / NLTlabsPE / ReportLab / tapps-brain / tapps-mcp |
| Violation logs (`.completion-gate-violations.jsonl`, `.cache-gate-violations.jsonl`) | 401 completion-gate + 956 cache-gate violations |
| Source audit (5 parallel deep reads) | Server split, lifecycle flows, skill templates, memory/caching internals, with file:line anchors |

---

## 1. Verdict summary

### What works — do not destabilize

- **Six-server NLT split with eager/deferred budget** (ADR-0016/0018/0024). 25 eager / 54
  deferred / 79 tools, zero duplication, HTTP fleet on 8760–8765 all reachable and supervised.
  The taxonomy is right; the budget discipline is real. Keep it.
- **Doctor's check catalog** (quick mode): 73 checks, 70 passing, including genuinely valuable
  ones (blue/green drift, transport drift, brain version floor, retired-hook detection,
  secrets scan, hook-script existence). Best-in-class breadth.
- **Upgrade machinery**: managed-block smart-merge for multi-file skills
  (`pipeline/skill_managed_block.py`), version stamps, timestamped backups, dry-run with
  `safe-to-run`/`review-recommended` verdicts, retired-hook migration. Solid design.
- **Context7/KB cache design**: per-library TTLs (12h fast-moving / 48h stable), stale-serve +
  background refresh, provider chain with LlmsTxt fallback, circuit breaker. Correct shape.
- **Linear snapshot cache + hook auto-populate** (TAP-1412): get 652 / invalidate 688 observed;
  0 gate-miss violations in 24h. The cache-first dance works now.
- **Telemetry substrate**: loop-metrics.jsonl + MetricsHub + violations logs give real
  observability. This review was only possible because of it.
- **Skill tool references are clean** — no broken MCP tool names in the key skills
  (tapps-init/upgrade/finish-task/research/memory all reference real, correctly-namespaced tools).
- **ADR-0029 unified cache substrate** is already in flight (PRs #188–190) — several findings
  below land inside that campaign rather than needing a new one.

### What's broken — headline numbers

| # | Finding | Evidence |
|---|---|---|
| F1 | `tapps_doctor` (full mode) **crashes** over MCP | `asyncio.run() cannot be called from a running event loop` — reproduced live |
| F2 | Bootstrap overhead is **55% of all tool calls** | session_start 1,026 + server_info 641 of 3,044 total |
| F3 | Research discipline collapsed: `lookup_docs_to_edit_ratio` = **0%** (7d, 45 loops) | doctor's own "Chronic lookup_docs_underused" finding |
| F4 | 397 CHECKLIST_MISSING violations; gate-skip ~24% overall; everything in warn mode | violations logs, 5 projects |
| F5 | ~12 tools with **zero lifetime usage**; eager slots spent on unused tools | catalog-vs-telemetry diff |
| F6 | `tapps_memory` action count: code says **44**, installed docs say 42 and 33 | `server_memory_tools.py:51-105` vs AGENTS.md / skills |
| F7 | `tapps_validate_changed` p95 = **58.7s** — the most-used gate is the slowest tool | tapps_stats, 373 calls |
| F8 | Docs cache **117 of 121 entries stale** (AgentForge, 72MB) | server_info diagnostics |
| F9 | Call graph: 54% in-repo resolution gap, ~1 lifetime call, 30–60s cold start | doctor check + telemetry |
| F10 | MCP server instructions: one generic blob ×3 servers; docs servers have **none** | `server.py:88-120`, `docs_mcp/server.py:67` |

---

## 2. P0 — broken now (fix this week)

### F1. Full-mode doctor crashes when called over MCP

- **Repro:** `tapps_doctor()` (quick=false) → `Error executing tool tapps_doctor: asyncio.run()
  cannot be called from a running event loop`. `tapps_doctor(quick=true)` works.
- **Root cause:** `distribution/doctor.py:4870` (`check_context7_live`) calls the sync
  `probe_context7(root, key, force=True)`; `diagnostics.py:210` does
  `asyncio.run(probe_context7_async(...))`. The docstring at `diagnostics.py:199-204` even says
  *"Must not be called from within a running event loop"* — but the MCP tool path runs inside
  FastMCP's loop.
- **Second defect in the same incident:** the exception escapes and kills the **entire** doctor
  run. One bad check must never take down the diagnostic tool — doctor is what you reach for
  when things are broken.
- **Fix:**
  1. In `check_context7_live`, detect a running loop (`asyncio.get_running_loop()`) and either
     run the probe in a worker thread (the `pipeline/init.py:1417-1427` pattern already handles
     exactly this) or accept an async path from the tool layer.
  2. Wrap every doctor check invocation in a per-check try/except that converts exceptions into
     a failed `CheckResult("…", ok=False, message=f"check crashed: {exc}")`. Add a regression
     test that runs `run_doctor_structured()` inside `asyncio.run()` wrapper to simulate the
     server context.
  3. Note `force=True` at doctor.py:4870 also defeats the probe's TTL marker — intentional for
     doctor, but confirm; if not, drop it.
- **Effort:** small (half-day incl. test).

### F6. Tool-surface documentation is generated by hand and provably wrong

- **Evidence:** `_VALID_ACTIONS` (`server_memory_tools.py:51-105`) = **44 actions**. Installed
  copies claim "42 actions" (AgentForge AGENTS.md, MEMORY_REFERENCE.md, tapps-pipeline.mdc,
  tapps-memory SKILL.md) and "33 actions" (AgentForge/projects/tapps-brain rules). A review
  subagent reading the code reported "32". Nobody matches the source.
- **Why it matters:** the LLM consumer takes these numbers/action lists literally. Wrong action
  lists → invalid calls → the tool "feels unreliable" → the LLM stops using it. This is the
  single most direct "100% accurate" failure in the stack.
- **Fix (pattern already exists in this repo):** `server_memory_tools.py:107-114` documents a
  drift test (`test_agents_template_memory_docs.py`) asserting templates don't claim invalid
  save scopes. Generalize:
  1. **Generate, don't transcribe.** Any count or enumeration of actions/tools in templates
     (AGENTS.md, SKILL.md, rules, MCP instructions) must be rendered from
     `_VALID_ACTIONS` / the tool registry at template-build time, or replaced by wording that
     can't drift ("the actions listed by `tapps_memory(action='profile_info')`").
  2. Add a drift test: for every shipped template containing `N actions` or a tool-name list,
     assert against the live registry. Fail the release on mismatch.
  3. `tapps_upgrade` then propagates corrected templates to consumers on next run.
- **Effort:** medium (1–2 days), high leverage.

### F2. Bootstrap overhead: 55% of all MCP calls produce no work product

- **Evidence:** of 3,044 lifetime calls in AgentForge's MetricsHub: `tapps_session_start` 1,026,
  `tapps_server_info` 641. Cross-project telemetry confirms session_start is the #1 tool
  (1,867 calls). Meanwhile every tool response embeds a `pipeline_progress` blob (~20 tool
  names + counts) and server_info returns ~4–5k tokens of `recommended_workflow` /
  `quick_start` / `critical_rules` / `pipeline` boilerplate.
- **Diagnosis:**
  - session_start at 1,026 is hook-driven and sentinel-cached (observed 51ms cached path) —
    acceptable, though the 1h sentinel means long sessions re-bootstrap.
  - **server_info at 641 is an anomaly.** Nothing in the documented flow needs discovery that
    often. Find the caller (statusline? a hook? skills instructing "call server_info first"?)
    via the loop-metrics `tools_used` adjacency and kill the repeat caller or give server_info
    the same sentinel-cache treatment as session_start.
  - `pipeline_progress` in **every** response is token spend on every single tool call in every
    session. It belongs in `tapps_usage`/`tapps_checklist`/`tapps_session_start` responses only.
- **Fix:** (1) trace + fix the server_info hammering; (2) strip `pipeline_progress` from all
  responses except the three pipeline-state tools; (3) cut server_info's static boilerplate to a
  pointer ("workflow: see nlt-build server instructions") — it duplicates the MCP instructions
  blob verbatim.
- **Effort:** small-medium. Direct token savings on every call in every consuming project.

---

## 3. P1 — the adoption problem: tools exist, the LLM doesn't use them

This is the core of "why some tools are used and others are not." The data says usage follows
**in-band prompting at the moment of need**, not documentation volume:

- Tools wired into hooks or skills get used: session_start (hook), quick_check (post-edit
  habit, 341–438 calls), validate_changed (finish-task skill, 373–535), checklist (162–249),
  linear snapshot tools (hook-enforced dance, 650+ each).
- Tools that require the LLM to *remember* they exist at the right moment don't get used:
  call_graph (1 call), diff_impact (0), impact_analysis (0 — **despite being an eager tool**),
  dead_code (5), dashboard (1), pipeline (0), decompose (0), domain_playbook (0),
  audit_close_coverage (0), federate_* memory actions (0, unreachable from any skill).
- lookup_docs sits in between: 106 calls lifetime but **0% of edit loops in the last 7 days** —
  it gets used in bursts when a skill/hook nudges, then decays.

### F3. Make research (lookup_docs) fire at the moment of edit — not in a manifesto

- Today the instruction lives in: MCP instructions ×3 servers, AGENTS.md, CLAUDE.md rules,
  server_info boilerplate, the tapps-research skill. Five copies of "call lookup_docs first"
  and a 0% ratio anyway. More text is not the fix.
- **Fix — in-band, targeted, at edit time:**
  1. The post-edit hook (or `tapps_quick_check` response) should detect **new/changed imports**
     in the diff and, when the library has no lookup recorded this session, append a one-line
     actionable nudge to the quick_check result: `"httpx imported — no docs lookup this
     session. Call tapps_lookup_docs(library='httpx', topic='<what you're doing>')"`.
     A specific instruction with arguments filled in gets followed; a generic rule doesn't.
  2. Wire `libraries_without_lookup` (already computed in `tapps_usage`) into
     `tapps_validate_changed`'s response as a named gap, so finish-task surfaces it before Done.
  3. Track the ratio weekly; if in-band nudging doesn't move it above ~50% on edit loops that
     touch external APIs, escalate to a soft gate at high engagement.
- **Effort:** medium. This is the highest-leverage change for "LLM does the research."

### F4. Stop shipping warn-mode forever — promote gates the data says are ready

- **Evidence:** 397 CHECKLIST_MISSING; gate-skip 24% overall (31% AgentForge, 39% NLTlabsPE);
  stop-hook `warn` everywhere; Linear cache gate `warn` with **0 violations in 24h** and
  doctor itself printing "TAP-1333 auto-promote criteria met" — while nothing promotes it.
- **Fix:**
  1. Implement the promotion: when doctor's criteria hold for N consecutive days, either
     auto-flip the yaml (`linear_enforce_cache_gate: block`, stop-gate `block` at high
     engagement) or emit a one-command remediation (`tapps-mcp doctor --apply-promotions`).
     Criteria-met-but-never-promoted is the worst state: the measurement exists, the action
     doesn't.
  2. Checklist enforcement: at `llm_engagement_level: high`, sessions that edited code should
     fail the stop gate (exit 2) without `tapps_checklist`, not warn into a log nobody reads
     until next session's reminder.
  3. Keep warn mode as the default for `medium`; this is about honoring the engagement level
     the consumer explicitly configured.
- **Effort:** small-medium.

### F5. Prune and re-tier the tool catalog against observed usage

- **Zero-lifetime-usage list (cross-project):** `tapps_diff_impact`, `tapps_impact_analysis`,
  `tapps_dashboard`, `tapps_decompose`, `tapps_pipeline`, `tapps_domain_playbook`,
  `tapps_audit_close_coverage`, `tapps_feedback`, `brain_propose/approve_hive_elevation`,
  memory `federate_*` (6 actions), and effectively `tapps_call_graph` (1 call) and
  `tapps_session_end` (4).
- **Mis-tiered eager slots:** `tapps_impact_analysis` is *eager* on nlt-build (9-slot budget)
  with **zero** observed calls; `tapps_validate_config` (17–87 calls) is deferred.
- **Fix, per tool, choose one of three:**
  1. **Retire** (delete or fold): `tapps_dashboard`, `tapps_decompose`, `tapps_pipeline`
     (the prompt covers it), `tapps_domain_playbook` unless a skill routes to it. Memory
     `federate_*`: no installed skill can reach them — retire from `_VALID_ACTIONS` or ship the
     skill that uses them; an unreachable action is pure maintenance tax plus schema tokens.
  2. **Re-tier**: demote `tapps_impact_analysis` to deferred; promote `tapps_validate_config`.
     Re-run this audit quarterly from loop-metrics — the data is already collected.
  3. **Route** (the tool is good but undiscoverable): `tapps_diff_impact` and
     `tapps_call_graph` should be *consumed by* the review pipeline / finish-task skill rather
     than waiting for the LLM to reach for them (the TappsMCP review-gate work from the
     call-graph campaign is the model — same pattern here: platform calls the tool, LLM reads
     the verdict).
- **Effort:** medium; mostly deletions and spec/table updates in
  `nlt-mcp-plugin-spec.yaml` + `nlt_mcp_config.py`.

### F10. Per-server MCP instructions (accuracy + tokens)

- **Evidence:** `_TAPPS_MCP_SERVER_INSTRUCTIONS` (`server.py:88-118`) is one blob passed to
  every profile — so **nlt-memory and nlt-setup ship code-gate instructions** ("call
  tapps_quick_check after editing", "tapps_lookup_docs before library APIs") that reference
  tools those servers don't even expose. The client renders the identical ~300-token blob
  three times per session. Meanwhile `docs_mcp/server.py:67` and the combined platform server
  pass **no instructions at all** — the 29-tool nlt-project-docs surface (0 eager) has zero
  guidance.
- **Fix:** instructions keyed by profile in `NLT_SERVER_SPECS`:
  - nlt-build: current pipeline blob (it's good), minus the memory/setup content.
  - nlt-memory: when to save/recall/handoff; the 3–4 actions that matter; pointer to
    `action='profile_info'` for the full surface.
  - nlt-setup: "doctor for diagnosis, init/upgrade for scaffolding; everything else is deferred."
  - nlt-project-docs / nlt-linear-issues / nlt-release-ship: 3–5 lines each describing when to
    reach for the surface (these are currently invisible to the LLM until a skill names them).
- **Effort:** small. Straight accuracy + token win.

### F7. `tapps_validate_changed` latency (p95 58.7s, avg 13.4s, 373 calls)

- The most-frequently-required gate is the slowest thing in the stack; slow gates teach the
  LLM to skip gates (see F4's 24% skip rate — these are causally linked).
- **Fix:** land it inside ADR-0029: per-file content-hash result cache
  (`tools/content_hash_cache.py` already started) so unchanged files re-validate in ~0ms;
  parallelize checker subprocesses per file; return first-failure fast. Target p95 < 10s on a
  10-file change set.
- **Effort:** medium; campaign already in flight.

---

## 4. P2 — lifecycle: init / upgrade / doctor gaps

### Doctor (beyond the P0 crash)

1. **Hook-wiring validation gap:** doctor verifies hook *scripts exist on disk*
   (`pipeline/upgrade.py:151-180` manifest) but never that they're *wired* in
   `.claude/settings.json`. A project with 17 scripts and zero wiring reports healthy. Add a
   wiring check: for each canonical hook, assert a matching `hooks.<Event>[].hooks[].command`
   entry. (The PreToolUse-matchers check does this for 4 matchers; generalize it.)
2. **Skill-template drift detection:** doctor checks presence ("tapps-memory skill: Present")
   but not content parity with the shipped template. Add per-skill content-hash comparison
   (managed-block hash vs template hash) → "current / stale / hand-edited" verdict. This is
   what would have caught F6 in the field.
3. **Auto-heal:** the three failing checks on AgentForge (CLAUDE.md stamp, AGENTS.md 3.12.48,
   missing Karpathy) all say "Run tapps-mcp upgrade". A `--fix` flag (or
   `doctor --apply-promotions`, same switch) that runs the named remediations would convert
   doctor from a report into a repair tool. Every failing check already carries its remediation
   string — execute it.

### Upgrade

4. **No rollback command.** Backups land in `.tapps-mcp/backups/` (kept 5, deduped 60s) but
   restoration is manual. Ship `tapps-mcp rollback [--list]`.
5. **Dry-run doesn't pre-parse managed JSON.** A malformed `.claude/settings.json` can pass
   dry-run (`safe-to-run`) then fail live. Parse all managed JSON during dry-run; downgrade the
   verdict to `blocked` on parse failure.
6. **Engagement-level changes silently don't propagate.** Editing `llm_engagement_level` in
   yaml leaves AGENTS.md/rules stale until a manual re-init with `overwrite_agents_md=True`.
   Minimum fix: doctor check comparing yaml level vs the level stamped into AGENTS.md;
   better: `tapps_set_engagement_level` triggers the template refresh itself.

### Skills & installed .md scaffolding

7. **Six shipped skills are installed nowhere:** `tapps-domain-{frontend,security,testing}` and
   `tapps-flow-{develop,frontend,review}` exist only in the source repo. Decide: ship them in
   init/upgrade manifests, or delete them. Templates that never install are silent rot.
8. **Multi-root duplication is a real context tax.** In a Claude Code session with several
   working directories, the same tapps-* skill descriptions load once *per project* — this
   session carries ~6 copies of the tapps skill set, including the contradictory
   "42 actions"/"33 actions" pair side by side. tapps-mcp can't change the client's loading
   behavior, but it can: (a) keep descriptions short and identical everywhere (byte-identical
   templates dedupe visually and cache better), and (b) fix drift (F6) so duplicates at least
   agree.
9. **`autonomy.md` drift is legitimate but invisible.** AgentForge's copy has a prod-gating
   section the template lacks. Today upgrade would either clobber or skip it silently
   depending on skip-tokens. The managed-block pattern (BEGIN/END markers + project region)
   used for skills should extend to rules files so local additions survive upgrades *visibly*.
10. **nlt-orchestrator has no scaffolding at all** (no AGENTS.md, no .tapps-mcp.yaml, 4 local
    skills). If intentional, add it to a documented "non-consumer" list doctor understands;
    if not, run init there.

---

## 5. P3 — caching, memory, research hardening

11. **Multi-agent sentinel race (highest-severity cache bug).** `.tapps-mcp/.tapps-session-id`
    (1h TTL) makes a second concurrent agent on the same checkout skip bootstrap and trust the
    first agent's call-graph fingerprint / dep-scan state. Concurrent sessions on one checkout
    are a documented reality in this fleet. Fix: include PID/session-id in the sentinel and
    treat foreign-session sentinels as valid-for-read but re-verify fingerprints; or per-session
    sentinel files with a shared freshness floor.
12. **KB cache is a write-mostly graveyard: 117/121 entries stale (72–80MB per project).**
    Stale-serve+refresh only helps entries that get *re-read*; one-shot lookups accumulate
    forever (LRU eviction exists but at `cache_max_mb: 100` it rarely triggers). Add to the
    ADR-0029 warmer: refresh only entries with ≥2 lifetime hits; GC entries unread for 30+
    days; surface hit-rate in doctor (`cache stats 5/5` shipped — wire it into a check with
    thresholds).
13. **Context7 library pinning.** Fuzzy library resolution can silently pick the wrong
    Context7 ID/version across sessions. Support `.tapps-mcp.yaml` `docs_pins: {httpx:
    "/encode/httpx", react: "/facebook/react/v18"}` consulted before fuzzy match; init's
    tech-stack detection can pre-populate pins. Directly serves "correct research, every time."
14. **Call-graph cold start & honesty** (mostly filed already — TAP-4553 CI-artifact +
    load-on-session-start, ADR on the honesty boundary): prioritize *warm at session_start in
    the background* (don't block), and keep printing `in_repo_gap_rate` (0.544 on AgentForge)
    in every call-graph response so consumers calibrate trust. The AgentForge gap-rate also
    suggests running the TS/dynamic-dispatch resolver improvements against consumer repos, not
    just this one.
15. **profile_mismatch warning noise:** `brain_bridge.profile_mismatch`
    (`brain_bridge.py:1647-1650`) fires at every AgentForge session start listing 22
    "gated" tools that are actually deferred-loading false positives (preflight was removed at
    line ~2100 but the warning survived). Either teach it about `defer_loading: true` or delete
    it. A warning that's always wrong trains operators to ignore all warnings.
16. **Dependency-scan cache is in-memory only** (5-min TTL, lost on restart) → duplicate
    pip-audit runs. Move onto the ADR-0029 substrate with a content-hash key
    (lockfile hash → verdict).
17. **Linear snapshot TTLs are global** — fine as a default, but expose per-project override
    keys in yaml (`linear_cache_ttl_open_seconds`) since fast/slow workspaces differ. Low
    priority; the gate data shows the current dance working.
18. **`tapps_validate_changed` fails open on path mismatch** (observed live during this
    review): absolute `file_paths` + `project_root` override → `files_validated: 0` but
    `success: true` and `all_gates_passed: true`. An LLM reads that as "gate passed." The
    `path_hint` is good, but the verdict should not be a pass when explicit paths were
    requested and zero validated — return `all_gates_passed: false` (or a distinct
    `verdict: "no-files-matched"`) whenever `file_paths` was non-empty and nothing resolved.

---

## 6. Measurement plan — prove the fixes worked

Track weekly (all already derivable from existing telemetry; consider a doctor summary table):

| KPI | Now | Target |
|---|---|---|
| `lookup_docs_to_edit_ratio` (7d, edit loops touching external APIs) | 0% | >50% |
| Checklist coverage on edit sessions | 40% (AgentForge) – 67% (tapps-mcp) | >90% at high engagement |
| Gate-skip rate (rolling 30d) | 16–30% | <5% |
| Bootstrap share of MCP calls (session_start+server_info) | ~55% | <25% |
| `tapps_validate_changed` p95 | 58.7s | <10s |
| KB cache stale ratio | 97% (117/121) | <30% with hit-rate ≥2 policy |
| Zero-usage tools in catalog | ~12 | 0 (retired, re-tiered, or routed) |
| Template drift failures (new CI check) | n/a (F6 latent) | 0 at release |

## 7. Suggested delivery order

1. **Wave 1 (stabilize, days):** F1 doctor crash + per-check containment · F6 drift test +
   regenerate templates · F15 profile_mismatch noise · F2 server_info hammering +
   `pipeline_progress` diet.
2. **Wave 2 (adoption, ~1 week):** F3 in-band lookup_docs nudge · F4 gate promotion mechanics ·
   F10 per-profile instructions · F5 catalog prune/re-tier.
3. **Wave 3 (performance, inside ADR-0029):** F7 validate_changed content-hash cache · F12 KB
   cache GC/warmer policy · F16 dep-scan persistence · F14 call-graph session-start warm
   (TAP-4553).
4. **Wave 4 (lifecycle polish):** doctor --fix/promotions · rollback command · hook-wiring
   check · skill-drift check · engagement propagation · domain/flow skills ship-or-delete ·
   managed-block rules.

Each wave is independently shippable; Waves 1–2 need no design work. Waves 3–4 items that
overlap ADR-0029 / TAP-4553 should be folded into those existing campaigns rather than filed
as new epics.

---

*Generated from a live review on 2026-07-01 against tapps-mcp 3.12.49 across five consuming
projects. Telemetry anchors: AgentForge MetricsHub (3,044 calls), cross-project loop-metrics
(3,729 stop events), completion/cache-gate violation logs (401 / 956 entries).*

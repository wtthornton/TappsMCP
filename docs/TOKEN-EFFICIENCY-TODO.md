# Token Efficiency Backlog (tapps-mcp)

> **Status (2026-08-21).** Two audits feed this file. The original **context
> audit** (T1–T10 below) covers the *always-loaded local surface* — settings,
> rules, memory, subagents — and is still almost entirely open. A later
> **fleet usage audit** covered the *MCP response surface* and is tracked in
> Linear, not here: epic **TAP-6433** plus **TAP-6438**–**TAP-6444**. Keep the
> split — this file is for work with no Linear home; anything filed gets a
> pointer, never a second copy.
>
> Shipped since: the `orchestration-prompt` skill cut (v3.12.73) and the doctor
> exemption fix — see *Shipped* at the bottom.

Derived from the 2026-08-21 context audit of this repo plus the Anthropic
prompt-caching contract ([Claude Code](https://code.claude.com/docs/en/prompt-caching),
[API](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)).

Every item below cites a measured number or a file path. Ordered by cost impact.
Ship top-down; items 1–3 are the ones that actually move the bill.

Cost model used for ranking (Opus 5, per MTok): input $5 · output $25 ·
1h cache write $10 (2x) · cache read $0.50 (0.1x). On a Max subscription these
are not billed per-token but consume the usage allowance proportionally.

---

## P0 — Cap the growth mechanism

### T1. Revert `BASH_MAX_OUTPUT_LENGTH` to the default

- **Where:** `.claude/settings.json` → `env.BASH_MAX_OUTPUT_LENGTH: "150000"`
- **Measured:** 150,000 characters ~= 37,500 tokens admitted per Bash call.
  A bare `pytest --collect-only -q` on `packages/tapps-core/tests/` alone emits
  **98,985 characters (~24,700 tokens)** and fits under the raised ceiling, so it
  lands in context whole and is re-read on every subsequent turn.
- **Do:** delete the override, or lower it to a deliberate value and record why.
- **Acceptance:** a full `pytest --collect-only` on tapps-core is truncated, not
  admitted whole.

### T2. Add a PreToolUse hook that rewrites noisy commands

- **Where:** `.claude/hooks/tapps-pre-bash.sh` (44 lines) is a destructive-command
  blocklist only — it has zero `updatedInput` / `hookSpecificOutput` emissions.
  No output filter exists in any settings file.
- **Do:** extend it (or add a sibling hook) that returns `updatedInput` to rewrite
  known-noisy invocations before they run:
  - `pytest ...` → append `-q --no-header -p no:cacheprovider --tb=line`
  - `pytest` without `-x` on a full package → append `--maxfail=5`
  - `uv sync ...` → append `-q`
  - `ruff check` → append `--output-format=concise`
  - `mypy --strict ...` → append `--no-error-summary --no-pretty`
  - any command → append `2>&1 | tail -n 200` only where the tail is sufficient
- **Constraint:** rewrite, never silence. Per `CLAUDE.md`, do not suppress a
  failure signal — the goal is fewer bytes per failure, not fewer failures shown.
- **Acceptance:** `scripts/run-regression.sh` output entering context drops below
  10,000 characters on a green run; a red run still shows every failing test id.

### T3. Trim the always-loaded memory surface

- **Measured:** 53,095 bytes combined and re-sent every turn —
  `CLAUDE.md` 15,615 B · `.claude/rules/*.md` 29,041 B (10 files) ·
  `~/.claude/CLAUDE.md` 1,421 B · `MEMORY.md` 7,018 B.
  Largest offenders: `.claude/rules/repo-workflow.md` 7,963 B,
  `.claude/rules/integration-hygiene.md` 6,136 B.
  This session's **first-turn context was 63,544 tokens** before any work began.
- **Do:**
  - Add `paths:` frontmatter to the rules that are not universally relevant, so
    they load on first matching file read instead of at session start.
    `linear-standards.md` (1,780 B) and `test-quality.md` (2,334 B) are the
    clearest candidates.
  - Move the `repo-workflow.md` CI/version-bump narrative into
    `.claude/references/` and leave a pointer, mirroring how
    `linear-standards.md` already defers to `LINEAR_TECHNICAL_DETAILS.md`.
  - Prune `MEMORY.md` (39 memory files indexed; several are resolved, e.g.
    `tap5671_fixed.md`, `project_tapps_mcp_scripts_lint_debt.md` "instance is fixed").
- **Edit the templates, not the deployed copies** — `pipeline/platform_rules.py`
  and friends regenerate `.claude/rules/`; direct edits are reverted by
  `tapps_upgrade` and never reach consumers. Bump the version in the same commit.
- **Acceptance:** combined always-loaded surface under 30,000 bytes; `/context`
  shows a first-turn floor under 45,000 tokens.

---

## P1 — Stop paying for cold caches

### T4. Stop spawning review agents into worktrees

- **Where:** `.claude/skills/tapps-review-pipeline/SKILL.md:19-20` —
  `subagent_type: "general-purpose"`, `isolation: "worktree"`.
- **Why:** the Claude Code cache is scoped to a working directory. The system
  prompt embeds cwd, so **every worktree builds a different prefix and shares no
  cache with the parent or with its siblings.** N parallel fixers in N worktrees
  is N cold caches, each paying full cache-write rate.
- **Do:** drop `isolation: "worktree"` unless the agents genuinely write the same
  files concurrently. For read-then-report review, run them in the repo directory
  so they share a prefix. Keep worktrees only for the concurrent-write case the
  isolation flag exists for.
- **Acceptance:** `tapps-review-pipeline` runs without worktrees for the
  review-only path; worktree use is documented as write-conflict-only.

### T5. Audit the two `continuous-learning-v2` observer loops

- **Measured:** PIDs 442466 (started 09:37:27) and 2097589 (started 12:30:46),
  both `~/.claude/skills/continuous-learning-v2/agents/observer-loop.sh`.
  Interval default **300s** (`session-guardian.sh:20`). Each fire runs
  `claude --model haiku --print` (`observer-loop.sh:231`).
- **Why:** every `--print` fire is a fresh session — 100% cache creation, 0% cache
  read, by construction. Two concurrent loops double it.
- **Do:** confirm one loop is a leftover and kill it; raise the interval; or scope
  the loop to projects where the instincts are actually consumed.
- **Note:** this is a user-level skill, not a tapps-mcp artifact. Out of repo
  scope — track it, fix it outside this repo.
- **Acceptance:** exactly one observer loop running, with a recorded interval.

### T6. Pin subagent effort as well as model

- **Measured:** all 7 project agents pin a model
  (`tapps-docs-validator`, `tapps-validator` → `claude-haiku-4-5-20251001`;
  the other 5 → `claude-sonnet-4-6`). None pin effort.
- **Why:** the cache key includes **both** model and effort. Subagents also use
  the 5-minute TTL even on a subscription, so they are already cache-cold.
- **Do:** add explicit `effort:` frontmatter to each agent so a session-level
  `/effort` change does not silently reshape subagent requests. Low effort on the
  two validators is likely correct.
- **Acceptance:** every file in `.claude/agents/` declares both `model` and `effort`.

---

## P2 — Hygiene and instrumentation

### T7. Remove `ANTHROPIC_API_KEY` from the environment

- **Measured:** set in env; direct probe returns
  `"Your credit balance is too low to access the Anthropic API"`
  (request id `req_011CeGT4gNgPJFC1WgY94Xhf`).
- **Why:** an inherited API key takes precedence over the CLI login in
  subprocesses. `observer-loop.sh:227` already carries an
  `env -u ANTHROPIC_API_KEY` workaround with a comment explaining exactly this.
  Separately, API-key auth defaults to the **5-minute** cache TTL where a
  subscription gets **1 hour**.
- **Do:** unset it in the shell profile, or scope it to the one tool that needs it.
- **Acceptance:** `env | grep ANTHROPIC_API_KEY` is empty; no script needs
  `env -u ANTHROPIC_API_KEY`.

### T8. Build a cache-hit statusline from the OTEL data already being collected

- **Measured:** `~/.claude/settings.json` already exports
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8766` with
  `OTEL_METRICS_EXPORTER=otlp` and `OTEL_LOG_TOOL_DETAILS=1`. The endpoint
  answered **HTTP 404** on `/v1/metrics` at audit time — verify the collector is
  actually ingesting.
- **Why:** the exporter reports cache read and creation tokens per session. You
  are paying to collect the exact signal this backlog needs and not reading it.
- **Do:** confirm ingestion, then add a statusline script reading `current_usage`
  so the read:creation ratio is visible live. Wire a regression check into
  `scripts/` that fails if creation share exceeds a threshold across a session.
- **Acceptance:** cache read/creation ratio visible in the statusline; a script
  under `scripts/` can report it for any session log.

### T9. Ship a `tapps_context_audit` tool or `/tapps-context-audit` skill

- **Why:** the analysis in this backlog was ad hoc. `scripts/measure_context_floor.py`
  already exists and uses a fixed `round(bytes/4)` estimator
  (`scripts/context_floor_core.py:36-38`), but nothing parses session logs for
  actual `cache_read_input_tokens` / `cache_creation_input_tokens`.
- **Do:** add a deterministic tool that reports, for a given session log:
  per-category token shares, first/last turn context size, cache hit ratio, and
  the always-loaded memory surface in bytes. Deterministic, no LLM calls
  (ADR-0004). Consuming projects get the same audit for free.
- **Acceptance:** `uv run tapps-mcp context-audit` emits the table this backlog
  was built from; registered in the checklist task map and AGENTS.md.

### T10. Document the caching contract in the platform rules

- **Do:** add a short `.claude/rules/context-hygiene.md` (via
  `pipeline/platform_rules.py`) stating the rules that actually matter here:
  do not switch model or effort mid-task; prefer `/rewind` over `/compact` when
  abandoning a path (rewind truncates to an already-cached prefix, compact builds
  a new one); run `/compact` at task boundaries, not mid-task; skills and plan
  mode are cache-safe because they append.
- **Keep it under 2,000 bytes** — this rule is itself always-loaded surface, and
  T3 is about shrinking that. Net budget must stay negative.
- **Acceptance:** rule ships, and the T3 reduction still nets out below 30,000 B.

---

## Explicitly NOT problems (verified, do not "fix")

| Checked | Verdict |
|---|---|
| Tool deferral | **ACTIVE.** 194 tools deferred (173 MCP + 21 built-in). Schemas withheld from the prefix. |
| Proxy / gateway | **None.** No `ANTHROPIC_BASE_URL`, no `ANTHROPIC_AUTH_TOKEN`, no gateway var. Deferral is not being silently disabled. |
| MCP server churn | **Harmless.** 6 HTTP servers; `tapps-mcp-fleet-watch.timer` restarts them every 60s, but with deferral active a connect/disconnect only appends and leaves the cached prefix intact. |
| Model / effort switching | **None mid-session.** `~/.claude/settings.json:55` pins `opus[1m]`; `CLAUDE_EFFORT=high`. Session logs show a single main-loop model. |
| Claude Code scheduled jobs | **None.** `CronList` → no scheduled jobs. All 8 systemd timers and the 1 crontab entry are shell/python; none invoke `claude`. |
| Cache TTL | **1 hour**, subscription default. No `FORCE_PROMPT_CACHING_5M` set. |

---

## P1b — orchestration-prompt residuals (after v3.12.73)

The skill went 21,341 B / 365 lines → 16,241 B / 287 lines and its frontmatter
description 849 → 555 B. Three things were deliberately **not** done.

### T11. Structural rewrite to clear the 120-line ceiling

- **Where:** `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skill_orchestration.py`
- **Measured:** 287 lines against `skill_body_max_lines: 120`
  (`distribution/context_budget.py`). Every other registered skill is under it;
  the next largest is `tapps-wayfind` at 116.
- **Do:** reduce `SKILL.md` to purpose + the seven load-bearing parts + the fog
  gate + the output procedure + pointers. All method rationale moves to
  `references/`. This changes how the skill *reads*, not just its size — it is a
  content decision, which is why the byte-level pass stopped short of it.
- **Acceptance:** `SKILL.md` ≤ 120 lines with no rule lost; the doctor
  `Skill inventory budget` check returns to pass without a raised ceiling.

### T12. Fleet drift — 5 repos carry hand-edited copies

- **Measured (2026-08-21), against the 364-line managed baseline:**
  1. `ReportLab` — 531 lines / 30,083 B
  2. `HeyGen` — 438 lines / 24,723 B
  3. `nlt-orchestrator` — 401 lines / 24,258 B
  4. `WebStoreDNA` — 386 lines / 23,039 B
  5. `CuttingEdgeGraphix` and `HomeIQ` — 363 lines, **no version header at all**
- **Why it matters:** the skill is not in `upgrade_skip_files`, so the next
  `tapps_upgrade` in each repo overwrites the edits silently. The two with no
  header have had the managed block stripped, so upgrade can no longer identify
  or merge them. TAP-5759 warned about exactly this before it happened.
- **Do:** decide per repo — promote the edit upstream into the template, move it
  below the managed block where smart-merge preserves it, or accept the
  overwrite. Do not "fix" it by adding the skill to `upgrade_skip_files`; that
  freezes those repos off the fleet doctrine channel permanently.
- **Acceptance:** every deployed copy either matches the generated body or keeps
  its customization in a project region below `<!-- END: tapps-skill -->`.

### T13. Skills are invisible to telemetry

- **Measured:** `tool_calls_*.jsonl` records MCP tool calls only. Skill
  invocations are not recorded anywhere, so the per-invocation cost of a
  ~16 KB `SKILL.md` cannot be multiplied by anything real.
- **Why:** every size argument about skills is currently unfalsifiable. The
  frontmatter description is the only part with a known multiplier (every
  session, every repo).
- **Do:** record skill invocations alongside tool calls, or accept that skill
  sizing stays a judgement call and say so in `docs/SKILL_AUTHORING.md`.
- **Related:** TAP-6441 — `tapps_memory` has the same blind spot for a
  44-action surface.

---

## Shipped

| Date | Change | Effect |
|---|---|---|
| 2026-08-21 | `orchestration-prompt` slimmed (v3.12.73) | `SKILL.md` −24% (21,341 → 16,241 B); description −35% (849 → 555 B) |
| 2026-08-21 | Doctor companion exemption removed | `check_skill_inventory_budget` had skipped any skill in `SKILL_COMPANION_FILES`, so the worst offender was the only one never measured |
| 2026-08-21 | 8 canonical `loops.md` anti-patterns mirrored (TAP-5759) | 5 were missing; a capability-preflight rule was added from a live run where a granted-but-inert `WebFetch` produced a confident wrong answer |

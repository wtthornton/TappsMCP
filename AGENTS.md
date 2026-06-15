<!-- tapps-agents-version: 3.12.29 -->
# TappsMCP - instructions for AI assistants

When the **TappsMCP** MCP server is configured, you have access to tools for **code quality, doc lookup, and domain expert advice**. Use them to avoid hallucinated APIs, missed quality steps, and inconsistent output.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## Tapps Rules

Seven rules every agent in this project should follow.

1. **Fix root causes, not symptoms.** No workarounds, no `--no-verify`, no try/except-and-swallow. If you are tempted to bypass a failure, stop and diagnose it.
2. **When confidence drops below 100%, query tapps-mcp before writing code.** `tapps_lookup_docs` for library APIs, `tapps_memory(action="search")` for prior decisions and patterns. Guessing from memory is the most common source of hallucinated APIs.
3. **`tapps_lookup_docs` is a Context7-backed cache — use it freely.** Lookups are local-cache-first; repeat calls are near-zero cost. There is no budget to conserve.
4. **Be context-window aware — delegate noisy work to subagents.** If a task would dump more than three file reads or large tool output you won't reference again, spawn `Explore` or `general-purpose`. Subagents return summaries; the main thread stays clean.
5. **Write clean, efficient code.** Clear names, no dead branches, no speculative abstractions, no commented-out code. Every line should justify its presence.
6. **Don't over-engineer.** The simplest solution that satisfies the requirement is the correct one. No knobs nobody asked for. Three similar lines beat a premature abstraction.
7. **Route Linear through skills, not raw plugin calls.** Use the `linear-issue` skill for any write (epic, story, update) — it runs the docs-mcp template + validator before push. Use the `linear-read` skill for multi-issue reads (cache-first). Single-issue lookups: `get_issue(id=...)` directly. Release announcements go through the `linear-release-update` skill.

---

## Essential tools (always-on workflow)

| Tool | When to use |
|------|--------------|
| **tapps_session_start** | **FIRST call in every session** - server info only |
| **tapps_quick_check** | **After editing any Python file** - quick score + gate + security |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - score + gate on changed files. **Always pass explicit `file_paths`** (comma-separated). Default is quick mode; only use `quick=false` as a last resort. |
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |

**For full tool reference** (32 tools with per-tool guidance), invoke the **tapps-tool-reference** skill when the user asks "what tools does TappsMCP have?", "when do I use tapps_score_file?", etc.

---

## NLT MCP session modes (ADR-0016)

Enable **1–3** `nlt-*` servers per session — not all six at once. Default after `tapps_init` is **Build + Memory + Linear** (`developer` bundle, ~18 eager tools). Use `--bundle minimal` for build-only.

| Mode | Enable these MCP servers | When |
|------|--------------------------|------|
| **Developer (default)** | `nlt-build`, `nlt-memory`, `nlt-linear-issues` | Daily coding + recall + backlog |
| **Build only** | `nlt-build` | Token-tight sessions (`--bundle minimal`) |
| **Build + Memory** | `nlt-build`, `nlt-memory` | Need `tapps_memory` search/save or session handoff |
| **Build + Plan** | `nlt-build`, `nlt-linear-issues` | Linear backlog / issue workflow |
| **Build + Docs** | `nlt-build`, `nlt-project-docs` | Doc generation / drift audit |
| **Build + Release** | `nlt-build`, `nlt-release-ship` | Release notes / ship gate |
| **Setup** | `nlt-setup` (short session) | Bootstrap, upgrade, doctor only |

Legacy server IDs `nlt-code-quality` / `nlt-platform-admin` map to `nlt-build` / `nlt-setup` for one release.

---

## Graph tools: import impact vs call graph (ADR-0016, ADR-0017)

Four graph concepts — do not conflate them:

| Concept | Tool(s) | Granularity | When |
|---------|---------|-------------|------|
| **Import / file impact** | `tapps_impact_analysis`, `tapps_dependency_graph` | Module / file | Before changing a file's public API or deleting a module |
| **Call graph** (Epic 114) | `tapps_call_graph` (Tier B+), symbol mode on `tapps_impact_analysis` | Function / method | Before refactoring a specific function — callers, callees, bounded chains |
| **Package CVE** | `tapps_dependency_scan` | Installed packages | Before releases |
| **Brain KG** | `tapps_memory(action="related")` on `nlt-memory` | Cross-session entities | Architecture recall |

**Today:** use `tapps_impact_analysis` for module-level blast radius (Python import graph).
**After Epic 114 Tier B:** add `tapps_call_graph` for symbol-level who-calls-whom instead of grep.
See [ADR-0017](docs/adr/0017-function-level-call-graph-python-first.md).

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_score_file** | When editing/reviewing a code file. Use `quick=True` during edit loops. |
| **tapps_lookup_docs** | **Before writing code** that uses an external library - prevents hallucinated APIs |
| **tapps_security_scan** | Security-sensitive changes or before security review |
| **tapps_impact_analysis** | Before modifying a file's public API (module-level importers). Pass `project_root` for external projects. Symbol-level callers: `tapps_call_graph` when Epic 114 Tier B ships. |
| **tapps_validate_config** | When adding/changing Dockerfile, docker-compose, infra config |
| **tapps_memory** | Session start: search past decisions. Session end: save learnings. See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) |
| **tapps_session_notes** | Key decisions during session - promote to memory for persistence |
| **tapps_dead_code** | Find unused code during refactoring |
| **tapps_dependency_scan** | Check for CVEs before releases |
| **tapps_dependency_graph** | Understand module dependencies, circular imports |
| **tapps_audit_campaign** | Plan a code-review campaign: cluster files into session-sized chunks, render parent epic + per-session ticket bodies. Read-only. |
| **tapps_report** | Generate quality reports (JSON, Markdown, HTML) |
| **tapps_dashboard** | Metrics dashboard for TappsMCP performance trends |
| **tapps_stats** | Tool usage statistics and call counts |
| **tapps_feedback** | Report tool effectiveness for adaptive learning |
| **tapps_init** | Pipeline bootstrap (once per project) - creates AGENTS.md, rules, hooks |
| **tapps_upgrade** | After TappsMCP version update - refreshes tapps-managed files (custom agents/skills/hooks preserved); use `dry_run=True` for a per-file verdict |
| **tapps_doctor** | Diagnose configuration issues |
| **tapps_set_engagement_level** | Change enforcement intensity (high/medium/low) |
| **tapps_release_update** | Source release body from CHANGELOG/git, generate + validate via docs-mcp, return for Linear post via `linear-release-update` skill |
| **tapps_pipeline** | Show TAPPS pipeline stage progress and next-step hint for the current session |
| **tapps_decompose** | Decompose a high-level task into TappsMCP tool call steps for the current pipeline stage |
| **tapps_linear_snapshot_get / _put / _invalidate** | Cache-first Linear list reads (TAP-1224); orchestrated by the `linear-read` skill — never call directly without snapshot_get first |
| **tapps_linear_count** | Count Linear issues for a `(team, project, state, label)` slice; backs the cache gate violation telemetry |
| **tapps_server_info** | Lightweight server discovery (version, checkers, config) — prefer `tapps_session_start` which returns the same info plus session bootstrap |
## Supported languages

| Language | Extensions | Notes |
|----------|------------|-------|
| **Python** | `.py`, `.pyi` | Full: ruff, mypy, bandit, radon, vulture |
| **TypeScript** | `.ts`, `.tsx` | Tree-sitter AST (regex fallback) |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | Routes to TypeScript scorer |
| **Go** | `.go` | Tree-sitter AST (regex fallback) |
| **Rust** | `.rs` | Tree-sitter AST (regex fallback) |

## Recommended workflow

1. **Session start:** Call `tapps_session_start` (returns server info and project context).
2. **Check project memory:** Consider calling `tapps_memory(action="search", query="...")` to recall past decisions and project context.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `tapps_memory(action="save", ...)` to persist decisions across sessions.
3. **Before using a library:** Call `tapps_lookup_docs(library=...)` and use the returned content when implementing.
4. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` for module-level dependents. For a specific function refactor, use `tapps_call_graph` once Epic 114 ships (ADR-0017).
5. **During edits:** Call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each change.
6. **Before declaring work complete:**
   - Recommended: invoke the `/tapps-finish-task` skill — bundles `tapps_validate_changed` + `tapps_checklist` + an optional memory save and reports a one-line summary.
   - If you'd rather run the steps manually: `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to score + gate changed files (never call without `file_paths` in large repos; default is quick mode), then `tapps_checklist(task_type=...)` and, if `complete` is false, call the missing required tools (use `missing_required_hints` for reasons).
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.
7. **When in doubt:** Use `tapps_lookup_docs` for domain-specific questions and library guidance; use `tapps_validate_config` for Docker/infra files.

### Review Pipeline (multi-file)

For reviewing and fixing multiple files in parallel, use the `/tapps-review-pipeline` skill:

1. It detects changed Python files and spawns `tapps-review-fixer` agents (one per file or batch)
2. Each agent scores the file, fixes issues, and runs the quality gate
3. Results are merged and validated with `tapps_validate_changed`
4. A summary table shows before/after scores, gate status, and fixes applied

You can also invoke the `tapps-review-fixer` agent directly on individual files for combined review+fix in a single pass.

---

## Generating epic, story, or prompt artifacts (DocsMCP)

When creating or updating **epic**, **story**, or **prompt** planning artifacts (e.g. in `docs/archive/planning/epics/`), use a consistent structure and the right tools. All three artifact types share a **Common schema** (Identity, **Purpose & Intent** (required), Goal, Success, Context, Steps, Out of scope, Expert enrichment). See [LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md](docs/archive/planning/LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md) and [LLM-ARTIFACT-COMMON-SCHEMA.md](docs/archive/planning/LLM-ARTIFACT-COMMON-SCHEMA.md).

**Recommended TappsMCP/DocsMCP calls:**

- **tapps_session_start** — returns project root, installed checkers, docs provider, and pipeline stage info (use this for context/technical notes instead of the removed `tapps_project_profile`).
- **docs_generate_epic** — primary epic generator (EpicConfig); use for parent epics.
- **docs_generate_story** — primary story generator (StoryConfig); use for child stories.
- **docs_generate_prompt** — prompt artifact generator (PromptConfig); use for LLM-facing prompt docs.
- **docs_validate_linear_issue** — when the epic/story will become a Linear issue, run this before save so only agent-ready payloads go live.

Provide **purpose_and_intent** for epic and story when calling the generators so the required "Purpose & Intent" section is populated.

## Deprecated tools

The following tools were removed in EPIC-94 and now return structured `TOOL_DEPRECATED` errors:

- **tapps_consult_expert** — The RAG-based expert system has been removed. Use `tapps_lookup_docs` for library documentation.
- **tapps_research** — Combined expert + docs lookup has been removed. Use `tapps_lookup_docs` for library documentation.

Both stubs return `alternatives` metadata pointing to `tapps_lookup_docs` and AgentForge.

---

## Checklist task types

Use the `task_type` that best matches the current work:

- **feature** - New code
- **bugfix** - Fixing a bug
- **refactor** - Refactoring
- **security** - Security-focused change
- **review** - General code review (default)

The checklist uses this to decide which tools are required vs recommended vs optional for that task.

---

## Platform automation

`tapps_init` generates hooks, agents, skills, and rules for Claude Code and Cursor. See the generated files in `.claude/` and `.cursor/` directories.

**Subagents:** tapps-reviewer (sonnet), tapps-researcher (haiku), tapps-validator (sonnet), tapps-review-fixer (sonnet + worktree).

**Skills:** tapps-finish-task, tapps-handoff-session, tapps-continue-session, tapps-review-pipeline, tapps-research, tapps-security, tapps-memory, tapps-tool-reference, tapps-init, tapps-engagement, tapps-upgrade, tapps-apply-files.

## Agent ecosystem (using TappsMCP with other agent libraries)

TappsMCP creates **4 quality-focused subagents** (tapps-reviewer, tapps-researcher, tapps-validator, tapps-review-fixer) and platform rules + skills. You can **optionally** add [agency-agents](https://github.com/msitarzewski/agency-agents) for 120+ domain personas (e.g. Frontend Developer, Reality Checker) — the two systems coexist with **no path conflict**.

- **Recommended install order:** (1) Configure MCP (tapps-mcp). (2) Run `tapps_init` to get TappsMCP rules, agents, and skills. (3) Optionally run agency-agents `./scripts/install.sh --tool claude-code` or `--tool cursor`.
- **Paths:** **Cursor** — agency-agents writes to `.cursor/rules/`; TappsMCP writes to `.cursor/agents/` and `.cursor/rules/` (no conflict). **Claude** — both can use the agents dir (project `.claude/agents/` or user `~/.claude/agents/`).

For details, see [2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md](docs/archive/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md). Optional: for more specialized agents (e.g. Frontend Developer, Reality Checker), see [agency-agents](https://github.com/msitarzewski/agency-agents) and run their install script for your platform.

## Memory systems

Your project may have two complementary memory systems:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Build commands, IDE preferences, personal workflow notes. Auto-managed.
- **TappsMCP shared memory** (`tapps_memory` tool): Architecture decisions, quality patterns, expert findings, cross-agent knowledge. Structured with tiers, confidence decay, contradiction detection, consolidation, and federation.

RECOMMENDED: Use `tapps_memory` for architecture decisions and quality patterns.

### Memory actions (42 total)

**Core:** `save`, `save_bulk`, `get`, `list`, `delete` — CRUD with tier/scope/tag classification (`save` + architectural tier may **supersede** prior versions when `memory.auto_supersede_architectural` is true). In HTTP-bridge mode `save_bulk` now batches every entry into a single `memory_save_many` round trip (TAP-1631).

**Search:** `search` — ranked BM25 retrieval with composite scoring (relevance + confidence + recency + frequency). Auto-emits `feedback_gap` on empty / low-similarity results to feed the brain's flywheel (toggle via `memory.feedback_auto_emit`; threshold via `memory.feedback_min_similarity`).

**Intelligence:** `reinforce`, `gc`, `contradictions`, `reseed`

**Knowledge graph (TAP-1630):** `related` (find entries connected to a key), `relations` (relations attached to a key OR matching an SPO triple via `subject` / `predicate` / `object_entity`), `neighbors` (k-hop neighborhood of one or more entity ids passed via `entry_ids`), `explain_connection` (path between `subject` and `object_entity`)

**Batch ops (TAP-1631):** `recall_many` (queries via `entries` JSON array of strings), `reinforce_many` (entries via `entries` JSON array of `{key, confidence_boost?}` objects). Single round-trip wrappers around the brain's `memory_*_many` tools.

**Feedback flywheel (TAP-1632):** `rate` — score an entry via `feedback_rate` (`key` + `rating` + optional `session_id` / `details_json`). The auto-emitted `feedback_gap` on `search` empties is governed here.

**Native session memory (TAP-1633):** `index_session` (store session chunks via `memory_index_session`), `search_sessions` (search indexed sessions via `memory_search_sessions`), `session_end` (record a session-end summary via `tapps_brain_session_end`; summary in `value`, tags in `tags`, daily-note flag in `dry_run`). Replaces the legacy local session-index merge.

**Consolidation:** `consolidate`, `unconsolidate`

**Import/export:** `import`, `export`

**Federation:** `federate_register`, `federate_publish`, `federate_subscribe`, `federate_sync`, `federate_search`, `federate_status`

**Maintenance:** `validate`, `maintain`

**Security:** `safety_check`, `verify_integrity`

**Profiles:** `profile_info`, `profile_list`, `profile_switch`

**Diagnostics:** `health` — surfaces a `brain_profile` block with the negotiated capability profile + gated bridge tools (TAP-1629).

**Hive / Agent Teams:** `hive_status`, `hive_search`, `hive_propagate`, `agent_register` (opt-in; see `hive_status` when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is set)

**Default pipeline behavior (POC-oriented):** Shipped config turns on auto-save quality signals, recurring quick_check memory, architectural supersede, impact enrichment, and `memory_hooks` auto-recall/capture — set `false` in `.tapps-mcp.yaml` if you want a quieter setup. See `docs/MEMORY_REFERENCE.md`.

### Brain health diagnostics (`brain_bridge_health`)

Every `tapps_session_start` response includes a `data.brain_bridge_health` block describing the live state of the tapps-brain connection:

| Field | Meaning |
|-------|---------|
| **enabled** | True when the bridge is configured (memory pipeline turned on). |
| **ok** | Roll-up: True only when the bridge can both reach the brain and pass its native self-check. |
| **dsn_reachable** | HTTP-bridge mode: brain endpoint responded to a probe. In-process mode: pool was constructible. |
| **pool_config_valid** | Connection pool sizing / DSN parsed cleanly. |
| **native_health_ok** | Result of the brain's own `health` tool — covers schema, embeddings, and indexes. |
| **errors / warnings** | Non-empty when one of the checks above failed; agents should surface these instead of swallowing them. |
| **details** | Mode (`http` / `in_process`), `http_url`, negotiated `brain_version`, and the brain's own `brain_status`. |

`tapps doctor` runs the same probe in CLI form and adds a brain-health row to its summary, so agents and humans see the same signal. When `errors` mentions `brain_auth_failed`, set `TAPPS_BRAIN_AUTH_TOKEN` (or set `memory.tolerate_brain_auth_failure: true` for offline workflows) — see [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md#brain-health-diagnostics) for the full troubleshooting matrix.

### Memory tiers and scopes

**Tiers:** `architectural` (180-day half-life, stable decisions), `pattern` (60-day, conventions), `procedural` (30-day, workflows), `context` (14-day, short-lived)

**Scopes:** `project` (default, all sessions), `branch` (git branch), `session` (current session only). Cross-project handoff goes through federation actions (`federate_publish` / `federate_subscribe`), not a `scope=` value.

**Memory profiles:** Built-in profiles from tapps-brain (e.g. `repo-brain` default). Use `profile_info`, `profile_list`, `profile_switch` actions.

**Configuration:** Override `memory.profile`, `memory.capture_prompt`, `memory.write_rules`, and `memory_hooks` in `.tapps-mcp.yaml`. Max 1500 entries per project. Auto-GC at 80% capacity.

**Cross-session handoff:** prefer `/tapps-handoff-session` at chat end and `/tapps-continue-session` at chat start — they read/write `.tapps-mcp/session-handoff.md` (canonical) with an optional brain mirror (`tapps-mcp memory save --key session-handoff`). For ad-hoc key/value payloads, use `tapps-mcp memory save/get` or brain recall. Cross-agent: `hive_propagate`; cross-project: federation actions above.

---

## Troubleshooting

**Server not available:** Run `/mcp` (Claude Code) or check Settings > MCP (Cursor). If not listed, run `tapps-mcp upgrade --force --host auto` then restart your IDE.

**Permissions rejected:** Ensure `.claude/settings.json` has `"mcp__tapps-mcp__*"` in `permissions.allow`.

**Doctor timeout:** Use `tapps-mcp doctor --quick` or `tapps_doctor(quick=True)`.

**Cursor hooks on Windows:** If hook scripts (e.g. `tapps-before-mcp.sh`) open in the editor instead of running, run `tapps-mcp upgrade --host cursor` from Windows so hooks are regenerated as PowerShell (`.ps1`). See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#cursor-hooks-on-windows).

### MCP Server Not Discoverable

If tapps-mcp tools don't appear in your IDE's tool list:

1. Check that your MCP client config includes tapps-mcp:
   - Cursor: `.cursor/mcp.json`
   - VS Code: `.vscode/mcp.json`
   - Claude Code: `.mcp.json` (project) or `~/.claude.json` (user)

2. Run `tapps-mcp doctor` to diagnose configuration issues

3. Example `.cursor/mcp.json`:
   ```json
   {
     "mcpServers": {
       "tapps-mcp": {
         "command": "uv",
         "args": ["run", "tapps-mcp", "serve"]
       }
     }
   }
   ```

4. After updating config, restart your IDE or reload MCP servers

### Reducing tool count (direct stdio)

For direct stdio connections you can expose only a subset of tools to keep the active tool count in an optimal range (Epic 79.1). Configure in `.tapps-mcp.yaml` or via env:

- **enabled_tools** (allow list): when non-empty, only these tools are exposed. Comma-separated in env: `TAPPS_MCP_ENABLED_TOOLS=tapps_session_start,tapps_quick_check,tapps_checklist`.
- **disabled_tools** (deny list): tools to exclude from the full set. Applied when `enabled_tools` is not set. Env: `TAPPS_MCP_DISABLED_TOOLS`.
- **tool_preset**: `full` (all tools), `core` (7 Tier-1 tools), `pipeline` (Tier 1 + Tier 2), or role presets: `reviewer`, `planner`, `frontend`, `developer` (Epic 79.5). NLT profiles: `nlt-build`, `nlt-memory`, `nlt-setup` (legacy: `nlt-code-quality`, `nlt-platform-admin`). Env: `TAPPS_MCP_TOOL_PRESET=nlt-build`.

Empty or missing = all 32 tools (default, backward compatible). Invalid tool names in `enabled_tools` are ignored and logged. Recommended subsets by task/role and Docker tool filtering: see `docs/archive/planning/TOOL-SUBSETS-AND-DOCKER-FILTERING.md`.

---
## tapps_session_start vs tapps_init

| Aspect | tapps_session_start | tapps_init |
|--------|---------------------|------------|
| **When** | **First call in every session** | **Pipeline bootstrap** (once per project, or when upgrading) |
| **Duration** | Fast (~1s, server info only) | Full run: 10-35+ seconds |
| **Purpose** | Load server info (version, checkers, config) into context | Create files (AGENTS.md, TECH_STACK.md, platform rules), optionally warm cache/RAG |
| **Side effects** | None (read-only) | Writes files, warms caches |
| **Typical flow** | Call at session start, then work | Call once to bootstrap, or `dry_run: true` to preview |

**Session start** -> `tapps_session_start`. Use this as the first call in every session. Returns server info and project context.

**Pipeline/bootstrap** -> `tapps_init`. Use when you need to set up TappsMCP in a project (AGENTS.md, TECH_STACK.md, platform rules) or upgrade existing files.

**Both in one session?** Yes. If the project is not yet bootstrapped: call `tapps_session_start` first (fast), then `tapps_init` (creates files). If the project is already bootstrapped: call only `tapps_session_start` at session start.

**Lighter tapps_init options** (for timeout-prone MCP clients): Use `dry_run: true` to preview (~2-5s); use `verify_only: true` for a quick server/checker check (~1-3s); or set `warm_cache_from_tech_stack: false` and `warm_expert_rag_from_tech_stack: false` for a faster init without cache warming.

**MCP config (default on):** `tapps_init` writes project-scoped `.mcp.json` / `.cursor/mcp.json` after bootstrap (`mcp_config=true`). Generation strips direct `tapps-brain` MCP entries (bridge-only) and includes docs-mcp when detected. Pass `mcp_config=false` to scaffold pipeline files only. Brain wiring: [docs/operations/CONSUMER-REPO-BRAIN-WIRING.md](docs/operations/CONSUMER-REPO-BRAIN-WIRING.md).

**Tool contract:** Session start returns server info and project context. tapps_validate_changed default = score + gate only; use `security_depth='full'` or `quick=false` for security. tapps_quick_check has no `quick` parameter (use tapps_score_file(quick=True) for that).

---

## Platform hooks and automation

When `tapps_init` generates platform-specific files, it also creates **hooks**, **subagents**, and **skills** that automate parts of the workflow:

### Hooks (auto-generated)

**Claude Code** (`.claude/hooks/`): advisory hook scripts that fire on lifecycle events. Which scripts are wired depends on engagement level (`low` = SessionStart only; `medium` = 8 events; `high` = 10 events). Common entries:
- **SessionStart** - Injects TappsMCP awareness on session start and after compaction
- **PostToolUse (Edit/Write)** - Reminds you to run `tapps_quick_check` after Python edits
- **Stop** - Reminds you to run `tapps_validate_changed` before session end (non-blocking)
- **TaskCompleted** - Reminds you to validate before marking task complete (non-blocking)
- **PreCompact** - Backs up scoring context before context window compaction
- **SubagentStart / SubagentStop** - Injects TappsMCP awareness into spawned subagents
- **SessionEnd / PostToolUseFailure / UserPromptSubmit** (high only) - End-of-session capture, tool-failure logging, and per-prompt pipeline reminders

Opt-in `PreToolUse` gates are independent flags in `.tapps-mcp.yaml` — enable each based on what you want blocked:
- `destructive_guard: true` — blocks destructive Bash commands (`rm -rf`, `format c:`, etc.).
- `linear_enforce_gate: true` — blocks `mcp__plugin_linear_linear__save_issue` unless the `linear-issue` skill flow (with `docs_validate_linear_issue`) was used recently. Bypass: `TAPPS_LINEAR_SKIP_VALIDATE=1`. Bash + PowerShell. Default: on at medium/high engagement, off at low.
- `linear_enforce_cache_gate: "off" | "warn" | "block"` (TAP-1224) — gates `mcp__plugin_linear_linear__list_issues` behind a recent `tapps_linear_snapshot_get` for the same `(team, project, state, label, limit)` slice. **Warn mode** (default at medium/high engagement) logs violations to `.tapps-mcp/.cache-gate-violations.jsonl` and allows the call. **Block mode** rejects with exit 2 unless a matching sentinel < 300s old exists. Single-issue lookups must use `mcp__plugin_linear_linear__get_issue` instead. Pairs with the `linear-read` skill which routes the cache-first dance. Bypass: `TAPPS_LINEAR_SKIP_CACHE_GATE=1`. `tapps doctor` reports current mode + 24h violation count.
- `install_git_hooks: true` (TAP-979) — writes `.githooks/pre-commit` and sets `core.hooksPath = .githooks`. Runs `tapps-mcp validate-changed --quick` on staged Python files and fails the commit on gate failure. Bypass: `TAPPS_SKIP_GATE=1`. Default: off.

Run `tapps-mcp doctor` to list wired matchers.

**Cursor** (`.cursor/hooks/`): 3 hook scripts:
- **beforeMCPExecution** - Logs MCP tool invocations for observability
- **afterFileEdit** - Fire-and-forget reminder to run quality checks
- **stop** - Prompts validation via followup_message before session ends

### Subagents (auto-generated)

Four agent definitions per platform in `.claude/agents/` or `.cursor/agents/`:
- **tapps-reviewer** (sonnet) - Reviews code quality and runs security scans after edits
- **tapps-researcher** (sonnet) - Looks up documentation and researches best practices
- **tapps-validator** (haiku) - Runs pre-completion validation on all changed files
- **tapps-review-fixer** (sonnet, isolated worktree) - Combined score-fix-validate pass; designed for parallel multi-file pipelines

### Skills (auto-generated)

Sixteen core tapps-* SKILL.md files per platform in `.claude/skills/` or `.cursor/skills/` (plus linear-* and optional continuous-learning-v2):
- **tapps-finish-task** - End-of-task pipeline: validate_changed + checklist + optional memory save
- **tapps-handoff-session** - Write `.tapps-mcp/session-handoff.md` and call `tapps_session_end` before ending a chat
- **tapps-continue-session** - Bootstrap a fresh chat from the last handoff + optional Linear issue
- **tapps-review-pipeline** - Orchestrate a parallel review-fix-validate pipeline
- **tapps-research** - Look up library documentation and research best practices
- **tapps-security** - Run a comprehensive security audit with vulnerability scanning
- **tapps-memory** - Manage shared project memory (42 actions, cross-session)
- **tapps-tool-reference** - Full per-tool reference and when-to-use guidance
- **tapps-init** - Bootstrap TappsMCP scaffolding in a project
- **tapps-upgrade** - Upgrade tapps-mcp / docs-mcp in a consuming project
- **tapps-engagement** - Switch enforcement intensity (high/medium/low)
- **tapps-apply-files** - Apply content-return file operations (Docker fallback)

> **Removed in v3.12.0:** `tapps-score`, `tapps-gate`, `tapps-validate`, and `tapps-report` wrapper skills were deleted. Prefer direct MCP tool calls or `/tapps-finish-task`.

### Agent Teams (opt-in, Claude Code only)

When `tapps_init` is called with `agent_teams=True`, additional hooks enable a quality watchdog teammate pattern:
- **TeammateIdle** - Keeps the quality watchdog active while issues remain
- **TaskCompleted** - Reminds about quality gate validation on task completion

Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` to enable Agent Teams.

### VS Code / Copilot Instructions (auto-generated)

`.github/copilot-instructions.md` - Provides GitHub Copilot in VS Code with
TappsMCP tool guidance, recommended workflow, and scoring category reference.

### Cursor BugBot Rules (auto-generated, Cursor only)

`.cursor/BUGBOT.md` - Quality standards for Cursor BugBot automated PR review:
security requirements, style rules, testing requirements, and scoring thresholds.

### CI Integration (auto-generated)

`.github/workflows/tapps-quality.yml` - GitHub Actions workflow that validates
changed Python files on every pull request using TappsMCP quality gates.

### MCP Elicitation

When the MCP client supports elicitation (e.g. Cursor), TappsMCP can prompt
the user interactively:
- `tapps_quality_gate` prompts for preset selection when none is provided
- `tapps_init` asks for confirmation before writing configuration files

On unsupported clients, tools fall back to default behavior silently.

---

## Troubleshooting: MCP tool permissions

If TappsMCP tools are being rejected or prompting for approval on every call:

**Claude Code:** Ensure `.claude/settings.json` contains **both** permission entries:
```json
{
  "permissions": {
    "allow": [
      "mcp__tapps-mcp",
      "mcp__tapps-mcp__*"
    ]
  }
}
```
The bare `mcp__tapps-mcp` entry is needed as a reliable fallback - the wildcard `mcp__tapps-mcp__*` syntax has known issues in some Claude Code versions (see issues #3107, #13077, #27139). Run `tapps-mcp upgrade --host claude-code` to fix automatically.

**Cursor / VS Code:** These hosts manage MCP tool permissions differently. No `.claude/settings.json` needed.

**If tools are still rejected after fixing permissions:**
1. Restart your MCP host (Claude Code / Cursor / VS Code)
2. Verify the TappsMCP server is running: `tapps-mcp doctor`
3. Check that your permission mode is not `dontAsk` (which auto-denies unlisted tools)
4. As a last resort, use `tapps_quick_check` on individual files instead of `tapps_validate_changed`

---

## Using tapps_lookup_docs for domain guidance

`tapps_lookup_docs` is the primary tool for both library documentation and domain-specific guidance. Pass a `library` name for API docs, or use `topic` to query for patterns and best practices.

| Context | Example call |
|---------|--------------|
| Using an external library | `tapps_lookup_docs(library="fastapi", topic="dependency injection")` |
| Testing patterns | `tapps_lookup_docs(library="pytest", topic="fixtures and parametrize")` |
| Security patterns | `tapps_lookup_docs(library="python-security", topic="input validation")` |
| API design | `tapps_lookup_docs(library="fastapi", topic="routing best practices")` |
| Database patterns | `tapps_lookup_docs(library="sqlalchemy", topic="session management")` |

---

<!-- BEGIN: karpathy-guidelines c9a44ae (MIT, forrestchang/andrej-karpathy-skills) -->
<!--
  Vendored from https://github.com/forrestchang/andrej-karpathy-skills
  Pinned commit: c9a44ae835fa2f5765a697216692705761a53f40 (2026-04-15)
  License: MIT (c) forrestchang
  Do not edit by hand — update KARPATHY_GUIDELINES_SOURCE_SHA in prompt_loader.py
  and re-run the vendor script, then bump tapps-mcp version.
-->
## Karpathy Behavioral Guidelines

> Source: https://github.com/forrestchang/andrej-karpathy-skills @ c9a44ae835fa2f5765a697216692705761a53f40 (MIT)
> Derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
<!-- END: karpathy-guidelines -->

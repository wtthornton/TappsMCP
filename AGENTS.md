<!-- tapps-agents-version: 3.12.55 -->
# TappsMCP - instructions for AI assistants

When the **TappsMCP** MCP server is configured, you have access to tools for **code quality, doc lookup, and domain expert advice**. Use them to avoid hallucinated APIs, missed quality steps, and inconsistent output.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## Tapps Rules

Seven rules every agent in this project should follow.

1. **Fix root causes, not symptoms.** No workarounds, no `--no-verify`, no try/except-and-swallow. If you are tempted to bypass a failure, stop and diagnose it.
2. **When confidence drops below 100%, query tapps-mcp before writing code.** `tapps_lookup_docs` for library APIs; `uv run tapps-mcp memory search --query "..."` for prior decisions. Guessing from memory is the most common source of hallucinated APIs.
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
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps. Response includes an inline `usage_gaps` payload (same data as `tapps_usage`) - read it before declaring done. |
| **tapps_usage** | When you want to see what you missed this session - per-session `gaps` + concrete `recommendations`. Inlined as `usage_gaps` on every `tapps_checklist` response. |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |

**For full tool reference** (43 tools with per-tool guidance), invoke the **tapps-tool-reference** skill when the user asks "what tools does TappsMCP have?", "when do I use tapps_score_file?", etc.

---

## NLT MCP session modes (ADR-0016, ADR-0018)

Default after `tapps_init` is the **`full`** bundle — all six `nlt-*` servers ([ADR-0018](docs/adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)). Opt **down** for token-tight sessions with `tapps-mcp mcp-bundle set developer` (Build + Memory + Linear, ~39 listed / ~18 eager) or `tapps-mcp mcp-bundle set minimal` (build-only), then reload MCP. Init/upgrade also accept `--bundle`.

| Mode | Enable these MCP servers | When |
|------|--------------------------|------|
| **Full (default)** | all six `nlt-*` servers | Full tool surface; no mid-task "enable the other server" gaps |
| **Developer** | `nlt-build`, `nlt-memory`, `nlt-linear-issues` | Daily coding + recall + backlog (`mcp-bundle set developer`) |
| **Build only** | `nlt-build` | Token-tight sessions (`mcp-bundle set minimal`) |
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
| **Call graph** (Epic 114) | `tapps_call_graph`, symbol mode on `tapps_impact_analysis`, `tapps_diff_impact` | Function / method | Before refactoring a function — callers, callees, bounded chains, affected tests |
| **Package CVE** | `tapps_dependency_scan` | Installed packages | Before releases |
| **Brain KG** | `tapps_memory(action="related")` on `nlt-memory` | Cross-session entities | Architecture recall |

**Call graph (Epic 114):** use `tapps_call_graph` for symbol-level who-calls-whom; `tapps_impact_analysis(symbol=..., granularity="symbol"|"both")` for blast radius; `tapps_diff_impact` for git-changed → affected tests. Module-level import graph remains `tapps_impact_analysis` without `symbol`.
See [ADR-0017](docs/adr/0017-function-level-call-graph-python-first.md).

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_score_file** | When editing/reviewing a code file. Use `quick=True` during edit loops. |
| **tapps_lookup_docs** | **Before writing code** that uses an external library - prevents hallucinated APIs |
| **tapps_security_scan** | Security-sensitive changes or before security review |
| **tapps_impact_analysis** | Before modifying a file's public API (module-level importers). Pass `symbol` + `granularity="symbol"` or `"both"` for function-level blast radius; `tapps_call_graph` for caller/callee chains. |
| **tapps_call_graph** | Before refactoring a function — deterministic callers, callees, token-budgeted chains (Epic 114 / ADR-0017). |
| **tapps_diff_impact** | After editing Python files — ranked affected tests via TESTS edges + call graph (Epic 114). |
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
| **tapps_domain_playbook** | Load a bundled domain checklist (testing, security, UX, etc.) and suggested TAPPS tool order — deterministic, not RAG |
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
2. **Check project memory:** Consider `uv run tapps-mcp memory search --query "..."` or read `.tapps-mcp/session-handoff.md`.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `uv run tapps-mcp memory save --key ... --tier ... --value "..."` to persist decisions across sessions.
3. **Before using a library:** Call `tapps_lookup_docs(library=...)` and use the returned content when implementing.
4. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` to see what depends on it.
5. **During edits:** Call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each change.
6. **Before declaring work complete:**
   - Recommended: invoke the `/tapps-finish-task` skill — bundles `tapps_validate_changed` + `tapps_checklist` + an optional memory save and reports a one-line summary.
   - If you'd rather run the steps manually: `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to score + gate changed files (never call without `file_paths` in large repos; default is quick mode), then `tapps_checklist(task_type=...)` and, if `complete` is false, call the missing required tools (use `missing_required_hints` for reasons). The checklist response also carries an inline `usage_gaps` block — review it for missed lookups or unvalidated edits.
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.

   **Stop-hook telemetry (warn mode):** if you edited Python/TS/Go files without validating, the Stop hook (`tapps-stop.sh`) appends to `.tapps-mcp/.completion-gate-violations.jsonl`. No block — telemetry that feeds `tapps_usage`. `tapps_doctor` reports `completion_gate_hook.installed`.

   **next_steps shape:** `tapps_score_file` and `tapps_quick_check` template `{file_path}` into next-tool suggestions, so you get paste-ready signatures like `tapps_security_scan(file_path='src/foo.py')`.
7. **When in doubt:** Use `tapps_lookup_docs` for domain-specific questions and library guidance; use `tapps_validate_config` for Docker/infra files.

### Review Pipeline (multi-file)

For reviewing and fixing multiple files in parallel, use the `/tapps-review-pipeline` skill:

1. It detects changed Python files and spawns `tapps-review-fixer` agents (one per file or batch)
2. Each agent scores the file, fixes issues, and runs the quality gate
3. Results are merged and validated with `tapps_validate_changed`
4. A summary table shows before/after scores, gate status, and fixes applied

You can also invoke the `tapps-review-fixer` agent directly on individual files for combined review+fix in a single pass.

---

## Linear epics and stories (DocsMCP)

**Linear is the backlog.** Do not commit epic or story markdown to this repo. Use the `linear-issue` skill:

- **docs_generate_epic** / **docs_generate_story** — structured bodies (inline by default; `write_to_disk=false`).
- **docs_validate_linear_issue** — must return `agent_ready: true` before `save_issue`.
- **docs_generate_prompt** — optional LLM-facing prompt artifacts when needed.

Provide **purpose_and_intent** for epics and stories so the required Purpose & Intent section is populated.

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

**Subagents:** tapps-reviewer (sonnet), tapps-researcher (haiku), tapps-validator (sonnet), tapps-review-fixer (sonnet + worktree), tapps-frontend-reviewer (sonnet).

**Skills:** tapps-finish-task, tapps-handoff-session, tapps-continue-session, tapps-review-pipeline, tapps-research, tapps-security, tapps-memory, tapps-tool-reference, tapps-init, tapps-engagement, tapps-upgrade, tapps-apply-files, tapps-domain-* (security/testing/frontend), tapps-flow-* (develop/review/frontend).

## Agent ecosystem (using TappsMCP with other agent libraries)

TappsMCP creates **4 quality-focused subagents** (tapps-reviewer, tapps-researcher, tapps-validator, tapps-review-fixer) and platform rules + skills. You can **optionally** add [agency-agents](https://github.com/msitarzewski/agency-agents) for 120+ domain personas (e.g. Frontend Developer, Reality Checker) — the two systems coexist with **no path conflict**.

- **Recommended install order:** (1) Configure MCP (tapps-mcp). (2) Run `tapps_init` to get TappsMCP rules, agents, and skills. (3) Optionally run agency-agents `./scripts/install.sh --tool claude-code` or `--tool cursor`.
- **Paths:** **Cursor** — agency-agents writes to `.cursor/rules/`; TappsMCP writes to `.cursor/agents/` and `.cursor/rules/` (no conflict). **Claude** — both can use the agents dir (project `.claude/agents/` or user `~/.claude/agents/`).

Optional: for more specialized agents (e.g. Frontend Developer, Reality Checker), see [agency-agents](https://github.com/msitarzewski/agency-agents) and run their install script for your platform.

## Memory systems

Your project may have two complementary memory systems:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Build commands, IDE preferences, personal workflow notes. Auto-managed.
- **TappsMCP shared memory** — **`uv run tapps-mcp memory`** CLI via BrainBridge (default; do not add direct `tapps-brain` to `.mcp.json`). When **`nlt-memory`** is enabled, `tapps_memory` MCP on that server is a slim facade (TAP-3895). Architecture decisions, quality patterns, cross-agent knowledge. See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) and `/tapps-memory` skill.

RECOMMENDED: Use `uv run tapps-mcp memory save|get|search` for architecture decisions and quality patterns. Pin always-on scope keys under `memory_hooks.auto_recall.recall_keys` in `.tapps-mcp.yaml`.

**Access:** Prefer `uv run tapps-mcp memory <subcommand>` (CLI). With `nlt-memory` enabled, `tapps_memory(action=...)` on that server exposes the same actions (TAP-3895). Not on default `nlt-build` alone (TAP-1994).

**Progressive disclosure:** full action catalog, tiers/scopes, brain health fields, and federation details live in the **tapps-memory** skill and [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md). Do not paste the full action list into always-on context.

**Cross-session handoff:** `/tapps-handoff-session` at chat end and `/tapps-continue-session` at chat start (`.tapps-mcp/session-handoff.md` is canonical).

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

Empty or missing = all 43 tools (default, backward compatible). Invalid tool names in `enabled_tools` are ignored and logged. Recommended subsets by task/role and Docker tool filtering: see [docs/architecture/tool-budget.md](docs/architecture/tool-budget.md).

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

**MCP config (default on):** `tapps_init` writes project-scoped MCP config after bootstrap (`mcp_config=true`); strips direct `tapps-brain` entries (bridge-only). Pass `mcp_config=false` to skip. Brain wiring: [docs/operations/CONSUMER-REPO-BRAIN-WIRING.md](docs/operations/CONSUMER-REPO-BRAIN-WIRING.md).

**Tool contract:** Session start returns server info and project context. tapps_validate_changed default = score + gate only; use `security_depth='full'` or `quick=false` for security. tapps_quick_check has no `quick` parameter (use tapps_score_file(quick=True) for that).

---

## Platform hooks and automation

`tapps_init` / `tapps_upgrade` deploy hooks, subagents, and skills. Keep this file thin — load details on demand:

- **Skills:** invoke `/tapps-finish-task`, `/tapps-memory`, `/tapps-tool-reference`, `linear-issue`, `linear-read` as needed. Set `skill_tier: core` in `.tapps-mcp.yaml` for a smaller inventory.
- **Hooks / subagents / CI:** run `tapps-mcp doctor` for what is wired; engagement level controls hook density.
- **Linear writes:** always use the `linear-issue` skill (never raw `save_issue`). Multi-issue reads: `linear-read`.

> **Removed in v3.12.0:** `tapps-score`, `tapps-gate`, `tapps-validate`, and `tapps-report` wrapper skills were deleted. Prefer direct MCP tool calls or `/tapps-finish-task`.

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

<!-- BEGIN: karpathy-guidelines 2c60614 (MIT, forrestchang/andrej-karpathy-skills) -->
<!--
  Vendored from https://github.com/forrestchang/andrej-karpathy-skills
  Pinned commit: 2c606141936f1eeef17fa3043a72095b4765b9c2 (2026-04-20)
  License: MIT (c) forrestchang
  Do not edit by hand — update KARPATHY_GUIDELINES_SOURCE_SHA in prompt_loader.py
  and re-run the vendor script, then bump tapps-mcp version.
-->
## Karpathy Behavioral Guidelines

> Source: https://github.com/forrestchang/andrej-karpathy-skills @ 2c606141936f1eeef17fa3043a72095b4765b9c2 (MIT)
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

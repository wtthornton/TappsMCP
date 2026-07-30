# TappsMCP - instructions for AI assistants (HIGH enforcement)

When the **TappsMCP** MCP server is configured, you **MUST** use its tools for code quality, doc lookup, and domain expert advice. The steps below are **BLOCKING REQUIREMENTS**. Follow the pipeline and run the checklist before declaring work complete.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## Tapps Rules

These are the seven rules every agent in this project MUST follow. They override default behavior.

1. **Fix root causes — never workarounds.** No `--no-verify`, no swallowed exceptions, no commented-out failing tests. If a check fails, diagnose and fix it. A solution that re-breaks next sprint is a regression, not a fix.
2. **Query tapps-mcp before writing code when confidence is not 100%.** Use `tapps_lookup_docs` for library APIs and `uv run tapps-mcp memory search --query "..."` for prior decisions. Guessing from training memory is the leading cause of hallucinated APIs and re-litigated decisions.
3. **`tapps_lookup_docs` is a Context7-backed local cache — call it freely.** Repeat lookups for the same library/topic are near-zero cost. There is no budget to conserve. If the real API surface would help, fetch it.
4. **Protect the main context window — delegate to subagents.** Route searches, log scans, and exploratory file reads through `Explore` or `general-purpose`. They return summaries, not raw output. If a task would consume more than three file reads or any large tool result you will not reference again, spawn a subagent.
5. **Write code a senior reviewer would accept on first pass.** Clear names, no dead branches, no commented-out code, no speculative abstractions. Match existing style. Every line MUST justify its presence.
6. **The simplest solution that satisfies the requirement is the correct one.** No flexibility for hypothetical futures. No configuration knobs nobody asked for. No abstractions for single-use code. Three similar lines beat a premature abstraction.
7. **All Linear writes go through the `linear-issue` skill; all multi-issue reads through `linear-read`.** NEVER call `mcp__plugin_linear_linear__save_issue` or `list_issues` directly. Epics and stories MUST be generated via `docs_generate_epic` / `docs_generate_story` and pass `docs_validate_linear_issue` (`agent_ready: true`) before push. Single-issue lookups go straight to `get_issue(id=...)`. Release announcements go through the `linear-release-update` skill.

---

## Essential tools (always-on workflow)

| Tool | When to use |
|------|--------------|
| **tapps_session_start** | **FIRST call in every session** - server info only |
| **tapps_quick_check** | **After editing any Python file** - quick score + gate + security |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - score + gate on changed files. **Always pass explicit `file_paths`** (comma-separated). Default is quick mode; only use `quick=false` as a last resort. |
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps. Response carries an inline `usage_gaps` payload — you MUST read it before declaring done. |
| **tapps_usage** | **REQUIRED on any session that touched code** - returns per-session gaps (`edits_without_validation`, `lookup_docs_underused`, etc.) and concrete `recommendations`. Same payload inlined as `usage_gaps` on every `tapps_checklist` response. |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |
| **Brain memory (CLI)** | **REQUIRED** - `uv run tapps-mcp memory search|get|save` for cross-session knowledge. Hooks auto-recall when enabled; pin scope keys in `memory_hooks.auto_recall.recall_keys`. See `/tapps-memory` skill. |

**For full tool reference** ({{TAPPS_MCP_TOOL_COUNT}} tools), invoke the **tapps-tool-reference** skill when asked about tools.

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

## REQUIRED workflow (MUST follow in order)

1. **Session start (REQUIRED):** You MUST call `tapps_session_start` first. It returns server info and project context.
2. **Check project memory (REQUIRED):** `uv run tapps-mcp memory search --query "..."` or `memory get --key <key>` for pinned scope; read `.tapps-mcp/session-handoff.md`.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `uv run tapps-mcp memory save --key ... --tier ... --value "..."` to persist decisions across sessions.
3. **Before using a library (BLOCKING):** You MUST call `tapps_lookup_docs(library=...)` before writing code that uses an external library.
4. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` to see what depends on it.
5. **During edits (REQUIRED):** You MUST call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each Python file edit.
6. **Before declaring work complete (BLOCKING):**
   - REQUIRED: Invoke the `/tapps-finish-task` skill — it bundles `tapps_validate_changed` + `tapps_checklist` + an optional memory save into one call. This is the recommended close-out path.
   - If invoking the skill is not possible, run the steps manually: `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths (never call without `file_paths` — auto-detect scans all git-changed files and can be very slow), then `tapps_checklist(task_type=...)` as the FINAL step. If `complete` is false, call the missing required tools. NEVER declare work complete without running the checklist.
   - MANDATORY: Read the inline `usage_gaps` block on the `tapps_checklist` response (same data as `tapps_usage`). If gaps list missed `tapps_lookup_docs` or unvalidated edits, fix them before declaring done.
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.

   **Stop-hook telemetry (warn mode):** the Stop hook (`tapps-stop.sh`) writes to `.tapps-mcp/.completion-gate-violations.jsonl` whenever Python/TS/Go edits ship without `tapps_validate_changed` + `tapps_checklist`. WARN mode only — no block. Feeds `tapps_usage`. `tapps_doctor` reports `completion_gate_hook.installed` and warns when the hook is absent.

   **next_steps shape:** high-traffic tools (`tapps_score_file`, `tapps_quick_check`) now template `{file_path}` into next-tool suggestions, producing paste-ready signatures like `tapps_security_scan(file_path='src/foo.py')`.
7. **Domain decisions (REQUIRED):** You MUST call `tapps_lookup_docs` for domain-specific decisions and library guidance. Use `tapps_validate_config` for Docker/infra files.

### Review Pipeline (multi-file)

For reviewing and fixing multiple files in parallel, use the `/tapps-review-pipeline` skill:

1. It detects changed Python files and spawns `tapps-review-fixer` agents (one per file or batch)
2. Each agent scores the file, fixes issues, and runs the quality gate
3. Results are merged and validated with `tapps_validate_changed`
4. A summary table shows before/after scores, gate status, and fixes applied

You can also invoke the `tapps-review-fixer` agent directly on individual files for combined review+fix in a single pass.

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

## Project scope (do not break out of this repo/project)

You were deployed into THIS repo by `tapps_init` / `tapps_upgrade`. Stay in scope:

- You **MAY read across projects** — docs lookups, reading sibling repos, fetching references.
- You **MUST NOT write outside this repo or this project**:
  - Do not create, update, comment on, or move Linear (or other tracker) issues belonging to a different project.
  - Do not modify files, branches, or pull requests in any other repository.
  - Do not push, merge, or release on behalf of another project.
- Read team / project / repo identity from local config (`.tapps-mcp.yaml`, current git remote) — never infer from search results or memory hits that point at unrelated workspaces.
- If a task seems to require a write outside this repo/project, stop and ask the user.

---

## Memory systems

Your project may have two complementary memory systems:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Build commands, IDE preferences, personal workflow notes. Auto-managed by Claude Code.
- {{MEMORY_SYSTEMS_BULLET}}

REQUIRED: Use `uv run tapps-mcp memory save|get|search` for architecture decisions and quality patterns. Pin scope keys under `memory_hooks.auto_recall.recall_keys`.

**Progressive disclosure:** full action catalog, tiers/scopes, brain health fields, and federation details live in the **tapps-memory** skill and [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md). Do not paste the full action list into always-on context.

**Cross-session handoff:** `/tapps-handoff-session` at chat end and `/tapps-continue-session` at chat start (`.tapps-mcp/session-handoff.md` is canonical).

---

## Platform hooks and automation

`tapps_init` / `tapps_upgrade` deploy hooks, subagents, and skills. Keep this file thin — load details on demand:

- **Skills:** invoke `/tapps-finish-task`, `/tapps-memory`, `/tapps-tool-reference`, `linear-issue`, `linear-read` as needed. Set `skill_tier: core` in `.tapps-mcp.yaml` for a smaller inventory.
- **Hooks / subagents / CI:** run `tapps-mcp doctor` for what is wired; high engagement enables denser hooks and blocking Stop/TaskCompleted reminders.
- **Linear writes:** always use the `linear-issue` skill (never raw `save_issue`). Multi-issue reads: `linear-read`.

> **Removed in v3.12.0:** `tapps-score`, `tapps-gate`, `tapps-validate`, and `tapps-report` wrapper skills were deleted. You MUST prefer direct MCP tool calls or `/tapps-finish-task`.

---

## Content-return pattern (Docker / read-only environments)

When TappsMCP or DocsMCP runs inside a Docker container with a read-only workspace
mount, tools **cannot write files directly**.  Instead they return a `file_manifest`
in the response with the file contents and instructions for you to apply.

**How to detect:** Check for `content_return: true` in the tool response `data`.

**How to apply (REQUIRED when content_return is true):**
1. Read `file_manifest.agent_instructions` for persona, tool preference, and warnings
2. For each file in `file_manifest.files[]` (sorted by `priority`, lowest first):
   - `mode: "create"` or `"overwrite"` → Use the **Write** tool with the `content` verbatim
   - `mode: "merge"` → The content is the pre-computed merge result; write it with the **Write** tool
3. Create parent directories as needed
4. Follow `verification_steps` after all files are written
5. **Never modify the content** — write it exactly as provided

**Tools that support content-return:** `tapps_init`, `tapps_upgrade`, `tapps_set_engagement_level`, `tapps_memory` (export), `docs_config`, and all `docs_generate_*` generators.

**Force content-return:** Pass `output_mode: "content_return"` to `tapps_init` or `tapps_upgrade`.

---

## DocsMCP - documentation tools (companion server)

When the **DocsMCP** MCP server is also configured, you have access to documentation generation and validation tools. Use them alongside TappsMCP quality tools for a complete development workflow.

| Tool | When to use |
|------|--------------|
| **docs_project_scan** | Audit documentation state for a project |
| **docs_generate_readme** | Generate or update README with smart merge |
| **docs_generate_changelog** | Generate CHANGELOG from git history |
| **docs_generate_api** | Generate API reference docs |
| **docs_generate_adr** | Create Architecture Decision Records |
| **docs_check_drift** | Detect code changes not reflected in docs |
| **docs_check_completeness** | Score documentation completeness |
| **docs_check_freshness** | Check documentation staleness |

DocsMCP is a separate MCP server. Install via `pip install docs-mcp` or `npx docs-mcp serve`. See [DocsMCP docs](https://github.com/tapps-mcp/tapps-mcp/tree/master/packages/docs-mcp) for setup.

**Combined server (TappsPlatform):** For clients that support 47+ tools (Claude Code, GitHub Copilot), you can run both servers as one via `tapps-platform serve`. This shares singletons (memory, knowledge cache, settings) and reduces overhead. Note: Cursor has a 40-tool limit, so use standalone servers there. See the [COMPOSITION_GUIDE](https://github.com/wtthornton/TappsMCP/blob/master/docs/archive/reference/COMPOSITION_GUIDE.md) in the tapps-mcp repo for configuration details.

### Optional: More specialized agents

For more specialized agents (e.g. Frontend Developer, Reality Checker), see [agency-agents](https://github.com/msitarzewski/agency-agents) and run their install script for your platform. TappsMCP and agency-agents can coexist; there is no path conflict.

---

## Troubleshooting: MCP server not available

For the full consumer requirements checklist, see the [TAPPS_MCP_REQUIREMENTS doc](https://github.com/wtthornton/TappsMCP/blob/master/docs/archive/reference/TAPPS_MCP_REQUIREMENTS.md) in the tapps-mcp repo.

TappsMCP tools (`tapps_session_start`, `tapps_init`, `tapps_quick_check`, etc.) are only callable when the tapps-mcp server is **listed as an available MCP server** in your host (Claude Code, Cursor, or VS Code). If the server is configured in MCP config files but not visible to the agent, tool calls will fail.

**How to verify the server is available:**
- **Claude Code:** Run `/mcp` to list connected servers, or check `.claude.json` / `.mcp.json`
- **Cursor:** Open Settings > MCP and confirm tapps-mcp is listed and enabled
- **VS Code:** Check `.vscode/mcp.json` and the MCP panel in the sidebar

**If the server is not available (CLI fallback):**
1. From the project root, run: `tapps-mcp upgrade --force --host auto`
2. Then verify: `tapps-mcp doctor`
3. Restart your MCP host (Claude Code / Cursor / VS Code) to pick up the new config
4. If tools are still unavailable, use CLI commands directly: `tapps-mcp init`, `tapps-mcp doctor`

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

## Troubleshooting: Doctor timeout

`tapps-mcp doctor` runs version checks on all quality tools (ruff, mypy, bandit, radon, vulture, pylint, pip-audit) and may take **30-60+ seconds**, especially on first run or in cold environments where mypy is slow to start.

**If doctor times out or takes too long:**
- Use `tapps-mcp doctor --quick` to skip tool version checks (completes in a few seconds)
- Run doctor in the background if your agent or IDE has a short CLI timeout
- The MCP tool `tapps_doctor(quick=True)` provides the same quick mode

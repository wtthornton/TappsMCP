# TappsMCP - instructions for AI assistants

When the **TappsMCP** MCP server is configured in your host (Claude Code, Cursor, VS Code Copilot, Claude Desktop, etc.), you have access to tools that provide **deterministic code quality checks, doc lookup, and domain expert advice**. TappsMCP is a quality toolset designed to help your project and LLM produce the best possible code - use it to avoid hallucinated APIs, missed quality steps, and inconsistent output.

---

## What TappsMCP is

TappsMCP is an MCP server that provides a comprehensive quality toolset for your project. It exposes 26 tools for:

- **Scoring** Python files (0-100 across 7 categories: complexity, security, maintainability, test coverage, performance, structure, devex)
- **Security scanning** (Bandit + secret detection with redacted context)
- **Quality gates** (pass/fail against configurable presets: standard, strict, framework)
- **Dead code detection** (Vulture-based unused function/class/import/variable detection with confidence scoring)
- **Dependency vulnerability scanning** (pip-audit for known CVEs in third-party packages)
- **Circular dependency detection** (import graph analysis, cycle detection, coupling metrics)
- **Documentation lookup** (up-to-date library docs via Context7 + LlmsTxt fallback and cache)
- **Config validation** (Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB best practices)
- **Project context** (project type detection, tech stack, impact analysis)
- **Shared memory** (persistent cross-session knowledge with decay, contradiction detection, and ranked retrieval)
- **Session management** (persist decisions, constraints, and notes within a session; promote to memory for cross-session persistence)
- **Quality reports** (JSON, Markdown, or HTML summaries)
- **Metrics and feedback** (dashboard, usage stats, adaptive learning via feedback)
- **Session checklist** (track which tools were used so you don't skip required steps)
- **Pipeline orchestration** (batch validation, workflow prompts, project initialization)
- **Structured outputs** (machine-parseable JSON alongside human-readable text for all scoring tools)

You only see these tools when the host has started the TappsMCP server and attached it to your session.

**File paths:** For tools that take `file_path`, use **paths relative to the project root** (e.g. `src/main.py`, `tests/test_foo.py`) so they work with both stdio and Docker. If the server is configured with `TAPPS_MCP_HOST_PROJECT_ROOT` (e.g. when using Docker), you can also pass **absolute host paths** (e.g. `C:\projects\myapp\src\main.py`); the server will map them to the project root.

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_session_start** | **FIRST call in every session** - returns server info (version, checkers, configuration) and project context. |
| **tapps_server_info** | Lightweight discovery: version, tools, checkers. Prefer **tapps_session_start** as FIRST call (adds memory status, auto-GC, session capture). Use tapps_server_info only when you need discovery without session init. |
| **tapps_score_file** | When **editing or reviewing** a Python file. Use `quick=True` during edit-lint-fix loops; use full (default) **before declaring work complete**. |
| **tapps_quick_check** | **After editing any Python file** - quick score + gate + basic security in one fast call. |
| **tapps_security_scan** | When the change is **security-sensitive** or before a security-focused review. |
| **tapps_quality_gate** | **Before declaring work complete** - ensures the file passes the configured quality preset. Do not consider work done until this passes (or the user accepts the risk). |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - auto-detects changed files via git diff and runs score + gate on each. **Default is quick mode** (ruff-only, under ~10s). Includes impact analysis by default. Pass `quick=false` for full validation. |
| **tapps_lookup_docs** | **Before writing code** that uses an external library - use the returned docs to avoid hallucinated APIs. Also use for domain-specific guidance (e.g. security patterns, testing strategies). |
| **tapps_validate_config** | When **adding or changing** Dockerfile, docker-compose, or infra config. |
| **tapps_memory** | **At session start** - search or list past decisions with `tapps_memory(action="search", query="...")` or `tapps_memory(action="list")`. **Before session end** - save learnings with `tapps_memory(action="save", key="...", value="...", tier="...", tags=[...])`. Supports save, get, list, search, delete, reinforce, contradictions, gc, reseed, import, export. |
| **tapps_session_notes** | When you make a **key decision or discover a constraint** - save it so you can recall it later in a long session. Use `action="promote"` to promote a session note to persistent cross-session memory. |
| **tapps_impact_analysis** | Before **modifying a file's public API** - shows what depends on it and what could break. |
| **tapps_report** | After scoring/gating, when the user wants a **formatted quality summary** (Markdown, JSON, or HTML). |
| **tapps_checklist** | **Before declaring work complete** - reports which tools were called and which are missing (with reasons). Fix missing required steps before saying done. |
| **tapps_dashboard** | When the user wants to **review how TappsMCP is performing** - scoring accuracy, gate pass rates, expert effectiveness, cache performance, quality trends, and alerts. Supports json, markdown, and html output. |
| **tapps_stats** | When the user wants **usage statistics** - call counts, success rates, average durations, cache hit rates, and gate pass rates. Filterable by tool and time period. |
| **tapps_feedback** | After receiving a tool result - report whether the output was **helpful or not**. This feedback improves adaptive scoring and expert weights over time. |
| **tapps_dead_code** | When you want to **find unused code** in a Python file - detects unused functions, classes, imports, and variables with confidence scoring. Use during refactoring or code review. |
| **tapps_dependency_scan** | When you want to **check for vulnerable dependencies** - scans pip packages for known CVEs using pip-audit. Use before releases or security reviews. |
| **tapps_dependency_graph** | When you want to **understand module dependencies** - builds import graph, detects circular imports, and calculates coupling metrics. Use before refactoring or when investigating import errors. |
| **tapps_workflow** | When you want the **recommended tool call order** for a specific task type (general, feature, bugfix, refactor, security, review). |
| **tapps_init** | At **pipeline bootstrap** - creates AGENTS.md, TECH_STACK.md, platform rules, optionally warms caches. Call once per project (or when upgrading). |
| **tapps_upgrade** | After a **TappsMCP version update** - validates and refreshes AGENTS.md, platform rules, hooks, agents, skills, and settings. Preserves custom command paths (e.g. PyInstaller exe). Use `dry_run: true` to preview. |
| **tapps_doctor** | When **diagnosing configuration issues** - checks binary availability, MCP configs, platform rules, generated files, hooks, and installed quality tools. Returns per-check pass/fail with remediation hints. |

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

---

## Tool contract (what each tool returns / when security runs)

Use this when writing project-specific tool priority docs or integrating TappsMCP.

| Contract | Detail |
|----------|--------|
| **tapps_session_start** | Returns server info (version, checkers, config) and project context. |
| **tapps_validate_changed** | Default `quick=true`: runs **score + quality gate** on each changed file; **security scan is not run**. To include security: pass `quick=false` or `security_depth='full'`. |
| **tapps_quick_check** | Single tool; **no `quick` parameter**. Always runs quick score + gate + basic security in one call. For per-file "quick" scoring with a `quick` flag, use **tapps_score_file(file_path, quick=True)** instead. |
| **tapps_lookup_docs** | Primary tool for both library documentation and domain-specific guidance. Returns structured docs for libraries and supports topic queries for patterns, best practices, and design guidance. |

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

## Recommended workflow

1. **Session start:** Call `tapps_session_start` (returns server info and project context).
2. **Check project memory:** Call `tapps_memory(action="search", query="...")` or `tapps_memory(action="list")` to recall past decisions and project context from previous sessions.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `tapps_memory(action="save", ...)` to persist decisions across sessions.
4. **Before using a library:** Call `tapps_lookup_docs(library=...)` and use the returned content when implementing.
5. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` to see what depends on it.
6. **During edits:** Call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each change.
7. **Before declaring work complete:**
   - Call `tapps_validate_changed()` to score + gate on all changed files (default quick mode). Pass `security_depth='full'` or `quick=false` to include security scan.
   - Call `tapps_checklist(task_type=...)` and, if `complete` is false, call the missing required tools (use `missing_required_hints` for reasons).
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.
8. **When in doubt:** Use `tapps_lookup_docs` for domain-specific questions and library guidance; use `tapps_validate_config` for Docker/infra files.

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

Your project may have two complementary memory systems. Use the right one for each type of knowledge:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Session learnings, user preferences, build commands, IDE settings, debugging insights. Auto-managed by Claude Code across sessions.
- **TappsMCP shared memory** (`tapps_memory` tool): Architecture decisions, quality patterns, expert consultation findings, cross-agent knowledge. Structured with tier classification (architectural/pattern/context), confidence scoring, decay, contradiction detection, and cross-session persistence.

**When to use which:**
- Build commands, IDE preferences, personal workflow notes --> auto memory
- Architecture decisions, quality patterns, cross-agent knowledge --> `tapps_memory`

Use `tapps_memory` for architecture decisions and quality patterns.

**Cross-session handoff:** when one session needs to pass a token, ID, or short payload to a later session in the same project, call `tapps_memory(action="save", key="<slug>", value="<payload>")` instead of printing it to stdout. The default `project` scope is already cross-session within the same repo. Read it back from the next session with `tapps_memory(action="get", key="<slug>")` or `action="search"`. For cross-agent handoff in Agent Teams, use `action="hive_propagate"`; for cross-project, use the federation actions.

**Brain health (`brain_bridge_health`):** every `tapps_session_start` response carries a `data.brain_bridge_health` block — `enabled`, `ok`, `dsn_reachable`, `pool_config_valid`, `native_health_ok`, `errors`, `warnings`, plus `details` (mode, `http_url`, `brain_version`, `brain_status`). `tapps doctor` runs the same probe. See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md#brain-health-diagnostics) for troubleshooting `brain_auth_failed`, `BrainBridgeUnavailable`, and version-floor mismatches.

---

## Platform hooks and automation

When `tapps_init` generates platform-specific files, it also creates **hooks**, **subagents**, and **skills** that automate parts of the workflow:

### Hooks (auto-generated)

**Claude Code** (`.claude/hooks/`): 7 hook scripts that enforce quality automatically:
- **SessionStart** - Injects TappsMCP awareness on session start and after compaction
- **PostToolUse (Edit/Write)** - Reminds you to run `tapps_quick_check` after Python edits
- **Stop** - Reminds you to run `tapps_validate_changed` before session end (non-blocking)
- **TaskCompleted** - Reminds you to validate before marking task complete (non-blocking)
- **PreCompact** - Backs up scoring context before context window compaction
- **SubagentStart** - Injects TappsMCP awareness into spawned subagents

**Cursor** (`.cursor/hooks/`): 3 hook scripts:
- **beforeMCPExecution** - Logs MCP tool invocations for observability
- **afterFileEdit** - Fire-and-forget reminder to run quality checks
- **stop** - Prompts validation via followup_message before session ends

### Subagents (auto-generated)

Three agent definitions per platform in `.claude/agents/` or `.cursor/agents/`:
- **tapps-reviewer** (sonnet) - Reviews code quality and runs security scans after edits
- **tapps-researcher** (haiku) - Looks up documentation and consults domain experts
- **tapps-validator** (sonnet) - Runs pre-completion validation on all changed files

### Skills (auto-generated)

Twelve SKILL.md files per platform in `.claude/skills/` or `.cursor/skills/`:
- **tapps-score** - Score a Python file across 7 quality categories
- **tapps-gate** - Run a quality gate check and report pass/fail
- **tapps-validate** - Validate all changed files before declaring work complete
- **tapps-review-pipeline** - Orchestrate a parallel review-fix-validate pipeline
- **tapps-research** - Research a technical question using domain experts and docs
- **tapps-security** - Run a comprehensive security audit with vulnerability scanning
- **tapps-memory** - Manage shared project memory for cross-session knowledge

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

### Optional: More specialized agents

For more specialized agents (e.g. Frontend Developer, Reality Checker), see [agency-agents](https://github.com/msitarzewski/agency-agents) and run their install script for your platform. TappsMCP and agency-agents can coexist; there is no path conflict.

---

## Content-return pattern (Docker / read-only environments)

When TappsMCP or DocsMCP runs inside a Docker container with a read-only workspace
mount, tools **cannot write files directly**.  Instead they return a `file_manifest`
in the response with the file contents and instructions for you to apply.

**How to detect:** Check for `content_return: true` in the tool response `data`.

**How to apply:**
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

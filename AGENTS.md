<!-- tapps-agents-version: 0.8.4 -->
# TappsMCP - instructions for AI assistants

When the **TappsMCP** MCP server is configured, you have access to tools for **code quality, doc lookup, and domain expert advice**. Use them to avoid hallucinated APIs, missed quality steps, and inconsistent output.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## What TappsMCP is

TappsMCP is an MCP server that provides a comprehensive quality toolset for your project. It exposes 29 tools for:

- **Scoring** code files (0-100 across 7 categories: complexity, security, maintainability, test coverage, performance, structure, devex) — supports **Python**, **TypeScript/JavaScript**, **Go**, and **Rust** with tree-sitter analysis (optional dependency for non-Python, falls back to regex)
- **Security scanning** (Bandit + secret detection with redacted context)
- **Quality gates** (pass/fail against configurable presets: standard, strict, framework)
- **Dead code detection** (Vulture-based unused function/class/import/variable detection with confidence scoring)
- **Dependency vulnerability scanning** (pip-audit for known CVEs in third-party packages)
- **Circular dependency detection** (import graph analysis, cycle detection, coupling metrics)
- **Documentation lookup** (up-to-date library docs via Context7 when key set, LlmsTxt fallback, cache)
- **Config validation** (Dockerfile, docker-compose, WebSocket/MQTT/InfluxDB best practices)
- **Domain experts** (17 built-in experts with RAG-backed answers, optional vector search)
- **Project context** (project type detection, tech stack, impact analysis)
- **Shared memory** (persistent cross-session knowledge with decay, contradiction detection, and ranked retrieval)
- **Session management** (persist decisions, constraints, and notes within a session; promote to memory for cross-session persistence)
- **Quality reports** (JSON, Markdown, or HTML summaries)
- **Metrics and feedback** (dashboard, usage stats, adaptive learning via feedback)
- **Session checklist** (track which tools were used so you don't skip required steps)
- **Pipeline orchestration** (batch validation, workflow prompts, project initialization)
- **Engagement level** (set how strongly the AI is prompted to use tools: high / medium / low via `tapps_set_engagement_level`)
- **Structured outputs** (machine-parseable JSON alongside human-readable text for all scoring tools)

You only see these tools when the host has started the TappsMCP server and attached it to your session.

**File paths:** For tools that take `file_path`, use **paths relative to the project root** (e.g. `src/main.py`, `tests/test_foo.py`) so they work with both stdio and Docker. If the server is configured with `TAPPS_MCP_HOST_PROJECT_ROOT` (e.g. when using Docker), you can also pass **absolute host paths** (e.g. `C:\projects\myapp\src\main.py`); the server will map them to the project root.

---

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_session_start** | **FIRST call in every session** - returns server info (version, checkers, configuration) only. Call **tapps_project_profile** when you need project context. |
| **tapps_server_info** | At **session start** - discover version, available tools, and installed checkers. Response includes a short `recommended_workflow` string. |
| **tapps_score_file** | When **editing or reviewing** a code file. Supports Python, TypeScript/JavaScript, Go, Rust. Use `quick=True` during edit-lint-fix loops; use full (default) **before declaring work complete**. |
| **tapps_quick_check** | **After editing any supported file** - quick score + gate + basic security in one fast call. Supports Python (.py), TypeScript (.ts/.tsx), JavaScript (.js/.jsx), Go (.go), Rust (.rs). |
| **tapps_security_scan** | When the change is **security-sensitive** or before a security-focused review. |
| **tapps_quality_gate** | **Before declaring work complete** - ensures the file passes the configured quality preset. Gate failures are sorted by category weight (highest-impact first). A security floor of 50/100 is enforced regardless of overall score. Do not consider work done until this passes (or the user accepts the risk). |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - runs score + gate on specified files. **Always pass explicit `file_paths`** (comma-separated) to scope validation to files you actually changed — do NOT rely on auto-detect, which scans all git-changed files and can be very slow in large repos. **Default is quick mode** (ruff-only, under ~10s). Only use `quick=false` as a **last resort** (pre-release, security audit) — it runs mypy, bandit, radon, vulture and takes 1–5+ min per file. |
| **tapps_lookup_docs** | **Before writing code** that uses an external library - use the returned docs to avoid hallucinated APIs. |
| **tapps_validate_config** | When **adding or changing** Dockerfile, docker-compose, or infra config. |
| **tapps_consult_expert** | When making **domain-specific decisions** (security, testing, APIs, database, etc.) and you want authoritative, RAG-backed guidance. Pass `domain` when context makes it obvious (e.g. editing a test file -> `domain="testing-strategies"`). |
| **tapps_research** | When you need **combined expert + docs** in one call - consults the domain expert, then supplements with Context7 (when key set) or LlmsTxt documentation. Pass `file_context` with the path to the file being edited to auto-infer library from imports. Saves a round-trip vs calling `tapps_consult_expert` + `tapps_lookup_docs` separately. |
| **tapps_list_experts** | When you need to see **which expert domains exist** before calling `tapps_consult_expert`. |
| **tapps_project_profile** | When you need **project context** - detects project type, tech stack, CI/Docker/tests, and recommendations. Session start does not include profile; call this on demand. |
| **tapps_memory** | Persistent cross-session knowledge store with 20 actions (see **Memory action reference** below). **At session start** - `action="search"` or `action="list"` to recall past decisions. **Before session end** - `action="save"` to persist learnings. |
| **tapps_session_notes** | When you make a **key decision or discover a constraint** - save it so you can recall it later in a long session. Use `action="promote"` to promote a session note to persistent cross-session memory. |
| **tapps_impact_analysis** | Before **modifying a file's public API** - shows what depends on it and what could break. |
| **tapps_report** | After scoring/gating, when the user wants a **formatted quality summary** (Markdown, JSON, or HTML). |
| **tapps_checklist** | **Before declaring work complete** - reports which tools were called and which are missing (with reasons). Fix missing required steps before saying done. Use `auto_run=True` to automatically run missing required validations. |
| **tapps_dashboard** | When the user wants to **review how TappsMCP is performing** - scoring accuracy, gate pass rates, expert effectiveness, cache performance, quality trends, and alerts. Supports json, markdown, and html output. |
| **tapps_stats** | When the user wants **usage statistics** - call counts, success rates, average durations, cache hit rates, and gate pass rates. Filterable by tool and time period. Response includes `recommendations` with actionable suggestions based on usage patterns. |
| **tapps_feedback** | After receiving a tool result - report whether the output was **helpful or not**. This feedback improves adaptive scoring and expert weights over time. Pass `domain` parameter for expert tools to enable **adaptive domain routing** (learns which domains work best for your project). |
| **tapps_dead_code** | When you want to **find unused code** - detects unused functions, classes, imports, and variables with confidence scoring. Use `scope` parameter: `"file"` (single file), `"project"` (all Python files), or `"changed"` (git diff only). Use during refactoring or code review. |
| **tapps_dependency_scan** | When you want to **check for vulnerable dependencies** - scans pip packages for known CVEs using pip-audit. Use before releases or security reviews. |
| **tapps_dependency_graph** | When you want to **understand module dependencies** - builds import graph, detects circular imports, and calculates coupling metrics. Use before refactoring or when investigating import errors. |
| **tapps_workflow** | *(MCP prompt, not a tool)* When you want the **recommended tool call order** for a specific task type (general, feature, bugfix, refactor, security, review). |
| **tapps_init** | At **pipeline bootstrap** - creates AGENTS.md, TECH_STACK.md, platform rules, optionally warms caches. On first run, presents an interactive wizard (5 questions covering quality preset, engagement level, agent teams, skill tier, and prompt hooks; answers persist in `.tapps-mcp.yaml`). Call once per project (or when upgrading). Use `llm_engagement_level` to set high/medium/low. |
| **tapps_set_engagement_level** | When the **user wants to change** how strongly TappsMCP prompts the AI (e.g. "set tappsmcp to high"). Writes `llm_engagement_level` to `.tapps-mcp.yaml`. Then run `tapps_init(overwrite_agents_md=True)` to regenerate AGENTS.md and platform rules with the new level. |
| **tapps_upgrade** | After a **TappsMCP version update** - validates and refreshes AGENTS.md, platform rules, hooks, agents, skills, and settings. Creates a timestamped backup before overwriting (use `tapps-mcp rollback` to restore). Preserves custom command paths (e.g. PyInstaller exe). Use `dry_run: true` to preview. |
| **tapps_doctor** | When **diagnosing configuration issues** - checks binary availability, MCP configs, platform rules, generated files, hooks, and installed quality tools. Reports `llm_engagement_level` when set in `.tapps-mcp.yaml`. Returns per-check pass/fail with remediation hints. |

---

## tapps_session_start vs tapps_init

| Aspect | tapps_session_start | tapps_init |
|--------|---------------------|------------|
| **When** | **First call in every session** | **Pipeline bootstrap** (once per project, or when upgrading) |
| **Duration** | Fast (~1s, server info only) | Full run: 10-35+ seconds |
| **Purpose** | Load server info (version, checkers, config) into context | Create files (AGENTS.md, TECH_STACK.md, platform rules), optionally warm cache/RAG |
| **Side effects** | None (read-only) | Writes files, warms caches |
| **Typical flow** | Call at session start, then work; call **tapps_project_profile** when you need project context | Call once to bootstrap, or `dry_run: true` to preview |

**Session start** -> `tapps_session_start`. Use this as the first call in every session. Call **tapps_project_profile** when you need project type, tech stack, or recommendations.

**Pipeline/bootstrap** -> `tapps_init`. Use when you need to set up TappsMCP in a project (AGENTS.md, TECH_STACK.md, platform rules) or upgrade existing files.

**Both in one session?** Yes. If the project is not yet bootstrapped: call `tapps_session_start` first (fast), then `tapps_init` (creates files). If the project is already bootstrapped: call only `tapps_session_start` at session start.

**Lighter tapps_init options** (for timeout-prone MCP clients): Use `dry_run: true` to preview (~2-5s); use `verify_only: true` for a quick server/checker check (~1-3s); or set `warm_cache_from_tech_stack: false` and `warm_expert_rag_from_tech_stack: false` for a faster init without cache warming.

---

## Domain hints for tapps_consult_expert

Pass the `domain` parameter when the context clearly implies a domain. This improves routing accuracy and avoids auto-detection mistakes.

| Context | domain value |
|---------|--------------|
| Editing test files, conftest.py, pytest config | `testing-strategies` |
| Security-sensitive code, auth, validation | `security` |
| API routes, FastAPI/Flask endpoints | `api-design-integration` |
| Database models, migrations, queries | `database-data-management` |
| Dockerfile, docker-compose, k8s manifests | `cloud-infrastructure` |
| CI/CD, workflows, build config | `development-workflow` |
| Code quality, linting, type hints | `code-quality-analysis` |
| Architecture decisions, patterns | `software-architecture` |

When in doubt, omit `domain` to let auto-detection from the question text choose.

---

## Supported languages

TappsMCP scoring tools support multiple programming languages:

| Language | Extensions | Scoring Status | Notes |
|----------|------------|----------------|-------|
| **Python** | `.py`, `.pyi` | ✅ Full | ruff, mypy, bandit, radon, vulture |
| **TypeScript** | `.ts`, `.tsx` | ✅ Full | Tree-sitter AST analysis (regex fallback); all 7 categories including `any` usage, nested callbacks |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ Full | Routes to TypeScript scorer |
| **Go** | `.go` | ✅ Full | Tree-sitter AST analysis (regex fallback); all 7 categories including `unsafe.Pointer`, defer-in-loop |
| **Rust** | `.rs` | ✅ Full | Tree-sitter AST analysis (regex fallback); all 7 categories including unsafe blocks, `.unwrap()` abuse |

**Tree-sitter mode:** When `tree-sitter` dependencies are installed (`uv sync --extra treesitter`), scorers use full AST analysis. Without tree-sitter, scorers fall back to regex-based analysis and mark results as `degraded: true`. The language is auto-detected from the file extension.

**Language detection:** Use any scoring tool (`tapps_score_file`, `tapps_quick_check`, `tapps_quality_gate`) with any supported file extension. The correct scorer is selected automatically. Unsupported file types return a clear "unsupported language" message.

---

## Recommended workflow

1. **Session start:** Call `tapps_session_start` (server info only). Call `tapps_project_profile` when you need project context (tech stack, type, recommendations). Optionally call `tapps_list_experts` if you may need experts.
2. **Check project memory:** Consider calling `tapps_memory(action="search", query="...")` to recall past decisions and project context.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `tapps_memory(action="save", ...)` to persist decisions across sessions.
3. **Before using a library:** Call `tapps_lookup_docs(library=...)` and use the returned content when implementing.
4. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` to see what depends on it.
5. **During edits:** Call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each change.
6. **Before declaring work complete:**
   - Call `tapps_validate_changed(file_paths="src/foo.py,src/bar.py")` with explicit paths to the files you changed. Always scope to your changed files — never call without `file_paths` in large repos.
   - Call `tapps_checklist(task_type=...)` and, if `complete` is false, call the missing required tools (use `missing_required_hints` for reasons).
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.
7. **When in doubt:** Use `tapps_consult_expert` for domain-specific questions; use `tapps_validate_config` for Docker/infra files. **For library-specific domain questions**, pair `tapps_consult_expert` with `tapps_lookup_docs` to get expert guidance backed by current documentation (the expert response will suggest the right library/topic to look up).

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

## Platform hooks and automation

When `tapps_init` generates platform-specific files, it also creates **hooks**, **subagents**, and **skills** that automate parts of the workflow:

### Hooks (auto-generated)

**Claude Code** (`.claude/hooks/`): 9 hook scripts that enforce quality automatically:
- **SessionStart** - Injects TappsMCP awareness on session start and after compaction
- **PostToolUse (Edit/Write)** - Reminds you to run `tapps_quick_check` after Python edits
- **Stop** - Reminds you to run `tapps_validate_changed` before session end (non-blocking)
- **TaskCompleted** - Reminds you to validate before marking task complete (non-blocking)
- **PreCompact** - Backs up scoring context before context window compaction
- **SubagentStart** - Injects TappsMCP awareness into spawned subagents
- **SubagentStop** - Captures subagent quality context on exit
- **MemoryCapture** - Persists session quality data to memory on session stop

**Cursor** (`.cursor/hooks/`): 2 hook scripts:
- **beforeMCPExecution** - Logs MCP tool invocations for observability
- **afterFileEdit** - Fire-and-forget reminder to run quality checks

### Subagents (auto-generated)

Four agent definitions per platform in `.claude/agents/` or `.cursor/agents/`:
- **tapps-reviewer** (sonnet) - Reviews code quality and runs security scans after edits
- **tapps-researcher** (haiku) - Looks up documentation and consults domain experts
- **tapps-validator** (sonnet) - Runs pre-completion validation on all changed files
- **tapps-review-fixer** (sonnet) - Combined review, fix, and validate in a single pass per file

### Skills (auto-generated)

Ten SKILL.md files per platform in `.claude/skills/` or `.cursor/skills/`:
- **tapps-score** - Score a Python file across 7 quality categories
- **tapps-gate** - Run a quality gate check and report pass/fail
- **tapps-validate** - Validate all changed files before declaring work complete
- **tapps-review-pipeline** - Orchestrate a parallel review-fix-validate pipeline
- **tapps-research** - Research a technical question using domain experts and docs
- **tapps-security** - Run a comprehensive security audit with vulnerability scanning
- **tapps-memory** - Manage shared project memory for cross-session knowledge
- **tapps-tool-reference** - Full tool reference with per-tool guidance
- **tapps-init** - Bootstrap TappsMCP in a project (AGENTS.md, rules, hooks, skills)
- **tapps-engagement** - Change enforcement intensity (high/medium/low)

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

## Troubleshooting: MCP server not available

For the full consumer requirements checklist, see [docs/TAPPS_MCP_REQUIREMENTS.md](docs/TAPPS_MCP_REQUIREMENTS.md).

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

`tapps-mcp doctor` runs version checks on all quality tools (ruff, mypy, bandit, radon, vulture, pip-audit) and may take **30-60+ seconds**, especially on first run or in cold environments where mypy is slow to start.

**If doctor times out or takes too long:**
- Use `tapps-mcp doctor --quick` to skip tool version checks (completes in a few seconds)
- Run doctor in the background if your agent or IDE has a short CLI timeout
- The MCP tool `tapps_doctor(quick=True)` provides the same quick mode

## Essential tools (always-on workflow)

| Tool | When to use |
|------|--------------|
| **tapps_session_start** | **FIRST call in every session** - server info only |
| **tapps_quick_check** | **After editing any supported file** - quick score + gate + security (Python, TypeScript, Go, Rust) |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - score + gate on changed files |
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |

**For full tool reference** (29 tools with per-tool guidance), invoke the **tapps-tool-reference** skill when the user asks "what tools does TappsMCP have?", "when do I use tapps_score_file?", etc.

---

## Memory systems

Your project may have two complementary memory systems. Use the right one for each type of knowledge:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Session learnings, user preferences, build commands, IDE settings, debugging insights. Auto-managed by Claude Code across sessions.
- **TappsMCP shared memory** (`tapps_memory` tool): Architecture decisions, quality patterns, expert consultation findings, cross-agent knowledge. Structured with tier classification, confidence scoring, decay, contradiction detection, consolidation, federation, and cross-session persistence.

**When to use which:**
- Build commands, IDE preferences, personal workflow notes --> auto memory
- Architecture decisions, quality patterns, cross-agent knowledge --> `tapps_memory`

Use `tapps_memory` for architecture decisions and quality patterns.

### Memory action reference

The `tapps_memory` tool supports **20 actions** organized in 5 groups:

#### Core CRUD

| Action | Parameters | Description |
|--------|-----------|-------------|
| **save** | `key`, `value`, `tier`, `scope`, `tags`, `source` | Save a memory entry. Tiers: `architectural` (180-day half-life), `pattern` (60-day), `procedural` (30-day), `context` (14-day). Scopes: `project` (default), `branch`, `session`, `shared` (federation-eligible). Sources: `human` (0.95 confidence), `agent` (0.6), `inferred` (0.4), `system` (0.9). |
| **save_bulk** | `entries` (list of dicts) | Save up to 50 entries at once. Each entry has `key`, `value`, `tier`, `scope`, `tags`. Returns per-entry saved/skipped/error status. |
| **get** | `key` | Retrieve a single entry by key. For consolidated entries, includes provenance (source entry IDs). |
| **list** | `scope`, `tier`, `tags`, `limit`, `include_sources` | List entries with optional filters. Hides consolidated source entries by default (`include_sources=True` to show all). Max 50 results. |
| **delete** | `key` | Delete a memory entry by key. |

#### Search & retrieval

| Action | Parameters | Description |
|--------|-----------|-------------|
| **search** | `query`, `ranked`, `limit`, `scope`, `tier`, `tags`, `include_sources` | Search memories. Default `ranked=True` uses BM25 composite scoring (40% text relevance + 30% confidence + 15% recency + 15% access frequency). Returns composite scores and stale flags. Max 10 results. |

#### Intelligence & maintenance

| Action | Parameters | Description |
|--------|-----------|-------------|
| **reinforce** | `key`, `boost` | Reset the decay clock on a memory and optionally boost confidence (max +0.2). Use when a memory is confirmed still relevant. |
| **gc** | *(none)* | Run garbage collection. Archives stale memories (confidence at floor for 30+ days, contradicted with low confidence, or expired session entries). |
| **contradictions** | *(none)* | Detect memories that contradict current project state (tech stack changes, deleted files, missing branches). Returns list of contradicted entries with reasons. |
| **reseed** | *(none)* | Re-seed memories from current project profile. Deletes only auto-seeded entries; never overwrites human/agent memories. |

#### Consolidation

| Action | Parameters | Description |
|--------|-----------|-------------|
| **consolidate** | `entry_ids` or `query`, `dry_run` | Merge related memories into a single consolidated entry with provenance tracking. Source entries are marked but kept for audit. Use `dry_run=True` to preview. |
| **unconsolidate** | `key` | Undo a consolidation — restores original source entries and removes the consolidated entry. |

#### Import / export

| Action | Parameters | Description |
|--------|-----------|-------------|
| **import** | `file_path`, `overwrite` | Import memories from a JSON file (up to 500 entries). Use `overwrite=True` to replace existing keys. |
| **export** | `file_path`, `format` | Export memories to JSON or Markdown. Markdown uses Obsidian-style frontmatter with tags, confidence, and tier metadata. |

#### Federation (cross-project sharing)

| Action | Parameters | Description |
|--------|-----------|-------------|
| **federate_register** | `project_id`, `tags` | Register this project in the federation hub (`~/.tapps-mcp/memory/federated.db`). Required before publishing or subscribing. |
| **federate_publish** | *(none)* | Publish all `shared`-scope memories to the federation hub. Only entries with `scope="shared"` are eligible. |
| **federate_subscribe** | `sources`, `tag_filter`, `min_confidence` | Subscribe to memories from other registered projects. Filter by source project IDs, tags, or minimum confidence. |
| **federate_sync** | *(none)* | Pull subscribed memories from the federation hub into this project's local store. |
| **federate_search** | `query` | Search across both local and federated memories. Local results get a relevance boost. |
| **federate_status** | *(none)* | Show federation hub status: registered projects, subscriptions, and entry counts. |

### Memory tiers and when to use them

| Tier | Half-life | Use for | Examples |
|------|-----------|---------|----------|
| **architectural** | 180 days | Stable, long-lived decisions | "We use PostgreSQL", "Monorepo with 3 packages", "Auth via OAuth2" |
| **pattern** | 60 days | Coding conventions and recurring solutions | "Use structlog not print", "All models inherit BaseModel", "Tests use pytest fixtures" |
| **procedural** | 30 days | Workflows, step sequences, how-tos | "Deploy: build → test → push → tag", "Migration: alembic upgrade head" |
| **context** | 14 days | Short-lived session facts | "Refactoring auth module this sprint", "Bug in rate limiter found" |

### Memory scopes

| Scope | Visibility | Use for |
|-------|-----------|---------|
| **project** | All sessions in this project (default) | Most memories — architecture, patterns, decisions |
| **branch** | Only sessions on this git branch | Branch-specific work-in-progress |
| **session** | Current session only (auto-expires after 7 days) | Temporary notes, ephemeral context |
| **shared** | Federation-eligible (cross-project) | Reusable knowledge across projects (e.g., "always use parameterized SQL") |

### Memory configuration (`.tapps-mcp.yaml`)

```yaml
memory:
  enabled: true
  max_memories: 1500           # Hard cap per project (default 1500)
  gc_auto_threshold: 0.8       # Auto-GC at 80% capacity on session start
  capture_prompt: |             # Guide what auto-capture stores
    Store durable memories: architectural (project structure, key decisions),
    pattern (coding conventions, recurring solutions),
    context (session-specific facts that matter next week).
    Skip: raw action logs, transient state, sensitive data.
  write_rules:                  # Block sensitive data from being stored
    block_sensitive_keywords: ["password", "secret", "api_key", "token"]
    min_value_length: 10
    max_value_length: 4096
  decay:
    architectural_half_life_days: 180
    pattern_half_life_days: 60
    procedural_half_life_days: 30
    context_half_life_days: 14
  # Optional: vector search for semantic similarity
  semantic_search:
    enabled: false              # Requires sentence-transformers
  # Optional: cross-encoder reranking (Cohere API cost)
  reranker:
    enabled: false
    provider: noop              # noop | cohere

# Memory hooks — auto-inject/capture
memory_hooks:
  auto_recall:
    enabled: false              # Inject relevant memories before each turn
    min_score: 0.3              # Tune: lower = more coverage, higher = less noise
  auto_capture:
    enabled: false              # Extract facts on session end
    max_facts: 5
```

### Memory hooks

When `memory_hooks.auto_recall.enabled` or `memory_hooks.auto_capture.enabled` in `.tapps-mcp.yaml`, `tapps_init` generates hooks that inject memories before turns or extract facts on session stop.

- **Auto-recall:** Injects relevant memories into context before each turn. Tune `min_score` (default 0.3) to balance coverage vs noise.
- **Auto-capture:** Extracts durable facts from session context on session end. Quality of `capture_prompt` determines what gets stored.
- **Engagement defaults:** high = both enabled, medium = auto_recall only, low = both disabled.

### Federation use case (monorepos / multi-project teams)

For teams working across multiple projects (e.g., monorepo packages, microservices):

1. Register each project: `tapps_memory(action="federate_register", project_id="backend-api", tags=["python", "fastapi"])`
2. Save reusable knowledge with shared scope: `tapps_memory(action="save", key="sql-parameterize", value="Always use parameterized queries", scope="shared")`
3. Publish to hub: `tapps_memory(action="federate_publish")`
4. From another project, subscribe: `tapps_memory(action="federate_subscribe", sources=["backend-api"])`
5. Sync: `tapps_memory(action="federate_sync")`
6. Search across all projects: `tapps_memory(action="federate_search", query="SQL best practices")`

---

## Adaptive domain learning

When `adaptive.enabled: true` is set in `.tapps-mcp.yaml`, TappsMCP learns which expert domains work best for your project:

- **Automatic weight adjustment:** When you use `tapps_feedback` with the `domain` parameter after expert consultations, TappsMCP updates domain routing weights based on whether the advice was helpful.
- **Business domain support:** Both built-in technical domains (security, testing, etc.) and custom business domains defined in `.tapps-mcp/experts.yaml` benefit from adaptive learning.
- **Persistence:** Learned weights are stored in `.tapps-mcp/adaptive/domain_weights.yaml` with separate sections for `technical` and `business` domains.

**Example workflow:**
1. Call `tapps_consult_expert` or `tapps_research` for domain-specific guidance
2. If the advice was helpful, call `tapps_feedback(tool_name="tapps_consult_expert", helpful=True, domain="security")`
3. Over time, frequently-helpful domains get boosted in routing confidence

**To enable adaptive learning:**
```yaml
# .tapps-mcp.yaml
adaptive:
  enabled: true
  learning_rate: 0.1
```

---


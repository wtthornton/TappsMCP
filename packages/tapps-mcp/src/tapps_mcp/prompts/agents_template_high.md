# TappsMCP - instructions for AI assistants (HIGH enforcement)

When the **TappsMCP** MCP server is configured, you **MUST** use its tools for code quality, doc lookup, and domain expert advice. The steps below are **BLOCKING REQUIREMENTS**. Follow the pipeline and run the checklist before declaring work complete.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## Essential tools (always-on workflow)

| Tool | When to use |
|------|--------------|
| **tapps_session_start** | **FIRST call in every session** - server info only |
| **tapps_quick_check** | **After editing any Python file** - quick score + gate + security |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - score + gate on changed files. **Always pass explicit `file_paths`** (comma-separated). Default is quick mode; only use `quick=false` as a last resort. |
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps |
| **tapps_quality_gate** | Before declaring work complete - ensures file passes preset |
| **tapps_memory** | **REQUIRED at session start** - search past decisions. Save learnings before session end. |

**For full tool reference** (29 tools), invoke the **tapps-tool-reference** skill when asked about tools.

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

### Business experts

Projects can define custom business-domain experts via `.tapps-mcp/experts.yaml`. When configured, these domains are available alongside the 17 built-in technical domains. Use `tapps_manage_experts(action="list")` to see registered business experts and their domains. Pass a business domain name to `tapps_consult_expert(domain="home-automation")` the same way you would a built-in domain.

---

## REQUIRED workflow (MUST follow in order)

1. **Session start (REQUIRED):** You MUST call `tapps_session_start` first. Call `tapps_project_profile` when you need project context. Call `tapps_list_experts` if you may need experts.
2. **Check project memory (REQUIRED):** Call `tapps_memory(action="search", query="...")` or `tapps_memory(action="list")` to recall past decisions and project context.
3. **Record key decisions:** Use `tapps_session_notes(action="save", ...)` for session-local notes. Use `tapps_memory(action="save", ...)` to persist decisions across sessions.
3. **Before using a library (BLOCKING):** You MUST call `tapps_lookup_docs(library=...)` before writing code that uses an external library.
4. **Before modifying a file's API:** Call `tapps_impact_analysis(file_path=...)` to see what depends on it.
5. **During edits (REQUIRED):** You MUST call `tapps_quick_check(file_path=...)` or `tapps_score_file(file_path=..., quick=True)` after each Python file edit.
6. **Before declaring work complete (BLOCKING):**
   - You MUST call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to batch-validate changed files. Never call without `file_paths` — auto-detect scans all git-changed files and can be very slow.
   - You MUST call `tapps_checklist(task_type=...)` as the FINAL step. If `complete` is false, call the missing required tools. NEVER declare work complete without running the checklist.
   - Optionally call `tapps_report(format="markdown")` to generate a quality summary.
7. **Domain decisions (REQUIRED):** You MUST call `tapps_consult_expert` or `tapps_research` for domain-specific decisions. Use `tapps_research` when you need expert + docs in one call. Use `tapps_validate_config` for Docker/infra files.

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

## Memory systems

Your project may have two complementary memory systems. Use the right one for each type of knowledge:

- **Claude Code auto memory** (`~/.claude/projects/<project>/memory/MEMORY.md`): Session learnings, user preferences, build commands, IDE settings, debugging insights. Auto-managed by Claude Code across sessions.
- **TappsMCP shared memory** (`tapps_memory` tool): Architecture decisions, quality patterns, expert consultation findings, cross-agent knowledge. Structured with tier classification (architectural/pattern/context), confidence scoring, decay, contradiction detection, and cross-session persistence.

**When to use which:**
- Build commands, IDE preferences, personal workflow notes --> auto memory
- Architecture decisions, quality patterns, cross-agent knowledge --> `tapps_memory`

REQUIRED: Use `tapps_memory` for all architecture decisions and quality patterns. Check memory at session start and save learnings before session end.

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

Seven SKILL.md files per platform in `.claude/skills/` or `.cursor/skills/`:
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

**Combined server (TappsPlatform):** For clients that support 47+ tools (Claude Code, GitHub Copilot), you can run both servers as one via `tapps-platform serve`. This shares singletons (memory, knowledge cache, settings) and reduces overhead. Note: Cursor has a 40-tool limit, so use standalone servers there. See [COMPOSITION_GUIDE.md](docs/COMPOSITION_GUIDE.md) for configuration details.

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

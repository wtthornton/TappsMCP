<!-- tapps-agents-version: 1.3.0 -->
# TappsMCP - Instructions for AI assistants

When the **TappsMCP** MCP server is configured, you have access to 29 tools for **code quality, doc lookup, and domain expert advice**. Use them to avoid hallucinated APIs, missed quality steps, and inconsistent output.

**File paths:** Use paths relative to project root (e.g. `src/main.py`). Absolute host paths also work when `TAPPS_MCP_HOST_PROJECT_ROOT` is set.

---

## Essential tools (always-on workflow)

| Tool | When to use |
|------|------------|
| **tapps_session_start** | **FIRST call in every session** - server info only |
| **tapps_quick_check** | **After editing any supported file** - quick score + gate + security |
| **tapps_validate_changed** | **Before declaring multi-file work complete** - always pass explicit `file_paths` |
| **tapps_checklist** | **Before declaring work complete** - reports missing required steps |
| **tapps_quality_gate** | Before declaring work complete - pass/fail against preset |

## When to use each tool

| Tool | When to use it |
|------|----------------|
| **tapps_score_file** | When editing/reviewing a code file. Use `quick=True` during edit loops. |
| **tapps_lookup_docs** | **Before writing code** that uses an external library - prevents hallucinated APIs |
| **tapps_consult_expert** | Domain-specific decisions (security, testing, APIs, database, etc.) |
| **tapps_research** | Combined expert + docs in one call |
| **tapps_security_scan** | Security-sensitive changes or before security review |
| **tapps_impact_analysis** | Before modifying a file's public API |
| **tapps_validate_config** | When adding/changing Dockerfile, docker-compose, infra config |
| **tapps_project_profile** | When you need project context (tech stack, type, recommendations) |
| **tapps_memory** | Session start: search past decisions. Session end: save learnings. See [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) |
| **tapps_session_notes** | Key decisions during session - promote to memory for persistence |
| **tapps_dead_code** | Find unused code during refactoring |
| **tapps_dependency_scan** | Check for CVEs before releases |
| **tapps_dependency_graph** | Understand module dependencies, circular imports |
| **tapps_report** | Generate quality reports (JSON, Markdown, HTML) |
| **tapps_dashboard** | Metrics dashboard for TappsMCP performance trends |
| **tapps_stats** | Tool usage statistics and call counts |
| **tapps_feedback** | Report tool effectiveness for adaptive learning |
| **tapps_init** | Pipeline bootstrap (once per project) - creates AGENTS.md, rules, hooks |
| **tapps_upgrade** | After TappsMCP version update - refreshes generated files |
| **tapps_doctor** | Diagnose configuration issues |
| **tapps_set_engagement_level** | Change enforcement intensity (high/medium/low) |

## Supported languages

| Language | Extensions | Notes |
|----------|------------|-------|
| **Python** | `.py`, `.pyi` | Full: ruff, mypy, bandit, radon, vulture |
| **TypeScript** | `.ts`, `.tsx` | Tree-sitter AST (regex fallback) |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | Routes to TypeScript scorer |
| **Go** | `.go` | Tree-sitter AST (regex fallback) |
| **Rust** | `.rs` | Tree-sitter AST (regex fallback) |

## Recommended workflow

1. **Session start:** `tapps_session_start` then `tapps_memory(action="search")` to recall context
2. **Before using a library:** `tapps_lookup_docs(library=...)`
3. **Before modifying API:** `tapps_impact_analysis(file_path=...)`
4. **During edits:** `tapps_quick_check(file_path=...)` after each change
5. **Before declaring complete:**
   - `tapps_validate_changed(file_paths="src/foo.py,src/bar.py")` with explicit paths
   - `tapps_checklist(task_type=...)` - fix any missing required tools
6. **When in doubt:** `tapps_consult_expert` for domain questions; `tapps_validate_config` for Docker/infra

## Domain hints for tapps_consult_expert

| Context | domain value |
|---------|--------------|
| Test files, pytest config | `testing-strategies` |
| Security, auth, validation | `security` |
| API routes, FastAPI/Flask | `api-design-integration` |
| Database models, migrations | `database-data-management` |
| Dockerfile, k8s manifests | `cloud-infrastructure` |
| CI/CD, build config | `development-workflow` |
| Code quality, linting | `code-quality-analysis` |
| Architecture decisions | `software-architecture` |
| UX, React, CSS, design systems | `user-experience` |
| Accessibility, WCAG | `accessibility` |

## Checklist task types

- **feature** - New code
- **bugfix** - Fixing a bug
- **refactor** - Refactoring
- **security** - Security-focused change
- **review** - General code review (default)

## Platform automation

`tapps_init` generates hooks, agents, skills, and rules for Claude Code and Cursor. See the generated files in `.claude/` and `.cursor/` directories.

**Subagents:** tapps-reviewer (sonnet), tapps-researcher (haiku), tapps-validator (sonnet), tapps-review-fixer (sonnet + worktree).

**Skills:** tapps-score, tapps-gate, tapps-validate, tapps-review-pipeline, tapps-research, tapps-security, tapps-memory, tapps-tool-reference, tapps-init, tapps-engagement, tapps-report.

## Memory systems

- **Claude Code auto memory** (`~/.claude/projects/.../MEMORY.md`): Session learnings, user preferences, debugging insights
- **TappsMCP shared memory** (`tapps_memory` tool): Architecture decisions, quality patterns, cross-agent knowledge

For the full 20-action reference, see [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md).

## Troubleshooting

**Server not available:** Run `/mcp` (Claude Code) or check Settings > MCP (Cursor). If not listed, run `tapps-mcp upgrade --force --host auto` then restart your IDE.

**Permissions rejected:** Ensure `.claude/settings.json` has `"mcp__tapps-mcp__*"` in `permissions.allow`.

**Doctor timeout:** Use `tapps-mcp doctor --quick` or `tapps_doctor(quick=True)`.

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

---

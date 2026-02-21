# Addenda — Best Practices for Using TappsMCP

This document supplements the main [README.md](README.md) and [AGENTS.md](AGENTS.md) with best practices, tips, and guidance for getting the most out of TappsMCP in your projects.

---

## TappsMCP as a quality toolset for your projects

TappsMCP is designed as a **shared quality infrastructure** that any MCP-capable AI assistant can use. Instead of embedding quality rules in system prompts or relying on the LLM's training data, TappsMCP provides **deterministic, tool-based** quality enforcement that produces consistent results regardless of which model or client you use.

### Who benefits

- **AI coding assistants** (Claude Code, Cursor, VS Code Copilot) — get structured quality feedback instead of guessing
- **Development teams** — enforce consistent quality standards across AI-assisted work
- **Individual developers** — use TappsMCP tools to validate AI-generated code before committing
- **CI/CD pipelines** — integrate quality gates into automated workflows

---

## Best practices for Claude Code

### Initial setup

1. Install TappsMCP: `pip install tapps-mcp` or `uv add tapps-mcp`
2. Run `tapps-mcp init --host claude-code` to generate MCP configuration
3. Optionally run `tapps-mcp init --host claude-code --scope project` for project-level config (`.mcp.json`)
4. For full access without permission prompts, see [docs/CLAUDE_FULL_ACCESS_SETUP.md](docs/CLAUDE_FULL_ACCESS_SETUP.md)

### Session workflow

```
1. tapps_session_start         → Initialize context (server info + project profile)
2. tapps_lookup_docs           → Before using any external library API
3. tapps_quick_check           → After each file edit (fast feedback)
4. tapps_validate_changed      → Before declaring work complete (all changed files)
5. tapps_checklist             → Final check that no required steps were skipped
```

### Tips

- Set `TAPPS_MCP_PROJECT_ROOT` to your project directory for path safety
- Use `.tapps-mcp.yaml` in your project root to configure quality presets
- Call `tapps_init` with `platform="claude"` to create a CLAUDE.md with pipeline rules
- After upgrading TappsMCP, run `tapps_init(overwrite_agents_md=True, overwrite_platform_rules=True)` to refresh templates

---

## Best practices for Cursor

### Initial setup

1. Install TappsMCP: `pip install tapps-mcp` or from source with `uv sync`
2. Add the MCP server to Cursor:
   - **Settings > MCP** or edit `.cursor/mcp.json` in your project
   - Use `--no-sync` with uv to avoid file lock errors:
     ```json
     {
       "mcpServers": {
         "tapps-mcp": {
           "command": "uv",
           "args": ["--directory", "/path/to/tapps-mcp", "run", "--no-sync", "tapps-mcp", "serve"]
         }
       }
     }
     ```
3. Run `tapps-mcp init --host cursor` to auto-generate the config
4. Call `tapps_init(platform="cursor")` to create `.cursor/rules/tapps-pipeline.md`

### Tips

- Use only **one** transport (stdio or HTTP) — not both
- If using Docker, connect via `http://localhost:8000/mcp` (HTTP transport)
- If Cursor shows "Error" for tapps-mcp, check: correct `serve` subcommand, `--no-sync` flag, PATH resolution
- Restart Cursor after config changes

---

## Best practices for consuming projects

### First-time setup

1. Install TappsMCP in your project environment
2. Call `tapps_init` (via AI or script) to bootstrap:
   - Creates `AGENTS.md` with AI workflow guidance
   - Creates `TECH_STACK.md` with detected project profile
   - Optionally warms Context7 cache and expert RAG indices
   - Generates platform rules (CLAUDE.md or .cursor/rules/)

### Upgrading TappsMCP

After `pip install -U tapps-mcp`:

| What to refresh | How |
|-----------------|-----|
| AGENTS.md (workflow) | `tapps_init(overwrite_agents_md=True)` |
| Platform rules | `tapps_init(platform="cursor", overwrite_platform_rules=True)` |
| TECH_STACK.md and caches | `tapps_init()` (default, always refreshes) |
| MCP host config | `tapps-mcp init --force` |

### Quality presets

| Preset | Threshold | Best for |
|--------|-----------|----------|
| `standard` | Overall >= 70 | General development, default |
| `strict` | Overall >= 80, security >= 8, maintainability >= 7 | Production code, security-sensitive |
| `framework` | Overall >= 75, security >= 8.5, maintainability >= 7.5 | Framework/library code |

Configure in `.tapps-mcp.yaml`:

```yaml
quality_preset: standard
```

---

## External tool dependencies

TappsMCP works without these, but produces best results with them installed:

| Tool | Purpose | Install | Without it |
|------|---------|---------|------------|
| **ruff** | Linting + formatting | `pip install ruff` | Limited lint analysis |
| **mypy** | Type checking | `pip install mypy` | No type error detection |
| **bandit** | Security scanning | `pip install bandit` | Heuristic-only security scoring |
| **radon** | Complexity metrics | `pip install radon` | AST-based complexity fallback |

Install all at once: `pip install ruff mypy bandit radon`

For semantic expert search (optional): `pip install tapps-mcp[rag]`

---

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `TAPPS_MCP_PROJECT_ROOT` | Restrict file operations to this directory | Current working directory |
| `TAPPS_MCP_HOST_PROJECT_ROOT` | Host path mapping for Docker/remote setups | Not set |
| `TAPPS_MCP_CONTEXT7_API_KEY` | Enable live Context7 documentation lookups | Not set (cache-only) |
| `TAPPS_MCP_QUALITY_PRESET` | Override quality preset | `standard` |
| `TAPPS_MCP_LOG_LEVEL` | Logging verbosity | `INFO` |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| All tools fail with `No module named 'tapps_mcp.tools.checklist'` | Install via pip/uv (not standalone binary): `pip install tapps-mcp` |
| Path denied errors | Set `TAPPS_MCP_PROJECT_ROOT` to the project directory |
| `tapps_lookup_docs` returns empty | Set `TAPPS_MCP_CONTEXT7_API_KEY` for live API fetches; cache works without it |
| Cursor shows "Error" for tapps-mcp | Ensure args end with `serve`, add `--no-sync` if using uv |
| Scoring shows `degraded: true` | Install missing checkers: `pip install ruff mypy bandit radon` |
| Docker: host paths rejected | Set `TAPPS_MCP_HOST_PROJECT_ROOT` to the host path the IDE uses |

---

## Further reading

- [README.md](README.md) — Full project documentation and tool reference
- [AGENTS.md](AGENTS.md) — AI assistant workflow guide
- [CLAUDE.md](CLAUDE.md) — Instructions for working on TappsMCP itself
- [docs/TAPPS_MCP_SETUP_AND_USE.md](docs/TAPPS_MCP_SETUP_AND_USE.md) — Detailed setup guide
- [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) — Docker deployment guide
- [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md) — Upgrade guide for consuming projects
- [docs/ARCHITECTURE_CACHE_AND_RAG.md](docs/ARCHITECTURE_CACHE_AND_RAG.md) — Cache and RAG architecture
- [CHANGELOG.md](CHANGELOG.md) — Release history

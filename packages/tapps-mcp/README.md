# tapps-mcp

<!-- mcp-name: io.github.wtthornton/tapps-mcp -->

MCP server providing deterministic code-quality tools for AI coding assistants. Scores Python (full) plus TypeScript / JavaScript / Go / Rust files across seven categories, runs security scans, enforces quality gates, looks up library docs, validates configs, and persists cross-session knowledge through [tapps-brain](https://github.com/wtthornton/tapps-brain). All tools are deterministic — same input, same output — so they slot cleanly into agent loops without LLM-in-the-loop variance.

Part of the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP). Pairs with [docs-mcp](../docs-mcp) (documentation tooling) and [tapps-core](../tapps-core) (shared infrastructure).

## Installation

tapps-mcp is **not published to PyPI** — it installs from this checkout. Clone the workspace and install the CLI globally with uv:

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv sync --all-packages
uv tool install -e packages/tapps-mcp
```

Upgrade later with `git pull && uv tool install --reinstall packages/tapps-mcp`.

## Quick start

```bash
tapps-mcp serve                         # stdio transport (default)
tapps-mcp serve --transport http --port 8000
tapps-mcp doctor                        # diagnose config + memory
tapps-mcp init                          # bootstrap in a consuming project
```

Wire it into Claude Code via `.mcp.json`:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uv",
      "args": ["run", "tapps-mcp", "serve"],
      "env": { "TAPPS_MCP_PROJECT_ROOT": "." }
    }
  }
}
```

## Top 5 MCP tools

The most-used handlers in a typical agent session — see [AGENTS.md](../../AGENTS.md) for the full 26-tool reference.

1. `tapps_session_start` — initialise project context, load memory, surface server info.
2. `tapps_quick_check(file_path)` — score + quality gate + security scan in one call after every Python edit.
3. `tapps_validate_changed(file_paths=...)` — batch validate before declaring work complete.
4. `tapps_lookup_docs(library, topic)` — fetch authoritative library docs to prevent hallucinated APIs.
5. `tapps_checklist(task_type)` — final-step audit that nothing required was skipped.

## Linear enforcement gates

Two opt-in PreToolUse hook pairs steer Linear traffic through structured tool flows (default on at `medium` / `high` engagement):

- `linear_enforce_gate` (TAP-981) — blocks raw `mcp__plugin_linear_linear__save_issue` without a recent `docs_validate_linear_issue`. Bypass: `TAPPS_LINEAR_SKIP_VALIDATE=1`.
- `linear_enforce_cache_gate` (TAP-1224) — gates `mcp__plugin_linear_linear__list_issues` behind a recent `tapps_linear_snapshot_get` for the same `(team, project, state, label, limit)` slice. Modes: `off`, `warn` (default at `medium` / `high`; logs violations to `.tapps-mcp/.cache-gate-violations.jsonl` and allows), `block` (rejects). Single-issue lookups must use `mcp__plugin_linear_linear__get_issue`. Bypass: `TAPPS_LINEAR_SKIP_CACHE_GATE=1`.

`tapps doctor` reports current mode + 24-hour violation count for both gates.

## Entry points

- `packages/tapps-mcp/src/tapps_mcp/__main__.py` and `cli.py` — CLI shipped as `tapps-mcp`.
- `packages/tapps-mcp/src/tapps_mcp/platform/cli.py` — CLI shipped as `tapps-platform`.
- `packages/tapps-mcp/src/tapps_mcp/server.py` — FastMCP server registration.

## Documentation

- [AGENTS.md](../../AGENTS.md) — AI assistant integration guide and full tool reference.
- [CLAUDE.md](../../CLAUDE.md) — repo conventions, dev commands, known gotchas.
- [docs/](../../docs) — architecture, config reference, troubleshooting.
- Issues: [github.com/wtthornton/TappsMCP/issues](https://github.com/wtthornton/TappsMCP/issues) (Linear project: TappsMCP Platform).

## License

MIT.

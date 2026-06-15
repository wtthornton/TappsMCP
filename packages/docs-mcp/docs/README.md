# docs-mcp

MCP server for **deterministic** documentation generation, validation, and maintenance. Part of the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP). Pairs with [tapps-mcp](../../tapps-mcp) (code quality) and [tapps-core](../../tapps-core) (shared infrastructure).

**38 MCP tools** — AST/git analysis, generators (`docs_generate_*`), validators (`docs_check_*`), Linear issue lint, and optional brain knowledge-graph queries. Same input → same output; no LLM calls in the tool chain.

## Installation

docs-mcp is **not published to PyPI**. Install from this monorepo checkout:

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv sync --all-packages
uv tool install -e packages/docs-mcp
```

Upgrade later with `git pull && uv tool install --reinstall packages/docs-mcp`.

## Quick start

```bash
docsmcp serve                          # stdio transport (default)
docsmcp serve --transport http --port 8000
docsmcp doctor                         # config + dependency check
docsmcp scan                           # documentation inventory
```

### NLT MCP profile

In consuming projects, DocsMCP ships as **`nlt-project-docs`** (~27 eager tools in the project-docs profile). Enable it alongside `nlt-build` when refreshing documentation — see [ADR-0016](../../../docs/adr/0016-needs-based-nlt-mcp-taxonomy.md) and [tutorial 05](../../../docs/tutorials/05-docs-refresh-workflow.md).

## Top tools

| Tool | When to use |
|------|-------------|
| `docs_session_start` | First call each session — inventory + recommendations |
| `docs_project_scan` | Completeness audit with gap list |
| `docs_check_drift` | Code changes not yet reflected in docs |
| `docs_generate_api` | Regenerate API reference from source |
| `docs_check_style` | Passive voice, headings, sentence length on markdown |

Full reference: [AGENTS.md](../AGENTS.md) (package) and [docs/INDEX.md](../../../docs/INDEX.md) (workspace).

## Development

From the **repo root** (uv workspace):

```bash
uv sync --all-packages --group dev
uv run pytest packages/docs-mcp/tests/ -m "not slow" -v
uv run mypy --strict packages/docs-mcp/src/docs_mcp/
uv run ruff check packages/docs-mcp/src/
```

## Documentation

- [AGENTS.md](../AGENTS.md) — tool inventory and recommended workflows
- [CLAUDE.md](../CLAUDE.md) — package layout, conventions, adding tools
- [docs/tutorials/05-docs-refresh-workflow.md](../../../docs/tutorials/05-docs-refresh-workflow.md) — consumer doc refresh runbook

## License

MIT.

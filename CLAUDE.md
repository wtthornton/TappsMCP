# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is TappsMCP?

TappsMCP is an **MCP server** providing deterministic code quality tools to LLMs and AI coding assistants. It scores Python files, runs security scans, enforces quality gates, looks up library docs, validates configs, and consults domain experts — all via structured MCP tool calls. Any MCP-capable client (Claude Code, Cursor, VS Code Copilot) can use it. If you are a consuming project, see [AGENTS.md](AGENTS.md) instead.

## Repository structure

This is a **uv workspace monorepo** with three packages:

| Package | Path | Purpose |
|---|---|---|
| **tapps-core** | `packages/tapps-core/` | Shared infrastructure library (config, security, logging, knowledge, memory, experts, metrics, adaptive) |
| **tapps-mcp** | `packages/tapps-mcp/` | Code quality MCP server (28 tools, 31 actions) |
| **docs-mcp** | `packages/docs-mcp/` | Documentation MCP server (3 tools, MVP) |

tapps-mcp re-exports from tapps-core for backward compatibility (`from tapps_mcp.config import load_settings` still works).

## Development commands

```bash
# Install all packages
uv sync --all-packages

# Run all tests (4500+ tests)
uv run pytest packages/tapps-core/tests/ packages/tapps-mcp/tests/ packages/docs-mcp/tests/ -v

# Run tests for a single package
uv run pytest packages/tapps-core/tests/ -v      # 1225 tests
uv run pytest packages/tapps-mcp/tests/ -v        # 3224 tests
uv run pytest packages/docs-mcp/tests/ -v         # 107 tests

# Run a single test file
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v

# Run a single test by name
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -k "test_score_empty_file" -v

# Run with coverage (80% minimum, fail_under enforced)
uv run pytest packages/tapps-mcp/tests/ --cov=tapps_mcp --cov-report=term-missing

# Skip slow subprocess-heavy tests
uv run pytest packages/tapps-mcp/tests/ -m "not slow" -v

# Type checking (strict mode)
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/
uv run mypy --strict packages/tapps-core/src/tapps_core/

# Linting and formatting
uv run ruff check packages/*/src/
uv run ruff format --check packages/*/src/

# Run the MCP servers (stdio)
uv run tapps-mcp serve           # TappsMCP (code quality)
uv run docsmcp serve             # DocsMCP (documentation)

# CLI utilities
uv run tapps-mcp doctor           # diagnose config issues
uv run tapps-mcp upgrade --dry-run  # preview generated file updates
uv run tapps-mcp build-plugin      # generate Claude Code plugin directory
uv run tapps-mcp rollback --list   # list available upgrade backups
uv run docsmcp doctor             # DocsMCP diagnostics
```

## Architecture

### Package dependency graph

```
tapps-core (library)  <──  tapps-mcp (28 tools)
                      <──  docs-mcp  (3 tools)
```

Shared infrastructure (config, security, logging, knowledge, memory, experts, metrics, adaptive) lives in `tapps-core`. Both MCP servers depend on it. Server files in tapps-mcp import from `tapps_core` directly for extracted packages.

### Server module split (tapps-mcp)

The MCP server is split across seven tool files plus a shared helpers module. All share the same `mcp` FastMCP instance created in `server.py`:

- **`server.py`** — Creates the `FastMCP("TappsMCP")` instance, registers MCP resources/prompts, and 8 tools (`tapps_server_info`, `tapps_security_scan`, `tapps_lookup_docs`, `tapps_validate_config`, `tapps_consult_expert`, `tapps_list_experts`, `tapps_checklist`, `tapps_project_profile`). Imports the other six modules which register their tools on the shared `mcp` object.
- **`server_scoring_tools.py`** — `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`
- **`server_pipeline_tools.py`** — `tapps_validate_changed`, `tapps_session_start`, `tapps_init`, `tapps_set_engagement_level`, `tapps_upgrade`, `tapps_doctor`
- **`server_metrics_tools.py`** — `tapps_dashboard`, `tapps_stats`, `tapps_feedback`, `tapps_research`
- **`server_memory_tools.py`** — `tapps_memory` (save, get, list, delete, search, reinforce, gc, contradictions, reseed, import, export actions)
- **`server_analysis_tools.py`** — `tapps_session_notes`, `tapps_impact_analysis`, `tapps_report`, `tapps_dead_code`, `tapps_dependency_scan`, `tapps_dependency_graph`
- **`server_helpers.py`** — Shared utilities: response builders, singleton caches (`_get_scorer()`, `_get_settings()`, `_get_memory_store()`)

### Tool registration flow

To add a new MCP tool:
1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top of the handler (for checklist tracking)
3. Register the tool in the checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md tools reference
5. Add tests in `packages/tapps-mcp/tests/unit/` and optionally `tests/integration/`

### Dual CLI / MCP tool pattern

Several features exist as both a CLI command (`cli.py` via Click) and an MCP tool. The CLI entry points delegate to shared logic:
- `tapps-mcp init` (CLI) → `pipeline/init.py` ← `tapps_init` (MCP tool in `server_pipeline_tools.py`)
- `tapps-mcp upgrade` (CLI) → `distribution/setup_generator.py` / `pipeline/upgrade.py` ← `tapps_upgrade` (MCP tool)
- `tapps-mcp doctor` (CLI) → `distribution/doctor.py` ← `tapps_doctor` (MCP tool)
- `tapps-mcp build-plugin` (CLI-only) → `distribution/plugin_builder.py` — generates a Claude Code plugin directory
- `tapps-mcp rollback` (CLI-only) → `distribution/rollback.py` — restores from pre-upgrade backups

### Engagement-level template variants (Epic 18)

AGENTS.md and platform rules (Cursor/Claude) have three variants per engagement level: **high**, **medium**, **low**. Templates live under `packages/tapps-mcp/src/tapps_mcp/prompts/` as `agents_template_high.md`, `agents_template_medium.md`, `agents_template_low.md`, and `platform_{cursor|claude}_{high|medium|low}.md`. The loader selects by `load_settings().llm_engagement_level` (or the `engagement_level` argument when provided). Checklist `TASK_TOOL_MAP_HIGH` / `TASK_TOOL_MAP_MEDIUM` / `TASK_TOOL_MAP_LOW` vary required vs recommended tools by level.

### Caching and singletons

Four module-level caches require reset in tests (done by autouse fixture in `packages/tapps-mcp/tests/conftest.py`):
- **Settings**: `load_settings()` in `config/settings.py` — cached singleton, reset via `_reset_settings_cache()`
- **CodeScorer**: `_get_scorer()` in `server_helpers.py` — cached singleton, reset via `_reset_scorer_cache()`
- **MemoryStore**: `_get_memory_store()` in `server_helpers.py` — cached singleton, reset via `_reset_memory_store_cache()`
- **Tool detection**: `detect_installed_tools()` in `tools/tool_detection.py` — reset via `_reset_tools_cache()`

The **knowledge cache** (`KBCache` in `tapps_core/knowledge/cache.py`) supports LRU eviction: when total disk size exceeds `cache_max_mb` (default 100 MB), least-recently-accessed entries are evicted. Access timestamps are tracked in `_metadata.json`. Call `evict_lru()` directly or rely on automatic eviction after `put()`.

### Scoring pipeline

`scoring/scorer.py` orchestrates the 7-category scoring engine. In full mode, `tools/parallel.py` runs ruff, mypy, bandit, and radon concurrently via `asyncio.gather`. Quick mode runs ruff only. When external tools are missing, AST-based fallbacks in `scoring/scorer.py` produce degraded results. The `tools/` directory has one module per external checker (ruff, mypy, bandit, radon, vulture, pip-audit) plus `ruff_direct.py` and `radon_direct.py` for library-mode execution.

### Security model

All file I/O goes through `security/path_validator.py`, which sandboxes operations to `TAPPS_MCP_PROJECT_ROOT`. The `security/` package also handles secret scanning, IO guardrails, governance checks, and content safety (`security/content_safety.py` — prompt injection filtering for all retrieved documentation and memory content).

### Expert system

17 domain experts in `experts/` with 139 curated knowledge markdown files under `experts/knowledge/`. The `experts/engine.py` uses keyword-based RAG (or optional vector RAG with faiss), with core logic split into helpers (`_detect_domain`, `_retrieve_knowledge`, `_format_consultation_response`, `_apply_freshness_warnings`). When `adaptive.enabled` is True, the `AdaptiveDomainDetector` routes queries based on learned feedback outcomes (with 0.4 confidence threshold), falling back to the static `DomainDetector`. Query expansion via `experts/query_expansion.py` (~60 synonym pairs) improves domain detection recall. Knowledge freshness warnings are included when retrieved chunks are >365 days old. All retrieved content passes through `security/content_safety.py` for prompt injection filtering (formerly in `knowledge/rag_safety.py`, which now delegates to the security module).

### Memory subsystem

`memory/` provides persistent cross-session knowledge sharing via `tapps_memory`. Core: `memory/models.py` (MemoryEntry, enums, validators), `memory/persistence.py` (SQLite with WAL, FTS5, schema versioning, JSONL audit), `memory/store.py` (in-memory cache, write-through, RAG safety, eviction). Intelligence (Epic 24): `memory/decay.py` (time-based confidence decay), `memory/reinforcement.py` (access-based boosting), `memory/contradictions.py` (conflict detection), `memory/gc.py` (garbage collection). Retrieval (Epic 25+34): `memory/retrieval.py` (BM25-scored ranked retrieval with stemming and stop-word filtering), `memory/bm25.py` (pure Python BM25 scoring engine), `memory/injection.py` (context injection), `memory/seeding.py` (initial population), `memory/io.py` (import/export). `server_memory_tools.py` exposes the `tapps_memory` MCP tool with 11 actions including `reinforce` (reset decay, boost confidence) and `gc` (archive decayed memories). Auto-GC triggers in `tapps_session_start` when memory exceeds 80% capacity (`gc_auto_threshold` setting). Storage lives at `{project_root}/.tapps-mcp/memory/`.

### Platform generation

Platform artifact generation is split across modules in `pipeline/`: `platform_generators.py` (facade re-exporting from split modules), `platform_hooks.py` (Claude Code hook generation), `platform_rules.py` (Cursor rules, Copilot instructions, BugBot config), `platform_skills.py` (Claude Code skills with 2026 `allowed-tools:` spec), `platform_subagents.py` (Claude Code subagents with `mcpServers`, `maxTurns`, role-appropriate `permissionMode`), `platform_bundles.py` (bundled generation including path-scoped quality rules), `platform_hook_templates.py` (hook script templates including memory capture Stop hooks). `pipeline/agents_md.py` handles AGENTS.md smart-merge (preserving custom sections while updating tool definitions). `pipeline/init.py` also generates `.claude/settings.json` permission rules (`mcp__tapps-mcp__*` auto-approval). When MCP elicitation is supported and no existing config is present, `tapps_init` runs an interactive 5-question wizard (`common/elicitation.py`) that collects quality preset, engagement level, agent teams, skill tier, and prompt hooks preferences before generating files.

### Distribution and packaging

`distribution/plugin_builder.py` provides the `PluginBuilder` class for generating Claude Code marketplace plugin directories (manifest, namespaced skills, agents, hooks.json, MCP config, rules, settings). `distribution/rollback.py` provides `BackupManager` for creating timestamped backups before upgrades (stored in `.tapps-mcp/backups/{timestamp}/` with `manifest.json`), listing backups, restoring from any backup, and auto-cleaning old backups (keeping the 5 most recent). `tapps_upgrade` automatically creates a backup before overwriting files.

### Quality gate evaluation

`gates/evaluator.py` checks 6 category scores + overall against thresholds. Failures are sorted by scoring weight (security 0.27 > maintainability 0.24 > complexity 0.18 > test coverage 0.13 > performance 0.08 > structure/devex 0.05). A security floor of 50 enforces that files with critical security issues always fail the gate regardless of overall score.

## Code conventions

- **Python 3.12+** — `from __future__ import annotations` at the top of every file
- **Type annotations everywhere** — `mypy --strict` must pass
- **`structlog`** for logging — never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers and external I/O
- All file operations through the path validator (`security/path_validator.py`)

## Known gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server` specifically.
- **mypy + optional deps**: `ignore_missing_imports = true` covers mcp, faiss, numpy, sentence_transformers, radon. Don't add redundant `# type: ignore[import-untyped]` — mypy won't flag those, and the comments become "unused-ignore" errors.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs in field types must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001` to suppress ruff.
- **`structlog.get_logger()`**: Returns `Any` — use `# type: ignore[no-any-return]` in the wrapper.
- **Ruff RUF012**: Mutable class-level attributes need `ClassVar` annotation.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests — Git Bash intercepts `cmd /c timeout`.
- **Patching lazy imports in server.py**: Some imports (e.g., `KBCache`, `LookupEngine`) happen inside tool handlers and now come from `tapps_core`. Patch them at their source modules (e.g., `tapps_core.knowledge.lookup.LookupEngine`), not at `tapps_mcp.server` or the re-export wrappers.

## Self-hosted quality pipeline

When TappsMCP's own MCP server is available in your session, use it on this codebase:

1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` or appropriate type before finishing

## Important context

- TappsMCP is a **tool for other projects** — changes should consider how consuming projects will be affected
- The `tapps_init` MCP tool bootstraps TappsMCP in consuming projects (creates AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills)
- All tools are **deterministic** — no LLM calls in the tool chain; same input produces same output
- When external checkers are missing, tools fall back to AST-based analysis and mark results as `degraded: true`

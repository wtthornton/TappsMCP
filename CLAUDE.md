# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What is TappsMCP?

TappsMCP is an **MCP server** providing deterministic code quality tools to LLMs and AI coding assistants. It scores Python files, runs security scans, enforces quality gates, looks up library docs, and validates configs -- all via structured MCP tool calls (26 tools). Any MCP-capable client (Claude Code, Cursor, VS Code Copilot) can use it. If you are a consuming project, see [AGENTS.md](AGENTS.md) instead.

## Repository structure

This is a **uv workspace monorepo** with three packages plus an external dependency:

| Package | Path | Purpose |
|---|---|---|
| **tapps-brain** | [github.com/wtthornton/tapps-brain](https://github.com/wtthornton/tapps-brain) | Shared memory service (Docker + Postgres, HTTP at `localhost:8080`). Accessed from tapps-mcp via `BrainBridge` and exposed through `tapps_memory`. See the [tapps-brain repo](https://github.com/wtthornton/tapps-brain) for storage internals, retrieval, and operational docs — treat that as the source of truth. |
| **tapps-core** | `packages/tapps-core/` | Shared infrastructure library (config, security, logging, knowledge, metrics, adaptive) |
| **tapps-mcp** | `packages/tapps-mcp/` | Code quality MCP server (26 tools) |
| **docs-mcp** | `packages/docs-mcp/` | Documentation MCP server (32 tools) |

tapps-core's `memory/` modules are re-export shims delegating to tapps-brain (except `injection.py` which is a bridge adapter). tapps-mcp re-exports from tapps-core for backward compatibility (`from tapps_mcp.config import load_settings` still works).

For detailed module maps and internal architecture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development commands

```bash
# Install all packages
uv sync --all-packages

# Run tests per package (recommended -- avoids conftest collisions)
uv run pytest packages/tapps-core/tests/ -v      # 960+ tests
uv run pytest packages/tapps-mcp/tests/ -v        # 3,790+ tests
uv run pytest packages/docs-mcp/tests/ -v         # 2,170+ tests

# Run tests excluding slow integration tests (fast local feedback)
uv run pytest packages/tapps-core/tests/ -m "not slow" -v
uv run pytest packages/tapps-mcp/tests/ -m "not slow" -v

# Run a single test file or by name
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -v
uv run pytest packages/tapps-mcp/tests/unit/test_scorer.py -k "test_score_empty_file" -v

# Coverage (80% minimum, fail_under enforced)
uv run pytest packages/tapps-mcp/tests/ --cov=tapps_mcp --cov-report=term-missing

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
uv run docsmcp doctor             # DocsMCP diagnostics

# Benchmark subsystem
uv run tapps-mcp benchmark run|analyze|report
uv run tapps-mcp template optimize|ablate|compare|history
uv run tapps-mcp benchmark tools report|rank|calibrate
```

## Common workflows

### Adding a new MCP tool
1. Add handler in appropriate `server_*.py` using `@mcp.tool()`
2. Call `_record_call("tool_name")` at top of handler
3. Register in checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md
5. Add tests in `packages/tapps-mcp/tests/unit/`

### Running the quality pipeline on this codebase
1. Call `tapps_session_start` first
2. Use `tapps_quick_check` after editing Python files
3. Use `tapps_validate_changed` before declaring work complete
4. Call `tapps_checklist(task_type="feature")` before finishing

## Code conventions

- **Python 3.12+** -- `from __future__ import annotations` at top of every file
- **Type annotations everywhere** -- `mypy --strict` must pass
- **`structlog`** for logging -- never `print()` or `logging` directly
- **`pathlib.Path`** for all file paths
- **Pydantic v2** models for configuration and data structures
- **`ruff`** for linting and formatting (line length: 100)
- **Async/await** for all tool handlers and external I/O
- All file operations through the path validator (`security/path_validator.py`)

## Known gotchas

- **mypy + `@mcp.tool()`**: The mcp SDK decorator is untyped. `pyproject.toml` has `disallow_untyped_decorators = false` for `tapps_mcp.server`.
- **mypy + optional deps**: `ignore_missing_imports = true` covers mcp, radon. Don't add redundant `# type: ignore[import-untyped]`.
- **Pydantic + `TYPE_CHECKING`**: Models using forward refs in field types must import at runtime, not under `TYPE_CHECKING`. Use `# noqa: TC001`.
- **`structlog.get_logger()`**: Returns `Any` -- use `# type: ignore[no-any-return]` in wrapper.
- **Ruff RUF012**: Mutable class-level attributes need `ClassVar` annotation.
- **Windows testing**: Use `python -c "import time; time.sleep(N)"` for timeout tests -- Git Bash intercepts `cmd /c timeout`.
- **Patching lazy imports**: Some imports happen inside tool handlers from `tapps_core`. Patch at source modules, not `tapps_mcp.server`.
- **tapps-brain version**: TappsMCP pins tapps-brain at [`>=3.7.2,<4`](https://github.com/wtthornton/tapps-brain/releases/tag/v3.7.2) in `packages/tapps-core/pyproject.toml`. 3.7.2 fixes the `TappsBrainClient` `/mcp` → `/mcp/mcp` path and the 3.7.1 streamable-HTTP lifespan crash — not load-bearing for tapps-mcp (in-process `AgentBrain` via `BrainBridge`, not the network client), but the floor is bumped so any future migration to remote brain-as-a-service gets a working client. Imports still use `try/except ImportError` for defensive degradation in non-standard installs.
- **MCP server zombies**: Claude Code spawns a new MCP server process per session but never cleans up old ones. The `.claude/hooks/tapps-session-start.sh` hook kills tapps-mcp/docsmcp processes older than 2 hours at startup. Do not remove this cleanup block.

## Important context

- TappsMCP is a **tool for other projects** -- changes should consider how consuming projects will be affected
- The `tapps_init` MCP tool bootstraps TappsMCP in consuming projects (creates AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills)
- All tools are **deterministic** -- no LLM calls in the tool chain; same input produces same output
- When external checkers are missing, tools fall back to AST-based analysis and mark results as `degraded: true`

# TAPPS Quality Pipeline

This project uses the TAPPS MCP server for code quality enforcement.
Every tool response includes `next_steps` - consider following them.
Full pipeline details are in `.claude/rules/tapps-pipeline.md` (auto-loaded for Python and infra files).

## Recommended Tool Call Obligations

You should follow these steps to avoid broken, insecure, or hallucinated code.

### Session Start

You should call `tapps_session_start()` as the first action in every session.
This returns server info (version, checkers, config) and project context.

### Before Using Any Library API

You should call `tapps_lookup_docs(library, topic)` before writing code that uses an external library.
This prevents hallucinated APIs. Prefer looking up docs over guessing from memory.

### After Editing Any Python File

You should call `tapps_quick_check(file_path)` after editing any Python file.
This runs scoring + quality gate + security scan in a single call.

### Before Declaring Work Complete

For multi-file changes: You should call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to batch-validate changed files. **Always pass `file_paths`** — auto-detect scans all git-changed files and can be very slow. Default is quick mode; only use `quick=false` as a last resort (pre-release, security audit).
Run the quality gate before considering work done.
You should call `tapps_checklist(task_type)` as the final step to verify no required tools were skipped.

### Domain Decisions

You should call `tapps_lookup_docs(library, topic)` when you need domain-specific guidance
(security patterns, testing strategy, API design, database best practices, etc.).

### Refactoring or Deleting Files

You should call `tapps_impact_analysis(file_path)` before refactoring or deleting any file.
This maps the blast radius via import graph analysis.

### Infrastructure Config Changes

You should call `tapps_validate_config(file_path)` when changing Dockerfile, docker-compose, or infra config.

## Memory System

`tapps_memory` provides persistent cross-session knowledge with **33 actions** (save, search, consolidate, federation, profiles, hive, health, and more). **Tiers:** architectural (180d), pattern (60d), procedural (30d), context (14d). **Scopes:** project, branch, session, shared. Max 5000 entries per project (`TAPPS_BRAIN_MAX_ENTRIES`; auto-evicts at cap, no warning — monitor via `brain_status()`). Configure `memory_hooks` in `.tapps-mcp.yaml` for auto-recall and auto-capture.

## Quality Gate Behavior

Gate failures are sorted by category weight (highest-impact first).
A security floor of 50/100 is enforced regardless of overall score.

## Upgrade & Rollback

After upgrading TappsMCP, run `tapps_upgrade` to refresh generated files.
A timestamped backup is created before overwriting. Use `tapps-mcp rollback` to restore.
To protect customized files from upgrade, add them to `upgrade_skip_files` in `.tapps-mcp.yaml`.

<!-- BEGIN: karpathy-guidelines c9a44ae (MIT, forrestchang/andrej-karpathy-skills) -->
<!--
  Vendored from https://github.com/forrestchang/andrej-karpathy-skills
  Pinned commit: c9a44ae835fa2f5765a697216692705761a53f40 (2026-04-15)
  License: MIT (c) forrestchang
  Do not edit by hand — update KARPATHY_GUIDELINES_SOURCE_SHA in prompt_loader.py
  and re-run the vendor script, then bump tapps-mcp version.
-->
## Karpathy Behavioral Guidelines

> Source: https://github.com/forrestchang/andrej-karpathy-skills @ c9a44ae835fa2f5765a697216692705761a53f40 (MIT)
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

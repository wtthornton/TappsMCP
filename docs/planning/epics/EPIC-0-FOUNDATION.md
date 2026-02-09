# Epic 0: Foundation & Security Hardening

**Status:** Complete
**Priority:** P0 — Critical Path (all other epics depend on this)
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** None (first epic)
**Blocks:** Epic 1, Epic 2, Epic 3, Epic 4, Epic 5, Epic 6

---

## Goal

Stand up the `tapps-mcp` package skeleton with a working MCP server, security layer, and dependency analysis. By the end of this epic, `tapps-mcp serve` starts a real MCP server that Claude Code can connect to, with `tapps_server_info` as the only tool.

## 2026 Best Practices Applied

- **MCP Protocol 2025-11-25**: Target the latest stable MCP spec (version `2025-11-25`). Use **Streamable HTTP** transport for remote deployments (SSE is deprecated), **stdio** for local dev (Claude Code, Cursor). MCP Python SDK v1.26.0+.
- **FastMCP decorator pattern**: Use `FastMCP` (high-level API) with `@mcp.tool()` decorators for tool registration. Type annotations auto-generate JSON schemas, docstrings become tool descriptions. Both sync and async handlers supported.
- **Python 3.12+ only**: Use modern Python — `type` statement, `match/case`, `tomllib` stdlib, improved error messages. SDK supports 3.10+ but we target 3.12+ for modern features.
- **`pyproject.toml` only**: No `setup.py`, no `setup.cfg`. PEP 621 metadata, PEP 660 editable installs.
- **`uv` as package manager**: Faster than pip/poetry, lockfile support via `uv.lock`, workspace-aware. Install MCP SDK via `uv add "mcp[cli]"`.
- **Ruff for linting AND formatting**: Single tool replaces black + isort + flake8 + pyflakes. Use `ruff check` + `ruff format`.
- **Strict type checking from day one**: `mypy --strict` or `pyright` in strict mode. Catch type errors before they become runtime bugs.
- **Structured logging with `structlog`**: JSON-structured logs from the start. No `print()` debugging, no unstructured `logging.info()` strings.
- **Pydantic v2 for all config/models**: Settings via `pydantic-settings`, config models via `BaseModel`. Env var + YAML + defaults with clear precedence.
- **MCP Resources & Prompts**: Evaluate exposing knowledge files as MCP resources (`tapps://knowledge/{domain}/{topic}`) and the system prompt as an MCP prompt template — these can eliminate manual system prompt configuration.

## Acceptance Criteria

- [ ] `tapps-mcp serve` starts an MCP server on stdio transport
- [ ] Claude Code connects and discovers `tapps_server_info` tool
- [ ] `tapps_server_info` returns version, protocol version, available tools, installed checkers
- [ ] All file path inputs are validated against `TAPPS_MCP_PROJECT_ROOT` boundary
- [ ] Dependency analysis report exists documenting transitive imports for all "standalone" modules
- [ ] `tapps_mcp/common/` contains shared utilities identified by dependency analysis
- [ ] Security modules extracted and unit tested: path validator, IO guardrails, RAG safety, governance
- [ ] Windows subprocess shim (`wrap_windows_cmd_shim`) extracted and tested
- [ ] YAML + env var configuration loads with correct precedence
- [ ] CI runs on Windows + Linux + macOS

---

## Stories

### 0.1 — Project Scaffolding

**Points:** 2

Create the `tapps-mcp` package with modern Python tooling.

**Tasks:**
- Create `pyproject.toml` with PEP 621 metadata, `[project.scripts]` entry for `tapps-mcp` CLI
- Set up `src/tapps_mcp/` layout (src-layout for proper packaging)
- Configure `ruff` (linting + formatting), `mypy` (strict), `pytest` with coverage
- Add `uv.lock` for reproducible installs
- Set up pre-commit hooks: ruff check, ruff format, mypy
- Create GitHub Actions CI: test matrix (Windows/Linux/macOS, Python 3.12/3.13)

**Definition of Done:** `uv run pytest` passes, `ruff check .` clean, `mypy --strict src/` clean.

---

### 0.2 — Dependency Graph Analysis

**Points:** 3

Run import graph analysis on all modules marked "standalone" or "copy directly" in the extraction map. Identify hidden transitive imports.

**Tasks:**
- Use `pydeps`, `import-linter`, or custom AST walker to map imports for every module in the extraction map
- Identify transitive dependencies on framework utilities (`core/exceptions.py`, `core/config.py`, logging helpers)
- Create `tapps_mcp/common/` package with extracted shared utilities:
  - `exceptions.py` — exception hierarchy
  - `logging.py` — structured logging setup (structlog)
  - `models.py` — shared Pydantic v2 models
- Produce a dependency analysis report (`docs/planning/DEPENDENCY_ANALYSIS.md`)
- Revise the extraction map with findings — annotate which "standalone" modules actually have hidden coupling

**Definition of Done:** Report published, `common/` package created, extraction map updated with findings.

---

### 0.3 — Adapt Tool Registry for MCP Wire Protocol

**Points:** 3

Adapt the existing `mcp/tool_registry.py` pattern to work with FastMCP's `@mcp.tool()` decorator pattern.

**Tasks:**
- Study existing `ToolRegistry`, `ToolDefinition`, `ToolCategory` patterns
- Create a `FastMCP` server instance and use `@mcp.tool()` decorators:
  ```python
  from fastmcp import FastMCP
  mcp = FastMCP("TappsMCP", json_response=True)

  @mcp.tool()
  def tapps_server_info() -> dict:
      """Return TappsMCP server version, available tools, and installed checkers."""
      ...
  ```
- Type annotations auto-generate JSON schemas (no manual `inputSchema` needed)
- Docstrings become tool descriptions automatically
- Use `Annotated[str, Field(description="...")]` for parameter descriptions
- Retain internal `ToolRegistry` for category tracking and metadata (TappsMCP-specific concerns)
- Unit test: FastMCP produces valid MCP tool definitions

**Definition of Done:** Tools registered via `@mcp.tool()` produce valid MCP-compliant JSON Schema definitions.

---

### 0.4 — Server Entry Point & Transport

**Points:** 3

Create `server.py` — the main MCP server entry point with stdio and Streamable HTTP transport.

**Tasks:**
- Create `FastMCP` server instance as the central server object
- Implement `tapps-mcp serve` CLI command (use `click` or `typer`)
- Support transport modes:
  - `--transport stdio` (default) — for local MCP hosts (Claude Code, Cursor)
  - `--transport http` — Streamable HTTP for remote/containerized deployments (serves at `/mcp`)
  - SSE is **deprecated** — do not implement
- Wire gateway routing concepts from existing `MCPGateway` (routing, result wrapping)
- Handle MCP protocol lifecycle: `initialize`, `tools/list`, `tools/call`
- Add graceful shutdown handling
- Add startup banner with version, transport, project root
- Support `fastmcp run server.py --reload` for development mode

**Definition of Done:** `tapps-mcp serve` starts, Claude Code connects via stdio, MCP handshake works.

---

### 0.5 — Error Handling & Progress Tracking

**Points:** 2

Implement standard error handling and MCP progress tracking patterns.

**Tasks:**
- Use FastMCP `ToolError` for user-visible errors:
  ```python
  from fastmcp.exceptions import ToolError
  raise ToolError("File not found: path/to/file")
  ```
- Implement standard error response schema (see main plan) for tool-level errors
- Add MCP progress tracking for long-running tools:
  ```python
  @mcp.tool()
  async def tapps_score_file(file_path: str, ctx: Context) -> dict:
      await ctx.report_progress(progress=0.5, total=1.0, message="Running mypy...")
  ```
- Map error codes: `tool_unavailable`, `file_not_found`, `path_denied`, `timeout`, `api_unavailable`, `degraded_result`, `config_error`
- Use `strict_input_validation=True` on the FastMCP instance for type safety

**Definition of Done:** Errors return structured responses. Long-running tools report progress.

---

### 0.6 — Security Hardening Extraction

**Points:** 5

Extract all security-critical modules. These are mandatory before any file-path-accepting tools are added.

**Tasks:**
- Extract `core/path_validator.py` → `tapps_mcp/security/path_validator.py`
  - Extend `assert_write_allowed()` to enforce `TAPPS_MCP_PROJECT_ROOT` boundary
  - All file paths must resolve to absolute and confirm within project root
  - Reject symlinks that escape project root
- Extract `core/io_guardrails.py` → `tapps_mcp/security/io_guardrails.py`
  - `sanitize_for_log()` — strip control characters from all log output
  - `detect_likely_prompt_injection()` — flag suspicious patterns in tool inputs
- Extract `experts/rag_safety.py` → `tapps_mcp/security/rag_safety.py`
  - Prompt injection defense for RAG-retrieved content
  - Regex pattern matching for known injection patterns
- Extract `experts/governance.py` → `tapps_mcp/security/governance.py`
  - `GovernanceLayer` — filter secrets/PII/credentials from tool responses
  - Decouple from expert base class
- Extract `context7/security.py` → `tapps_mcp/security/api_keys.py`
  - `SecretStr` handling for API keys — never in logs, responses, or errors
- Unit tests for every security module (target: 100% coverage on security code)

**Definition of Done:** All security modules extracted, decoupled, tested. No file I/O occurs without path validation.

---

### 0.7 — Windows Subprocess Compatibility

**Points:** 1

Extract the Windows subprocess shim for cross-platform external tool execution.

**Tasks:**
- Extract `core/subprocess_utils.py` → `tapps_mcp/tools/subprocess_utils.py`
- Extract `utils/subprocess_runner.py` → `tapps_mcp/tools/subprocess_runner.py`
- `wrap_windows_cmd_shim()` handles `.cmd` wrappers for ruff, mypy, bandit on Windows
- `run_command()` / `run_command_async()` for subprocess execution
- Test on Windows: verify ruff/mypy invocation works through `.cmd` shims

**Definition of Done:** `subprocess_utils` works on Windows and Unix. CI passes on both platforms.

---

### 0.8 — Configuration System

**Points:** 2

Implement configuration with clear precedence: env vars > YAML config > defaults.

**Tasks:**
- Create `config/default.yaml` with default thresholds and presets
- Implement `tapps_mcp/config.py` using `pydantic-settings`:
  - `TAPPS_MCP_PROJECT_ROOT` — project root boundary (default: cwd)
  - `TAPPS_MCP_QUALITY_PRESET` — standard/strict/framework
  - `TAPPS_MCP_LOG_LEVEL` — logging level
  - `CONTEXT7_API_KEY` — optional, SecretStr
- Support `.tapps-mcp.yaml` project-level config file
- Config precedence: env vars > `.tapps-mcp.yaml` > `config/default.yaml`

**Definition of Done:** Config loads from all three sources with correct precedence. SecretStr fields never appear in logs.

---

### 0.9 — `tapps_server_info` Tool

**Points:** 1

Implement the Tier 0 meta tool that reports server capabilities.

**Tasks:**
- Implement `tapps_server_info` tool handler
- Detect installed external tools (ruff, mypy, bandit, radon, coverage) with versions
- Report available MCP tools, server version, protocol version
- Report active configuration (project root, quality preset, config source)
- Include `install_hint` for missing tools

**Definition of Done:** `tapps_server_info` returns accurate capability report. Missing tools show install hints.

---

### 0.10 — Integration Test: End-to-End MCP Handshake

**Points:** 2

Verify the full MCP protocol lifecycle works.

**Tasks:**
- Write integration test: start server, connect via stdio, perform handshake
- Verify `initialize` response includes correct capabilities
- Verify `tools/list` returns `tapps_server_info`
- Verify `tools/call` for `tapps_server_info` returns valid response
- Test on Windows + Linux

**Definition of Done:** Integration test passes on both platforms. Server correctly speaks MCP protocol.

---

## Technical Notes

### Key Dependencies
- `mcp[cli]>=1.26.0` — Python MCP SDK with CLI tools (includes FastMCP)
- `fastmcp` — High-level MCP server framework (decorator-based tool registration)
- `pydantic>=2.0` + `pydantic-settings` — config and models
- `structlog` — structured logging
- `pyyaml` — YAML config parsing
- `click` or `typer` — CLI framework
- `anyio` — async runtime (used by MCP SDK)
- `httpx` — async HTTP client (for Streamable HTTP transport + Context7 API)

### Architecture Decisions
- **FastMCP over low-level API**: Use `FastMCP` for tool registration (less boilerplate, auto JSON Schema). Use low-level `Server` API only if FastMCP is insufficient for specific needs.
- **src-layout**: `src/tapps_mcp/` — prevents accidental imports from project root
- **Strict typing**: `mypy --strict` from day one — no `Any` types without justification
- **Security-first**: Path validation module must be in place before any file-path tool is added
- **Structured errors**: Use `ToolError` for user-visible errors, standard error schema for tool responses
- **Async-first**: Prefer `async def` for tool handlers (MCP SDK is async-native). Sync handlers run in threadpool automatically.
- **Protocol version**: Target `2025-11-25` (latest stable). The plan's original `2024-11-05` reference is outdated.

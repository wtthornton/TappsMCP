# `packages.tapps-mcp.src.tapps_mcp.server_pipeline_tools`

Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_validate_changed`

```python
async def tapps_validate_changed(file_paths: str = '', base_ref: str = 'HEAD', preset: str = 'standard', include_security: bool = True, quick: bool = True, security_depth: str = 'basic', include_impact: bool = True, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

REQUIRED before declaring multi-file work complete.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_paths` | `str` | Comma-separated file paths (empty = auto-detect via git diff). | '' |
| `base_ref` | `str` | Git ref to diff against (default: HEAD for unstaged changes). | 'HEAD' |
| `preset` | `str` | Quality gate preset - "standard", "strict", or "framework". | 'standard' |
| `include_security` | `bool` | Whether to run security scan on each file (ignored if quick=True). | True |
| `quick` | `bool` | If True (default), ruff-only scoring for speed. If False, full validation. | True |
| `security_depth` | `str` | Security scan depth - "basic" (default) or "full". When "full", security scan runs even in quick mode. | 'basic' |
| `include_impact` | `bool` | Whether to run impact analysis on changed files (default: True). | True |
| `ctx` | `Context[Any, Any, Any] \| None` | Optional MCP context (injected by host); used for progress notifications. | None |

### async `tapps_session_start`

```python
async def tapps_session_start(project_root: str = '') -> dict[str, Any]:
```

REQUIRED as the FIRST call in every session. Returns server info

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Unused; reserved for future use. Server uses configured root. | '' |

### async `tapps_init`

```python
async def tapps_init(create_handoff: bool = True, create_runlog: bool = True, create_agents_md: bool = True, create_tech_stack_md: bool = True, platform: str = '', verify_server: bool = True, install_missing_checkers: bool = False, warm_cache_from_tech_stack: bool = True, warm_expert_rag_from_tech_stack: bool = True, overwrite_platform_rules: bool = False, overwrite_agents_md: bool = False, agent_teams: bool = False, memory_capture: bool = False, destructive_guard: bool | None = None, minimal: bool = False, dry_run: bool = False, verify_only: bool = False, llm_engagement_level: str | None = None, scaffold_experts: bool = False, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Bootstrap TAPPS pipeline in the current project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `create_handoff` | `bool` | Create docs/TAPPS_HANDOFF.md template. | True |
| `create_runlog` | `bool` | Create docs/TAPPS_RUNLOG.md template. | True |
| `create_agents_md` | `bool` | Create AGENTS.md with AI assistant workflow (if missing). | True |
| `create_tech_stack_md` | `bool` | Create or update TECH_STACK.md from project profile. | True |
| `platform` | `str` | Generate platform rules. One of: "claude", "cursor", "". | '' |
| `verify_server` | `bool` | Verify server info and installed checkers. | True |
| `install_missing_checkers` | `bool` | Attempt to pip-install missing checkers (opt-in). | False |
| `warm_cache_from_tech_stack` | `bool` | Pre-fetch docs for tech stack libraries into cache. | True |
| `warm_expert_rag_from_tech_stack` | `bool` | Pre-build expert RAG indices for relevant domains. | True |
| `overwrite_platform_rules` | `bool` | When ``True``, refresh platform rule files even if they already exist (useful when templates are upgraded). | False |
| `overwrite_agents_md` | `bool` | When ``True``, replace AGENTS.md entirely with the latest template. When ``False`` (default), validate and smart-merge missing sections/tools. | False |
| `agent_teams` | `bool` | When ``True`` and platform is ``"claude"``, generate Agent Teams hooks (TeammateIdle, TaskCompleted) for quality watchdog teammate. | False |
| `memory_capture` | `bool` | When ``True`` and platform is ``"claude"``, generate a Stop hook that captures session quality data for memory persistence. | False |
| `destructive_guard` | `bool \| None` | When ``True``, add a PreToolUse hook that blocks Bash commands containing destructive patterns (rm -rf, format c:, etc.). When ``None``, uses value from settings. Default ``False``. | None |
| `minimal` | `bool` | When ``True``, create only AGENTS.md, TECH_STACK.md, platform rules, and MCP config. Skip hooks, skills, sub-agents, CI, governance, GitHub templates, handoff/runlog, and cache warming. | False |
| `dry_run` | `bool` | When ``True``, compute and return what would be created without writing files or warming caches. Keeps dry_run lightweight (~2-5s). | False |
| `verify_only` | `bool` | When ``True``, run only server verification and return (~1-3s). Use for quick connectivity/checker checks without creating files. | False |
| `llm_engagement_level` | `str \| None` | When set, use this level (high/medium/low) for AGENTS.md and platform rules. When ``None``, use config/settings. | None |
| `scaffold_experts` | `bool` | When ``True`` and ``.tapps-mcp/experts.yaml`` exists, scaffold missing knowledge directories for business experts (creates README.md and overview.md starter files). | False |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### async `tapps_upgrade`

```python
async def tapps_upgrade(platform: str = '', force: bool = False, dry_run: bool = False, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Upgrade all TappsMCP-generated files after a version update.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `platform` | `str` | Target platform - "claude", "cursor", "both", or "" for auto-detection. | '' |
| `force` | `bool` | If True, overwrite all generated files without prompting. | False |
| `dry_run` | `bool` | If True, show what would be updated without making changes. | False |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### `tapps_set_engagement_level`

```python
def tapps_set_engagement_level(level: str) -> dict[str, Any]:
```

Set the LLM engagement level (high / medium / low) for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `level` | `str` | One of ``"high"`` (mandatory), ``"medium"`` (balanced), ``"low"`` (optional guidance). | *required* |

### `tapps_doctor`

```python
def tapps_doctor(project_root: str = '') -> dict[str, Any]:
```

Diagnose TappsMCP configuration and connectivity.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path (default: server's configured root). | '' |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register pipeline/validation tools on *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

---

*Documentation coverage: 100.0%*

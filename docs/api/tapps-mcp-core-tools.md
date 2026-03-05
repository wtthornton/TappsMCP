# `packages.tapps-mcp.src.tapps_mcp.server`

TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
  - ``server_memory_tools``: tapps_memory
  - ``server_expert_tools``: tapps_manage_experts
  - ``server_analysis_tools``: tapps_session_notes, tapps_impact_analysis, tapps_report,
    tapps_dead_code, tapps_dependency_scan, tapps_dependency_graph
  - ``server_resources``: MCP resources and prompts

## Functions

### `tapps_server_info`

```python
def tapps_server_info() -> dict[str, Any]:
```

Discovers server version, available tools, installed checkers (ruff, mypy,

### `tapps_security_scan`

```python
def tapps_security_scan(file_path: str, scan_secrets: bool = True) -> dict[str, Any]:
```

REQUIRED when changes touch security-sensitive code. Runs bandit and

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to scan. | *required* |
| `scan_secrets` | `bool` | Whether to scan for hardcoded secrets (default: True). | True |

### async `tapps_lookup_docs`

```python
async def tapps_lookup_docs(library: str, topic: str = 'overview', mode: str = 'code') -> dict[str, Any]:
```

BLOCKING REQUIREMENT before using any external library API. Returns

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library` | `str` | Library name (fuzzy-matched). | *required* |
| `topic` | `str` | Specific topic within the library (default "overview"). | 'overview' |
| `mode` | `str` | "code" for API references, "info" for conceptual guides. | 'code' |

### `tapps_validate_config`

```python
def tapps_validate_config(file_path: str, config_type: str = 'auto') -> dict[str, Any]:
```

REQUIRED when changing Dockerfile, docker-compose, or infra config.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the config file to validate. | *required* |
| `config_type` | `str` | Config type or "auto" for auto-detection. | 'auto' |

### `tapps_consult_expert`

```python
def tapps_consult_expert(question: str, domain: str = '') -> dict[str, Any]:
```

REQUIRED for domain-specific decisions. Routes to one of 17+ built-in

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The technical question to ask (natural language). | *required* |
| `domain` | `str` | Optional domain from the list above. Omit to auto-detect from question. | '' |

### `tapps_list_experts`

```python
def tapps_list_experts() -> dict[str, Any]:
```

Returns built-in and business experts with domain, description, and knowledge-base status.

### async `tapps_checklist`

```python
async def tapps_checklist(task_type: str = 'review', auto_run: bool = False) -> dict[str, Any]:
```

REQUIRED as the FINAL step before declaring work complete.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `task_type` | `str` | "feature" \| "bugfix" \| "refactor" \| "security" \| "review". | 'review' |
| `auto_run` | `bool` | When True, automatically run missing required validations (via tapps_validate_changed) and re-evaluate the checklist. | False |

### `tapps_project_profile`

```python
def tapps_project_profile(project_root: str = '') -> dict[str, Any]:
```

Call when you need project context. Detects tech stack, type, CI, Docker,

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path (default: server's configured root). | '' |

### `run_server`

```python
def run_server(transport: str = 'stdio', host: str = '127.0.0.1', port: int = 8000) -> None:
```

Start the TappsMCP MCP server.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `transport` | `str` |  | 'stdio' |
| `host` | `str` |  | '127.0.0.1' |
| `port` | `int` |  | 8000 |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `mcp` | `` | `FastMCP('TappsMCP')` |
| `tapps_score_file` | `` | `_scoring.tapps_score_file` |
| `tapps_quality_gate` | `` | `_scoring.tapps_quality_gate` |
| `tapps_quick_check` | `` | `_scoring.tapps_quick_check` |
| `tapps_validate_changed` | `` | `_pipeline.tapps_validate_changed` |
| `tapps_session_start` | `` | `_pipeline.tapps_session_start` |
| `tapps_init` | `` | `_pipeline.tapps_init` |
| `tapps_dashboard` | `` | `_metrics.tapps_dashboard` |
| `tapps_stats` | `` | `_metrics.tapps_stats` |
| `tapps_feedback` | `` | `_metrics.tapps_feedback` |
| `tapps_research` | `` | `_metrics.tapps_research` |
| `tapps_memory` | `` | `_memory.tapps_memory` |
| `tapps_manage_experts` | `` | `_experts.tapps_manage_experts` |
| `tapps_session_notes` | `` | `_analysis.tapps_session_notes` |
| `tapps_impact_analysis` | `` | `_analysis.tapps_impact_analysis` |
| `tapps_report` | `` | `_analysis.tapps_report` |
| `tapps_dead_code` | `` | `_analysis.tapps_dead_code` |
| `tapps_dependency_scan` | `` | `_analysis.tapps_dependency_scan` |
| `tapps_dependency_graph` | `` | `_analysis.tapps_dependency_graph` |

---

*Documentation coverage: 100.0%*

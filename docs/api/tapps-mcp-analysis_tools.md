# `packages.tapps-mcp.src.tapps_mcp.server_analysis_tools`

Analysis and inspection tool handlers for TappsMCP.

Contains: tapps_report, tapps_dead_code, tapps_dependency_scan,
tapps_dependency_graph, tapps_session_notes, tapps_impact_analysis.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_session_notes`

```python
async def tapps_session_notes(action: str, key: str = '', value: str = '') -> dict[str, Any]:
```

Persist notes across the session to avoid losing context.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `action` | `str` | "save" \| "get" \| "list" \| "clear" \| "promote". | *required* |
| `key` | `str` | Note key (required for save/get/promote). | '' |
| `value` | `str` | Note value (required for save). For promote, optional tier name. | '' |

### async `tapps_impact_analysis`

```python
async def tapps_impact_analysis(file_path: str, change_type: str = 'modified') -> dict[str, Any]:
```

REQUIRED before refactoring or deleting files. Maps the blast radius.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the file being changed. | *required* |
| `change_type` | `str` | "added" \| "modified" \| "removed". | 'modified' |

### async `tapps_report`

```python
async def tapps_report(file_path: str = '', report_format: str = 'json', max_files: int = 20, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Generate a quality report combining scoring and gate results.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to a Python file (optional - project-wide if omitted). | '' |
| `report_format` | `str` | "json" \| "markdown" \| "html". | 'json' |
| `max_files` | `int` | Maximum files to score for project-wide report (default 20). | 20 |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### async `tapps_dead_code`

```python
async def tapps_dead_code(file_path: str = '', min_confidence: int = 80, scope: str = 'file', ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Scan a Python file for dead code (unused functions, classes, imports, variables).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to scan (required when scope="file"). | '' |
| `min_confidence` | `int` | Minimum confidence threshold (0-100, default 80). | 80 |
| `scope` | `str` | Scan scope - "file" (single file), "project" (all .py files), or "changed" (git-changed .py files only). | 'file' |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### async `tapps_dependency_scan`

```python
async def tapps_dependency_scan(project_root: str = '', ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Scan project dependencies for known vulnerabilities using pip-audit.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path (default: server's configured root). | '' |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### async `tapps_dependency_graph`

```python
async def tapps_dependency_graph(project_root: str = '', detect_cycles: bool = True, include_coupling: bool = True, ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

Analyze import dependencies: detect circular imports and measure coupling.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path (default: server's configured root). | '' |
| `detect_cycles` | `bool` | Whether to detect circular dependency cycles. | True |
| `include_coupling` | `bool` | Whether to calculate coupling metrics. | True |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register analysis tools on the shared *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*

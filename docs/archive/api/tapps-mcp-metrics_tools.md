# `packages.tapps-mcp.src.tapps_mcp.server_metrics_tools`

Metrics, dashboard, feedback, and research tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_dashboard`

```python
async def tapps_dashboard(output_format: str = 'json', time_range: str = '7d', sections: list[str] | None = None) -> dict[str, Any]:
```

Generate a comprehensive metrics dashboard.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `output_format` | `str` | Output format - "json" (default), "markdown", "html", or "otel". | 'json' |
| `time_range` | `str` | Time range - "1d", "7d", "30d", "90d". | '7d' |
| `sections` | `list[str] \| None` | Specific sections to include (default: all). | None |

### `tapps_stats`

```python
def tapps_stats(tool_name: str | None = None, period: str = 'session') -> dict[str, Any]:
```

Return usage statistics for TappsMCP tools.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tool_name` | `str \| None` | Filter stats to a specific tool (optional). | None |
| `period` | `str` | Stats period - "session", "1d", "7d", "30d", "all". | 'session' |

### `tapps_feedback`

```python
def tapps_feedback(tool_name: str, helpful: bool, context: str | None = None) -> dict[str, Any]:
```

Report whether a tool's output was helpful.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tool_name` | `str` | Which tool to provide feedback on. | *required* |
| `helpful` | `bool` | Was the output helpful? | *required* |
| `context` | `str \| None` | Additional context about why it was or wasn't helpful. | None |

### async `tapps_research`

```python
async def tapps_research(question: str, domain: str = '', library: str = '', topic: str = '', file_context: str = '') -> dict[str, Any]:
```

Combined expert consultation + documentation lookup in one call.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The technical question to research (natural language). | *required* |
| `domain` | `str` | Optional domain override for expert routing. | '' |
| `library` | `str` | Optional library name for docs lookup (auto-inferred when empty). | '' |
| `topic` | `str` | Optional topic for docs lookup (auto-inferred when empty). | '' |
| `file_context` | `str` | Optional file path for inferring library from imports. | '' |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register metrics/feedback/research tools on *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

---

*Documentation coverage: 100.0%*

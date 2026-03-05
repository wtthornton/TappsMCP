# `packages.tapps-mcp.src.tapps_mcp.server_memory_tools`

Memory tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_memory`

```python
async def tapps_memory(action: str, key: str = '', value: str = '', tier: str = 'pattern', source: str = 'agent', source_agent: str = 'unknown', scope: str = 'project', tags: str = '', branch: str = '', query: str = '', confidence: float = -1.0, ranked: bool = True, limit: int = 0, include_summary: bool = True, file_path: str = '', overwrite: bool = False) -> dict[str, Any]:
```

Persist and retrieve project memories across sessions.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `action` | `str` | One of "save", "get", "list", "delete", "search", "reinforce", "gc", "contradictions", "reseed", "import", "export". | *required* |
| `key` | `str` | Memory key (required for save/get/delete/reinforce). Lowercase slug. | '' |
| `value` | `str` | Memory content (required for save). Max 4096 chars. | '' |
| `tier` | `str` | "architectural", "pattern", or "context" (default: "pattern"). | 'pattern' |
| `source` | `str` | "human", "agent", "inferred", or "system" (default: "agent"). | 'agent' |
| `source_agent` | `str` | Agent identifier (default: "unknown"). | 'unknown' |
| `scope` | `str` | "project", "branch", or "session" (default: "project"). | 'project' |
| `tags` | `str` | Comma-separated tags for categorization (optional). | '' |
| `branch` | `str` | Git branch name (required when scope="branch"). | '' |
| `query` | `str` | Search query (for search action). | '' |
| `confidence` | `float` | Override default confidence 0.0-1.0 (optional, -1 for default). | -1.0 |
| `ranked` | `bool` | When True (default), search returns BM25-ranked results with scores. | True |
| `limit` | `int` | Max results for search/list (0 = use defaults: 10 for search, 50 for list). | 0 |
| `include_summary` | `bool` | When True (default), list/search include one-line summaries. | True |
| `file_path` | `str` | File path for import/export actions. | '' |
| `overwrite` | `bool` | When True, import overwrites existing keys (default: False). | False |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register memory tools on the shared *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

---

*Documentation coverage: 100.0%*

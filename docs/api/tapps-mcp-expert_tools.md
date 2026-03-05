# `packages.tapps-mcp.src.tapps_mcp.server_expert_tools`

Business expert management tool handlers for TappsMCP.

Provides the tapps_manage_experts MCP tool with actions:
list, add, remove, scaffold, validate.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_manage_experts`

```python
async def tapps_manage_experts(action: str, expert_id: str = '', expert_name: str = '', primary_domain: str = '', description: str = '', keywords: str = '', rag_enabled: bool = True, knowledge_dir: str = '') -> dict[str, Any]:
```

Manage user-defined business experts (CRUD + validation).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `action` | `str` | One of "list", "add", "remove", "scaffold", "validate". | *required* |
| `expert_id` | `str` | Expert identifier (required for add/remove/scaffold). Must start with "expert-". | '' |
| `expert_name` | `str` | Human-readable name (required for add). | '' |
| `primary_domain` | `str` | Primary domain of authority (required for add). | '' |
| `description` | `str` | Short description of the expert's focus (optional). | '' |
| `keywords` | `str` | Comma-separated keywords for domain detection (optional). | '' |
| `rag_enabled` | `bool` | Whether RAG retrieval is enabled (default: True). | True |
| `knowledge_dir` | `str` | Override knowledge directory name (optional). | '' |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register expert management tools on the shared *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*

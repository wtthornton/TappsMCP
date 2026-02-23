# MCP Testing Patterns

## Overview

Testing MCP (Model Context Protocol) servers and tools requires mocking tool handlers, simulating server responses, and validating tool schemas. This guide covers patterns for pytest-based MCP server testing.

## Key Patterns

### 1. Fixture-Based Tool Mocking

Use pytest fixtures to mock MCP tool handlers and control responses:

```python
@pytest.fixture
def mock_tool_handler(monkeypatch):
    """Mock the actual tool implementation for deterministic tests."""
    results = []
    async def _mock(name, args):
        results.append((name, args))
        return {"success": True, "data": {}}
    monkeypatch.setattr("tapps_mcp.server._dispatch_tool", _mock)
    return results
```

### 2. Testing Tool Schemas

Validate that tools accept expected parameters and return structured output:

```python
def test_tapps_score_file_schema():
    """Ensure tapps_score_file accepts file_path and optional quick param."""
    tool = get_tool_def("tapps_score_file")
    assert "file_path" in tool["inputSchema"]["required"]
    assert "quick" in tool["inputSchema"]["properties"]
```

### 3. MCP Server Integration Tests

Use the MCP SDK test utilities or a real stdio/HTTP transport to exercise the full stack:

```python
async def test_tool_call_roundtrip(mcp_client):
    result = await mcp_client.call_tool("tapps_score_file", {"file_path": "src/main.py"})
    assert result.success
    assert "overall_score" in result.data
```

### 4. Conftest and Monkeypatch for Environment

For tools that read project root or config, use conftest.py to set up a temporary project:

```python
# conftest.py
@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# test")
    return tmp_path
```

## Best Practices

- **Isolate tool logic** so it can be unit-tested without starting the full MCP server.
- **Mock external dependencies** (Context7 API, file system) for fast, deterministic tests.
- **Use `tapps_init` with `dry_run=True`** in tests to avoid side effects.

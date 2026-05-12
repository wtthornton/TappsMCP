# Tutorial: Add a new MCP tool to tapps-mcp

**Time:** ~15 minutes. **Outcome:** A working `tapps_hello` MCP tool callable from Claude Code, registered in the checklist, documented in [AGENTS.md](../../AGENTS.md), and covered by a unit test.

This walkthrough takes you end-to-end through the file paths and registration touchpoints you need for any new tool. The example tool just echoes a greeting — focus on the wiring, not the logic.

## Prerequisites

- This repo cloned, `uv sync --all-packages` already run.
- `uv run tapps-mcp serve` runs without errors.

## Step 1 — Add the handler

Tools live in topic-specific `server_*.py` modules. For a brand-new "hello" tool, pick the closest existing module or create one. We'll add to [server_helpers.py](../../packages/tapps-mcp/src/tapps_mcp/server_helpers.py)'s neighborhood by putting it in a new module — but for the tutorial, append to [server_metrics_tools.py](../../packages/tapps-mcp/src/tapps_mcp/server_metrics_tools.py) to keep the diff small.

Append at the bottom of the file:

```python
@mcp.tool()
async def tapps_hello(name: str = "world") -> dict[str, Any]:
    """Return a greeting. Tutorial-only tool — remove after walkthrough."""
    _record_call("tapps_hello")
    return success_response(
        tool="tapps_hello",
        data={"greeting": f"hello, {name}"},
    )
```

The three things that matter:
- **`@mcp.tool()`** registers the handler with FastMCP.
- **`_record_call("tapps_hello")`** at the top is required — the checklist tool reads this counter to verify each obligation was met.
- **`success_response(...)`** wraps your data in the standard `{tool, success, elapsed_ms, data}` envelope. Use `error_response(...)` for failures.

## Step 2 — Register in the checklist task map

Open [packages/tapps-mcp/src/tapps_mcp/tools/checklist.py](../../packages/tapps-mcp/src/tapps_mcp/tools/checklist.py) and grep for `_TOOL_TO_TASKS`. Add an entry mapping your tool to the task type(s) that should consider it:

```python
_TOOL_TO_TASKS: dict[str, set[str]] = {
    # ... existing entries ...
    "tapps_hello": {"feature"},
}
```

If your tool isn't tied to any task type, leave it out — the checklist won't fail, it just won't surface a "you should call X" reminder.

## Step 3 — Document in AGENTS.md

Open [AGENTS.md](../../AGENTS.md) and add a row to the appropriate tools table (use the same pattern as `tapps_quick_check`):

```markdown
| `tapps_hello` | Return a greeting (tutorial example). | After session start, before any feature work. |
```

The `When to use` column is what the LLM consumer reads to decide whether to invoke the tool. Be specific — vague guidance produces vague usage.

## Step 4 — Add a unit test

Create [packages/tapps-mcp/tests/unit/test_tapps_hello.py](../../packages/tapps-mcp/tests/unit/):

```python
"""Tests for the tutorial tapps_hello tool."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_tapps_hello_default() -> None:
    from tapps_mcp.server_metrics_tools import tapps_hello

    result = await tapps_hello()
    assert result["success"] is True
    assert result["data"]["greeting"] == "hello, world"


@pytest.mark.asyncio
async def test_tapps_hello_named() -> None:
    from tapps_mcp.server_metrics_tools import tapps_hello

    result = await tapps_hello(name="Bill")
    assert result["data"]["greeting"] == "hello, Bill"
```

## Step 5 — Verify

Run the test:

```bash
uv run pytest packages/tapps-mcp/tests/unit/test_tapps_hello.py -v
```

You should see two passes. Then run the type check on the modules you touched:

```bash
uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/server_metrics_tools.py
```

Expected: `Success: no issues found`.

Finally, restart your Claude Code session (so the MCP server reloads) and ask Claude to call `tapps_hello`. The response should include the `hello, world` greeting in `data.greeting`.

## Cleanup

Tutorial-only — delete the handler, checklist entry, AGENTS.md row, and test file before committing real work.

## What you learned

The five touchpoints for any new MCP tool: handler registration, `_record_call`, checklist mapping, AGENTS.md documentation, and a unit test. The same pattern applies to all 30 production tapps-mcp tools — see [server_scoring_tools.py](../../packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py) for a real, larger-shape example.

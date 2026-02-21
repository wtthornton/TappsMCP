# MCP Tool Annotations — Reference

**Source:** Deep research conducted 2026-02-21
**Spec:** MCP Protocol 2025-03-26

## Overview

Tool annotations provide metadata hints to MCP clients about tool behavior.
They enable clients to make UX decisions (like auto-approving read-only tools)
without understanding the tool's implementation.

## Annotation Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | — | Human-readable display name |
| `readOnlyHint` | boolean | false | Tool does not modify state |
| `destructiveHint` | boolean | true | Tool may perform destructive updates |
| `idempotentHint` | boolean | false | Safe to call repeatedly with same args |
| `openWorldHint` | boolean | true | Interacts with external entities |

## Client Behavior

- `readOnlyHint=true` → Clients may auto-approve without user confirmation
- `destructiveHint=false` → Clients may skip "are you sure?" prompts
- `idempotentHint=true` → Clients may enable automatic retry
- `openWorldHint=false` → Tool operates only on local/internal state

## TappsMCP Tool Audit

### Read-Only Tools (18 of 21) — Set `readOnlyHint=true`

| Tool | Read-Only | Destructive | Idempotent | Open World |
|------|:---------:|:-----------:|:----------:|:----------:|
| `tapps_score_file` | true | false | true | false |
| `tapps_quality_gate` | true | false | true | false |
| `tapps_quick_check` | true | false | true | false |
| `tapps_validate_changed` | true | false | true | false |
| `tapps_consult_expert` | true | false | true | false |
| `tapps_research` | true | false | false | true |
| `tapps_lookup_docs` | true | false | false | true |
| `tapps_dashboard` | true | false | true | false |
| `tapps_stats` | true | false | true | false |
| `tapps_checklist` | true | false | true | false |
| `tapps_validate_config` | true | false | true | false |
| `tapps_impact_analysis` | true | false | true | false |
| `tapps_project_profile` | true | false | true | false |
| `tapps_session_notes` | true | false | true | false |
| `tapps_adaptive_weights` | true | false | true | false |
| `tapps_explain_score` | true | false | true | false |
| `tapps_compare_scores` | true | false | true | false |
| `tapps_trend_analysis` | true | false | true | false |

### Tools with Side Effects (3 of 21)

| Tool | Read-Only | Destructive | Idempotent | Open World | Notes |
|------|:---------:|:-----------:|:----------:|:----------:|-------|
| `tapps_session_start` | false | false | true | false | Creates session state |
| `tapps_feedback` | false | false | false | false | Records feedback |
| `tapps_init` | false | false | true | false | Creates files on disk |

### Notes
- `tapps_research` and `tapps_lookup_docs` are read-only but `openWorldHint=true` because they may call Context7 external API
- `tapps_session_start` is idempotent (safe to call multiple times)
- `tapps_init` creates files but is idempotent (re-running updates existing files)
- None of the tools are destructive

## Implementation

In `server.py`, add annotations when registering tools:

```python
@mcp.tool(
    annotations={
        "title": "Score File",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def tapps_score_file(...):
    ...
```

## Impact

With annotations, MCP clients can:
1. Auto-approve 18/21 tools (read-only) without user confirmation
2. Skip "destructive action" warnings on all 21 tools
3. Enable automatic retry on 19/21 idempotent tools
4. Know that 19/21 tools operate locally (no external calls)

This eliminates the #1 friction point across ALL MCP clients.

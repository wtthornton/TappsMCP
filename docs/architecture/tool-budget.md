# MCP Server Eager-Tool Budget

**Default budget:** 20 tools per MCP server  
**Config key:** `doctor_tool_budget_limit` in `.tapps-mcp.yaml`

---

## What is the tool budget?

Each MCP server exposes a set of tools in its `tools/list` response. These are the
**eager** tools — tools immediately visible to the client without needing `tool_search`.
As the eager tool count grows, the client's context window is consumed by tool schema
descriptions, reducing effective context for actual work.

`tapps_doctor` probes each known tapps-family server and emits a `WARN` line when any
server's eager tool count exceeds the budget.

## Known server tool counts

Post TAP-1986/TAP-1987: non-daily-driver tools carry `defer_loading=True` and are loaded
on-demand via Tool Search. The counts below reflect the current **eager** vs **deferred** split.

Eager tools: `tapps_session_start`, `tapps_validate_changed`, `tapps_score_file`,
`tapps_quality_gate`, `tapps_quick_check`, `tapps_lookup_docs`, `tapps_checklist`,
`tapps_impact_analysis`, `tapps_usage` (9 total).

| Server | Mode | Eager tools | Deferred tools | Total |
|---|---|---|---|---|
| `tapps-mcp` | full (no `--mode`) | 9 | 26 | 35 |
| `tapps-quality` | `--mode quality` | 9 | 6 | 15 |
| `tapps-admin` | `--mode admin` | 1 | 12 | 13 |
| `docs-mcp` | — | 6 | 32 | 38 |

> **Note:** The original TAP-1986 count was 8 eager tools. `tapps_usage` was added
> as an eager daily-driver in v3.11.0, and two deferred brain-elevation tools
> (`brain_propose_hive_elevation`, `brain_approve_hive_elevation`) were added in
> TAP-2014, bringing full-mode totals to 35 tools (9 eager, 26 deferred).

## Updating the budget

Set `doctor_tool_budget_limit` in `.tapps-mcp.yaml`:

```yaml
# Allow up to 30 tools per server before WARN
doctor_tool_budget_limit: 30
```

If you intentionally run tapps-mcp in full mode (32 tools) and accept the context cost,
raise the budget to 35 to silence the WARN. If you want a stricter check, lower it to 15
to enforce quality-preset-level discipline.

## Reducing tool count

To bring a server within budget:

1. **Use a preset**: start tapps-mcp with `--mode quality` (15 tools) or `--mode admin`
   (13 tools) instead of the default full mode.
2. **Disable individual tools**: set `disabled_tools` in `.tapps-mcp.yaml`:
   ```yaml
   disabled_tools:
     - tapps_linear_snapshot_get
     - tapps_linear_snapshot_put
     - tapps_release_update
   ```
3. **Enable only specific tools**: set `enabled_tools` in `.tapps-mcp.yaml`:
   ```yaml
   enabled_tools:
     - tapps_session_start
     - tapps_quick_check
     - tapps_quality_gate
   ```

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full server mode table.

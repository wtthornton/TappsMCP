# Agent Gateway Refusal Envelope — Field Spec

> Referenced from [docs/ARCHITECTURE.md](../ARCHITECTURE.md#agent-gateway-pattern-tap-2008-2026)
> and `.claude/rules/integration-hygiene.md`.

When a tapps-mcp or docs-mcp gateway fires, the tool response (or PreToolUse exit-2 body)
carries this structured envelope. Clients should branch on `ok` + `code`; never parse `hint`
strings programmatically.

## Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `ok` | `bool` | yes | `false` when the gate fired. |
| `code` | `str` | yes | Machine-readable refusal code (see table below). |
| `gate` | `str` | yes | Which gate fired (e.g. `linear_cache_first_read`). |
| `hint` | `str` | yes | Human-readable corrective action — for logs and agent reasoning. |
| `bypass_env` | `str` | no | Environment variable name the caller can set to skip this gate (logged). |
| `logged_to` | `str` | no | Path of the violations log where this firing was recorded. |
| `extra` | `object` | no | Gate-specific context (e.g. `{"cache_key": "...", "age_seconds": 310}`). |

## Refusal codes

| Code | Gate | Meaning | Corrective action |
|---|---|---|---|
| `gate_miss` | `linear_cache_first_read` | `list_issues` called without a prior `snapshot_get` on the same `(team, project, state)` slice. | Call `tapps_linear_snapshot_get(team, project, state)` first; on miss fetch + `snapshot_put`, on hit use cached issues. |
| `validate_missing` | `linear_write_validation` | `save_issue` called without a recent `docs_validate_linear_issue` sentinel. | Call `docs_validate_linear_issue(title, description)` first; must return `agent_ready: true`. |
| `checklist_missing` | `completion_gate` | Session ended without `tapps_checklist` on a loop that edited Python files. | Call `tapps_checklist(task_type="feature"|"bug"|"refactor")` before declaring work complete. |
| `cross_project` | `linear_cache_first_read` | `list_issues` targeted a `(team, project)` not belonging to the deploying repo. | Read `agent-scope.md` — writes to foreign projects are forbidden; reads pass through but are logged. |

## Example envelopes

### `gate_miss` (cache-first read gate, warn mode)

```json
{
  "ok": false,
  "code": "gate_miss",
  "gate": "linear_cache_first_read",
  "hint": "Call tapps_linear_snapshot_get(team='TappsCodingAgents', project='TappsMCP Platform', state='backlog') first, then re-issue list_issues.",
  "bypass_env": "TAPPS_LINEAR_SKIP_CACHE_GATE",
  "logged_to": ".tapps-mcp/.cache-gate-violations.jsonl",
  "extra": {
    "cache_key": "TappsCodingAgents__TappsMCP Platform__backlog__44622e6685a46d5b",
    "mode": "warn"
  }
}
```

### `validate_missing` (Linear write gate, block mode)

```json
{
  "ok": false,
  "code": "validate_missing",
  "gate": "linear_write_validation",
  "hint": "Run docs_validate_linear_issue(title, description) and confirm agent_ready=true before calling save_issue.",
  "bypass_env": "TAPPS_LINEAR_SKIP_VALIDATE",
  "logged_to": ".tapps-mcp/.bypass-log.jsonl"
}
```

## Hook implementation

tapps-mcp gates are implemented as Claude Code hook pairs:

- **PostToolUse** on the prerequisite tool → writes a sentinel file with the Unix epoch.
- **PreToolUse** on the guarded tool → reads the sentinel; if missing or stale, exits 2 with the envelope JSON on stderr.

The sentinel + exit-2 pattern is described in full in `docs/ARCHITECTURE.md` under
[Hook system and MCP server lifecycle](../ARCHITECTURE.md#hook-system-and-mcp-server-lifecycle).

## Adding a new gate

1. Choose a unique `code` and `gate` name (snake_case).
2. Implement the PostToolUse sentinel writer (Bash or Python).
3. Implement the PreToolUse sentinel checker; emit the envelope to stderr and `exit 2` on failure.
4. Add the `bypass_env` env var check; log bypasses to `.tapps-mcp/.bypass-log.jsonl`.
5. Register the gate in `tapps_doctor` diagnostics so `tapps doctor` reports its mode + violation count.
6. Add a row to the "Refusal codes" table above and the gates table in `ARCHITECTURE.md`.

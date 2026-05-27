# Agent Teams Feature Gate Audit (TAP-2021)

Audit of every `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` gate in tapps-mcp.
Decision per gate: **(a) ship as default**, **(b) delete dead code**, or **(c) preview flag with exit date**.

---

## Gate Inventory

### 1. `collect_session_hive_status` — `server_helpers.py`

**Previous behavior:** Returned `{"enabled": False}` immediately when
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` was unset, skipping the brain probe.

**Decision: (a) Ship as default — gate removed (TAP-2021).**

The hive-status probe is a passive read; it already degrades gracefully when
the brain is not reachable (`enabled: "unknown"`, `degraded: true`). Gating it
on the env var caused session-start to report stale `enabled: false` even for
projects where the brain IS configured. The gate had no safety purpose — brain
connectivity is handled by the `BrainBridge` null-check inside the function.

*Status: Removed in commit for TAP-2021.*

---

### 2. `_handle_hive_status` — `server_memory_tools.py`

Action: `tapps_memory(action="hive_status")`

**Decision: (c) Exit date already documented — deprecated 2026-Q3.**

This action and its gate will be removed in the Q3 2026 cleanup sweep when
`mcp__tapps-brain__brain_status` is the fully adopted replacement. No
intermediate code change needed; the exit date is already in the docstring.

*Status: Gate stays; action deleted Q3 2026.*

---

### 3. `_handle_hive_search` — `server_memory_tools.py`

Action: `tapps_memory(action="hive_search")`

**Decision: (c) Exit date already documented — deprecated 2026-Q3.**

Superseded by `mcp__tapps-brain__hive_search`. Gate and action deleted Q3 2026.

*Status: Gate stays; action deleted Q3 2026.*

---

### 4. `_handle_hive_propagate` — `server_memory_tools.py`

Action: `tapps_memory(action="hive_propagate")`

**Decision: (c) Exit date already documented — deprecated 2026-Q3.**

Superseded by `mcp__tapps-brain__brain_status` / direct brain MCP surface.
Gate and action deleted Q3 2026.

*Status: Gate stays; action deleted Q3 2026.*

---

### 5. `_handle_agent_register` — `server_memory_tools.py`

Action: `tapps_memory(action="agent_register")`

**Decision: (c) Exit date already documented — deprecated 2026-Q3.**

Superseded by `mcp__tapps-brain__brain_status`. Gate and action deleted Q3 2026.

*Status: Gate stays; action deleted Q3 2026.*

---

### 6. `pipeline/init.py` — high-engagement `.mcp.json` injection

`env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")` for
`engagement_level == "high"`.

**Decision: Keep as-is — this is platform configuration, not a tapps-mcp gate.**

The env var here is Claude Code's own feature flag being forwarded to consumers
at high engagement. tapps-mcp doesn't own the flag; it configures consumers to
opt in. This is correct behavior and needs no change.

*Status: No change.*

---

### 7. Documentation and template references

Files: `AGENTS.md`, `pipeline/platform_bundles.py`,
`pipeline/platform_hook_templates.py`, `distribution/setup_generator.py`,
`.claude/rules/tapps-pipeline.md`

These mention the env var in prose as instructions/documentation — they are not
runtime gates. They describe the opt-in mechanism for consumers and are correct
as-is (the feature IS opt-in for consumers even though the session-start probe
is now ungated).

*Status: No change.*

---

## Summary Table

| Gate location | Decision | Action |
|---|---|---|
| `collect_session_hive_status` — session-start probe | (a) Ship as default | Gate removed (TAP-2021) |
| `_handle_hive_status` | (c) Exit date 2026-Q3 | Delete with action Q3 2026 |
| `_handle_hive_search` | (c) Exit date 2026-Q3 | Delete with action Q3 2026 |
| `_handle_hive_propagate` | (c) Exit date 2026-Q3 | Delete with action Q3 2026 |
| `_handle_agent_register` | (c) Exit date 2026-Q3 | Delete with action Q3 2026 |
| `pipeline/init.py` injection | Keep — platform config | No change |
| Docs / templates | Keep — instructions | No change |

No gate holds "EXPERIMENTAL forever" status after this audit.
The deprecated actions (groups 2-5) have a concrete exit date: **Q3 2026**.

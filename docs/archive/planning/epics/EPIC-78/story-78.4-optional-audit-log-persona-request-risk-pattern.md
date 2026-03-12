# Story 78.4: Optional audit log when persona request + injection pattern in same message

**Epic:** [EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE](../EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE.md)  
**Priority:** P3 | **LOE:** 0.5 day

## Problem

When `tapps_get_canonical_persona` is called, the host may provide the current user message in context. If that message both requests a persona and contains likely prompt-injection patterns (e.g. “ignore previous instructions”), logging an audit event helps with analysis and security monitoring without blocking the tool.

## Purpose & Intent

This story exists so that **suspicious patterns (persona request + injection-like text) are visible in logs** for security review and auditing. The tool still returns the canonical content and does not block; the audit trail helps operators detect potential abuse or misconfiguration without changing user-visible behavior.

## Tasks

- [ ] In the `tapps_get_canonical_persona` tool handler, after successfully resolving and returning content, optionally check whether a “current user message” or “last user input” is available (e.g. from MCP context or an optional parameter). If not available, skip audit; no change to tool contract required.
- [ ] If user message is available, call `detect_likely_prompt_injection(user_message)` from `tapps_core.security.io_guardrails` (or `tapps_mcp.security.io_guardrails` re-export). If it returns `True`, log an audit event: e.g. `structlog.get_logger().warning("persona_request_with_risk_pattern", persona_name=..., slug=..., source_path=...)` or use an existing metrics/audit hook if the project has one.
- [ ] Do **not** block the tool or alter the return value when a risk pattern is detected; this is audit-only.
- [ ] Document in the same place as 78.3 that this audit exists and what the log key means (optional one sentence).
- [ ] Add a unit test: when the tool is called with an optional user_message that triggers `detect_likely_prompt_injection`, the audit log is emitted (mock or capture logs).

## Acceptance criteria

- [ ] When the tool is called and the provided user message matches `detect_likely_prompt_injection`, a warning/audit log is emitted with persona_name (and optionally slug/source_path).
- [ ] Tool behavior and return value are unchanged; no blocking.
- [ ] Optional: one sentence in doc (78.3 section) about the audit.

## Files

- Same module as 78.1: `packages/tapps-mcp/src/tapps_mcp/server.py` or `server_persona_tools.py` (inside `tapps_get_canonical_persona` handler)
- `packages/tapps-core/src/tapps_core/security/io_guardrails.py` — use existing `detect_likely_prompt_injection`; no changes
- `packages/tapps-mcp/tests/unit/test_canonical_persona.py` (or equivalent) — test that audit log is emitted when user_message is injection-like
- Doc from 78.3 — optional one-line note about audit

## Dependencies

- Story 78.1 (tool) must be implemented; 78.3 doc optional for the one-line audit note.

## References

- tapps_core.security.io_guardrails.detect_likely_prompt_injection; Epic 78

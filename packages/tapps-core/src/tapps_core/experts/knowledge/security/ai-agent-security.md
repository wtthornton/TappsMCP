---
last_reviewed: 2026-03-24
---

# AI and agent security (LLM, tools, MCP)

## Threat model

Agents combine **untrusted natural language**, **tools with side effects**, and **third-party context** (RAG, MCP resources, web). Assume:

- Users and upstream documents may attempt **direct or indirect prompt injection**.
- Tools may be invoked with **attacker-influenced arguments** unless constrained.
- **MCP servers** and **plugins** expand attack surface like any remote capability.

## Prompt injection and control hijacking

1. **Separate instructions from data** — Treat retrieved content, tickets, emails, and web pages as **data**, not trusted system instructions.
2. **System/developer messages** — Keep immutable policy (allow/deny, safety rules) in the highest-priority instruction channel your stack supports.
3. **Output filtering** — Block exfiltration patterns (secrets, env vars, `.ssh`, token formats) before returning to users or downstream tools.
4. **Human-in-the-loop** for irreversible actions (payments, deploys, data deletion).

## Tool and MCP safety

1. **Least privilege** — Each tool should do **one** thing with **minimal** scope (narrow file paths, read-only where possible).
2. **Explicit confirmation** for destructive or cross-security-boundary operations.
3. **Schema validation** — Reject malformed tool arguments; bound string lengths and collection sizes.
4. **Allow lists** — Prefer enumerated commands over arbitrary shell; block path traversal and glob escapes.
5. **Rate limits and quotas** — Mitigate automated abuse and runaway agent loops.

## Supply chain

- **Pin** model vendor SDKs and MCP server versions; review upgrades for new capabilities.
- **Verify** publisher identity for MCP servers and extensions where your host supports it.
- **Sandbox** tool execution (containers, seccomp, separate service accounts).

## Logging and privacy

- **Minimize** prompt/response retention; redact secrets and PII in logs.
- Align with **data-privacy-compliance** guidance when logs contain personal data.

## Testing

- Maintain **regression suites** for injection payloads and tool misuse (see **testing** knowledge on MCP and agent patterns).
- Fuzz tool inputs and adversarial RAG snippets.

## Related knowledge

- **AI frameworks** — orchestration patterns: `../ai-frameworks/mcp-patterns.md`, `../ai-frameworks/llm-integration-patterns.md`
- **Agent learning** — memory and trust boundaries: `../agent-learning/tool-trust-and-safety.md`
- **Privacy / EU AI Act** — `../data-privacy-compliance/eu-ai-act.md`

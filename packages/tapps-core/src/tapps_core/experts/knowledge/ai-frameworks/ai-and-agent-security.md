---
last_reviewed: 2026-03-24
---

# AI frameworks: security cross-reference

Orchestration and framework choices (chains, graphs, MCP tool wiring) must be paired with a **security** review.

## When to use which expert

| Topic | Primary expert (`domain`) |
|-------|---------------------------|
| Prompt injection, tool abuse, MCP hardening, secrets exfiltration | `security` |
| Model routing, RAG design, structured outputs, cost/latency | `ai-frameworks` |
| Memory tiers, feedback loops, adaptive routing | `agent-learning` |

## Authoritative patterns in this repo

- **Threats and controls** — `../security/ai-agent-security.md`
- **MCP protocol and transport** — `mcp-patterns.md`
- **LLM client resilience** — `llm-integration-patterns.md`
- **Trust boundaries for memory/tool output** — `../agent-learning/tool-trust-and-safety.md`

Always call **`tapps_lookup_docs`** for vendor-specific APIs (SDKs change faster than this knowledge base).

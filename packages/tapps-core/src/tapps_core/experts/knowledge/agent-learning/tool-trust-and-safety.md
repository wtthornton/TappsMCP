---
last_reviewed: 2026-03-24
---

# Tool trust, memory, and safety

Agent learning systems (memory stores, feedback trackers, adaptive routing) **must not** blur trust boundaries between **trusted configuration** and **untrusted observations**.

## Principles

1. **Untrusted by default** — User text, retrieved documents, web pages, and MCP resource payloads are **untrusted data** unless cryptographically verified.
2. **Memory poisoning** — Attackers may try to store instructions or “facts” that steer future turns. Apply **validation**, **scopes**, and **human review** for high-impact memories.
3. **Provenance** — Tag memories with **source** (human, agent, inferred) and **scope** (project, branch, session) to enable rollback and contradiction detection.
4. **Decay and GC** — Short **TTL** or decay for context-tier memories reduces long-lived poison.

## Controls

- **Schema validation** on anything written to durable memory.
- **Allow lists** for keys or namespaces that agents may write without review.
- **Rate limits** on automatic capture hooks.
- **Audit** unusual memory growth or sudden topic shifts.

## Security detail

See `../security/ai-agent-security.md` for prompt injection, MCP/tool abuse, and logging minimization.

## Framework patterns

See `pattern-extraction.md` and `memory-systems.md` for constructive learning patterns—always combine with the controls above.

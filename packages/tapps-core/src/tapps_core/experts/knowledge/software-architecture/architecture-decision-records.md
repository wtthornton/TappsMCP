---
last_reviewed: 2026-03-24
---

# Architecture decision records (ADRs)

## Why ADRs

ADRs capture **significant** architectural choices with **context**, **decision**, and **consequences**. They reduce repeated debate, onboard new contributors, and make reversals explicit.

## When to write one

- Selecting **service boundaries**, **data stores**, **messaging**, **auth model**, or **deployment topology**.
- Choosing between **build-vs-buy** options with multi-year cost.
- Any decision that is **expensive to undo** within 6–12 months.

## Lightweight template (Markdown)

1. **Title** — `ADR-NNNN: <short decision>`
2. **Status** — Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
3. **Context** — Forces, constraints, metrics, stakeholders.
4. **Decision** — What we will do (one clear statement).
5. **Consequences** — Positive, negative, and mitigations.
6. **Compliance** — Security, privacy, operability checkpoints.

Store under `docs/adr/` or `architecture/adr/`; link from the main README or CONTRIBUTING.

## Good practices (2026)

- **Time-box** discussion; default to **reversible** decisions for non-critical paths.
- **Link** to diagrams (C4, sequence) without duplicating them inside the ADR body.
- **Supersede**, don’t silently edit accepted ADRs—keep history.
- **Review** ADRs when related code paths change materially (architectural tier in team memory helps).

## Related

- Modularization and boundaries — `modularization-and-boundaries.md`
- MCP server modular design — `mcp-server-architecture.md`

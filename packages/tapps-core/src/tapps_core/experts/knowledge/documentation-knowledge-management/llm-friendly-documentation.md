---
last_reviewed: 2026-03-24
---

# LLM-friendly documentation (without dumbing down humans)

## Goals

Humans and coding agents both consume your docs. Optimize for **clarity**, **determinism**, and **verifiable facts**.

## Practices

1. **Stable anchors** — Meaningful headings; avoid renaming H1/H2 without redirects.
2. **Explicit contracts** — Show request/response examples **and** link to machine-readable schema (OpenAPI, protobuf, JSON Schema).
3. **Version pins** — State **which release** a page describes; agents hallucinate less when versions are explicit.
4. **Failure modes** — Document error codes, retry guidance, and idempotency expectations (pairs with **api-design-integration** content).
5. **Short paths** — Prefer one canonical page per task; use includes or transclusion to avoid drift between duplicates.

## What to avoid

- **Ambiguous “latest”** without a date or semver.
- **Screenshot-only** procedures—add text steps for accessibility and agent parsing.
- **Hidden prerequisites**—list required roles, flags, and quotas up front.

## Governance

- **CODEOWNERS** on docs directories for critical surfaces.
- **Changelog** entries for externally visible behavior; link from reference pages.

## Related

- Technical writing guide — `technical-writing-guide.md`
- AI/agent security when docs are retrieved into agents — `../security/ai-agent-security.md`

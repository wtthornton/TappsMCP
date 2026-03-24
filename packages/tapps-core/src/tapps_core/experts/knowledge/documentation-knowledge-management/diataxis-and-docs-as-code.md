---
last_reviewed: 2026-03-24
---

# Diátaxis and docs-as-code

## Diátaxis (four quadrants)

Structure documentation by **user need**, not by org chart:

| Quadrant | Answers | Examples |
|----------|---------|----------|
| **Tutorials** | “Teach me step-by-step” | First deploy in 15 minutes |
| **How-to guides** | “How do I solve X?” | Rotate API keys, restore backup |
| **Reference** | “What are the knobs?” | OpenAPI, CLI `--help`, config schema |
| **Explanation** | “Why is it like this?” | Architecture, trade-offs, threat model |

**Anti-pattern:** mixing tutorial prose inside reference tables—split pages and cross-link.

## Docs-as-code

- **Version** docs with code (same PR as behavior change).
- **Lint** markdown and snippets (links, code sample extraction where feasible).
- **Preview** on PRs; protect `main` docs from broken internal links.

## Navigation

- Global **sidebar** mirrors Diátaxis buckets.
- Page-level **“See also”** links to the sibling quadrant (e.g. how-to → reference).

## Metrics

- **Time-to-first-success** on top tutorial.
- **Support ticket tags** mapped to missing how-tos.
- **Search logs** for repeated failed queries.

## Related

- Documentation strategy — `documentation-strategy.md`
- API documentation patterns — `api-documentation-patterns.md`

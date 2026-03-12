# Archived Documentation

This directory contains documentation that was archived on 2026-03-12 to reduce noise for LLMs and developers. These files are historical reference only and may be outdated.

## Contents

| Directory | Description |
|---|---|
| `planning/` | All completed epic plans, PRDs, research docs, roadmaps (Epics 0-79, DocsMCP Epics 1-21) |
| `reviews/` | Code reviews, architecture reviews, comparison analyses |
| `diagrams/` | Auto-generated architecture and dependency diagrams (regenerate with `docs_generate_diagram`) |
| `api/` | Auto-generated API reference docs (regenerate with `docs_generate_api`) |
| `reference/` | Supplementary reference docs (migration guides, internal timing docs, composition guides) |

## Why archived?

- All epics and planning work is complete - these docs served their purpose during development
- API and diagram docs can be regenerated from code at any time
- Review docs are point-in-time analyses that are now outdated
- Keeping them in the main docs/ folder confused LLMs and inflated context windows

## How to find things

- For current architecture: see `docs/ARCHITECTURE.md`
- For current config reference: see `docs/CONFIG_REFERENCE.md`
- For setup help: see `docs/ONBOARDING.md` and `docs/TROUBLESHOOTING.md`
- For the full tool list: see `AGENTS.md` (root)

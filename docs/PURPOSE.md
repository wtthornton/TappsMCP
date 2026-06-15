# tapps-mcp — Architecture Overview

## Purpose & Scope

**tapps-mcp** exists to give AI coding assistants **deterministic, checker-backed quality tools** instead of relying on model memory for lint rules, security patterns, and gate thresholds. It provides MCP servers that score code, enforce quality gates, scan dependencies, look up library documentation, and persist cross-session decisions via tapps-brain — for Claude Code, Cursor, VS Code Copilot, and any MCP-capable client.

The monorepo ships **TappsMCP** (32 quality tools), **DocsMCP** (documentation generation and validation), and **tapps-core** (shared infrastructure). Consuming projects bootstrap via `tapps_init` and run the TAPPS quality pipeline (`tapps_session_start` → `tapps_quick_check` → `tapps_validate_changed` → `tapps_checklist`).

## Design Principles

- **Deterministic tools only** — same input → same output; no LLM calls in the tool chain ([ADR-0004](adr/0004-deterministic-tools-only-contract.md))
- **Explicit validation** — `tapps_validate_changed` requires explicit `file_paths` ([ADR-0006](adr/0006-tapps-validate-changed-requires-explicit-file-paths.md))
- **Needs-based MCP surface** — enable 1–3 NLT servers per session, not all six ([ADR-0016](adr/0016-needs-based-nlt-mcp-taxonomy.md))
- **Brain bridge, not duplicate memory** — tapps-brain holds persistence; tapps-mcp exposes a slim MCP memory profile ([ADR-0001](adr/0001-in-process-agentbrain-via-brainbridge.md))
- **Global install from source** — no PyPI publish; consumers pin by git tag ([ADR-0003](adr/0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md))

## Key Architectural Decisions

- **Monorepo** with three packages: `tapps-core`, `tapps-mcp`, `docs-mcp`
- **NLT MCP taxonomy:** `nlt-build` (score/gate/validate), `nlt-memory` (recall/save/handoff), `nlt-setup` (init/upgrade/doctor); situational: `nlt-linear-issues`, `nlt-project-docs`, `nlt-release-ship`
- **Default session bundle:** `developer` = Build + Memory + Linear (~18 eager tools)
- **Docker** images for external distribution and CI

See [docs/adr/README.md](adr/README.md) for the full ADR index.

## Intended Audience

| Audience | What they need |
|---|---|
| Developers | [ONBOARDING.md](ONBOARDING.md), [ARCHITECTURE.md](ARCHITECTURE.md), [api/](api/), tutorials |
| Operators | [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md), [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md), [operations/](operations/) |
| AI agents | [AGENTS.md](../AGENTS.md), [llms.txt](../llms.txt), quality pipeline rules |
| Consumers | [UPGRADE_FOR_CONSUMERS.md](UPGRADE_FOR_CONSUMERS.md), [operations/CONSUMER-REPO-BRAIN-WIRING.md](operations/CONSUMER-REPO-BRAIN-WIRING.md) |

## Quality Attributes

- **Testability** — 6,000+ pytest tests across packages; per-package test runs
- **CI/CD** — GitHub Actions quality gate on changed Python files
- **Deployability** — Docker MCP toolkit, npm wrappers, global `uv tool install`
- **Maintainability** — uv workspace, strict mypy, ruff, structured logging
- **Documentation** — DocsMCP generators, drift/link/completeness checks, Diataxis balance

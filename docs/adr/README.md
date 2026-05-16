# Architecture Decision Records

Architectural decisions for tapps-mcp / tapps-core / docs-mcp / tapps-brain. Each ADR follows the [MADR](https://adr.github.io/madr/) template (Context / Decision / Consequences / Alternatives).

CLAUDE.md and per-package CLAUDE.md files point at ADRs by number rather than embedding the deciding context inline. When a decision changes, supersede the ADR — don't edit history.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-in-process-agentbrain-via-brainbridge.md) | In-process AgentBrain via BrainBridge | Accepted |
| [0002](0002-pin-tapps-brain-version-floor-at-372.md) | Pin tapps-brain version floor at 3.7.2 | Superseded by [0009](0009-pin-tapps-brain-version-floor-at-3170.md) |
| [0003](0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md) | No PyPI or npm publish — global install from local checkout | Accepted |
| [0004](0004-deterministic-tools-only-contract.md) | Deterministic-tools-only contract | Accepted |
| [0005](0005-mcp-server-zombie-cleanup-hook-on-session-start.md) | MCP server zombie-cleanup hook on session start | Accepted |
| [0006](0006-tapps-validate-changed-requires-explicit-file-paths.md) | tapps_validate_changed requires explicit file_paths | Accepted |
| [0007](0007-linear-writes-default-assignee-to-the-agent-never-the-oauth-human.md) | Linear writes default assignee to the agent, never the OAuth human | Accepted |
| [0008](0008-delete-sqlite-persistence-edge-case-tests.md) | Delete SQLite MemoryPersistence edge-case tests | Accepted |
| [0009](0009-pin-tapps-brain-version-floor-at-3170.md) | Pin tapps-brain version floor at 3.17.0 | Superseded by [0010](0010-pin-tapps-brain-version-floor-at-3180.md) |
| [0010](0010-pin-tapps-brain-version-floor-at-3180.md) | Pin tapps-brain version floor at 3.18.0 | Accepted |

## Adding a new ADR

Use `docs_generate_adr` from docs-mcp:

```
docs_generate_adr(
  title="...",
  adr_directory="docs/adr/",
  project_root="<repo root>",
  context="...",
  decision="...",
  consequences="...",
  status="accepted",
)
```

Numbering auto-increments from the existing files in `docs/adr/`. Update this README's index after the file lands.

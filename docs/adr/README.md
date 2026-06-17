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
| [0010](0010-pin-tapps-brain-version-floor-at-3180.md) | Pin tapps-brain version floor at 3.18.0 | Superseded by [0011](0011-pin-tapps-brain-by-tag.md) |
| [0011](0011-pin-tapps-brain-by-tag.md) | Pin tapps-brain by release tag instead of commit SHA | Accepted |
| [0012](0012-brain-capability-profile-per-consumer-role.md) | Select the tapps-brain capability profile per consumer role | Accepted |
| [0013](0013-pin-tapps-brain-version-floor-at-3240.md) | Pin tapps-brain version floor at 3.24.0 | Accepted (amended by [0015](0015-require-tapps-brain-docs-lookup-at-3240.md)) |
| [0014](0014-brain-central-doc-rag-big-bang.md) | Brain-central doc RAG (big-bang cutover) | Accepted |
| [0015](0015-require-tapps-brain-docs-lookup-at-3240.md) | Require tapps-brain docs_lookup at 3.24.0+ | Accepted |
| [0016](0016-needs-based-nlt-mcp-taxonomy.md) | Needs-based NLT MCP taxonomy (Build / Memory / Setup) | Accepted (default bundle superseded by [0018](0018-deploy-all-six-nlt-mcp-servers-by-default.md)) |
| [0017](0017-function-level-call-graph-python-first.md) | Function-level call graph (Python-first) | Accepted |
| [0018](0018-deploy-all-six-nlt-mcp-servers-by-default.md) | Deploy all six NLT MCP servers by default (full bundle) | Accepted |
| [0019](0019-blue-green-dev-monorepo-mcp-deploy.md) | Blue/green dev-monorepo MCP deploy | Accepted (default superseded by [0020](0020-global-uv-tool-default-blue-green-opt-in.md)) |
| [0020](0020-global-uv-tool-default-blue-green-opt-in.md) | Global uv-tool default; blue/green deploy opt-in | Accepted (inplace default superseded by [0023](0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md)) |
| [0023](0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md) | Immutable MCP CLI releases — no in-place uv reinstall | Accepted |
| [0021](0021-usage-gap-doc-lookup-telemetry-and-import-cache-aliases.md) | Usage-gap doc lookup: import/cache aliases + cross-channel telemetry | Accepted |
| [0022](0022-agent-hint-contract-lookup-and-validation-semantics.md) | Agent hint contract — lookup timing and validation semantics | Accepted |
| [0024](0024-shared-http-mcp-fleet.md) | Shared HTTP MCP fleet for multi-window Cursor | Accepted |

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

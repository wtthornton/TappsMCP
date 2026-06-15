# tapps-core

Shared infrastructure library for the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP). Provides config, security, logging, knowledge lookup, metrics, adaptive scoring, and the bridge into [tapps-brain](https://github.com/wtthornton/tapps-brain) — everything that both [tapps-mcp](../tapps-mcp) (code-quality MCP) and [docs-mcp](../docs-mcp) (documentation MCP) build on. tapps-core has no MCP tools of its own; it is a pure library installed transitively via the workspace.

## Installation

tapps-core is **not published to PyPI**. It is a workspace member resolved automatically when you install tapps-mcp or docs-mcp from this checkout:

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv sync --all-packages           # installs every workspace member (tapps-core, tapps-mcp, docs-mcp); tapps-brain is an external repo, cloned separately
```

To use tapps-core directly inside this workspace:

```python
from tapps_core.config import load_settings
from tapps_core.security.path_validator import PathValidator
from tapps_core.knowledge.lookup import lookup_docs
```

## Modules

| Module | Purpose |
|---|---|
| `config/` | Pydantic v2 + YAML + env-var settings (`TappsMCPSettings`, `MemorySettings`). Includes the engagement-aware Linear gate flags `linear_enforce_gate` (TAP-981, write gate) and `linear_enforce_cache_gate` (TAP-1224, cache-first read gate; `off`/`warn`/`block`). |
| `security/` | Path validation, IO guardrails, secret scanning, governance. |
| `common/` | Exceptions, structured logging (structlog), shared models, utilities. |
| `knowledge/` | Context7 / LlmsTxt doc lookup, cache, fuzzy matching, RAG safety (`docs_via_brain` routing per ADR-0014). |
| `brain_bridge.py` | `BrainBridge` adapter — in-process or HTTP access to tapps-brain. Replaces the removed `tapps_core.memory.*` shims (TAP-1995). |
| `metrics/` | Collector, dashboard, alerts, trends, OpenTelemetry export. |
| `adaptive/` | Adaptive scoring weights, expert voting, weight distribution. |
| `prompts/` | Workflow prompt templates. |

## Top public APIs

The four most-used entry points by tapps-mcp and docs-mcp:

1. `tapps_core.config.settings.load_settings()` — load + cache the root `TappsMCPSettings` singleton.
2. `tapps_core.security.path_validator.PathValidator` — gate every file write to keep tools inside `project_root`.
3. `tapps_core.knowledge.lookup.lookup_docs(library, topic)` — backend for `tapps_lookup_docs`; deterministic doc retrieval.
4. `tapps_core.brain_bridge.BrainBridge` — in-process adapter that lets tapps-mcp talk to tapps-brain without a network hop. See [ADR-0001](../../docs/adr/0001-in-process-agentbrain-via-brainbridge.md).

## Memory subsystem

Memory persistence lives in [tapps-brain](https://github.com/wtthornton/tapps-brain). tapps-mcp and tapps-core access it through `BrainBridge` (`tapps_core.brain_bridge`):

```python
from tapps_core.brain_bridge import BrainBridge
```

Consumer-facing surface: `uv run tapps-mcp memory …` CLI or `nlt-memory` MCP profile — not a standalone `tapps_memory` MCP tool (removed v3.12.0).

See the [tapps-brain repo](https://github.com/wtthornton/tapps-brain) for storage internals (Postgres in Docker, HTTP at `localhost:8080`), retrieval, and operational docs.

## Documentation

- [Workspace AGENTS.md](../../AGENTS.md) — how AI assistants consume the platform.
- [Workspace CLAUDE.md](../../CLAUDE.md) — repo conventions, monorepo layout, known gotchas.
- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — module map for every workspace package.
- Issues: [github.com/wtthornton/TappsMCP/issues](https://github.com/wtthornton/TappsMCP/issues) (Linear project: TappsMCP Platform).

## License

MIT.

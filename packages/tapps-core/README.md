# tapps-core

Shared infrastructure library for the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP).

## Overview

tapps-core provides the common foundation used by both tapps-mcp and docs-mcp:

- **config/** - Settings management (Pydantic v2, YAML, env vars)
- **security/** - Path validation, IO guardrails, secret scanning, governance
- **common/** - Exceptions, structured logging (structlog), shared models, utilities
- **knowledge/** - Context7/LlmsTxt doc lookup, cache, fuzzy matching, RAG safety
- **experts/** - 17 domain experts with 171 knowledge files, keyword + vector RAG
- **memory/** - Re-export shims delegating to [tapps-brain](https://github.com/wtthornton/tapps-brain)
- **metrics/** - Collector, dashboard, alerts, trends, OpenTelemetry export
- **adaptive/** - Adaptive scoring weights, expert voting, weight distribution
- **prompts/** - Workflow prompt templates

## Memory subsystem

The memory package (`tapps_core.memory.*`) re-exports from the standalone [tapps-brain](https://github.com/wtthornton/tapps-brain) library. This provides backward compatibility for existing code:

```python
# Both work - tapps_brain is preferred for new code
from tapps_brain.store import MemoryStore       # direct (preferred)
from tapps_core.memory.store import MemoryStore  # re-export (deprecated)
```

The one exception is `tapps_core.memory.injection`, which is a bridge adapter that translates TappsMCP settings into tapps-brain's `InjectionConfig`.

## Installation

tapps-core is installed automatically as a dependency of tapps-mcp or docs-mcp:

```bash
pip install tapps-mcp   # installs tapps-core + tapps-brain
pip install docs-mcp    # installs tapps-core + tapps-brain
```

## License

MIT

---

Part of the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP).

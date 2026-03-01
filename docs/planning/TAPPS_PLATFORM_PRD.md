# Tapps Platform PRD — Monorepo + Shared Core + DocsMCP

**Version:** 1.0.0-draft
**Date:** 2026-02-28
**Author:** TappsMCP Team
**Status:** Draft
**Depends on:** [DOCSMCP_PRD.md](DOCSMCP_PRD.md) (DocsMCP feature specification)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Architecture Decision](#3-architecture-decision)
4. [Current State Analysis](#4-current-state-analysis)
5. [Target Architecture](#5-target-architecture)
6. [Extraction Plan: tapps-core](#6-extraction-plan-tapps-core)
7. [Package Specifications](#7-package-specifications)
8. [FastMCP Composition Layer](#8-fastmcp-composition-layer)
9. [Migration Strategy](#9-migration-strategy)
10. [Epic & Story Breakdown](#10-epic--story-breakdown)
11. [Distribution Strategy](#11-distribution-strategy)
12. [Testing Strategy](#12-testing-strategy)
13. [Risk Matrix](#13-risk-matrix)
14. [Success Criteria](#14-success-criteria)
15. [References](#15-references)

---

## 1. Executive Summary

This PRD defines the restructuring of TappsMCP from a single-package project into a **uv workspace monorepo** containing three packages:

| Package | PyPI Name | Purpose | Tools |
|---|---|---|---|
| **tapps-core** | `tapps-core` | Shared infrastructure (config, security, logging, knowledge, memory, experts, metrics) | 0 (library) |
| **tapps-mcp** | `tapps-mcp` | Code quality MCP server (scoring, gates, tools, validation) | 28 |
| **docs-mcp** | `docs-mcp` | Documentation generation and maintenance MCP server | 18 |

All three packages live in a single GitHub repository (`tapps-platform`) with a shared `uv.lock`. Users install what they need. FastMCP 3.0's `mount()` enables optional composition into a single server.

### Why This Architecture

| Constraint | Solution |
|---|---|
| **Cursor 40-tool hard limit** | Separate servers: 28 + 18, each under limit |
| **Claude Code context overhead** | Users choose: lean (one server) or full (composed) |
| **70-80% shared infrastructure** | `tapps-core` library eliminates duplication |
| **2026 MCP best practice** | "Focused servers + composition" (AWS, IBM, community consensus) |
| **FastMCP 3.0 composition** | Native `mount()` makes combining trivial |
| **uv workspace maturity** | Proven at scale (Airflow: 120+ distributions) |
| **Single repo benefits** | Atomic PRs, shared CI, one place to star/fork |

---

## 2. Problem Statement

### Immediate Problem

We need to build DocsMCP (documentation generation MCP server) but it requires infrastructure that already exists in TappsMCP:

- Expert system (17 domains, RAG engine, 139 knowledge files)
- Memory system (SQLite persistence, decay, retrieval, injection)
- Knowledge lookup (Context7, cache, fuzzy matching, circuit breaker)
- Security sandbox (path validation, content safety)
- Configuration (settings, engagement levels, presets)
- Metrics/observability (collector, dashboard, feedback)
- Project analysis (profiler, AST parser, tech stack detection)

Building DocsMCP from scratch duplicates ~15,000 lines of infrastructure code and creates double maintenance burden.

### Structural Problem

TappsMCP was built as a monolith. As the platform grows (DocsMCP now, potentially more servers later), the single-package architecture doesn't scale:

- Can't share code across servers without duplication
- Can't respect client tool limits (Cursor: 40 tools)
- Can't let users install only what they need
- Can't evolve servers independently

### Client Constraints (Research-Validated)

| Client | Tool Limit | Context Impact | Source |
|---|---|---|---|
| **Cursor** | **40 tools hard limit** | First 40 only; rest inaccessible | [Cursor Forum](https://forum.cursor.com/t/mcp-server-40-tool-limit-in-cursor-is-this-frustrating-your-workflow/81627) |
| **Claude Code** | No hard limit | Tool Search activates at >10% context; 473 tools = 150K tokens | [GitHub Issue #3036](https://github.com/anthropics/claude-code/issues/3036) |
| **GitHub Copilot** | 128 tools | Manageable for composed server | Microsoft docs |

Combined TappsMCP (28) + DocsMCP (18) = **46 tools** — exceeds Cursor's limit by 6.

---

## 3. Architecture Decision

### ADR-001: Monorepo with Shared Core and FastMCP Composition

**Status:** Proposed
**Context:** Need to share infrastructure between TappsMCP and DocsMCP while respecting client tool limits.
**Decision:** Restructure into uv workspace monorepo with tapps-core shared library. Use FastMCP 3.0 `mount()` for optional composition.

**Alternatives considered:**

| # | Architecture | Verdict | Reason |
|---|---|---|---|
| 1 | Fully separate servers | Rejected | Duplicates 70-80% infrastructure |
| 2 | MCP-to-MCP protocol | Deferred | Agent-to-agent not in MCP spec yet |
| 3 | Shared library (separate repos) | Acceptable | Cross-repo coordination overhead |
| 4 | Extension within TappsMCP | Rejected | Breaks Cursor 40-tool limit |
| **5** | **Monorepo + shared core** | **Selected** | Best balance of all factors |

**Consequences:**
- One-time refactoring investment (~2-3 weeks for extraction)
- Three PyPI packages to version and publish
- uv workspace adds minor build complexity
- Pattern scales to future MCP servers

---

## 4. Current State Analysis

### 4.1 TappsMCP Module Dependency Map

Based on thorough codebase analysis (~300 Python files, ~30,000 LOC):

#### Tier 1: Core Infrastructure (Extract to tapps-core)

| Package | LOC | Imports From | Imported By | Notes |
|---|---|---|---|---|
| `common/` | ~800 | ~~experts, pipeline~~ (refactorable) | 25+ files | Logging, exceptions, models, utils |
| `config/` | ~600 | None | 15+ files | Settings, YAML, presets, weights |
| `security/` | ~1,200 | common, ~~scoring.models~~ | memory, knowledge, validators | Path validation, sandboxing, secrets |
| `prompts/` | ~300 | `__version__` only | pipeline, server | Resource loader, templates |

**Extraction complexity:** Low. ~2,900 LOC. 2-3 circular imports to refactor.

#### Tier 2: Core Subsystems (Extract to tapps-core)

| Package | LOC | Imports From | Imported By | Notes |
|---|---|---|---|---|
| `knowledge/` | ~3,500 | Internal only | memory, validators, server | Context7, cache, RAG, fuzzy matching |
| `memory/` | ~2,500 | knowledge.rag_safety | server_helpers, server_memory_tools | SQLite persistence, decay, retrieval |
| `experts/` | ~3,000 + 139 knowledge files | Internal only | common/nudges, server | Domain experts, RAG engine, confidence |
| `metrics/` | ~4,000 | common.utils | server_metrics_tools | Collector, dashboard, feedback, OTEL |
| `adaptive/` | ~1,500 | None (self-contained) | None (unused) | Weight adjustment, voting engine |

**Extraction complexity:** Medium. ~14,500 LOC. knowledge ↔ memory coupling needs refactoring.

#### Tier 3: Quality-Specific (Stay in tapps-mcp)

| Package | LOC | Purpose |
|---|---|---|
| `scoring/` | ~1,500 | 7-category scoring engine |
| `tools/` | ~3,000 | ruff, mypy, bandit, radon, vulture, pip-audit |
| `gates/` | ~500 | Quality gate evaluation |
| `project/` | ~2,000 | Profiler, AST parser, impact analyzer, report |
| `validators/` | ~800 | Dockerfile, docker-compose, MQTT, etc. |

#### Tier 4: Distribution (Stay in tapps-mcp)

| Package | LOC | Purpose |
|---|---|---|
| `pipeline/` | ~4,000 | Init, upgrade, platform generators, GitHub integration |
| `distribution/` | ~500 | Doctor, exe manager |

### 4.2 Circular Dependencies to Resolve

| Dependency | Current | Resolution |
|---|---|---|
| `common/nudges.py` → `experts.models` | Imports `LOW_CONFIDENCE_THRESHOLD` | Move constant to `common/constants.py` |
| `common/nudges.py` → `pipeline.models` | Imports `STAGE_ORDER`, `PipelineStage` | Move stage definitions to `common/models.py` |
| `security/` → `scoring.models` | Imports `SecurityIssue` dataclass | Move `SecurityIssue` to `common/models.py` |
| `security/` → `tools.bandit` | Imports `run_bandit_check` | Make bandit integration optional (feature flag) |
| `memory/` → `knowledge.rag_safety` | Content safety check | Extract `rag_safety` to `security/content_safety.py` |

---

## 5. Target Architecture

### 5.1 Repository Structure

```
tapps-platform/                              ← GitHub repo (renamed from TappMCP)
├── pyproject.toml                           ← uv workspace root
├── uv.lock                                  ← single lockfile
├── README.md                                ← platform overview
├── CLAUDE.md                                ← development instructions
├── LICENSE
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                           ← shared CI (test all packages)
│   │   ├── publish-core.yml                 ← PyPI publish tapps-core
│   │   ├── publish-tapps-mcp.yml            ← PyPI publish tapps-mcp
│   │   └── publish-docs-mcp.yml             ← PyPI publish docs-mcp
│   └── ISSUE_TEMPLATE/
├── docs/
│   └── planning/                            ← epics, PRDs (existing)
├── packages/
│   ├── tapps-core/                          ← SHARED INFRASTRUCTURE
│   │   ├── pyproject.toml                   ← name = "tapps-core"
│   │   ├── src/
│   │   │   └── tapps_core/
│   │   │       ├── __init__.py              ← version, public API
│   │   │       ├── py.typed
│   │   │       ├── common/                  ← logging, exceptions, models, utils
│   │   │       ├── config/                  ← settings, YAML, presets
│   │   │       ├── security/                ← path_validator, io_guardrails, content_safety
│   │   │       ├── knowledge/               ← Context7, cache, RAG, fuzzy matching
│   │   │       ├── memory/                  ← SQLite persistence, store, retrieval
│   │   │       ├── experts/                 ← domain experts, RAG engine, 139 knowledge files
│   │   │       ├── metrics/                 ← collector, dashboard, feedback, OTEL
│   │   │       ├── adaptive/                ← weights, voting, persistence
│   │   │       └── prompts/                 ← resource loader, base templates
│   │   └── tests/
│   │       ├── unit/
│   │       └── conftest.py
│   ├── tapps-mcp/                           ← CODE QUALITY SERVER
│   │   ├── pyproject.toml                   ← name = "tapps-mcp", depends on tapps-core
│   │   ├── src/
│   │   │   └── tapps_mcp/
│   │   │       ├── __init__.py
│   │   │       ├── py.typed
│   │   │       ├── cli.py                   ← Click CLI
│   │   │       ├── server.py                ← FastMCP("TappsMCP"), core tools
│   │   │       ├── server_scoring_tools.py
│   │   │       ├── server_pipeline_tools.py
│   │   │       ├── server_metrics_tools.py
│   │   │       ├── server_analysis_tools.py
│   │   │       ├── server_memory_tools.py
│   │   │       ├── server_helpers.py
│   │   │       ├── server_resources.py
│   │   │       ├── scoring/                 ← 7-category scoring engine
│   │   │       ├── gates/                   ← quality gate evaluation
│   │   │       ├── tools/                   ← ruff, mypy, bandit, radon, vulture
│   │   │       ├── project/                 ← profiler, AST parser, impact analyzer
│   │   │       ├── validators/              ← config validators
│   │   │       ├── pipeline/                ← init, upgrade, platform generators
│   │   │       ├── distribution/            ← doctor, exe manager
│   │   │       └── prompts/                 ← quality-specific templates
│   │   └── tests/
│   │       ├── unit/                        ← existing 2700+ tests (migrated)
│   │       ├── integration/
│   │       └── conftest.py
│   └── docs-mcp/                            ← DOCUMENTATION SERVER
│       ├── pyproject.toml                   ← name = "docs-mcp", depends on tapps-core
│       ├── src/
│       │   └── docs_mcp/
│       │       ├── __init__.py
│       │       ├── py.typed
│       │       ├── cli.py                   ← Click CLI
│       │       ├── server.py                ← FastMCP("DocsMCP"), core tools
│       │       ├── server_gen_tools.py      ← generation tools
│       │       ├── server_val_tools.py      ← validation tools
│       │       ├── server_analysis.py       ← analysis tools
│       │       ├── server_helpers.py
│       │       ├── extractors/              ← Python AST, generic, (future: tree-sitter)
│       │       ├── analyzers/               ← module_map, api_surface, git_history
│       │       ├── generators/              ← readme, api, changelog, adr, diagram, guides
│       │       ├── validators/              ← drift, completeness, links, freshness
│       │       ├── templates/               ← Jinja2 templates for all doc types
│       │       └── prompts/                 ← docs-specific prompt templates
│       └── tests/
│           ├── unit/
│           ├── integration/
│           ├── fixtures/                    ← sample projects for testing
│           └── conftest.py
└── examples/
    ├── combined_server.py                   ← mount() composition example
    ├── tapps_only.py                        ← standalone quality server
    └── docs_only.py                         ← standalone docs server
```

### 5.2 Package Dependency Graph

```
                 tapps-core (shared library)
                /           |              \
         tapps-mcp      docs-mcp       (future servers)
        (28 tools)     (18 tools)
              \           /
               \         /
          FastMCP mount() composition (optional)
                    |
            tapps-platform (46 tools, combined)
```

### 5.3 User Installation Options

```bash
# Quality only (most users today)
uv add tapps-mcp

# Documentation only
uv add docs-mcp

# Both (separate servers — Cursor-friendly)
uv add tapps-mcp docs-mcp

# Combined server (Claude Code power users)
uv add tapps-mcp docs-mcp
# Then use examples/combined_server.py
```

---

## 6. Extraction Plan: tapps-core

### 6.1 What Moves to tapps-core

| Current Path | New Path | Changes Required |
|---|---|---|
| `tapps_mcp/common/` | `tapps_core/common/` | Remove imports of experts.models, pipeline.models |
| `tapps_mcp/config/` | `tapps_core/config/` | None — already standalone |
| `tapps_mcp/security/path_validator.py` | `tapps_core/security/path_validator.py` | None |
| `tapps_mcp/security/io_guardrails.py` | `tapps_core/security/io_guardrails.py` | None |
| `tapps_mcp/security/governance.py` | `tapps_core/security/governance.py` | None |
| `tapps_mcp/security/api_keys.py` | `tapps_core/security/api_keys.py` | None |
| `tapps_mcp/security/secret_scanner.py` | `tapps_core/security/secret_scanner.py` | None |
| `tapps_mcp/security/security_scanner.py` | Stays in tapps-mcp | Depends on tools.bandit |
| `tapps_mcp/knowledge/` | `tapps_core/knowledge/` | None — already self-contained |
| `tapps_mcp/knowledge/rag_safety.py` | `tapps_core/security/content_safety.py` | Rename + move to resolve memory↔knowledge cycle |
| `tapps_mcp/memory/` | `tapps_core/memory/` | Update import: knowledge.rag_safety → security.content_safety |
| `tapps_mcp/experts/` | `tapps_core/experts/` | None — self-contained |
| `tapps_mcp/experts/knowledge/` | `tapps_core/experts/knowledge/` | 139 markdown files, no code changes |
| `tapps_mcp/metrics/` | `tapps_core/metrics/` | Update import: common.utils |
| `tapps_mcp/adaptive/` | `tapps_core/adaptive/` | None — already self-contained |
| `tapps_mcp/prompts/prompt_loader.py` | `tapps_core/prompts/prompt_loader.py` | Parameterize package name |

### 6.2 What Stays in tapps-mcp

| Package | Reason |
|---|---|
| `scoring/` | Quality-specific scoring engine |
| `tools/` | Quality-specific external tool runners |
| `gates/` | Quality-specific gate evaluation |
| `project/` | Quality-specific code analysis (depends on scoring, gates) |
| `validators/` | Quality-specific config validation |
| `pipeline/` | TappsMCP-specific project bootstrapping |
| `distribution/` | TappsMCP-specific deployment |
| `security/security_scanner.py` | Depends on tools.bandit (quality-specific) |
| `server*.py` | TappsMCP MCP tool handlers |
| `cli.py` | TappsMCP CLI |

### 6.3 Circular Dependency Resolutions

**Resolution 1: `common/nudges.py` → `experts.models.LOW_CONFIDENCE_THRESHOLD`**
```python
# Before (in common/nudges.py):
from tapps_mcp.experts.models import LOW_CONFIDENCE_THRESHOLD

# After (in tapps_core/common/constants.py):
LOW_CONFIDENCE_THRESHOLD = 0.4  # Move constant here
# experts/models.py imports from common/constants.py instead
```

**Resolution 2: `common/nudges.py` → `pipeline.models.STAGE_ORDER`**
```python
# Before (in common/nudges.py):
from tapps_mcp.pipeline.models import STAGE_ORDER, STAGE_TOOLS, PipelineStage

# After: Move stage definitions to tapps_core/common/pipeline_models.py
# pipeline/models.py re-exports from common/pipeline_models.py
```

**Resolution 3: `security/` → `scoring.models.SecurityIssue`**
```python
# Before (in security/security_scanner.py):
from tapps_mcp.scoring.models import SecurityIssue

# After: Move SecurityIssue to tapps_core/common/models.py
# scoring/models.py imports from common/models.py
```

**Resolution 4: `memory/` → `knowledge/rag_safety.py`**
```python
# Before (in memory/store.py):
from tapps_mcp.knowledge.rag_safety import check_content_safety

# After: Move rag_safety.py to tapps_core/security/content_safety.py
# Both memory/ and knowledge/ import from security/content_safety.py
```

---

## 7. Package Specifications

### 7.1 tapps-core

```toml
# packages/tapps-core/pyproject.toml
[project]
name = "tapps-core"
version = "1.0.0"
description = "Shared infrastructure for the Tapps MCP platform"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
vector = ["faiss-cpu>=1.7", "sentence-transformers>=2.0", "numpy>=1.26"]
```

**Public API surface:**
```python
# tapps_core — public exports
from tapps_core.config import load_settings, TappsCoreSettings
from tapps_core.common import get_logger, PathValidationError
from tapps_core.security import PathValidator, check_content_safety
from tapps_core.knowledge import KBCache, LookupEngine
from tapps_core.memory import MemoryStore, MemoryEntry
from tapps_core.experts import ExpertEngine, ExpertRegistry
from tapps_core.metrics import MetricsCollector, MetricsDashboard
from tapps_core.adaptive import ScoringWrapper, WeightDistributor
```

### 7.2 tapps-mcp

```toml
# packages/tapps-mcp/pyproject.toml
[project]
name = "tapps-mcp"
version = "0.6.0"  # next release after 0.5.0
description = "MCP server for deterministic code quality tools"
requires-python = ">=3.12"
dependencies = [
    "tapps-core>=1.0.0",
    "mcp[cli]>=1.26.0",
    "click>=8.0",
    "jinja2>=3.0",
]

[tool.uv.sources]
tapps-core = { workspace = true }
```

### 7.3 docs-mcp

```toml
# packages/docs-mcp/pyproject.toml
[project]
name = "docs-mcp"
version = "0.1.0"
description = "MCP server for documentation generation and maintenance"
requires-python = ">=3.12"
dependencies = [
    "tapps-core>=1.0.0",
    "mcp[cli]>=1.26.0",
    "click>=8.0",
    "jinja2>=3.0",
    "gitpython>=3.1",
]

[tool.uv.sources]
tapps-core = { workspace = true }
```

### 7.4 Workspace Root

```toml
# pyproject.toml (workspace root)
[project]
name = "tapps-platform"
version = "1.0.0"
description = "Tapps MCP Platform — code quality + documentation servers"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
tapps-core = { workspace = true }
tapps-mcp = { workspace = true }
docs-mcp = { workspace = true }

[tool.pytest.ini_options]
testpaths = ["packages/tapps-core/tests", "packages/tapps-mcp/tests", "packages/docs-mcp/tests"]

[tool.mypy]
strict = true
packages = ["tapps_core", "tapps_mcp", "docs_mcp"]

[tool.ruff]
line-length = 100
src = ["packages/tapps-core/src", "packages/tapps-mcp/src", "packages/docs-mcp/src"]
```

---

## 8. FastMCP Composition Layer

### 8.1 Standalone Servers (Default — Cursor-friendly)

Users configure each server independently in their MCP client settings:

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "command": "uvx",
      "args": ["tapps-mcp", "serve"]
    },
    "docs-mcp": {
      "command": "uvx",
      "args": ["docs-mcp", "serve"]
    }
  }
}
```

Each server runs independently. 28 + 18 tools. Cursor users enable per-project.

### 8.2 Composed Server (Optional — Claude Code power users)

```python
# examples/combined_server.py
from tapps_mcp.server import mcp as tapps_server
from docs_mcp.server import mcp as docs_server
from fastmcp import FastMCP

platform = FastMCP("TappsPlatform")
platform.mount(tapps_server)                          # 28 tools (no prefix)
platform.mount(docs_server, namespace="docs")         # 18 tools as docs_*

if __name__ == "__main__":
    platform.run()
```

Or via CLI:
```bash
# Combined server
tapps-platform serve  # runs composed server with both mounted
```

### 8.3 Namespace Strategy

When composed, DocsMCP tools get a `docs_` prefix to avoid collision:

| Standalone Name | Composed Name | Reason |
|---|---|---|
| `docs_session_start` | `docs_docs_session_start` | Avoid collision with `tapps_session_start` |
| `docs_generate_readme` | `docs_docs_generate_readme` | Unique namespace |
| `tapps_score_file` | `tapps_score_file` | No prefix (primary server) |

**Alternative:** Mount without namespace and rely on distinct `tapps_*` / `docs_*` naming:

```python
platform.mount(tapps_server)  # tapps_* tools
platform.mount(docs_server)   # docs_* tools — already prefixed
```

This is cleaner since both servers already use distinct prefixes. **Recommended approach.**

### 8.4 Shared State in Composition

When mounted together, both servers share:
- **Memory store:** Same SQLite database via `tapps_core.memory`
- **Knowledge cache:** Same Context7 cache via `tapps_core.knowledge`
- **Expert engine:** Same 17 domain experts via `tapps_core.experts`
- **Config:** Same settings via `tapps_core.config`
- **Metrics:** Same collector via `tapps_core.metrics`

This is automatic because both import from `tapps_core` — singletons are shared in-process.

---

## 9. Migration Strategy

### 9.1 Phased Approach

**Phase 1: Monorepo Restructure** (Epics 0-2, ~3 weeks)
- Create uv workspace structure
- Extract tapps-core from TappsMCP
- Migrate TappsMCP to workspace package
- All 2700+ existing tests pass in new structure

**Phase 2: DocsMCP Foundation** (Epics 3-5, ~4 weeks)
- DocsMCP package scaffolding
- Code extraction engine (Python AST)
- Git analysis engine

**Phase 3: DocsMCP Generation** (Epics 6-8, ~5 weeks)
- README, API docs, changelog generators
- Diagram generation
- ADR and guide generators

**Phase 4: DocsMCP Validation** (Epics 9-10, ~3 weeks)
- Drift detection, completeness, link validation
- Project scan and workflow

**Phase 5: Composition & Distribution** (Epics 11-12, ~2 weeks)
- FastMCP composition layer
- PyPI publishing for all 3 packages
- Docker, npm wrappers

### 9.2 Migration Principles

1. **Green tests at every step** — No epic completes without all tests passing
2. **No breaking changes to TappsMCP consumers** — `pip install tapps-mcp` still works
3. **tapps-core is an internal dependency** — Consuming projects don't interact with it directly
4. **Import path compatibility** — `from tapps_mcp.X import Y` continues to work via re-exports
5. **Version coordination** — All packages in lockstep during v1.0; independent after stabilization

### 9.3 Import Compatibility Layer

To avoid breaking existing TappsMCP consumers, the `tapps_mcp` package re-exports from `tapps_core`:

```python
# packages/tapps-mcp/src/tapps_mcp/config/__init__.py
# Re-export for backward compatibility
from tapps_core.config import *  # noqa: F401,F403
from tapps_core.config import load_settings, TappsCoreSettings as TappsMCPSettings
```

This means `from tapps_mcp.config import load_settings` still works, but internally it's `tapps_core.config.load_settings`.

---

## 10. Epic & Story Breakdown

---

### PHASE 1: MONOREPO RESTRUCTURE

---

### Epic 0: Workspace Foundation

**Goal:** Create the uv workspace structure with build tooling.
**Duration:** 3-4 days
**Risk:** Low

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 0.1 | Create workspace root | Create root `pyproject.toml` with `[tool.uv.workspace]`, configure members, shared tool configs (ruff, mypy, pytest) | 3h | — |
| 0.2 | Create tapps-core scaffold | Create `packages/tapps-core/` with `pyproject.toml`, empty `src/tapps_core/__init__.py`, `py.typed`, basic test structure | 2h | 0.1 |
| 0.3 | Create tapps-mcp scaffold | Create `packages/tapps-mcp/` with `pyproject.toml` depending on `tapps-core`, empty `src/tapps_mcp/__init__.py` | 2h | 0.1 |
| 0.4 | Create docs-mcp scaffold | Create `packages/docs-mcp/` with `pyproject.toml` depending on `tapps-core`, empty `src/docs_mcp/__init__.py` | 2h | 0.1 |
| 0.5 | Configure shared CI | GitHub Actions workflow that runs `uv sync --all-packages`, tests all packages, publishes independently | 4h | 0.1-0.4 |
| 0.6 | Configure shared linting/typing | Single ruff and mypy config at workspace root covering all packages. Verify `uv run ruff check`, `uv run mypy` work across workspace | 3h | 0.1-0.4 |
| 0.7 | Lock file and dependency resolution | Run `uv lock`, verify all packages resolve. Test `uv sync -p tapps-core`, `uv sync -p tapps-mcp`, `uv sync -p docs-mcp` individually | 2h | 0.1-0.6 |

**Acceptance criteria:**
- `uv sync --all-packages` succeeds
- `uv run pytest packages/tapps-core/tests/` runs (even if no tests yet)
- `uv run ruff check packages/` passes
- `uv run mypy --strict packages/tapps-core/src/ packages/tapps-mcp/src/ packages/docs-mcp/src/` passes
- Each package can be installed independently: `uv pip install -e packages/tapps-core`

---

### Epic 1: tapps-core Extraction — Tier 1 (Infrastructure)

**Goal:** Extract zero-dependency infrastructure packages (common, config, security, prompts).
**Duration:** 4-5 days
**Risk:** Medium (import path changes across 200+ files)

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 1.1 | Resolve circular dependencies in common/ | Move `LOW_CONFIDENCE_THRESHOLD` to `common/constants.py`. Move `STAGE_ORDER`, `STAGE_TOOLS`, `PipelineStage` to `common/pipeline_models.py`. Move `SecurityIssue` to `common/models.py`. Update all importers. | 4h | 0.* |
| 1.2 | Extract common/ to tapps-core | Copy `common/` to `packages/tapps-core/src/tapps_core/common/`. Update internal imports. Create `__init__.py` with public API. | 3h | 1.1 |
| 1.3 | Extract config/ to tapps-core | Copy `config/` to `packages/tapps-core/src/tapps_core/config/`. Copy `default.yaml`. Update imports. | 2h | 1.2 |
| 1.4 | Extract security/ (core parts) to tapps-core | Copy `path_validator.py`, `io_guardrails.py`, `governance.py`, `api_keys.py`, `secret_scanner.py` to tapps-core. Leave `security_scanner.py` in tapps-mcp (bandit dependency). | 3h | 1.2 |
| 1.5 | Move rag_safety to security/content_safety | Move `knowledge/rag_safety.py` to `tapps_core/security/content_safety.py`. Update all importers (memory/store.py, memory/injection.py, knowledge/lookup.py). | 3h | 1.4 |
| 1.6 | Extract prompts/ to tapps-core | Copy `prompt_loader.py` to tapps-core. Parameterize package name for `importlib.resources`. Copy base template files shared across servers. | 3h | 1.2 |
| 1.7 | Create compatibility re-exports in tapps-mcp | Add `tapps_mcp.common`, `tapps_mcp.config`, `tapps_mcp.security` modules that re-export from `tapps_core`. Ensure `from tapps_mcp.config import load_settings` still works. | 4h | 1.2-1.6 |
| 1.8 | Migrate Tier 1 tests | Move/copy tests for common, config, security, prompts to `packages/tapps-core/tests/`. Update imports. Verify all pass. | 4h | 1.2-1.7 |
| 1.9 | Verify TappsMCP tests still pass | Run full `uv run pytest packages/tapps-mcp/tests/` — all 2700+ tests must pass with the re-export compatibility layer. | 2h | 1.7-1.8 |

**Acceptance criteria:**
- `tapps_core.common`, `tapps_core.config`, `tapps_core.security`, `tapps_core.prompts` all importable
- `from tapps_mcp.config import load_settings` still works (backward compat)
- All existing TappsMCP tests pass unchanged
- Core tests pass in isolation: `uv run pytest packages/tapps-core/tests/`
- `mypy --strict` passes for both packages
- No circular imports

---

### Epic 2: tapps-core Extraction — Tier 2 (Subsystems)

**Goal:** Extract knowledge, memory, experts, metrics, adaptive subsystems.
**Duration:** 5-7 days
**Risk:** Medium-High (larger codebase, more interdependencies)

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 2.1 | Extract knowledge/ to tapps-core | Move entire knowledge package. Update imports for content_safety (now in security/). Verify Context7 client, KBCache, LookupEngine, fuzzy matcher, circuit breaker all work. | 6h | 1.* |
| 2.2 | Extract memory/ to tapps-core | Move entire memory package. Update rag_safety import to `tapps_core.security.content_safety`. Verify SQLite persistence, FTS5 search, WAL mode, decay, retrieval, injection. | 6h | 2.1 |
| 2.3 | Extract experts/ to tapps-core | Move entire experts package including 139 knowledge markdown files. Update internal imports. Verify domain detection, RAG engine, confidence scoring. | 6h | 2.1 |
| 2.4 | Extract metrics/ to tapps-core | Move entire metrics package. Update imports to tapps_core.common. Verify collector, dashboard, feedback, OTEL export. | 4h | 1.* |
| 2.5 | Extract adaptive/ to tapps-core | Move entire adaptive package. Self-contained, minimal changes needed. | 2h | 1.* |
| 2.6 | Create Tier 2 compatibility re-exports | Add `tapps_mcp.knowledge`, `tapps_mcp.memory`, `tapps_mcp.experts`, `tapps_mcp.metrics`, `tapps_mcp.adaptive` re-export modules. | 4h | 2.1-2.5 |
| 2.7 | Update server_helpers.py singletons | Update `_get_scorer()`, `_get_settings()`, `_get_memory_store()` to import from `tapps_core`. Update cache reset functions. | 3h | 2.1-2.6 |
| 2.8 | Update all server*.py imports | Update `server.py`, `server_scoring_tools.py`, `server_pipeline_tools.py`, `server_metrics_tools.py`, `server_analysis_tools.py`, `server_memory_tools.py` to import from tapps_core where appropriate. | 6h | 2.7 |
| 2.9 | Migrate Tier 2 tests | Move/copy tests for knowledge, memory, experts, metrics, adaptive to `packages/tapps-core/tests/`. Update imports. Verify all pass. | 6h | 2.1-2.5 |
| 2.10 | Full regression test | Run complete test suite across all packages. Fix any remaining import issues. Verify `uv run pytest` passes for all packages. | 4h | 2.6-2.9 |
| 2.11 | Update conftest.py cache resets | Update the autouse fixture in `tests/conftest.py` to reset caches from `tapps_core` (not `tapps_mcp`). Ensure test isolation still works. | 3h | 2.7 |

**Acceptance criteria:**
- All tapps-core subsystems importable independently
- `uv run pytest packages/tapps-core/tests/` passes all core tests
- `uv run pytest packages/tapps-mcp/tests/` passes all 2700+ existing tests
- `mypy --strict` passes for both packages
- `from tapps_mcp.memory import MemoryStore` still works (backward compat)
- Cache singletons properly shared when servers are co-located
- Knowledge files (139 markdown) correctly bundled in tapps-core

---

### PHASE 2: DOCSMCP FOUNDATION

---

### Epic 3: DocsMCP Server Skeleton

**Goal:** Minimal viable DocsMCP server with session management.
**Duration:** 3-4 days
**Risk:** Low

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 3.1 | DocsMCP FastMCP server | Create `packages/docs-mcp/src/docs_mcp/server.py` with `FastMCP("DocsMCP")`. Register `docs_session_start` tool. Import tapps_core for config, logging, security. | 4h | 2.* |
| 3.2 | DocsMCP configuration system | Create `docs_mcp/config/` extending tapps_core config with docs-specific settings (output_dir, styles, formats). Create `.docsmcp.yaml` loader. | 4h | 3.1 |
| 3.3 | DocsMCP CLI skeleton | Create `docs_mcp/cli.py` with Click: `docsmcp serve`, `docsmcp doctor`, `docsmcp generate`. Wire to server. | 3h | 3.1 |
| 3.4 | `docs_session_start` implementation | Detect project, scan existing documentation, return inventory + config + recommendations. Use tapps_core.config and security. | 4h | 3.2 |
| 3.5 | `docs_project_scan` implementation | Comprehensive documentation state audit. Inventory all .md files, detect README, CHANGELOG, API docs, ADRs. Calculate quick completeness score. | 6h | 3.4 |
| 3.6 | `docs_config` tool | View/set DocsMCP configuration. Read/write `.docsmcp.yaml`. | 3h | 3.2 |
| 3.7 | DocsMCP test infrastructure | Create conftest.py, fixtures, sample project fixtures. Verify tapps_core cache isolation works across packages. | 4h | 3.1 |

**Acceptance criteria:**
- `docsmcp serve` starts an MCP server
- `docs_session_start` returns project context
- `docs_project_scan` returns documentation inventory
- All tools use tapps_core infrastructure (logging, config, security)
- Tests pass: `uv run pytest packages/docs-mcp/tests/`

---

### Epic 4: Code Extraction Engine

**Goal:** AST-based code analysis for Python with extensible language support.
**Duration:** 5-7 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 4.1 | Extractor base protocol | Define `ExtractorProtocol` with methods: `extract_functions()`, `extract_classes()`, `extract_imports()`, `extract_module_info()`. Return typed models. | 3h | 3.* |
| 4.2 | Python AST extractor — functions | Extract function signatures, parameters, return types, decorators, docstrings. Handle `async def`, `@property`, `@staticmethod`, `@classmethod`. | 6h | 4.1 |
| 4.3 | Python AST extractor — classes | Extract class definitions, base classes, methods, class variables, `__init__` signature, `__all__` exports. Handle dataclasses, Pydantic models. | 6h | 4.1 |
| 4.4 | Docstring parser | Parse Google, NumPy, and Sphinx docstring formats. Extract description, parameters, returns, raises, examples, notes. | 6h | 4.2 |
| 4.5 | Type annotation extractor | Extract and stringify complex type annotations. Handle `Optional`, `Union`, `Generic`, forward references, `from __future__ import annotations`. | 4h | 4.2 |
| 4.6 | Import graph builder | Build module dependency graph from imports. Detect circular dependencies. Calculate coupling metrics. Identify package boundaries. | 6h | 4.2 |
| 4.7 | Public API surface detector | Detect public API via `__all__`, naming conventions (`_` prefix), `__init__.py` re-exports. Generate API surface summary per module. | 4h | 4.2, 4.3 |
| 4.8 | Module structure analyzer | Walk directory tree, detect packages vs modules, identify entry points, detect test directories, detect config files. | 4h | 4.6 |
| 4.9 | Generic regex fallback extractor | Regex-based extraction for non-Python files. Extract function/class-like patterns. Return best-effort results with `confidence: low` flag. | 4h | 4.1 |
| 4.10 | `docs_module_map` MCP tool | Wire module structure analyzer to MCP tool. Return hierarchical module tree with descriptions, API counts, import relationships. | 3h | 4.8 |
| 4.11 | `docs_api_surface` MCP tool | Wire API surface detector to MCP tool. Return public functions, classes, methods with type signatures and docstring presence. | 3h | 4.7 |

**Acceptance criteria:**
- Python AST extractor handles all major Python 3.12+ constructs
- Docstring parser correctly handles Google, NumPy, Sphinx styles
- Import graph correctly identifies circular dependencies
- `docs_module_map` returns accurate project structure
- `docs_api_surface` returns complete public API
- Tested against TappsMCP's own codebase as a real-world fixture

---

### Epic 5: Git Analysis Engine

**Goal:** Git history analysis for changelogs, drift detection, and freshness scoring.
**Duration:** 4-5 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 5.1 | Git log parser | Parse git log into structured objects. Extract: hash, author, date, message, files changed, insertions/deletions. Handle merge commits. | 4h | 3.* |
| 5.2 | Conventional commits parser | Parse commit messages following conventional commits spec. Extract: type, scope, description, body, breaking changes, references (#123). | 6h | 5.1 |
| 5.3 | Non-conventional commit classifier | Keyword heuristics for commits not following conventional format. Classify as: feat, fix, refactor, docs, test, chore, other. Assign confidence. | 4h | 5.2 |
| 5.4 | Tag and version boundary detection | Detect version tags (v1.0.0, 1.0.0), order semantically, identify commit ranges between versions. | 3h | 5.1 |
| 5.5 | Git blame analyzer | Parse git blame for documentation files. Identify most recently modified sections, oldest unchanged sections. Map line ranges to authors and dates. | 4h | 5.1 |
| 5.6 | Git diff analyzer | Compare file states between refs. Identify functions/classes added, removed, modified. Detect signature changes. | 4h | 5.1 |
| 5.7 | `docs_git_summary` MCP tool | Wire git analysis to MCP tool. Return: commit count, contributors, most changed files, commit type distribution, key changes narrative. | 3h | 5.1-5.4 |

**Acceptance criteria:**
- Conventional commits parser handles all standard types + custom scopes
- Non-conventional classifier achieves >70% accuracy on sample repos
- Tag detection handles `v1.0.0`, `1.0.0`, `release/1.0` patterns
- Git blame correctly identifies stale documentation sections
- Tested with TappsMCP's git history as fixture

---

### PHASE 3: DOCSMCP GENERATION

---

### Epic 6: README Generation

**Goal:** Generate and maintain README.md from codebase analysis.
**Duration:** 5-7 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 6.1 | Project metadata extractor | Extract name, version, description, license, URLs from `pyproject.toml`, `package.json`, `Cargo.toml`, `setup.py`, `setup.cfg`. Unified model. | 6h | 4.* |
| 6.2 | Jinja2 template engine | Set up Jinja2 environment with custom filters. Create base template structure. Handle optional sections, conditional rendering. | 4h | 3.* |
| 6.3 | README templates (3 styles) | Create `minimal.md.j2`, `standard.md.j2`, `comprehensive.md.j2` templates. Define section ordering and content placeholders. | 6h | 6.2 |
| 6.4 | Section generators — installation | Detect installation methods (pip, uv, npm, cargo, docker). Generate install commands, dependency requirements, system prerequisites. | 4h | 6.1 |
| 6.5 | Section generators — usage & commands | Extract CLI entry points, key functions. Generate usage examples, common commands. Detect Makefile/justfile targets. | 4h | 4.8 |
| 6.6 | Section generators — development | Detect test frameworks, linters, formatters. Generate development setup, testing, linting commands. Detect pre-commit hooks. | 4h | 6.1 |
| 6.7 | Badge generator | Generate markdown badges: CI status, coverage, version (PyPI/npm), license, Python version, downloads. Configurable badge style. | 3h | 6.1 |
| 6.8 | Smart-merge engine | Parse existing README into sections. Detect human-written vs generated sections (via markers). Update generated sections, preserve human sections. Handle section reordering. | 8h | 6.3 |
| 6.9 | `docs_generate_readme` MCP tool | Wire all generators and smart-merge to MCP tool. Support `create`, `update`, `smart_merge` modes. Return structured data for LLM prose enhancement. | 4h | 6.1-6.8 |

**Acceptance criteria:**
- README generation produces valid, well-structured markdown
- 3 style variants produce distinct output (minimal: 5 sections, standard: 10, comprehensive: 15+)
- Smart-merge preserves human-written sections while updating generated ones
- Badge generation supports GitHub, GitLab, Shields.io formats
- Tested against multiple sample projects (Python, Node, Rust)

---

### Epic 7: API Documentation Generation

**Goal:** Generate API reference documentation from source code analysis.
**Duration:** 5-7 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 7.1 | API doc template system | Create templates for Markdown, MkDocs, and Sphinx RST output formats. Module-level, class-level, and function-level templates. | 6h | 6.2 |
| 7.2 | Module documentation generator | Generate per-module documentation: module docstring, public API summary, cross-references, import information. | 6h | 4.7, 7.1 |
| 7.3 | Class documentation generator | Generate class documentation: description, constructor, methods, properties, class variables, inheritance hierarchy, associated types. | 6h | 4.3, 7.1 |
| 7.4 | Function documentation generator | Generate function documentation: description, parameters with types, return type, exceptions, decorators, examples. | 4h | 4.2, 7.1 |
| 7.5 | Cross-reference resolver | Resolve type references to their documentation location. Generate internal links. Handle re-exports and aliases. | 4h | 4.6, 4.7 |
| 7.6 | Example extraction from tests | Analyze test files to find usage examples for documented functions/classes. Extract test bodies as code examples. Filter by relevance. | 4h | 4.2 |
| 7.7 | `docs_generate_api` MCP tool | Wire generators to MCP tool. Support file/directory scope, public/protected/all depth, multiple output formats. | 4h | 7.2-7.6 |

**Acceptance criteria:**
- API docs generated for TappsMCP's own codebase produce accurate output
- Markdown, MkDocs, and Sphinx RST formats all produce valid output
- Cross-references resolve correctly within and across modules
- Docstrings in all 3 styles (Google, NumPy, Sphinx) parsed correctly
- Type annotations rendered as human-readable strings

---

### Epic 8: Changelog & Release Notes Generation

**Goal:** Generate changelogs from git history and release notes for versions.
**Duration:** 4-5 days
**Risk:** Low-Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 8.1 | Keep-a-Changelog format generator | Generate CHANGELOG.md following keep-a-changelog spec. Sections: Added, Changed, Deprecated, Removed, Fixed, Security. Version headers with dates and comparison links. | 6h | 5.* |
| 8.2 | Conventional changelog format generator | Generate changelog following conventional-changelog format. Group by commit type, include scope, link to commits. | 4h | 5.2 |
| 8.3 | Simple changelog format generator | Flat bullet-list format for projects without conventional commits. Group by date or file-change area. | 3h | 5.3 |
| 8.4 | Breaking changes highlighter | Detect breaking changes from conventional commits (`!` suffix, `BREAKING CHANGE:` footer), semver analysis, API surface diffs between versions. | 4h | 5.2, 5.6 |
| 8.5 | Release notes generator | User-facing release notes for a specific version. Summarize changes by impact, highlight new features, list fixes, note breaking changes with migration hints. | 4h | 8.1, 8.4 |
| 8.6 | `docs_generate_changelog` MCP tool | Wire changelog generators. Support format selection, ref range, grouping strategy. Handle incremental updates (append new version). | 4h | 8.1-8.3 |
| 8.7 | `docs_generate_release_notes` MCP tool | Wire release notes generator. Support version/tag input, auto-detect previous version, style selection. | 3h | 8.5 |

**Acceptance criteria:**
- Keep-a-Changelog output validates against specification
- Conventional changelog correctly groups by type and scope
- Breaking changes detected from both commit messages and API diff
- Incremental changelog update appends new version without regenerating history
- Release notes provide user-facing narrative distinct from raw changelog

---

### Epic 9: Diagram Generation

**Goal:** Generate Mermaid diagrams from code analysis.
**Duration:** 4-5 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 9.1 | Mermaid primitives | Build Mermaid text generation utilities: nodes (with shapes), edges (with labels and styles), subgraphs, styling, directives. Emit valid Mermaid syntax. | 4h | — |
| 9.2 | Dependency graph → flowchart | Convert import graph to Mermaid flowchart. Package grouping via subgraphs. Circular dependency highlighting. Depth limiting. | 6h | 4.6, 9.1 |
| 9.3 | Class hierarchy → class diagram | Convert AST class data to Mermaid class diagram. Show inheritance, composition, key methods/properties. | 6h | 4.3, 9.1 |
| 9.4 | Module structure → architecture diagram | Convert module map to high-level architecture diagram. Show layers, boundaries, entry points, external interfaces. | 4h | 4.8, 9.1 |
| 9.5 | Pydantic/dataclass → ER diagram | Detect model definitions, extract fields and relationships. Generate Mermaid ER diagram with cardinality. | 4h | 4.3, 9.1 |
| 9.6 | PlantUML output option | Alternative output format for teams using PlantUML. Convert same analysis to PlantUML syntax. | 3h | 9.2-9.5 |
| 9.7 | `docs_generate_diagram` MCP tool | Wire all diagram generators. Support type selection, scope, depth, format. Return diagram text + rendering hints. | 3h | 9.2-9.6 |

**Acceptance criteria:**
- Generated Mermaid renders correctly in GitHub, GitLab, VS Code preview
- Dependency graphs handle 50+ module projects without visual clutter (depth limiting works)
- Class diagrams correctly show inheritance chains and key methods
- ER diagrams detect Pydantic models, dataclasses, SQLAlchemy models
- TappsMCP's own codebase produces useful diagrams

---

### PHASE 4: DOCSMCP VALIDATION

---

### Epic 10: Documentation Validation

**Goal:** Drift detection, completeness checking, link validation, freshness scoring.
**Duration:** 5-7 days
**Risk:** Medium

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 10.1 | Drift detection engine | Compare documentation state against code. Detect: new public APIs without docs, removed APIs still documented, signature changes not reflected, config changes not documented. Produce drift score 0-100. | 8h | 4.*, 5.6 |
| 10.2 | Completeness checker | Measure documentation coverage. Check: README sections, API doc coverage (% public APIs documented), docstring coverage, CHANGELOG existence, CONTRIBUTING existence, license, architecture docs. Score 0-100. | 6h | 3.5, 4.7 |
| 10.3 | Link validator | Validate all links in markdown files. Check: relative file paths, anchor references, image paths, code references (file:line). Optional external URL validation with rate limiting. | 6h | 3.* |
| 10.4 | Freshness scorer | Score documentation recency. Use git blame to find oldest unchanged doc sections. Compare doc file modification dates against corresponding code modification dates. Alert on stale docs. | 4h | 5.5 |
| 10.5 | Consistency checker | Cross-document terminology and naming consistency. Detect: inconsistent project name usage, version string mismatches, conflicting instructions across docs. | 4h | 3.5 |
| 10.6 | `docs_check_drift` MCP tool | Wire drift engine. Support scope selection, sensitivity levels, base ref configuration. Return per-section drift with evidence and suggested actions. | 4h | 10.1 |
| 10.7 | `docs_check_completeness` MCP tool | Wire completeness checker. Support minimal/standard/comprehensive requirement levels. Return per-category scores and missing items. | 3h | 10.2 |
| 10.8 | `docs_check_links` MCP tool | Wire link validator. Support scope selection, external link opt-in, anchor checking. Return broken links with locations and suggested fixes. | 3h | 10.3 |
| 10.9 | `docs_check_freshness` MCP tool | Wire freshness scorer. Return per-file freshness scores, staleness alerts, trending indicators. | 3h | 10.4 |

**Acceptance criteria:**
- Drift detection correctly identifies stale README sections on TappsMCP's own repo
- Completeness score accurately reflects documentation state
- Link validator finds broken internal references with zero false positives
- Freshness scoring correlates with actual documentation staleness
- All validators handle edge cases: empty repos, no git history, binary files

---

### Epic 11: ADR, Guides & Workflow

**Goal:** Architecture Decision Records, onboarding/contributing guides, MCP prompts and resources.
**Duration:** 4-5 days
**Risk:** Low

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 11.1 | ADR templates (MADR, Nygard) | Create ADR templates in Jinja2. Support MADR v3 and Nygard formats. Include context, decision, status, consequences sections. | 4h | 6.2 |
| 11.2 | ADR numbering and indexing | Auto-detect ADR directory, parse existing ADR numbers, generate next number. Maintain index file (README or INDEX.md in ADR directory). Support supersession. | 3h | 11.1 |
| 11.3 | `docs_generate_adr` MCP tool | Wire ADR generator. Support create/list/supersede actions. Accept context_files for code-grounded evidence. | 3h | 11.1, 11.2 |
| 11.4 | Onboarding guide generator | Generate getting-started guide from codebase analysis. Detect: dev requirements, install commands, env vars, test commands, build commands, common tasks. | 6h | 4.8, 6.1 |
| 11.5 | Contributing guide generator | Generate CONTRIBUTING.md. Detect: branch strategy, commit conventions, PR template, CI checks, code style tools, test requirements. | 4h | 5.2, 6.1 |
| 11.6 | `docs_generate_onboarding` and `docs_generate_contributing` MCP tools | Wire generators to tools. Support audience and depth parameters. | 3h | 11.4, 11.5 |
| 11.7 | Migration guide generator | Detect breaking changes between versions. Generate migration guide with before/after examples, step-by-step instructions. | 4h | 8.4 |
| 11.8 | MCP resources and prompts | Create `docs://status`, `docs://config`, `docs://templates/{type}`, `docs://coverage` resources. Create `docs_workflow_overview` and `docs_workflow(task_type)` prompts. | 4h | 3.* |

**Acceptance criteria:**
- ADR generation follows MADR v3 specification
- Onboarding guide accurately reflects development environment for test projects
- Contributing guide detects real project conventions
- Migration guide provides actionable upgrade steps
- MCP resources return accurate, current data

---

### PHASE 5: COMPOSITION & DISTRIBUTION

---

### Epic 12: FastMCP Composition Layer

**Goal:** Enable optional composition of TappsMCP + DocsMCP into a single server.
**Duration:** 3-4 days
**Risk:** Low

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 12.1 | Combined server script | Create `examples/combined_server.py` that mounts both servers. Verify all 46 tools accessible. Handle shared singletons (memory, knowledge, config). | 4h | 3.*, existing TappsMCP |
| 12.2 | tapps-platform CLI | Create `tapps-platform` CLI entry point. Commands: `serve` (combined), `serve-tapps` (quality only), `serve-docs` (docs only). | 4h | 12.1 |
| 12.3 | Namespace collision testing | Verify no tool name collisions between tapps_* and docs_* tools. Test mounted vs standalone tool behavior parity. | 3h | 12.1 |
| 12.4 | Shared singleton verification | Verify that when mounted together, both servers share the same MemoryStore, KBCache, ExpertEngine, MetricsCollector instances. Write integration tests. | 4h | 12.1 |
| 12.5 | Documentation for composition | Write usage guide: how to configure standalone vs composed, Cursor vs Claude Code recommendations, performance characteristics. | 3h | 12.1-12.4 |

**Acceptance criteria:**
- Combined server starts and all 46 tools work
- Standalone servers work independently without the other
- Shared singletons are actually shared (memory write in tapps visible in docs)
- No tool name collisions
- Performance: composed server adds <5ms overhead per tool call vs standalone

---

### Epic 13: Distribution & Publishing

**Goal:** PyPI publishing, Docker, npm wrappers, CI/CD automation.
**Duration:** 3-4 days
**Risk:** Low

| # | Story | Description | LOE | Depends |
|---|---|---|---|---|
| 13.1 | PyPI publishing — tapps-core | Configure build, test, publish workflow. Verify `pip install tapps-core` works. Test import paths. | 3h | 2.* |
| 13.2 | PyPI publishing — tapps-mcp | Update existing publish workflow. Verify `pip install tapps-mcp` pulls tapps-core as dependency. Backward compatibility: existing installs still work. | 3h | 13.1 |
| 13.3 | PyPI publishing — docs-mcp | New publish workflow. Verify `pip install docs-mcp` pulls tapps-core. Test `docsmcp serve` command. | 3h | 13.1 |
| 13.4 | Docker images | Multi-stage Dockerfile for each server. Combined image option. Verify stdio and Streamable HTTP transport. | 4h | 13.1-13.3 |
| 13.5 | npm wrapper packages | `tapps-mcp` and `docs-mcp` npm wrappers (like existing TappsMCP pattern). Enable `npx tapps-mcp` and `npx docs-mcp`. | 4h | 13.1-13.3 |
| 13.6 | Version coordination | Implement version bumping strategy. tapps-core version pinned in tapps-mcp and docs-mcp. Create release script that bumps all packages atomically. | 3h | 13.1-13.3 |
| 13.7 | Update TappsMCP init for DocsMCP | Update `tapps_init` to optionally detect and configure DocsMCP alongside TappsMCP in consuming projects. Update AGENTS.md templates to reference docs tools. | 4h | 3.*, 13.3 |

**Acceptance criteria:**
- All 3 packages installable from PyPI independently
- `pip install tapps-mcp` continues to work for existing users (no breaking change)
- Docker images for standalone and combined servers
- npm wrappers work: `npx tapps-mcp`, `npx docs-mcp`
- Version coordination ensures compatible releases

---

## Summary: All Epics at a Glance

| Phase | Epic | Title | Duration | Stories | Risk |
|---|---|---|---|---|---|
| **1: Restructure** | 0 | Workspace Foundation | 3-4 days | 7 | Low |
| | 1 | tapps-core Extraction — Tier 1 | 4-5 days | 9 | Medium |
| | 2 | tapps-core Extraction — Tier 2 | 5-7 days | 11 | Medium-High |
| **2: Foundation** | 3 | DocsMCP Server Skeleton | 3-4 days | 7 | Low |
| | 4 | Code Extraction Engine | 5-7 days | 11 | Medium |
| | 5 | Git Analysis Engine | 4-5 days | 7 | Medium |
| **3: Generation** | 6 | README Generation | 5-7 days | 9 | Medium |
| | 7 | API Documentation Generation | 5-7 days | 7 | Medium |
| | 8 | Changelog & Release Notes | 4-5 days | 7 | Low-Medium |
| | 9 | Diagram Generation | 4-5 days | 7 | Medium |
| **4: Validation** | 10 | Documentation Validation | 5-7 days | 9 | Medium |
| | 11 | ADR, Guides & Workflow | 4-5 days | 8 | Low |
| **5: Distribution** | 12 | FastMCP Composition Layer | 3-4 days | 5 | Low |
| | 13 | Distribution & Publishing | 3-4 days | 7 | Low |
| | | **TOTALS** | **~58-75 days** | **111 stories** | |

---

## 11. Distribution Strategy

### 11.1 PyPI Packages

| Package | Install | Contains | Depends On |
|---|---|---|---|
| `tapps-core` | `pip install tapps-core` | Shared infrastructure only | pydantic, structlog, httpx |
| `tapps-mcp` | `pip install tapps-mcp` | Code quality MCP server (28 tools) | tapps-core, mcp, click |
| `docs-mcp` | `pip install docs-mcp` | Documentation MCP server (18 tools) | tapps-core, mcp, click, gitpython, jinja2 |

### 11.2 User Configurations

**Cursor (40-tool limit):**
```json
{
  "mcpServers": {
    "tapps-mcp": { "command": "uvx", "args": ["tapps-mcp", "serve"] },
    "docs-mcp": { "command": "uvx", "args": ["docs-mcp", "serve"] }
  }
}
```
Enable per-project in `.cursor/mcp.json`. Each under 40-tool limit.

**Claude Code (no limit, Tool Search handles scale):**
```json
{
  "mcpServers": {
    "tapps-mcp": { "command": "uvx", "args": ["tapps-mcp", "serve"] },
    "docs-mcp": { "command": "uvx", "args": ["docs-mcp", "serve"] }
  }
}
```
Or combined: `"tapps-platform": { "command": "uvx", "args": ["tapps-platform", "serve"] }`

---

## 12. Testing Strategy

### 12.1 Test Distribution

| Package | Test Types | Target Coverage |
|---|---|---|
| **tapps-core** | Unit (all modules), integration (cross-module) | 85% |
| **tapps-mcp** | Unit (scoring, gates, tools), integration (server tools), existing 2700+ migrated | 80% |
| **docs-mcp** | Unit (extractors, generators, validators), integration (MCP tools), snapshot (output stability) | 80% |
| **Cross-package** | Composition tests, shared singleton tests, backward compatibility | N/A |

### 12.2 Test Commands

```bash
# All packages
uv run pytest

# Individual packages
uv run pytest packages/tapps-core/tests/
uv run pytest packages/tapps-mcp/tests/
uv run pytest packages/docs-mcp/tests/

# With coverage
uv run pytest --cov=tapps_core --cov=tapps_mcp --cov=docs_mcp --cov-fail-under=80
```

### 12.3 CI Matrix

```yaml
# .github/workflows/ci.yml
strategy:
  matrix:
    package: [tapps-core, tapps-mcp, docs-mcp]
    python-version: ["3.12", "3.13"]
    os: [ubuntu-latest, windows-latest, macos-latest]
```

---

## 13. Risk Matrix

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| 1 | **Import path breakage** during extraction | High | Medium | Compatibility re-exports; gradual migration with tests at every step |
| 2 | **Test failures** during restructure | High | Medium | Green tests required per-story; no epic without full regression pass |
| 3 | **uv workspace edge cases** on Windows | Medium | Medium | Test on Windows early (Epic 0); TappsMCP already Windows-tested |
| 4 | **Version coordination complexity** | Medium | Low | Lockstep versioning for v1.0; pin ranges after stabilization |
| 5 | **FastMCP mount() overhead** | Low | Low | 1-2ms for local mount (research-validated); only HTTP adds latency |
| 6 | **Existing consumers break** | High | Low | Re-export layer ensures `from tapps_mcp.X import Y` still works |
| 7 | **tapps-core scope creep** | Medium | Medium | Clear extraction criteria: only move packages needed by 2+ servers |
| 8 | **Publication order dependency** | Medium | Low | Publish tapps-core first; CI enforces order |
| 9 | **DocsMCP AST parsing edge cases** | Medium | Medium | Graceful degradation; regex fallback; test against diverse codebases |
| 10 | **Git analysis slow on large repos** | Medium | Medium | Configurable depth limits; incremental analysis; caching |

---

## 14. Success Criteria

### Phase 1 Complete (Monorepo Restructure)

- [ ] uv workspace with 3 packages builds successfully
- [ ] All 2700+ existing TappsMCP tests pass in new structure
- [ ] `pip install tapps-mcp` still works for existing users
- [ ] `from tapps_mcp.config import load_settings` backward compatible
- [ ] `mypy --strict` passes across all packages
- [ ] CI runs tests for all packages on push

### Phase 2-4 Complete (DocsMCP v0.1)

- [ ] 18 DocsMCP MCP tools implemented and tested
- [ ] `docs_session_start` returns project documentation state
- [ ] `docs_generate_readme` produces valid, useful README
- [ ] `docs_check_drift` detects stale documentation
- [ ] `docs_check_completeness` accurately scores documentation coverage
- [ ] 80%+ test coverage for docs-mcp package

### Phase 5 Complete (Distribution)

- [ ] All 3 packages published to PyPI
- [ ] Combined server via FastMCP mount() works with all 46 tools
- [ ] Cursor users can run servers separately (under 40-tool limit)
- [ ] Docker images available for all deployment options
- [ ] npm wrappers work: `npx tapps-mcp`, `npx docs-mcp`

---

## 15. References

### Architecture & Patterns
- [FastMCP 3.0 Server Composition](https://gofastmcp.com/servers/composition)
- [FastMCP 3.0 What's New](https://www.jlowin.dev/blog/fastmcp-3-whats-new)
- [FastMCP 3.0 GA Launch](https://www.jlowin.dev/blog/fastmcp-3-launch)
- [MCP Architecture Patterns (IBM)](https://developer.ibm.com/articles/mcp-architecture-patterns-ai-systems/)
- [MCP Server Best Practices 2026](https://www.cdata.com/blog/mcp-server-best-practices-2026)
- [Virtual MCP Server Aggregation](https://www.truefoundry.com/blog/virtual-mcp-server)
- [Multi-MCP: Exposing Multiple Servers as One](https://itnext.io/multi-mcp-exposing-multiple-mcp-servers-as-one-5732ebe3ba20)
- [AWS MCP Servers Monorepo](https://github.com/awslabs/mcp)
- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)

### Client Constraints
- [Cursor 40-Tool Limit](https://forum.cursor.com/t/mcp-server-40-tool-limit-in-cursor-is-this-frustrating-your-workflow/81627)
- [Claude Code Context Overhead (Issue #3036)](https://github.com/anthropics/claude-code/issues/3036)
- [Optimising MCP Context Usage](https://scottspence.com/posts/optimising-mcp-server-context-usage-in-claude-code)

### uv Workspace / Monorepo
- [uv Workspaces Documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [FOSDEM: Modern Python Monorepo with uv](https://pydevtools.com/blog/fosdem-talk-modern-python-monorepo/)
- [Releasing Monorepo with uv Workspace](https://medium.com/@asafshakarzy/releasing-a-monorepo-using-uv-workspace-and-python-semantic-release-0dafc889f4cc)
- [uv Monorepo Example](https://github.com/JasperHG90/uv-monorepo)

### DocsMCP Feature References
- See [DOCSMCP_PRD.md](DOCSMCP_PRD.md) Section 18 for complete documentation tool research

### Internal References
- [TappsMCP CLAUDE.md](../../CLAUDE.md) — Current architecture and conventions
- [TappsMCP Module Map](../../CLAUDE.md#architecture) — Current package structure
- [Epic History](epics/) — Previous epic planning documents

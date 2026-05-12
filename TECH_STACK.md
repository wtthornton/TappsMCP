# Tech Stack

> Companion to [README.md](README.md) (project overview), [CLAUDE.md](CLAUDE.md) (AI assistant guidance),
> and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (module layout and data flow).
> For install + consumer setup see [docs/UPGRADE_FOR_CONSUMERS.md](docs/UPGRADE_FOR_CONSUMERS.md).

## Language & Runtime
- **Python 3.12+** with `from __future__ import annotations`
- **uv** package manager (workspace monorepo)

## Core Frameworks
- **FastMCP** (mcp[cli] >= 1.26.0) - MCP server framework
- **Pydantic v2** - Data models and validation
- **structlog** - Structured JSON logging
- **Click** - CLI interface

## Quality Toolchain
- **ruff** - Linting and formatting (line-length: 100)
- **mypy** - Static type checking (strict mode)
- **bandit** - Security scanning
- **radon** - Complexity metrics
- **vulture** - Dead code detection
- **pip-audit** - Dependency vulnerability scanning

## Testing
- **pytest** - Test framework
- **pytest-asyncio** - Async test support
- **pytest-cov** - Coverage reporting (80% minimum)
- **unittest.mock** - Mocking and patching

## Optional Dependencies
- **tree-sitter** - AST analysis for TypeScript, Go, Rust scoring

## Storage
- **tapps-brain** (PostgreSQL, Docker service at `localhost:8080`) — persistent cross-session memory, accessed from tapps-mcp via `BrainBridge`. Storage/retrieval details live in the [tapps-brain repo](https://github.com/wtthornton/tapps-brain).
- **YAML** - Configuration files
- **JSON/JSONL** - Metrics, audit logs, benchmark results

## Infrastructure
- **Docker** - Container builds, MCP Toolkit distribution
- **GitHub Actions** - CI/CD pipelines
- **cosign** - Image signing
- **SBOM** - Supply chain security

## Architecture
- **3-package monorepo**: tapps-core (library), tapps-mcp (30 tools), docs-mcp (38 tools) — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module map and data flow
- **MCP Protocol**: 2025-11-25 (latest stable)
- **7-category scoring**: complexity, security, maintainability, test coverage, performance, structure, devex — see [docs/CHECKLIST.md](docs/CHECKLIST.md) for category weights and [README.md](README.md) for scoring tool reference
- **Memory subsystem**: see [docs/MEMORY_REFERENCE.md](docs/MEMORY_REFERENCE.md) for the 33-action `tapps_memory` surface; [tapps-brain repo](https://github.com/wtthornton/tapps-brain) for retrieval, decay, consolidation, and federation internals
- **Adaptive learning** with domain weight persistence
- **Config reference**: all Pydantic settings + env vars listed in [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md)
- **Troubleshooting**: common install / hook / Cursor issues covered in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

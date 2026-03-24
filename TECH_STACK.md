# Tech Stack

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
- **faiss** - Vector search for expert RAG
- **numpy** - Vector operations
- **sentence-transformers** - Semantic embeddings

## Storage
- **SQLite** (WAL mode) - Memory persistence, FTS5 search
- **YAML** - Configuration files
- **JSON/JSONL** - Metrics, audit logs, benchmark results

## Infrastructure
- **Docker** - Container builds, MCP Toolkit distribution
- **GitHub Actions** - CI/CD pipelines
- **cosign** - Image signing
- **SBOM** - Supply chain security

## Architecture
- **3-package monorepo**: tapps-core (library), tapps-mcp (30 tools), docs-mcp (32 tools)
- **MCP Protocol**: 2025-11-25 (latest stable)
- **7-category scoring**: complexity, security, maintainability, test coverage, performance, structure, devex
- **17 domain experts** with 174 curated knowledge files
- **BM25 ranked retrieval** for memory search
- **Adaptive learning** with domain weight persistence

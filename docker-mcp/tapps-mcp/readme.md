# TappsMCP

Deterministic code quality MCP server providing 30 tools for AI coding assistants.

## Features

- **7-category scoring** - complexity, security, maintainability, test coverage, performance, structure, developer experience
- **Quality gates** - configurable pass/fail thresholds (standard 70+, strict 80+)
- **Security scanning** - bandit + secret detection
- **17 domain experts** - 171 curated knowledge files with keyword-based RAG
- **Library docs lookup** - Context7 integration for real-time documentation
- **Dead code detection** - vulture-based unused code finder
- **Dependency scanning** - pip-audit CVE checks
- **Circular dependency detection** - import graph analysis
- **Project memory** - persistent cross-session knowledge sharing

## Quick Start

```bash
# Via PyPI
pip install tapps-mcp

# Via Docker
docker pull ghcr.io/wtthornton/tapps-mcp:latest
```

## Documentation

- [GitHub Repository](https://github.com/tapps-mcp/tapps-mcp)
- [README](https://github.com/tapps-mcp/tapps-mcp#readme)
- [Tool Reference](https://github.com/tapps-mcp/tapps-mcp/blob/master/AGENTS.md)

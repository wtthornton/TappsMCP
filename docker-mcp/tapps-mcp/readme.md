# TappsMCP

Deterministic code quality MCP server providing 30 tools for AI coding assistants.

## Features

- **7-category scoring** - complexity, security, maintainability, test coverage, performance, structure, developer experience
- **Quality gates** - configurable pass/fail thresholds (standard 70+, strict 80+)
- **Security scanning** - bandit + secret detection
- **Library docs lookup** - Context7 integration for real-time documentation
- **Dead code detection** - vulture-based unused code finder
- **Dependency scanning** - pip-audit CVE checks
- **Circular dependency detection** - import graph analysis
- **Project memory** - persistent cross-session knowledge sharing backed by tapps-brain

## Quick Start

```bash
# Run from the published Docker image
docker pull ghcr.io/wtthornton/tapps-mcp:latest
docker run --rm -v $(pwd):/workspace ghcr.io/wtthornton/tapps-mcp:latest
```

To install the Python CLI directly (the package is not published to PyPI), clone the repo and run `uv tool install -e packages/tapps-mcp` from the checkout.

## Documentation

- [GitHub Repository](https://github.com/wtthornton/TappsMCP)
- [README](https://github.com/wtthornton/TappsMCP#readme)
- [Tool Reference](https://github.com/wtthornton/TappsMCP/blob/master/AGENTS.md)

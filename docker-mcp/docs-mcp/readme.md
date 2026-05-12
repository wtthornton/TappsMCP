# DocsMCP

Documentation generation and maintenance MCP server providing 38 tools for AI coding assistants.

## Features

- **README generation** - AST-based project analysis with smart merge
- **API documentation** - Function/class/module API reference generation
- **Changelog & release notes** - Git history-driven changelog generation
- **Architecture Decision Records** - Structured ADR generation
- **Diagram generation** - Module dependency, class hierarchy, call graph, and architecture diagrams
- **Drift detection** - Identifies stale documentation relative to code changes
- **Completeness checking** - Validates documentation coverage
- **Link checking** - Finds broken documentation links
- **Freshness scoring** - Measures documentation currency
- **Linear-issue quality tooling** - lint, validate, and batch-triage Linear issue payloads
- **TappsMCP integration** - Enriches analysis with quality scoring data

## Quick Start

```bash
# Run from the published Docker image
docker pull ghcr.io/wtthornton/docs-mcp:latest
docker run --rm -v $(pwd):/workspace ghcr.io/wtthornton/docs-mcp:latest
```

To install the Python CLI directly (the package is not published to PyPI), clone the repo and run `uv tool install -e packages/docs-mcp` from the checkout.

## Documentation

- [GitHub Repository](https://github.com/wtthornton/TappsMCP/tree/master/packages/docs-mcp)
- [README](https://github.com/wtthornton/TappsMCP/blob/master/packages/docs-mcp/docs/README.md)

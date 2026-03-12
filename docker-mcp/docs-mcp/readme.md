# DocsMCP

Documentation generation and maintenance MCP server providing 24 tools for AI coding assistants.

## Features

- **README generation** — AST-based project analysis with smart merge
- **API documentation** — Function/class/module API reference generation
- **Changelog & release notes** — Git history-driven changelog generation
- **Architecture Decision Records** — Structured ADR generation
- **Diagram generation** — Module dependency, class hierarchy, call graph, and architecture diagrams
- **Drift detection** — Identifies stale documentation relative to code changes
- **Completeness checking** — Validates documentation coverage
- **Link checking** — Finds broken documentation links
- **Freshness scoring** — Measures documentation currency
- **TappsMCP integration** — Enriches analysis with quality scoring data

## Quick Start

```bash
# Via Docker MCP Catalog
docker mcp catalog install docs-mcp

# Via profile (includes TappsMCP + Context7)
docker mcp profile import tapps-standard
```

## Documentation

- [GitHub Repository](https://github.com/tapps-mcp/tapps-mcp/tree/master/packages/docs-mcp)
- [README](https://github.com/tapps-mcp/tapps-mcp/blob/master/packages/docs-mcp/docs/README.md)

# DocsMCP

<!-- mcp-name: io.github.wtthornton/docs-mcp -->

MCP server for automated documentation generation, validation, and maintenance.

## Overview

DocsMCP is part of the [TappsMCP](https://github.com/tapps-mcp/tapps-mcp) platform. It provides 31 MCP tools that help AI coding assistants generate, validate, and maintain project documentation.

## Features

- **Code extraction** - Parse Python modules to extract classes, functions, types, and docstrings
- **README generation** - Generate and smart-merge README.md files with project metadata
- **API documentation** - Generate structured API docs from source code analysis
- **Changelog generation** - Build changelogs from git commit history using conventional commits
- **Release notes** - Generate release notes for specific versions
- **Architecture Decision Records** - Generate ADRs from context and rationale
- **Onboarding and contributing guides** - Generate developer guides
- **Diagram generation** - Generate architecture diagrams in Mermaid, PlantUML, or D2 format (dependency, module, class, ER, C4 context/container/component, sequence). D2 supports themes (default, sketch, terminal)
- **Interactive HTML diagrams** - Generate interactive, zoomable diagram viewers with Mermaid.js
- **llms.txt generation** - Machine-readable project summaries for LLMs
- **Frontmatter management** - YAML frontmatter injection and update for markdown files
- **Architecture templates** - Purpose/intent architecture templates with auto-inferred principles
- **Documentation index** - Auto-categorized documentation index/map
- **Diataxis analysis** - Diataxis quadrant coverage analysis and balance scoring
- **Drift detection** - Identify when documentation falls out of sync with code
- **Completeness analysis** - Assess documentation coverage gaps
- **Link validation** - Check for broken documentation links
- **Freshness checking** - Flag stale documentation
- **Cross-reference validation** - Find orphans, broken refs, and missing backlinks

## Installation

See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions.

```bash
# Quick install
uv add docs-mcp

# Verify
docsmcp doctor
```

## Usage

```bash
# Start the MCP server
docsmcp serve

# Check configuration
docsmcp doctor

# Show version
docsmcp version
```

## License

MIT

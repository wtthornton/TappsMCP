# tapps-mcp

<!-- mcp-name: io.github.wtthornton/tapps-mcp -->

MCP server providing deterministic code quality tools for AI coding assistants (scoring, gates, security, validation).

## Features

- **Code scoring** (0-100) across 7 categories: complexity, security, maintainability, test coverage, performance, structure, developer experience
- **Multi-language support**: Python (full), TypeScript/JavaScript, Go, Rust (tree-sitter-based)
- **Quality gates** with configurable presets (standard, strict, framework)
- **Security scanning** with Bandit and secret detection
- **Dead code detection** with Vulture
- **Dependency vulnerability scanning** with pip-audit
- **Domain expert consultation** (17 built-in experts with RAG)
- **Documentation lookup** via Context7 or LlmsTxt
- **Shared memory** for cross-session knowledge persistence
- **Platform integration** for Claude Code, Cursor, VS Code Copilot

## Installation

```bash
# Using pip
pip install tapps-mcp

# Using uv
uv pip install tapps-mcp

# Using pipx (recommended for CLI)
pipx install tapps-mcp
```

## Quick Start

```bash
# Start the MCP server (stdio)
tapps-mcp serve

# Initialize in a project
tapps-mcp init

# Run diagnostics
tapps-mcp doctor
```

## MCP Tools

TappsMCP provides 29 MCP tools for code quality automation. See the [main README](../../README.md) for the complete tool reference.

## Documentation

- [Main Documentation](../../README.md)
- [AGENTS.md](../../AGENTS.md) - AI assistant integration guide
- [CLAUDE.md](../../CLAUDE.md) - Architecture and development guide

## License

MIT

---

Part of the [TappsMCP Platform](https://github.com/wtthornton/TappsMCP).

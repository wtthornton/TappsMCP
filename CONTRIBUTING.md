# Contributing to TappsMCP

Thank you for considering contributing to TappsMCP! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Getting Started

```bash
git clone https://github.com/tapps-mcp/tapps-mcp.git
cd tapps-mcp
uv sync
```

### Running Tests

```bash
# All tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=tapps_mcp --cov-report=term-missing

# Specific test file
uv run pytest tests/unit/test_scorer.py -v
```

### Linting and Type Checking

```bash
# Lint
uv run ruff check src/
uv run ruff format --check src/

# Type check (strict mode)
uv run mypy --strict src/tapps_mcp/
```

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/tapps-mcp/tapps-mcp/issues)
- Include Python version, OS, and steps to reproduce

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with a descriptive message
6. Push and open a PR

### Code Style

- Follow existing patterns in the codebase
- `from __future__ import annotations` at top of every file
- Type annotations everywhere (`mypy --strict`)
- Use `structlog` for logging (not `print()` or `logging`)
- Use `pathlib.Path` for file paths
- Pydantic v2 models for data structures
- `ruff` for linting and formatting

### Adding Knowledge Files

Expert knowledge files live in `src/tapps_mcp/experts/knowledge/{domain}/`. To add a new topic:

1. Create a markdown file in the appropriate domain directory
2. Follow the existing format (title, sections, code examples)
3. The file is automatically picked up by the expert system

### Adding Validators

Config validators live in `src/tapps_mcp/validators/`. To add a new validator:

1. Create a new module in `validators/`
2. Implement a validation function following the pattern in `base.py`
3. Register it in the auto-detection logic in `base.py`
4. Add tests in `tests/unit/`

## Architecture

See [docs/planning/TAPPS_MCP_PLAN.md](docs/planning/TAPPS_MCP_PLAN.md) for the full architecture document.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

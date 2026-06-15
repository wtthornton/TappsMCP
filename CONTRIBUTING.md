# Contributing to tapps-mcp

Thank you for your interest in contributing to tapps-mcp! This guide will help you get started.

## Code of Conduct

This project has a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone <your-fork-url>
cd tapps-mcp
```

## Development Setup

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode
pip install -e '.[dev]'
```

## Coding Standards

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format --check .
```

Type checking is enforced with mypy:

```bash
mypy .
```

## Testing

Please ensure all tests pass before submitting a pull request.

```bash
pytest -v
```

When adding new features, please include appropriate tests.

CI runs automatically on pull requests (workflows: brain-contract, codeql-analysis, mcp-guardrails).

## Submitting Changes

1. Create a feature branch from `main`:

   ```bash
   git checkout -b feature/my-feature
   ```

2. Make your changes and commit with a descriptive message:

   ```bash
   git add .
   git commit -m "feat: add my new feature"
   ```

3. Push your branch to your fork:

   ```bash
   git push origin feature/my-feature
   ```

4. Open a Pull Request against the `main` branch
5. Describe your changes and link any related issues
6. Wait for review and address any feedback

## Reporting Issues

When reporting issues, please include:

- A clear and descriptive title
- Steps to reproduce the problem
- Expected behavior vs actual behavior
- Your environment (OS, language version, etc.)

Please use the provided [issue templates](.github/ISSUE_TEMPLATE/) when applicable.

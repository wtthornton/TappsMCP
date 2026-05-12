# Contributing to docs-mcp

docs-mcp lives inside the TappsMCP monorepo and follows the same conventions as the parent project. See the [top-level CONTRIBUTING guide](../../../CONTRIBUTING.md) for canonical setup, code conventions, and the commit-direct-to-master workflow.

## Getting Started

```bash
git clone https://github.com/wtthornton/TappsMCP.git
cd TappsMCP
uv sync --all-packages
```

## Testing

```bash
uv run pytest packages/docs-mcp/tests/ -v
```

When adding new features, please include appropriate tests.

## Submitting Changes

This repository follows a **commit-direct-to-master** workflow — no feature branches, no pull requests (see [`.claude/rules/repo-workflow.md`](../../../.claude/rules/repo-workflow.md)).

1. Make your changes and verify they pass:

   ```bash
   uv run pytest packages/docs-mcp/tests/ -v
   uv run ruff check packages/docs-mcp/src/
   uv run mypy --strict packages/docs-mcp/src/docs_mcp/
   ```

2. Commit with a descriptive message (conventional commits preferred):

   ```bash
   git commit -m "feat(docs-mcp): add my new feature"
   ```

3. Push to `master`. The pre-push hook enforces a green non-slow unit suite before allowing the push.

## Reporting Issues

When reporting issues, please include:

- A clear and descriptive title
- Steps to reproduce the problem
- Expected behavior vs actual behavior
- Your environment (OS, language version, etc.)

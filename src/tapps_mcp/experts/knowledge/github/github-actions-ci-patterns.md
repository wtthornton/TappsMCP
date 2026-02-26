# GitHub Actions CI Patterns for Python

## Standard Python CI Workflow

```yaml
name: CI
on: [push, pull_request]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov
```

## Using uv for Fast Installs

```yaml
- name: Install uv
  run: pip install uv

- name: Install dependencies
  run: uv sync --frozen

- name: Run tests
  run: uv run pytest tests/ -v
```

## Dependency Caching

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
    cache: "pip"  # or "uv"
```

## Parallel Test Execution

Split tests across multiple runners:

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - run: pytest tests/ --splits 4 --group ${{ matrix.shard }}
```

## Conditional Jobs

```yaml
jobs:
  lint:
    if: github.event_name == 'pull_request'
    steps:
      - run: ruff check src/

  deploy:
    needs: [test, lint]
    if: github.ref == 'refs/heads/main'
    steps:
      - run: deploy.sh
```

## Job Outputs

```yaml
jobs:
  check:
    outputs:
      score: ${{ steps.quality.outputs.score }}
    steps:
      - id: quality
        run: echo "score=85" >> "$GITHUB_OUTPUT"

  gate:
    needs: check
    if: needs.check.outputs.score >= 70
```

## Upload Quality Reports

```yaml
- name: Upload report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: quality-report
    path: .tapps-mcp/reports/
    retention-days: 30
    if-no-files-found: ignore
```

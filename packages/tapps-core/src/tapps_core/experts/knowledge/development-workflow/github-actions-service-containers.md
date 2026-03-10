# GitHub Actions Service Containers

## Overview

GitHub Actions provides native service container support and Docker Compose integration for running databases, caches, and other dependencies alongside CI jobs. This guide covers the `services:` block, Docker Compose workflows, caching strategies, artifact management, concurrency groups, and matrix strategies for multi-platform testing. Updated 2026-03-10.

## GitHub Actions `services:` Block

### Basic Service Container

The `services:` block runs Docker containers alongside your job. Service containers are accessible by their key name when the job runs in a container, or via `localhost` with mapped ports when running directly on the runner.

```yaml
name: Integration Tests
on: [push, pull_request]
permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd="pg_isready -U postgres"
          --health-interval=2s
          --health-timeout=5s
          --health-retries=10
          --health-start-period=10s

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd="redis-cli ping"
          --health-interval=2s
          --health-timeout=3s
          --health-retries=5

    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379/0
        run: uv run pytest tests/integration/ -v
```

### Service Container Health Checks

GitHub Actions waits for service containers to pass their health checks before running steps. Configure health checks via the `options` field using Docker's `--health-*` flags.

**Health check parameters:**

| Flag | Purpose | Recommended Value |
|---|---|---|
| `--health-cmd` | Command to check health | Service-specific (see below) |
| `--health-interval` | Time between checks | 2-5s |
| `--health-timeout` | Max time for single check | 3-10s |
| `--health-retries` | Failures before unhealthy | 5-15 |
| `--health-start-period` | Grace period before checks count | 5-30s |

**Common health check commands:**

```yaml
# PostgreSQL
options: --health-cmd="pg_isready -U postgres" --health-interval=2s --health-timeout=5s --health-retries=10

# MySQL
options: --health-cmd="mysqladmin ping -h 127.0.0.1" --health-interval=2s --health-timeout=5s --health-retries=10

# Redis
options: --health-cmd="redis-cli ping" --health-interval=2s --health-timeout=3s --health-retries=5

# Elasticsearch
options: --health-cmd="curl -f http://localhost:9200/_cluster/health" --health-interval=5s --health-timeout=10s --health-retries=15

# RabbitMQ
options: --health-cmd="rabbitmq-diagnostics -q ping" --health-interval=5s --health-timeout=10s --health-retries=10
```

### Multiple Services

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: testdb
    ports:
      - 5432:5432
    options: --health-cmd="pg_isready -U postgres" --health-interval=2s --health-timeout=5s --health-retries=10

  redis:
    image: redis:7-alpine
    ports:
      - 6379:6379
    options: --health-cmd="redis-cli ping" --health-interval=2s --health-timeout=3s --health-retries=5

  minio:
    image: minio/minio:latest
    ports:
      - 9000:9000
    env:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    options: --health-cmd="mc ready local" --health-interval=5s --health-timeout=5s --health-retries=5
```

### Container Network Access

When the job runs directly on the runner (not in a container), services are on `localhost` via mapped ports:

```yaml
env:
  DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
```

When the job runs inside a container, use the service key as hostname:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    container: python:3.12-slim
    services:
      postgres:
        image: postgres:16-alpine
    env:
      # Use service name, not localhost
      DATABASE_URL: postgresql://postgres:test@postgres:5432/testdb
```

## Docker Compose in GitHub Actions

### Setup and Teardown

For complex multi-service rigs that exceed the `services:` block capabilities, use Docker Compose directly.

```yaml
jobs:
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Start services
        run: docker compose -f docker-compose.test.yml up -d --build --wait --wait-timeout 120

      - uses: astral-sh/setup-uv@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev

      - name: Run integration tests
        env:
          APP_URL: http://localhost:8000
          DATABASE_URL: postgresql://postgres:test@localhost:5433/testdb
        run: uv run pytest tests/integration/ -v --tb=short

      - name: Collect service logs on failure
        if: failure()
        run: docker compose -f docker-compose.test.yml logs --no-color > service-logs.txt

      - name: Upload service logs
        if: failure()
        uses: actions/upload-artifact@v6
        with:
          name: service-logs
          path: service-logs.txt

      - name: Teardown
        if: always()
        run: docker compose -f docker-compose.test.yml down -v --remove-orphans
```

### When to Use `services:` vs Docker Compose

| Feature | `services:` Block | Docker Compose |
|---|---|---|
| Setup complexity | Simple (single service) | Complex (multi-service rigs) |
| Health check wait | Automatic | Manual (`--wait` flag) |
| Custom networking | Limited | Full control |
| Build from source | Not supported | Supported (`build:`) |
| Volume mounts | Limited | Full support |
| Override files | Not supported | Supported |
| Service profiles | Not supported | Supported |

**Rule of thumb:** Use `services:` for standard databases and caches. Use Docker Compose when you need to build images, share networks, or manage complex dependencies.

## Caching Strategies

### Docker Layer Cache

Cache Docker build layers between workflow runs using GitHub Actions cache.

```yaml
- uses: docker/setup-buildx-action@v3

- uses: docker/build-push-action@v6
  with:
    context: .
    load: true
    tags: myapp:test
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### pip/uv Cache

```yaml
# uv cache
- uses: astral-sh/setup-uv@v7
  with:
    enable-cache: true

# pip cache (if not using uv)
- uses: actions/setup-python@v6
  with:
    python-version: "3.12"
    cache: "pip"
```

### Node Module Cache

```yaml
- uses: actions/setup-node@v4
  with:
    node-version: "22"
    cache: "npm"
```

### Custom Cache Keys

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.cache/uv
      .venv
    key: venv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
    restore-keys: |
      venv-${{ runner.os }}-
```

### Docker Compose Image Cache

Pre-pull images to avoid repeated downloads:

```yaml
- name: Pull service images
  run: docker compose -f docker-compose.test.yml pull

- uses: actions/cache@v4
  with:
    path: /tmp/docker-images
    key: docker-${{ hashFiles('docker-compose.test.yml') }}
    restore-keys: docker-

- name: Load cached images
  if: steps.cache.outputs.cache-hit == 'true'
  run: |
    for image in /tmp/docker-images/*.tar; do
      docker load -i "$image"
    done
```

## Artifact Upload/Download Between Jobs

### Build-Once, Test-Many Pattern

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv build
      - uses: actions/upload-artifact@v6
        with:
          name: dist
          path: dist/

  test-unit:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist/
      - run: pip install dist/*.whl
      - run: pytest tests/unit/ -v

  test-integration:
    needs: build
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: --health-cmd="pg_isready" --health-interval=2s --health-retries=10
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist/
      - run: pip install dist/*.whl
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
        run: pytest tests/integration/ -v
```

### Sharing Test Reports

```yaml
- name: Run tests with JUnit output
  run: uv run pytest tests/ -v --junitxml=test-results.xml

- uses: actions/upload-artifact@v6
  if: always()
  with:
    name: test-results-${{ matrix.os }}-${{ matrix.python-version }}
    path: test-results.xml
```

## Concurrency Groups

### Prevent Duplicate Runs

Cancel redundant workflow runs when new commits are pushed.

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

### Per-Environment Concurrency

Prevent simultaneous deployments to the same environment:

```yaml
# CI: cancel old runs
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

# Deploy: queue, don't cancel
concurrency:
  group: deploy-production
  cancel-in-progress: false  # Don't cancel an in-progress deploy
```

### PR-Specific Groups

```yaml
concurrency:
  group: pr-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: true
```

## Matrix Strategies for Multi-Platform Testing

### Basic Matrix

```yaml
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v
```

### Matrix with Service Containers (Linux Only)

Service containers only work on Linux runners. Use conditional steps for cross-platform matrices:

```yaml
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.12", "3.13"]
        include:
          - os: ubuntu-latest
            run-integration: true
    runs-on: ${{ matrix.os }}

    # Service containers -- only available on ubuntu
    services:
      postgres:
        image: ${{ matrix.run-integration && 'postgres:16-alpine' || '' }}
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd="pg_isready"
          --health-interval=2s
          --health-retries=10

    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest tests/unit/ -v

      - name: Run integration tests
        if: matrix.run-integration
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres
        run: pytest tests/integration/ -v
```

### Exclude and Include

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.12", "3.13"]
    exclude:
      # Skip Python 3.13 on Windows (known issue)
      - os: windows-latest
        python-version: "3.13"
    include:
      # Add a specific combo with extra env
      - os: ubuntu-latest
        python-version: "3.12"
        coverage: true
```

### Conditional Steps in Matrix

```yaml
- name: Upload coverage
  if: matrix.coverage
  uses: codecov/codecov-action@v5
  with:
    files: coverage.xml
```

## Example: Full CI Workflow with Service Containers

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy --strict src/

  unit-test:
    needs: lint
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --dev
      - name: Run unit tests
        run: uv run pytest tests/unit/ -v --tb=short
      - name: Run unit tests with coverage
        if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        run: uv run pytest tests/unit/ --cov=src --cov-report=xml -v
      - uses: codecov/codecov-action@v5
        if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        with:
          files: coverage.xml

  integration-test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd="pg_isready -U postgres"
          --health-interval=2s
          --health-timeout=5s
          --health-retries=10
          --health-start-period=10s
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd="redis-cli ping"
          --health-interval=2s
          --health-timeout=3s
          --health-retries=5
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - name: Run database migrations
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
        run: uv run alembic upgrade head
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379/0
        run: uv run pytest tests/integration/ -v --tb=short

  docker-test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v3
      - name: Build and start test rig
        run: docker compose -f docker-compose.test.yml up -d --build --wait --wait-timeout 120
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - name: Run smoke tests
        env:
          APP_URL: http://localhost:8000
        run: uv run pytest tests/smoke/ -v --tb=short
      - name: Collect logs on failure
        if: failure()
        run: docker compose -f docker-compose.test.yml logs --no-color > service-logs.txt
      - uses: actions/upload-artifact@v6
        if: failure()
        with:
          name: service-logs
          path: service-logs.txt
      - name: Teardown
        if: always()
        run: docker compose -f docker-compose.test.yml down -v --remove-orphans

  all-checks:
    needs: [unit-test, integration-test, docker-test]
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Verify all checks passed
        run: |
          if [ "${{ needs.unit-test.result }}" != "success" ] || \
             [ "${{ needs.integration-test.result }}" != "success" ] || \
             [ "${{ needs.docker-test.result }}" != "success" ]; then
            echo "::error::One or more checks failed"
            exit 1
          fi
```

## Anti-Patterns and Common Mistakes

### No Health Checks on Service Containers

**Problem:** Steps start before the database accepts connections, causing flaky test failures.

```yaml
# Bad: no health check -- job steps start immediately
services:
  postgres:
    image: postgres:16-alpine
    ports:
      - 5432:5432

# Good: health check ensures service is ready
services:
  postgres:
    image: postgres:16-alpine
    ports:
      - 5432:5432
    options: --health-cmd="pg_isready" --health-interval=2s --health-retries=10
```

### Using Service Containers on Non-Linux Runners

**Problem:** Service containers only work on `ubuntu-*` runners. They silently fail on Windows and macOS.

```yaml
# Bad: service containers on Windows
jobs:
  test:
    runs-on: windows-latest
    services:
      postgres:  # This will not work
        image: postgres:16-alpine

# Good: restrict service containers to Linux
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
```

### Not Capturing Logs on Failure

**Problem:** When container-based tests fail, you have no way to debug the service side.

```yaml
# Good: always collect logs on failure
- name: Service logs
  if: failure()
  run: docker compose logs --no-color > logs.txt
- uses: actions/upload-artifact@v6
  if: failure()
  with:
    name: debug-logs
    path: logs.txt
```

### Missing `if: always()` on Teardown

**Problem:** Docker Compose teardown is skipped when tests fail, leaving resources allocated.

```yaml
# Bad: teardown only runs on success
- run: docker compose down -v

# Good: teardown runs regardless of test outcome
- name: Teardown
  if: always()
  run: docker compose -f docker-compose.test.yml down -v --remove-orphans
```

### Cancel-in-Progress on Release Workflows

**Problem:** A new commit cancels an in-progress publish, leaving a partial release.

```yaml
# Bad: cancels release mid-flight
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: true

# Good: queue releases, never cancel
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false
```

### Overly Broad Matrix Without Service Limitations

**Problem:** Running integration tests on all matrix combinations when services only work on Linux wastes time and creates confusing failures.

Use `include` to limit which matrix cells run integration tests, or split unit and integration into separate jobs.

## See Also

- `github-actions-advanced.md` -- Advanced GitHub Actions patterns (OIDC, artifacts, releases)
- `ci-cd-patterns.md` -- General CI/CD pipeline patterns
- `docker-compose-testing.md` -- Docker Compose test rig patterns
- `container-testing-patterns.md` -- pytest fixtures for container tests

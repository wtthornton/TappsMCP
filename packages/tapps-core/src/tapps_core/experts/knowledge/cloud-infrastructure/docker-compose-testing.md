# Docker Compose Testing Patterns

## Overview

Docker Compose v2 provides powerful orchestration for multi-service test rigs. This guide covers override files, profile-based service selection, health check ordering, environment injection, and complete examples of test rigs combining application services with databases and caches. Updated 2026-03-10.

## Docker Compose v2 for Test Rigs

### Base + Override File Pattern

Keep the production `docker-compose.yml` clean and layer test-specific configuration via override files.

```yaml
# docker-compose.yml (base -- production config)
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://app:secret@db:5432/appdb

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: appdb

volumes:
  pgdata:
```

```yaml
# docker-compose.test.yml (override -- test-specific)
services:
  app:
    build:
      context: .
      target: test  # Use test stage from multi-stage Dockerfile
    environment:
      DATABASE_URL: postgresql://postgres:test@db:5432/testdb
      ENVIRONMENT: test
      LOG_LEVEL: DEBUG
    depends_on:
      db:
        condition: service_healthy

  db:
    environment:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: testdb
    ports:
      - "5433:5432"  # Non-standard port to avoid conflicts
    volumes:
      - ./tests/init-scripts:/docker-entrypoint-initdb.d:ro
    # No persistent volume -- test data is ephemeral
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 2s
      timeout: 5s
      retries: 10
```

Launch with both files:

```bash
# Compose merges the files: test overrides base
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d

# Or use COMPOSE_FILE env var
export COMPOSE_FILE=docker-compose.yml:docker-compose.test.yml
docker compose up -d
```

### Standalone Test Compose File

For simpler projects, use a single dedicated test file:

```bash
docker compose -f docker-compose.test.yml up -d --build --wait
pytest tests/integration/
docker compose -f docker-compose.test.yml down -v --remove-orphans
```

## Profile-Based Service Selection

### Defining Profiles

Use `profiles` to optionally include services. Services without a profile always start. Services with a profile start only when that profile is activated.

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    # No profile -- always starts

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: testdb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 2s
      timeout: 5s
      retries: 10
    # No profile -- always starts (app needs it)

  redis:
    image: redis:7-alpine
    profiles:
      - cache
      - full
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 5

  mailhog:
    image: mailhog/mailhog:latest
    profiles:
      - email
      - full
    ports:
      - "8025:8025"  # Web UI

  selenium:
    image: selenium/standalone-chrome:latest
    profiles:
      - e2e
      - full
    ports:
      - "4444:4444"
    shm_size: 2gb
```

### Activating Profiles

```bash
# Unit/integration tests: only app + db
docker compose up -d

# Tests that need caching
docker compose --profile cache up -d

# Full end-to-end rig
docker compose --profile full up -d

# Multiple specific profiles
docker compose --profile cache --profile email up -d
```

### Profile-Aware pytest Configuration

```python
import os
import pytest


def pytest_configure(config):
    """Register profile-based markers."""
    config.addinivalue_line("markers", "needs_redis: requires Redis container")
    config.addinivalue_line("markers", "needs_email: requires mail server")
    config.addinivalue_line("markers", "e2e: end-to-end browser tests")


def pytest_collection_modifyitems(config, items):
    """Skip tests whose required containers are not running."""
    active_profiles = os.environ.get("COMPOSE_PROFILES", "").split(",")

    skip_redis = pytest.mark.skip(reason="Redis not running (needs --profile cache)")
    skip_email = pytest.mark.skip(reason="Mail server not running (needs --profile email)")

    for item in items:
        if "needs_redis" in item.keywords and "cache" not in active_profiles:
            item.add_marker(skip_redis)
        if "needs_email" in item.keywords and "email" not in active_profiles:
            item.add_marker(skip_email)
```

## Service Dependencies and Health Check Ordering

### depends_on with Health Checks

Docker Compose v2 supports `condition: service_healthy` to ensure services start in the correct order.

```yaml
services:
  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 2s
      timeout: 5s
      retries: 10
      start_period: 5s

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 5

  migrate:
    build: .
    command: ["python", "-m", "alembic", "upgrade", "head"]
    depends_on:
      db:
        condition: service_healthy
    # One-shot service: runs migration then exits

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
```

### Startup Order

The above configuration enforces:

1. `db` and `redis` start in parallel
2. `migrate` waits for `db` to be healthy, then runs migrations
3. `app` waits for `db` healthy + `redis` healthy + `migrate` completed successfully
4. Tests wait for `app` to be healthy

### The `--wait` Flag

```bash
# Blocks until all services with health checks report healthy
docker compose up -d --wait

# With a timeout (default: no timeout)
docker compose up -d --wait --wait-timeout 120
```

## Environment Variable Injection

### .env Files for Test Configuration

```bash
# .env.test
POSTGRES_PASSWORD=test
POSTGRES_DB=testdb
APP_SECRET_KEY=test-secret-not-for-production
LOG_LEVEL=DEBUG
CACHE_TTL=0
RATE_LIMIT_ENABLED=false
```

```yaml
# docker-compose.test.yml
services:
  app:
    env_file:
      - .env.test
    environment:
      # Inline vars override .env.test
      DATABASE_URL: postgresql://postgres:test@db:5432/testdb
```

### Dynamic Environment from CI

```yaml
services:
  app:
    environment:
      # Compose interpolates host environment variables
      CI: ${CI:-false}
      GITHUB_RUN_ID: ${GITHUB_RUN_ID:-local}
      TEST_PARALLELISM: ${TEST_PARALLELISM:-4}
```

### Environment Variable Validation

Add a startup check in the app to fail fast on missing configuration:

```python
# src/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    environment: str = "production"
    log_level: str = "INFO"

    model_config = {"env_file": ".env"}


# Fails immediately at container start if DATABASE_URL is missing
settings = Settings()
```

## Example: Multi-Service Test Rig

### Full docker-compose.test.yml

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:test@db:5432/testdb
      REDIS_URL: redis://redis:6379/0
      ENVIRONMENT: test
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
    volumes:
      - ./tests/fixtures:/app/fixtures:ro

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: testdb
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 2s
      timeout: 5s
      retries: 10
    volumes:
      - ./tests/init-scripts:/docker-entrypoint-initdb.d:ro

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 5
    command: ["redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru"]
```

### Test Script (Makefile Target)

```makefile
.PHONY: test-integration
test-integration:
	docker compose -f docker-compose.test.yml up -d --build --wait
	pytest tests/integration/ -v --tb=short; \
	EXIT_CODE=$$?; \
	docker compose -f docker-compose.test.yml down -v --remove-orphans; \
	exit $$EXIT_CODE
```

### pytest conftest.py for Multi-Service Rig

```python
import subprocess
import pytest
import httpx
import time
import redis


def wait_for_url(url: str, timeout: float = 60.0) -> None:
    """Wait for an HTTP endpoint to return 200."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1.0)
    raise TimeoutError(f"{url} not ready after {timeout}s")


@pytest.fixture(scope="session")
def services():
    """Start the full test rig and wait for all services."""
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml",
         "up", "-d", "--build", "--wait"],
        check=True,
    )
    wait_for_url("http://localhost:8000/health")
    yield {
        "app_url": "http://localhost:8000",
        "db_url": "postgresql://postgres:test@localhost:5433/testdb",
        "redis_url": "redis://localhost:6380/0",
    }
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml",
         "down", "-v", "--remove-orphans"],
        check=True,
    )


@pytest.fixture
def app_client(services):
    """Provide an httpx client pointed at the test app."""
    with httpx.Client(base_url=services["app_url"]) as client:
        yield client


@pytest.fixture
def redis_client(services):
    """Provide a Redis client connected to the test Redis."""
    client = redis.from_url(services["redis_url"])
    yield client
    client.flushdb()  # Clean up between tests
```

### Integration Tests

```python
import pytest


@pytest.mark.integration
class TestMultiServiceRig:
    def test_app_connects_to_database(self, app_client):
        """Verify the app can query the database."""
        response = app_client.get("/api/items")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_app_uses_redis_cache(self, app_client, redis_client):
        """Verify cache-aside pattern works."""
        # First call: cache miss, hits DB
        resp1 = app_client.get("/api/items/1")
        assert resp1.status_code == 200

        # Verify item was cached
        cached = redis_client.get("item:1")
        assert cached is not None

        # Second call: should hit cache
        resp2 = app_client.get("/api/items/1")
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_app_health_includes_dependencies(self, app_client):
        """Health check reports status of DB and Redis."""
        response = app_client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["dependencies"]["database"] == "connected"
        assert data["dependencies"]["redis"] == "connected"
```

## Anti-Patterns and Common Mistakes

### Using `depends_on` Without Health Checks

**Problem:** `depends_on` only waits for the container to start, not for the service inside to be ready.

```yaml
# Bad: app starts before DB is ready to accept connections
services:
  app:
    depends_on:
      - db

# Good: app waits for DB health check to pass
services:
  app:
    depends_on:
      db:
        condition: service_healthy
```

### Persistent Volumes in Test Compose

**Problem:** Test data leaks between test runs.

```yaml
# Bad: named volume persists across runs
volumes:
  testdata:

# Good: no named volume, or use tmpfs
services:
  db:
    tmpfs:
      - /var/lib/postgresql/data
```

### Hardcoded Container Names

**Problem:** Compose project name collisions in CI.

```yaml
# Bad: fixed container name
services:
  db:
    container_name: test-db  # Collides with parallel CI runs

# Good: let Compose generate names, use -p flag for isolation
# docker compose -p "test-${GITHUB_RUN_ID}" up -d
```

### Missing `--remove-orphans`

**Problem:** Renaming a service in `docker-compose.test.yml` leaves the old container running.

```bash
# Bad
docker compose -f docker-compose.test.yml down

# Good
docker compose -f docker-compose.test.yml down -v --remove-orphans
```

### Forgetting to Publish Ports for Host-Side Tests

**Problem:** Test code on the host cannot reach services inside the Docker network.

```yaml
# Bad: no ports published, tests on host cannot connect
services:
  db:
    image: postgres:16-alpine

# Good: publish on a non-standard port
services:
  db:
    image: postgres:16-alpine
    ports:
      - "5433:5432"
```

### Not Using `--wait` or Health Checks

**Problem:** `docker compose up -d` returns immediately; tests start before services are ready.

```bash
# Bad: starts containers and immediately runs tests
docker compose up -d
pytest tests/integration/

# Good: waits for health checks
docker compose up -d --wait --wait-timeout 120
pytest tests/integration/
```

## See Also

- `containerization.md` -- Docker image building patterns
- `container-testing-patterns.md` -- pytest fixtures and health check strategies
- `github-actions-service-containers.md` -- Running Docker Compose in CI
- `ci-cd-patterns.md` -- General CI/CD pipeline patterns

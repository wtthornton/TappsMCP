# Container Testing Patterns

## Overview

Testing containerized applications requires specialized fixtures, health check strategies, and cleanup patterns. This guide covers pytest-docker integration, container lifecycle management, network configuration, and smoke testing patterns for Python services running in Docker containers. Updated 2026-03-10.

## pytest-docker Fixtures

### Basic Container Fixture

Use `pytest-docker` or manual `subprocess` calls to manage containers in test fixtures. The fixture pattern ensures containers start before tests and stop after.

```python
import pytest
import subprocess
import time
import httpx


@pytest.fixture(scope="session")
def docker_compose_up():
    """Start services via Docker Compose for the test session."""
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d"],
        check=True,
        capture_output=True,
    )
    yield
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"],
        check=True,
        capture_output=True,
    )
```

### Scoped Fixtures for Isolation

Choose fixture scope based on how much isolation tests need versus startup cost.

```python
@pytest.fixture(scope="session")
def database_container():
    """Session-scoped: one DB for all tests (fast, shared state)."""
    container_id = subprocess.check_output(
        ["docker", "run", "-d", "-p", "5433:5432",
         "-e", "POSTGRES_PASSWORD=test",
         "-e", "POSTGRES_DB=testdb",
         "postgres:16-alpine"],
    ).decode().strip()
    yield container_id
    subprocess.run(["docker", "rm", "-f", container_id], check=True)


@pytest.fixture(scope="function")
def clean_database(database_container):
    """Function-scoped: reset DB state between tests."""
    yield database_container
    # Truncate all tables after each test
    subprocess.run(
        ["docker", "exec", database_container,
         "psql", "-U", "postgres", "-d", "testdb",
         "-c", "DO $$ DECLARE r RECORD; BEGIN FOR r IN "
               "(SELECT tablename FROM pg_tables WHERE schemaname='public') "
               "LOOP EXECUTE 'TRUNCATE TABLE ' || r.tablename || ' CASCADE'; "
               "END LOOP; END $$;"],
        check=True,
    )
```

### conftest.py Organization

Place container fixtures in the appropriate `conftest.py` level.

```python
# tests/integration/conftest.py
import pytest


def pytest_collection_modifyitems(items):
    """Auto-mark all tests in integration/ with the 'integration' marker."""
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def app_container(docker_compose_up, wait_for_healthy):
    """Provide the running app container after health checks pass."""
    wait_for_healthy("http://localhost:8000/health", timeout=30)
    return "http://localhost:8000"
```

### pytest Markers for Container Tests

```python
# pyproject.toml
# [tool.pytest.ini_options]
# markers = [
#     "integration: tests requiring Docker containers",
#     "slow: tests with container startup overhead",
#     "docker: tests that require Docker daemon",
# ]

# Usage in tests
@pytest.mark.integration
@pytest.mark.docker
def test_api_returns_items(app_container):
    response = httpx.get(f"{app_container}/api/items")
    assert response.status_code == 200
```

Run subsets with markers:

```bash
# Run only unit tests (skip containers)
pytest -m "not integration"

# Run only container-based tests
pytest -m docker

# Run everything
pytest
```

## Health Check Wait Strategies

### Simple Polling

```python
import httpx
import time


def wait_for_healthy(url: str, timeout: float = 30.0, interval: float = 0.5) -> None:
    """Poll a health endpoint until it returns 200 or timeout expires."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.ConnectError as exc:
            last_error = exc
        time.sleep(interval)

    raise TimeoutError(
        f"Service at {url} not healthy after {timeout}s. "
        f"Last error: {last_error}"
    )
```

### Exponential Backoff

For services with slow startup (databases, JVM apps), exponential backoff avoids hammering the container.

```python
def wait_for_healthy_backoff(
    url: str,
    timeout: float = 60.0,
    initial_interval: float = 0.5,
    max_interval: float = 5.0,
    backoff_factor: float = 2.0,
) -> None:
    """Wait with exponential backoff for a service to become healthy."""
    deadline = time.monotonic() + timeout
    interval = initial_interval

    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.ConnectError:
            pass

        time.sleep(min(interval, max_interval))
        interval *= backoff_factor

    raise TimeoutError(f"Service at {url} not healthy after {timeout}s")
```

### TCP Port Check (No HTTP)

For services that expose TCP but not HTTP (databases, Redis, message queues):

```python
import socket


def wait_for_port(
    host: str, port: int, timeout: float = 30.0, interval: float = 0.5
) -> None:
    """Wait for a TCP port to accept connections."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            sock.close()
            return
        except (ConnectionRefusedError, socket.timeout, OSError):
            pass
        finally:
            sock.close()
        time.sleep(interval)

    raise TimeoutError(f"Port {host}:{port} not available after {timeout}s")
```

## Container Cleanup and Isolation

### Cleanup Strategies

**Always use `docker compose down -v`** to remove both containers and volumes:

```python
@pytest.fixture(scope="session", autouse=True)
def cleanup_containers():
    """Ensure containers are cleaned up even if tests crash."""
    yield
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v",
         "--remove-orphans"],
        capture_output=True,
    )
```

### Unique Container Names

Prevent collisions when tests run in parallel (CI matrix builds):

```python
import os
import uuid


@pytest.fixture(scope="session")
def compose_project_name():
    """Generate a unique project name to isolate parallel test runs."""
    run_id = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex[:8])
    return f"test-{run_id}"


@pytest.fixture(scope="session")
def docker_compose_up(compose_project_name):
    subprocess.run(
        ["docker", "compose", "-p", compose_project_name,
         "-f", "docker-compose.test.yml", "up", "-d"],
        check=True,
    )
    yield
    subprocess.run(
        ["docker", "compose", "-p", compose_project_name,
         "-f", "docker-compose.test.yml", "down", "-v"],
        check=True,
    )
```

### Database Transaction Rollback

For database-backed tests, wrap each test in a transaction that rolls back:

```python
@pytest.fixture
def db_session(database_container):
    """Provide a database session that rolls back after each test."""
    import sqlalchemy
    engine = sqlalchemy.create_engine(
        "postgresql://postgres:test@localhost:5433/testdb"
    )
    connection = engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()
```

## Network Modes for Test Containers

### Bridge Network (Default)

Containers get internal IPs. Access via published ports from the host.

```yaml
# docker-compose.test.yml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    networks:
      - test-net
  db:
    image: postgres:16-alpine
    # No ports published -- only app talks to db
    networks:
      - test-net

networks:
  test-net:
    driver: bridge
```

### Host Network Mode

Useful when the app needs to reach services on `localhost` (like a test database started outside Docker):

```yaml
services:
  app:
    build: .
    network_mode: host
```

**Caveat:** Host networking is not supported on Docker Desktop for Mac/Windows. Use bridge mode with published ports for cross-platform compatibility.

### Container-to-Container Communication

Services on the same Docker network can reach each other by service name:

```python
# Inside the app container, connect to DB by service name
DATABASE_URL = "postgresql://postgres:test@db:5432/testdb"

# From the test host, connect via published port
DATABASE_URL = "postgresql://postgres:test@localhost:5433/testdb"
```

## Volume Mounts for Test Fixtures

### Mounting Test Data

```yaml
services:
  app:
    build: .
    volumes:
      - ./tests/fixtures:/app/fixtures:ro
      - ./tests/data:/app/test-data:ro
```

### Mounting Configuration

```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - ./tests/init-scripts:/docker-entrypoint-initdb.d:ro
```

Place SQL initialization scripts in `tests/init-scripts/`:

```sql
-- tests/init-scripts/01-schema.sql
CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- tests/init-scripts/02-seed.sql
INSERT INTO items (name) VALUES ('test-item-1'), ('test-item-2');
```

## Smoke Testing with httpx

### Basic Smoke Test

```python
import httpx
import pytest


@pytest.mark.integration
class TestAppSmoke:
    """Smoke tests for the containerized FastAPI app."""

    def test_health_endpoint(self, app_container: str) -> None:
        response = httpx.get(f"{app_container}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_create_and_retrieve_item(self, app_container: str) -> None:
        # Create
        create_resp = httpx.post(
            f"{app_container}/api/items",
            json={"name": "test-item"},
        )
        assert create_resp.status_code == 201
        item_id = create_resp.json()["id"]

        # Retrieve
        get_resp = httpx.get(f"{app_container}/api/items/{item_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "test-item"

    def test_not_found_returns_404(self, app_container: str) -> None:
        response = httpx.get(f"{app_container}/api/items/99999")
        assert response.status_code == 404
```

### Async Smoke Tests

```python
import httpx
import pytest


@pytest.mark.integration
@pytest.mark.anyio
async def test_concurrent_requests(app_container: str) -> None:
    """Verify the app handles concurrent requests."""
    async with httpx.AsyncClient(base_url=app_container) as client:
        import asyncio
        responses = await asyncio.gather(
            *[client.get("/health") for _ in range(10)]
        )
        assert all(r.status_code == 200 for r in responses)
```

## Example: Testing a FastAPI App in Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY src/ src/
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=5 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.test.yml

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:test@db:5432/testdb
      ENVIRONMENT: test
    depends_on:
      db:
        condition: service_healthy

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
    volumes:
      - ./tests/init-scripts:/docker-entrypoint-initdb.d:ro
```

### Complete Test conftest.py

```python
import subprocess
import pytest
import httpx
import time


def wait_for_healthy(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1.0)
    raise TimeoutError(f"{url} not healthy after {timeout}s")


@pytest.fixture(scope="session")
def app_container():
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d",
         "--build", "--wait"],
        check=True,
    )
    wait_for_healthy("http://localhost:8000/health", timeout=60)
    yield "http://localhost:8000"
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"],
        check=True,
    )
```

## Anti-Patterns and Common Mistakes

### Hardcoded Ports Without Conflict Avoidance

**Problem:** Tests fail when port 5432 is already in use.

```python
# Bad: hardcoded well-known port
subprocess.run(["docker", "run", "-p", "5432:5432", "postgres:16-alpine"])

# Good: use a non-standard host port or let Docker assign one
subprocess.run(["docker", "run", "-p", "5433:5432", "postgres:16-alpine"])

# Better: let Docker pick a random port
result = subprocess.check_output(
    ["docker", "run", "-d", "-P", "postgres:16-alpine"]
).decode().strip()
port = subprocess.check_output(
    ["docker", "port", result, "5432"]
).decode().strip().split(":")[-1]
```

### No Health Check Before Tests

**Problem:** Tests start before the service is ready, causing flaky failures.

```python
# Bad: arbitrary sleep
time.sleep(10)
run_tests()

# Good: poll health endpoint
wait_for_healthy("http://localhost:8000/health", timeout=30)
run_tests()
```

### Leaking Containers

**Problem:** Crashed test runs leave containers running, consuming resources.

```python
# Bad: cleanup only in fixture teardown (skipped on crash)
@pytest.fixture
def container():
    start_container()
    yield
    stop_container()  # Never runs if test process is killed

# Good: add a finalizer AND label containers for cleanup
@pytest.fixture
def container():
    cid = start_container(labels={"test-run": "true"})
    yield cid
    stop_container(cid)

# CI cleanup step (runs even if tests fail):
# docker ps -q --filter "label=test-run" | xargs -r docker rm -f
```

### Shared Mutable State Across Tests

**Problem:** Test A writes to the database, Test B reads stale data.

Use one of:
1. Transaction rollback per test (fastest)
2. Truncate tables between tests
3. Separate database per test (slowest, most isolated)

### Missing `--remove-orphans` on Down

**Problem:** Renamed services leave zombie containers.

```bash
# Bad
docker compose down

# Good
docker compose down -v --remove-orphans
```

## See Also

- `best-practices.md` -- General testing best practices
- `containerization.md` -- Docker image building patterns
- `docker-compose-testing.md` -- Docker Compose test rig patterns
- `github-actions-service-containers.md` -- CI service container patterns

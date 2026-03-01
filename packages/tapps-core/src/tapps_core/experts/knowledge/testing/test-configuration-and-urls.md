# Test Configuration, URLs, and Environment Patterns

## Overview

Keeping tests portable across local, CI, and containerized environments requires
careful management of configuration, URLs, environment variables, and external
dependencies. This guide covers pytest patterns for configuration isolation,
network mocking, secret management, and CI/CD compatibility.

## Base URL Configuration

### Fixture-Based URL Management

Avoid hardcoded URLs in test logic. Use fixtures that read from environment:

```python
import os
import pytest

@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for integration tests, configurable via env."""
    return os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def api_url(base_url: str) -> str:
    """API endpoint URL derived from base URL."""
    return f"{base_url}/api/v1"
```

### URL Builder Pattern

Centralize URL construction to keep tests focused on behavior:

```python
from dataclasses import dataclass

@dataclass
class TestEndpoints:
    """Centralized endpoint configuration for tests."""

    base_url: str

    @property
    def health(self) -> str:
        return f"{self.base_url}/health"

    @property
    def score(self) -> str:
        return f"{self.base_url}/api/v1/score"

    @property
    def validate(self) -> str:
        return f"{self.base_url}/api/v1/validate"

    def file_url(self, file_path: str) -> str:
        return f"{self.base_url}/api/v1/files/{file_path}"


@pytest.fixture(scope="session")
def endpoints(base_url: str) -> TestEndpoints:
    return TestEndpoints(base_url=base_url)
```

### Multiple Service URLs

When tests depend on multiple services:

```python
@pytest.fixture(scope="session")
def service_urls() -> dict[str, str]:
    """URLs for all external services used in tests."""
    return {
        "api": os.getenv("TEST_API_URL", "http://127.0.0.1:8000"),
        "db": os.getenv("TEST_DB_URL", "sqlite:///test.db"),
        "redis": os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/1"),
        "mcp": os.getenv("TEST_MCP_URL", "http://127.0.0.1:8080"),
    }
```

## Environment Variable Strategy

### Setting Environment Variables in Tests

Use `monkeypatch` for isolated environment variable manipulation:

```python
def test_reads_project_root(monkeypatch):
    """Verify function reads TAPPS_MCP_PROJECT_ROOT."""
    monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", "/test/project")
    from tapps_mcp.config.settings import load_settings
    settings = load_settings()
    assert str(settings.project_root) == "/test/project"


def test_handles_missing_env(monkeypatch):
    """Verify graceful fallback when env var is missing."""
    monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)
    from tapps_mcp.config.settings import load_settings
    settings = load_settings()
    assert settings.project_root is not None  # uses default
```

### Environment Fixture Patterns

```python
@pytest.fixture
def clean_env(monkeypatch):
    """Remove all TAPPS_MCP_ environment variables."""
    for key in list(os.environ):
        if key.startswith("TAPPS_MCP_"):
            monkeypatch.delenv(key)


@pytest.fixture
def production_like_env(monkeypatch, tmp_path):
    """Set up environment matching production configuration."""
    monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("TAPPS_MCP_CONFIG", str(tmp_path / ".tapps-mcp.yaml"))
    monkeypatch.setenv("TAPPS_MCP_LOG_LEVEL", "WARNING")
    return tmp_path
```

### Never Commit Real Secrets

```python
# conftest.py
@pytest.fixture
def mock_api_keys(monkeypatch):
    """Provide fake API keys for testing."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_not_real")
    monkeypatch.setenv("API_KEY", "test-api-key-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
```

## Fixtures for Config Isolation

### Config Object Fixtures

Provide fixtures that construct config objects from env and test overrides:

```python
from pathlib import Path

@pytest.fixture
def test_config(tmp_path, monkeypatch):
    """Create an isolated test configuration."""
    config_file = tmp_path / ".tapps-mcp.yaml"
    config_file.write_text(
        "quality_preset: standard\n"
        "llm_engagement_level: medium\n"
    )
    monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("TAPPS_MCP_CONFIG", str(config_file))

    from tapps_mcp.config.settings import load_settings, _reset_settings_cache
    _reset_settings_cache()
    settings = load_settings()
    yield settings
    _reset_settings_cache()
```

### Scoping Strategy

```python
# Function-scoped (default) - fresh per test, safest for mutation
@pytest.fixture
def mutable_config(tmp_path):
    """Config that tests can modify safely."""
    pass

# Session-scoped - expensive setup, shared across all tests
@pytest.fixture(scope="session")
def knowledge_base():
    """Load knowledge base once for all tests."""
    return load_all_knowledge_files()

# Module-scoped - shared within a test file
@pytest.fixture(scope="module")
def db_connection(tmp_path_factory):
    """Database connection shared within a test module."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    conn = create_connection(db_path)
    yield conn
    conn.close()
```

## Monkeypatching Network and Endpoints

### Patching HTTP Clients

```python
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_http_client():
    """Mock HTTP client for deterministic tests."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value={"status": 200, "data": {}})
    mock.post = AsyncMock(return_value={"status": 201, "data": {}})
    return mock


@pytest.mark.asyncio
async def test_api_call(mock_http_client, monkeypatch):
    """Test API integration with mocked HTTP client."""
    monkeypatch.setattr(
        "tapps_mcp.knowledge.context7_client.http_get",
        mock_http_client.get,
    )
    result = await lookup_docs("fastapi")
    assert result is not None
```

### Mocking Subprocess Calls

```python
from unittest.mock import AsyncMock

@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess execution for tool tests."""
    mock_result = AsyncMock()
    mock_result.returncode = 0
    mock_result.stdout = "[]"
    mock_result.stderr = ""

    mock_run = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(
        "tapps_mcp.tools.subprocess_runner.run_subprocess",
        mock_run,
    )
    return mock_run
```

### Fake Server for Integration Tests

```python
import asyncio
from aiohttp import web

@pytest.fixture
async def fake_api_server():
    """Spin up a fake API server for integration tests."""
    async def handle_score(request):
        return web.json_response({"overall_score": 85.0})

    app = web.Application()
    app.router.add_get("/api/v1/score", handle_score)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"

    await runner.cleanup()
```

## Avoiding Localhost Assumptions

### Container-Aware URLs

In CI, services may run in containers with custom hostnames:

```python
@pytest.fixture(scope="session")
def database_url() -> str:
    """Database URL that works in both local and CI environments."""
    # Docker Compose uses service names as hostnames
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "test")
    return f"postgresql://test:test@{host}:{port}/{name}"
```

### Configurable Timeouts

```python
@pytest.fixture(scope="session")
def request_timeout() -> float:
    """Timeout for HTTP requests, longer in CI for shared runners."""
    default = 5.0
    ci_timeout = 30.0
    return ci_timeout if os.getenv("CI") else default
```

### GitHub Actions Service Containers

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
    env:
      DB_HOST: localhost
      DB_PORT: 5432
      DB_NAME: test
    steps:
      - run: pytest tests/ -v
```

## Secret Management in Tests

### Placeholder Secrets

```python
# conftest.py

# NEVER use real secrets in tests
FAKE_SECRETS = {
    "GITHUB_TOKEN": "ghp_0000000000000000000000000000000000000000",
    "API_KEY": "sk-test-000000000000000000000000",
    "WEBHOOK_SECRET": "test-webhook-secret-not-real",
}

@pytest.fixture(autouse=True)
def _inject_fake_secrets(monkeypatch):
    """Ensure no real secrets leak into test execution."""
    for key, value in FAKE_SECRETS.items():
        monkeypatch.setenv(key, value)
```

### Detecting Leaked Secrets

```python
import re

def test_no_secrets_in_output(capsys):
    """Verify tool output does not contain secrets."""
    # Run the tool
    result = run_some_tool()

    # Check output for secret patterns
    secret_patterns = [
        r"ghp_[a-zA-Z0-9]{36}",          # GitHub token
        r"sk-[a-zA-Z0-9]{48}",            # API key
        r"-----BEGIN (RSA )?PRIVATE KEY", # Private key
    ]

    for pattern in secret_patterns:
        assert not re.search(pattern, result), f"Secret pattern found: {pattern}"
```

## Test Data Management

### Fixture Files

```python
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_python_file(tmp_path) -> Path:
    """Create a sample Python file for testing."""
    content = (FIXTURES_DIR / "sample.py").read_text()
    target = tmp_path / "sample.py"
    target.write_text(content)
    return target


@pytest.fixture
def sample_config(tmp_path) -> Path:
    """Create a sample config file for testing."""
    config = tmp_path / ".tapps-mcp.yaml"
    config.write_text(
        "quality_preset: standard\n"
        "llm_engagement_level: medium\n"
    )
    return config
```

### Parameterized URL Tests

```python
@pytest.mark.parametrize("endpoint,expected_status", [
    ("/health", 200),
    ("/api/v1/score", 200),
    ("/nonexistent", 404),
    ("/api/v1/admin", 403),
])
def test_endpoint_status(endpoint, expected_status, base_url):
    """Verify endpoint responses across the API surface."""
    pass  # Implementation depends on HTTP client
```

## Quick Checklist

- No hardcoded production URLs in test code
- All external endpoints configurable by env or fixtures
- Secrets replaced with test values via monkeypatch
- Network calls patched or isolated (no real HTTP in unit tests)
- Base URL and ports configurable for CI environments
- Timeouts configurable and conservative for shared runners
- Container hostnames supported (not just localhost)
- Test data in fixtures directory, not inline
- Cache singletons reset between tests
- Config fixtures scoped appropriately (function for mutable, session for read-only)

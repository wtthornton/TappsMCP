# Test Configuration, URLs, and Environment Patterns

Use these patterns to keep tests portable across local, CI, and containerized environments.

## Base URL configuration

- Avoid hardcoded URLs such as `http://localhost:8000` in test logic.
- Prefer a fixture that reads `TEST_BASE_URL` and falls back to a sensible default.
- Keep URL building in one helper so tests focus on behavior.

```python
import os
import pytest

@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")
```

## Environment variable strategy

- Use explicit env var names for external dependencies (`DB_URL`, `REDIS_URL`, `API_KEY`).
- In tests, set env vars with `monkeypatch.setenv` and clear with `monkeypatch.delenv`.
- Never commit real secrets in `.env` fixtures; use placeholders.

```python
def test_reads_env(monkeypatch):
    monkeypatch.setenv("DB_URL", "sqlite:///test.db")
    # call function under test
```

## Fixtures for config isolation

- Provide a fixture that constructs config objects from env and test overrides.
- Scope config fixtures narrowly (`function`) unless expensive to build.
- For framework settings modules, use temporary files/directories and patch paths.

## Monkeypatching network and endpoints

- Patch network entry points (`requests.Session.request`, SDK clients) for determinism.
- Inject clients into app services where possible; avoid global singletons in tests.
- Prefer fake servers only for integration tests, not unit tests.

## Avoiding localhost assumptions

- In CI, services may run in containers with custom hostnames.
- Use compose service names or injected `TEST_BASE_URL`, not bare localhost.
- Keep timeout values configurable and conservative for shared runners.

## Quick checklist

- [ ] No hardcoded production URLs
- [ ] All external endpoints configurable by env/fixtures
- [ ] Secrets replaced with test values
- [ ] Network calls patched or isolated
- [ ] Base URL and ports configurable in CI

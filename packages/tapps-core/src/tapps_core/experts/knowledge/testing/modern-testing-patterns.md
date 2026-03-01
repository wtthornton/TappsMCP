# Modern Testing Patterns

## Overview

This guide covers modern testing patterns including async testing, property-based testing with Hypothesis, snapshot testing, and mutation testing. These patterns complement traditional unit and integration testing for more robust test suites.

## Async Testing

### pytest-asyncio

**Setup:**
```python
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # No need to mark every test with @pytest.mark.asyncio
```

**Basic Async Test:**
```python
import pytest

async def test_async_endpoint():
    result = await fetch_data("http://api.example.com/users")
    assert result["status"] == "ok"
```

**Async Fixtures:**
```python
@pytest.fixture
async def db_session():
    session = await create_async_session()
    yield session
    await session.close()

async def test_query(db_session):
    users = await db_session.execute("SELECT * FROM users")
    assert len(users) > 0
```

### anyio (Backend-Agnostic)

**Test with both asyncio and trio:**
```python
import anyio
import pytest

@pytest.mark.anyio
async def test_concurrent_tasks():
    results = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(fetch_and_append, results, "url1")
        tg.start_soon(fetch_and_append, results, "url2")

    assert len(results) == 2
```

### AsyncMock

**Mock async dependencies:**
```python
from unittest.mock import AsyncMock, patch

async def test_service_calls_api():
    mock_client = AsyncMock()
    mock_client.get.return_value = {"data": [1, 2, 3]}

    service = DataService(client=mock_client)
    result = await service.fetch_all()

    assert result == [1, 2, 3]
    mock_client.get.assert_awaited_once()
```

**Patch async context managers:**
```python
@patch("module.aiohttp.ClientSession")
async def test_http_client(mock_session_cls):
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {"key": "value"}
    mock_response.status = 200
    mock_session.get.return_value.__aenter__.return_value = mock_response
    mock_session_cls.return_value.__aenter__.return_value = mock_session

    result = await fetch_json("http://example.com/api")
    assert result == {"key": "value"}
```

### Testing Timeouts and Cancellation

**Verify timeout behavior:**
```python
import asyncio
import pytest

async def test_operation_respects_timeout():
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.1):
            await slow_operation()

async def test_cancellation_cleanup():
    resource = AsyncResource()
    task = asyncio.create_task(resource.long_running())

    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert resource.cleaned_up  # Verify cleanup ran
```

## Property-Based Testing

### Hypothesis Basics

**Replace hand-picked examples with generated inputs:**
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(st.integers(), st.integers())
def test_addition_commutative(x, y):
    assert x + y == y + x

@given(st.lists(st.integers()))
def test_sort_preserves_length(xs):
    assert len(sorted(xs)) == len(xs)

@given(st.lists(st.integers(), min_size=1))
def test_sort_idempotent(xs):
    assert sorted(sorted(xs)) == sorted(xs)
```

### Custom Strategies

**Build domain objects:**
```python
from hypothesis import strategies as st

emails = st.from_regex(
    r"[a-z]{1,10}@[a-z]{1,5}\.(com|org|net)",
    fullmatch=True,
)

user_strategy = st.builds(
    User,
    name=st.text(min_size=1, max_size=100),
    email=emails,
    age=st.integers(min_value=0, max_value=150),
)

@given(user=user_strategy)
def test_user_serialization_roundtrip(user):
    data = user.model_dump()
    restored = User.model_validate(data)
    assert restored == user
```

### Stateful Testing

**Test stateful systems with rule-based state machines:**
```python
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize

class ShoppingCartMachine(RuleBasedStateMachine):
    @initialize()
    def create_cart(self):
        self.cart = ShoppingCart()
        self.expected_items = []

    @rule(item=st.text(min_size=1), qty=st.integers(min_value=1, max_value=10))
    def add_item(self, item, qty):
        self.cart.add(item, qty)
        self.expected_items.append((item, qty))

    @rule()
    def check_total_items(self):
        expected = sum(q for _, q in self.expected_items)
        assert self.cart.total_items == expected

TestShoppingCart = ShoppingCartMachine.TestCase
```

### Hypothesis with Pydantic

**Generate valid Pydantic models:**
```python
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, Field

class SensorReading(BaseModel):
    device_id: str = Field(min_length=1, max_length=50)
    value: float = Field(ge=-100.0, le=100.0)
    unit: str

# Strategy that respects Pydantic constraints
sensor_readings = st.builds(
    SensorReading,
    device_id=st.text(min_size=1, max_size=50),
    value=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False),
    unit=st.sampled_from(["celsius", "fahrenheit", "percent"]),
)

@given(reading=sensor_readings)
def test_sensor_reading_valid(reading):
    assert reading.device_id
    assert -100.0 <= reading.value <= 100.0
```

### Hypothesis Settings

**Tune test parameters:**
```python
from hypothesis import given, settings, HealthCheck

@settings(
    max_examples=500,       # More thorough (default: 100)
    deadline=1000,          # ms per example (None to disable)
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.text())
def test_thorough(s):
    assert process(s) is not None
```

**Profile-based settings in conftest.py:**
```python
# conftest.py
from hypothesis import settings, Phase

settings.register_profile("ci", max_examples=1000)
settings.register_profile("dev", max_examples=50)
settings.register_profile(
    "debug",
    max_examples=10,
    phases=[Phase.explicit, Phase.generate],
)
```

## Snapshot Testing

### syrupy (pytest snapshot plugin)

**Capture and verify complex outputs:**
```python
def test_api_response(snapshot):
    response = get_user_profile(user_id=1)
    assert response == snapshot

def test_html_rendering(snapshot):
    html = render_template("profile.html", user=mock_user)
    assert html == snapshot
```

**Update snapshots:**
```bash
pytest --snapshot-update
```

### JSON Snapshot Testing

**Useful for API contract testing:**
```python
def test_openapi_schema(snapshot):
    schema = app.openapi()
    assert schema == snapshot

def test_serialization_format(snapshot):
    data = SensorReading(device_id="d1", value=23.5, unit="celsius")
    assert data.model_dump() == snapshot
```

## Mutation Testing

### mutmut

**Verify test quality by injecting faults:**
```bash
# Run mutation testing
mutmut run --paths-to-mutate=src/my_module/

# View results
mutmut results

# View specific surviving mutant
mutmut show 42
```

**Interpret results:**
- Killed mutant: Tests caught the bug (good)
- Survived mutant: Tests missed the bug (gap in coverage)
- Target: >80% mutation score for critical code

## Testing Patterns for Common Scenarios

### Testing Retries

```python
from unittest.mock import AsyncMock

async def test_retries_on_failure():
    mock_client = AsyncMock()
    mock_client.get.side_effect = [
        ConnectionError("timeout"),
        ConnectionError("timeout"),
        {"data": "success"},
    ]

    service = RetryingService(client=mock_client, max_retries=3)
    result = await service.fetch()

    assert result == {"data": "success"}
    assert mock_client.get.await_count == 3
```

### Testing Rate Limiters

```python
import time

async def test_rate_limiter():
    limiter = RateLimiter(max_calls=2, period=1.0)

    # First two calls succeed immediately
    await limiter.acquire()
    await limiter.acquire()

    # Third call should be delayed
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.9  # ~1 second delay
```

### Testing Event-Driven Code

```python
async def test_event_handler():
    events_received = []

    async def handler(event):
        events_received.append(event)

    bus = EventBus()
    bus.subscribe("user.created", handler)

    await bus.publish("user.created", {"user_id": 1})
    await asyncio.sleep(0.01)  # Allow event propagation

    assert len(events_received) == 1
    assert events_received[0]["user_id"] == 1
```

## Best Practices

1. **Use `asyncio_mode = "auto"`**: Avoid decorating every test with `@pytest.mark.asyncio`
2. **Prefer `AsyncMock` over manual coroutine stubs**: Built-in, tracks awaits
3. **Start Hypothesis with defaults**: Tune `max_examples` only when needed
4. **Use `@example()` for regression tests**: Pin specific inputs that previously failed
5. **Combine property tests with unit tests**: Properties verify invariants, unit tests verify specific behaviors
6. **Keep snapshots small**: Snapshot only the relevant parts of responses
7. **Run mutation testing on critical paths**: Focus on business logic, not boilerplate
8. **Use `anyio` for library code**: Test with both asyncio and trio backends

## References

- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [AsyncMock Documentation](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.AsyncMock)
- [syrupy Documentation](https://github.com/syrupy-project/syrupy)
- [mutmut Documentation](https://mutmut.readthedocs.io/)

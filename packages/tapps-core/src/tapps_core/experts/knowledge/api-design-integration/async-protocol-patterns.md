# Async Protocol Patterns

## Overview

This guide covers patterns for async protocols (WebSocket, MQTT, gRPC streaming,
Server-Sent Events) used in real-time systems. Topics include connection management,
reconnection strategies, message handling, backpressure, error recovery, and
testing approaches for async protocol clients.

## Connection Management

### Base Protocol Client

```python
import asyncio
from abc import ABC, abstractmethod

class AsyncProtocolClient(ABC):
    """Base class for async protocol clients with lifecycle management."""

    def __init__(self, uri: str, max_reconnect_delay: float = 60.0) -> None:
        self.uri = uri
        self.max_reconnect_delay = max_reconnect_delay
        self._connected = False
        self._reconnect_delay = 1.0
        self._connection = None

    @abstractmethod
    async def _establish_connection(self) -> None:
        """Establish the protocol-specific connection."""

    @abstractmethod
    async def _close_connection(self) -> None:
        """Close the protocol-specific connection."""

    async def connect(self) -> None:
        """Connect with retry logic."""
        while not self._connected:
            try:
                await self._establish_connection()
                self._connected = True
                self._reconnect_delay = 1.0
            except (ConnectionError, OSError) as e:
                await self._handle_connection_failure(e)

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._connected = False
        if self._connection is not None:
            await self._close_connection()

    async def ensure_connected(self) -> None:
        """Ensure the connection is active, reconnecting if needed."""
        if not self._connected:
            await self.connect()

    async def _handle_connection_failure(self, error: Exception) -> None:
        """Handle connection failure with exponential backoff."""
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(
            self._reconnect_delay * 2,
            self.max_reconnect_delay,
        )
```

### Context Manager Pattern

```python
class ManagedConnection:
    """Async context manager for protocol connections."""

    def __init__(self, client: AsyncProtocolClient) -> None:
        self._client = client

    async def __aenter__(self) -> AsyncProtocolClient:
        await self._client.connect()
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.disconnect()
        return False

# Usage
async def main():
    client = WebSocketClient("wss://example.com/ws")
    async with ManagedConnection(client) as conn:
        await conn.send({"type": "subscribe", "channel": "updates"})
```

## Reconnection Strategies

### Exponential Backoff with Jitter

```python
import random
import asyncio

async def connect_with_backoff(
    connect_fn,
    max_retries: int = 10,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> None:
    """Connect with exponential backoff and jitter."""
    for attempt in range(max_retries):
        try:
            await connect_fn()
            return
        except ConnectionError:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            await asyncio.sleep(delay + jitter)
```

### Using tenacity for Retries

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
)
async def connect_with_tenacity(client):
    """Connect with exponential backoff via tenacity."""
    await client.connect()
```

### Circuit Breaker Pattern

```python
import time

class CircuitBreaker:
    """Prevent repeated connection attempts to a failing service."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    def can_attempt(self) -> bool:
        """Check if a connection attempt is allowed."""
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.monotonic() - self._last_failure_time > self.reset_timeout:
                self._state = "half-open"
                return True
            return False
        return True  # half-open: allow one attempt

    def record_success(self) -> None:
        """Record a successful connection."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record a failed connection attempt."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
```

## WebSocket Patterns

### WebSocket Client

```python
import asyncio
import json

class WebSocketHandler:
    """Handle WebSocket messages with typed dispatch."""

    def __init__(self) -> None:
        self._handlers: dict[str, callable] = {}

    def on(self, message_type: str):
        """Register a handler for a message type."""
        def decorator(fn):
            self._handlers[message_type] = fn
            return fn
        return decorator

    async def dispatch(self, raw_message: str) -> None:
        """Parse and dispatch a message to the appropriate handler."""
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        msg_type = message.get("type", "unknown")
        handler = self._handlers.get(msg_type)
        if handler is not None:
            await handler(message)
```

### Heartbeat and Keepalive

```python
async def heartbeat_loop(
    ws,
    interval: float = 30.0,
    timeout: float = 10.0,
) -> None:
    """Send periodic pings and detect dead connections."""
    while True:
        try:
            pong = await asyncio.wait_for(
                ws.ping(),
                timeout=timeout,
            )
            await pong
        except (asyncio.TimeoutError, ConnectionError):
            raise ConnectionError("Heartbeat failed")
        await asyncio.sleep(interval)
```

## Message Handling Patterns

### Typed Message Dispatch

```python
from dataclasses import dataclass

@dataclass
class Message:
    type: str
    payload: dict
    timestamp: float

async def handle_message(message: Message) -> dict:
    """Handle an incoming message with error isolation."""
    handlers = {
        "score_request": handle_score_request,
        "config_update": handle_config_update,
        "heartbeat": handle_heartbeat,
    }

    handler = handlers.get(message.type)
    if handler is None:
        return {"error": "unknown_message_type", "type": message.type}

    try:
        return await handler(message.payload)
    except Exception as e:
        return {"error": str(e), "type": message.type}


async def handle_score_request(payload: dict) -> dict:
    """Handle a scoring request."""
    file_path = payload.get("file_path", "")
    return {"status": "scored", "file": file_path}


async def handle_config_update(payload: dict) -> dict:
    """Handle a configuration update."""
    return {"status": "updated"}


async def handle_heartbeat(payload: dict) -> dict:
    """Handle a heartbeat ping."""
    return {"status": "pong"}
```

### Message Queue with Backpressure

```python
import asyncio

class MessageQueue:
    """Bounded async message queue with backpressure."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._dropped = 0

    async def put(self, message: dict) -> bool:
        """Add a message, returning False if queue is full."""
        try:
            self._queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            return False

    async def get(self) -> dict:
        """Get the next message, waiting if empty."""
        return await self._queue.get()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        return self._dropped
```

## MQTT Patterns

### MQTT Client with asyncio

```python
import asyncio
import json

class AsyncMQTTClient:
    """Async MQTT client wrapper for IoT messaging."""

    def __init__(self, broker: str, port: int = 1883) -> None:
        self.broker = broker
        self.port = port
        self._subscriptions: dict[str, list] = {}

    async def publish(
        self,
        topic: str,
        payload: dict,
        qos: int = 1,
    ) -> None:
        """Publish a JSON message to a topic."""
        message = json.dumps(payload)
        # Implementation delegates to underlying MQTT library
        pass

    def subscribe(self, topic: str):
        """Decorator to register a topic handler."""
        def decorator(fn):
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(fn)
            return fn
        return decorator
```

### QoS Levels

| QoS | Delivery | Use Case |
|---|---|---|
| 0 | At most once | Sensor telemetry (loss OK) |
| 1 | At least once | Commands, state updates |
| 2 | Exactly once | Financial, critical events |

## gRPC Streaming Patterns

### Server-Side Streaming

```python
import asyncio

async def stream_scores(request, context):
    """Stream quality scores as files are processed."""
    files = request.file_paths
    for file_path in files:
        score = await compute_score(file_path)
        yield ScoreResponse(
            file_path=file_path,
            score=score,
        )
        await asyncio.sleep(0)  # yield control


async def compute_score(file_path: str) -> float:
    """Compute a quality score for a file."""
    return 85.0
```

### Bidirectional Streaming

```python
async def interactive_review(request_stream, context):
    """Bidirectional streaming for interactive code review."""
    async for request in request_stream:
        if request.type == "score":
            result = await score_file(request.file_path)
            yield ReviewResponse(score=result)
        elif request.type == "explain":
            explanation = await explain_issue(request.issue_id)
            yield ReviewResponse(explanation=explanation)
```

## Server-Sent Events (SSE)

### SSE Producer

```python
import asyncio
import json

async def sse_stream(request):
    """Generate Server-Sent Events for real-time progress."""
    async def event_generator():
        for i in range(10):
            data = json.dumps({"progress": (i + 1) * 10, "status": "scoring"})
            yield f"data: {data}\n\n"
            await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'progress': 100, 'status': 'complete'})}\n\n"

    return event_generator()
```

Note: SSE is deprecated in MCP 2025-11-25. Use Streamable HTTP instead for
MCP transport. SSE remains useful for browser-facing real-time updates.

## Testing Async Protocols

### Mocking WebSocket Connections

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value='{"type": "ping"}')
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    ws.closed = False
    return ws


@pytest.mark.asyncio
async def test_message_handling(mock_websocket):
    handler = WebSocketHandler()
    received = []

    @handler.on("ping")
    async def on_ping(msg):
        received.append(msg)

    message = await mock_websocket.recv()
    await handler.dispatch(message)
    assert len(received) == 1
```

### Testing Reconnection Logic

```python
@pytest.mark.asyncio
async def test_reconnection_backoff():
    """Verify exponential backoff on connection failure."""
    attempts = []

    async def failing_connect():
        attempts.append(len(attempts))
        if len(attempts) < 3:
            raise ConnectionError("refused")

    await connect_with_backoff(failing_connect, max_retries=5, base_delay=0.01)
    assert len(attempts) == 3
```

## Anti-Patterns

### No Reconnection Logic

Always implement automatic reconnection with backoff. Network interruptions
are normal in production.

### Unbounded Message Queues

Without backpressure, slow consumers cause memory exhaustion. Use bounded
queues and drop or buffer messages when full.

### Blocking the Event Loop

Never use synchronous I/O in async protocol handlers:

```python
# BAD
def handle_message(msg):
    result = requests.get(url)  # blocks the event loop

# GOOD
async def handle_message(msg):
    async with aiohttp.ClientSession() as session:
        result = await session.get(url)
```

### Missing Heartbeats

Without heartbeats, dead connections go undetected. Implement periodic
ping/pong or application-level heartbeats.

## Quick Reference

| Protocol | Transport | Pattern | Use Case |
|---|---|---|---|
| WebSocket | TCP | Full-duplex | Real-time bidirectional |
| MQTT | TCP | Pub/sub | IoT, sensor data |
| gRPC | HTTP/2 | Streaming RPC | Microservices |
| SSE | HTTP/1.1 | Server push | Browser notifications |
| Streamable HTTP | HTTP | Request/response + streaming | MCP transport |

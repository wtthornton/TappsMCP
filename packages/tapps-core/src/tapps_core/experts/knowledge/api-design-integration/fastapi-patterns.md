# FastAPI Patterns

## Overview

FastAPI is a modern Python web framework for building APIs. This guide covers FastAPI patterns for production microservices applications.

## Version & Compatibility (as of early 2026)

- **Latest:** FastAPI 0.135.x (install via `pip install "fastapi[standard]"`)
- **`fastapi-slim` is deprecated** - use `"fastapi[standard]"` for the full install
- **Python:** 3.9+ minimum; recommend 3.12 or 3.13 for best performance
- **Pydantic:** v2.12+ required (v1 compatibility shims removed)
- **Starlette:** 1.0.0+ (stable API, no more 0.x breaking changes)
- **Key additions in 2025-2026:**
  - Server-Sent Events (SSE) support via `EventSourceResponse`
  - Streaming JSON Lines and binary data with `yield` in `StreamingResponse`
  - Strict Content-Type checking enabled by default (disable with `strict_content_type=False` on route)
  - `datetime.utcnow()` deprecated in Python 3.12+ - use `datetime.now(UTC)` instead

## Core Patterns

### Pattern 1: Basic FastAPI Application

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="My API",
    description="Application API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

### Pattern 2: Dependency Injection

```python
from fastapi import Depends, FastAPI
from typing import Annotated

# Database dependency
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Service dependency
def get_user_service(db: Annotated[Session, Depends(get_db)]):
    return UserService(db)

@app.get("/users/{user_id}")
async def get_user(
    user_id: str,
    service: Annotated[UserService, Depends(get_user_service)]
):
    return await service.get_user(user_id)
```

### Pattern 3: Async Endpoints

```python
import asyncio
from fastapi import FastAPI

app = FastAPI()

@app.get("/sensors/{device_id}")
async def get_sensor_data(device_id: str):
    """Async endpoint for sensor data."""
    # Async database call
    data = await db.fetch_sensor_data(device_id)
    return data

@app.post("/devices/{device_id}/command")
async def send_command(device_id: str, command: dict):
    """Async endpoint for device commands."""
    # Async service call
    result = await device_service.send_command(device_id, command)
    return result
```

### Pattern 4: Request/Response Models (Pydantic v2)

```python
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

class SensorReading(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    device_id: str = Field(..., description="Device identifier", min_length=1)
    value: float = Field(..., description="Sensor value")
    unit: str = Field(..., description="Unit of measurement")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("unit")
    @classmethod
    def unit_must_be_known(cls, v: str) -> str:
        allowed = {"celsius", "fahrenheit", "percent", "ppm", "lux"}
        if v.lower() not in allowed:
            msg = f"Unknown unit: {v}"
            raise ValueError(msg)
        return v.lower()

class SensorResponse(BaseModel):
    device_id: str
    readings: list[SensorReading]
    count: int

@app.post("/sensors", response_model=SensorResponse)
async def create_sensor_reading(reading: SensorReading):
    """Create sensor reading."""
    return SensorResponse(
        device_id=reading.device_id,
        readings=[reading],
        count=1,
    )
```

## Advanced Patterns

### Pattern 1: Background Tasks

```python
from fastapi import BackgroundTasks

@app.post("/devices/{device_id}/command")
async def send_command(
    device_id: str,
    command: dict,
    background_tasks: BackgroundTasks
):
    """Send command with background processing."""
    # Immediate response
    result = await device_service.send_command(device_id, command)
    
    # Background task
    background_tasks.add_task(
        log_command,
        device_id,
        command
    )
    
    return result

async def log_command(device_id: str, command: dict):
    """Background task to log command."""
    await logger.log(f"Command sent to {device_id}: {command}")
```

### Pattern 2: WebSocket Endpoints

```python
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Pattern 3: Error Handling

```python
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"message": str(exc)}
    )

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found"
        )
    return user
```

### Pattern 4: Middleware

```python
from fastapi import Request
import time

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

### Pattern 5: Server-Sent Events (SSE)

```python
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

async def event_generator():
    """Yield events as Server-Sent Events."""
    while True:
        data = await get_next_event()
        yield {
            "event": "update",
            "data": json.dumps(data),
        }

@app.get("/stream/events")
async def stream_events():
    """Stream events via SSE."""
    return EventSourceResponse(event_generator())
```

### Pattern 6: Streaming Responses (JSON Lines & Binary)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

async def jsonl_generator():
    """Yield newline-delimited JSON (JSON Lines)."""
    async for record in fetch_records():
        yield json.dumps(record) + "\n"

@app.get("/export/data")
async def export_data():
    """Stream JSON Lines response."""
    return StreamingResponse(
        jsonl_generator(),
        media_type="application/x-ndjson",
    )

async def binary_generator():
    """Yield binary chunks for file download."""
    async for chunk in read_file_chunks(path):
        yield chunk

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """Stream binary file download."""
    return StreamingResponse(
        binary_generator(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file_id}"},
    )
```

### Pattern 7: Strict Content-Type Checking

```python
from fastapi import FastAPI

app = FastAPI()

# FastAPI 0.135+ enables strict Content-Type checking by default.
# Clients MUST send Content-Type: application/json for JSON bodies.
# To disable (e.g., for legacy clients):
@app.post("/legacy/endpoint", strict_content_type=False)
async def legacy_endpoint(data: dict):
    return data
```

## Domain-Specific Patterns

### Pattern 1: Sensor Data Endpoint

```python
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

class SensorData(BaseModel):
    device_id: str
    value: float
    unit: str
    timestamp: datetime

@app.post("/sensors/data")
async def ingest_sensor_data(
    data: SensorData,
    db: Session = Depends(get_db)
):
    """Ingest sensor data."""
    # Store in InfluxDB
    await influxdb_client.write(data.model_dump())
    return {"status": "success"}

@app.get("/sensors/{device_id}")
async def get_sensor_data(
    device_id: str,
    start_time: datetime,
    end_time: datetime
):
    """Get sensor data."""
    # Query InfluxDB
    data = await influxdb_client.query(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time
    )
    return data
```

### Pattern 2: Device Control Endpoint

```python
@app.post("/devices/{device_id}/command")
async def send_device_command(
    device_id: str,
    command: dict,
    user: User = Depends(get_current_user)
):
    """Send command to device."""
    # Validate user permissions
    if not await user.has_permission(device_id, "control"):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Send command via MQTT
    await mqtt_client.publish(
        f"home/device/{device_id}/command",
        command
    )
    
    return {"status": "command_sent"}
```

## Best Practices

### 1. Use Pydantic Models

```python
# GOOD: Type-safe models
class UserCreate(BaseModel):
    email: str
    name: str

@app.post("/users")
async def create_user(user: UserCreate):
    # Type checking and validation
    pass
```

### 2. Async Database Operations

```python
# GOOD: Async database calls
@app.get("/users")
async def get_users():
    users = await db.fetch_all("SELECT * FROM users")
    return users
```

### 3. Dependency Injection

```python
# GOOD: Dependency injection
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

### 4. Error Handling

```python
# GOOD: Proper error handling
@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### 5. API Documentation

```python
# GOOD: Comprehensive documentation
@app.post(
    "/sensors",
    response_model=SensorResponse,
    summary="Create sensor reading",
    description="Create a new sensor reading",
    response_description="The created sensor reading"
)
async def create_sensor(reading: SensorReading):
    pass
```

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [Starlette SSE](https://github.com/sysid/sse-starlette)


# TappsMCP: Docker Deployment

Run TappsMCP as a **local Docker MCP server** using Streamable HTTP. The server listens on port **8000** and exposes the MCP endpoint at **`/mcp`**.

---

## Prerequisites

- **Docker** and **Docker Compose** installed and running.

---

## Quick Start

```bash
# From the TappsMCP repo root
cd c:\cursor\TappsMCP   # or your path

# Build and start
docker compose up --build -d

# Check status and logs
docker compose ps
docker compose logs -f
```

The MCP server is available at **http://localhost:8000** (Streamable HTTP endpoint: **http://localhost:8000/mcp**).

---

## Verify

1. **Container health**
   ```bash
   docker compose ps
   # State should show "running", Health "healthy"
   ```

2. **Server reachable**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
   # 404 is expected (root path); server is up
   ```

3. **Logs**
   ```bash
   docker compose logs --tail 20
   # Should show: "Uvicorn running on http://0.0.0.0:8000"
   ```

---

## Configuration

### Environment variables (docker-compose)

| Variable | Default | Description |
|----------|---------|-------------|
| `TAPPS_MCP_PROJECT_ROOT` | `/workspace` | Directory used for file scoring; must match the mounted volume if you mount a project. |
| `TAPPS_MCP_HOST_PROJECT_ROOT` | *(none)* | **Optional.** Host path the client/IDE uses for the same project (e.g. `C:\projects\myapp`). When set, absolute paths sent by Cursor under this path are mapped to `project_root`, so you can use host paths without "path denied" errors. |
| `TAPPS_MCP_QUALITY_PRESET` | `standard` | `standard` \| `strict` \| `framework` |
| `TAPPS_MCP_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

### Mounting a project (optional)

To let TappsMCP score files from a host directory, mount it at `/workspace`:

```yaml
volumes:
  - /path/to/your/project:/workspace:ro
```

The default `docker-compose.yml` mounts the **current directory** (TappsMCP repo) as `/workspace:ro`. To score a different project, change the volume to that path.

---

## Using TappsMCP Docker from another project

To use the MCP server for a **different project** (e.g. `C:\projects\myapp`):

### 1. Start the container with that project mounted

Run Docker from the TappsMCP repo but mount the **other project** as `/workspace` so the server can read its files:

```bash
# From the TappsMCP repo
cd c:\cursor\TappsMCP

# Override the volume for this run (Windows example)
docker compose run -d -p 8000:8000 -v "C:\projects\myapp:/workspace:ro" tapps-mcp
```

Or create a **docker-compose.override.yml** in the TappsMCP repo that overrides the volume:

```yaml
# docker-compose.override.yml (in TappsMCP repo)
services:
  tapps-mcp:
    volumes:
      - C:\projects\myapp:/workspace:ro
```

Then from the TappsMCP repo: `docker compose up -d`. The container will see the other project at `/workspace`.

**Optional — accept host paths from Cursor:** Set `TAPPS_MCP_HOST_PROJECT_ROOT` to the same path the IDE uses (e.g. `C:\projects\myapp`). Then Cursor can send absolute paths like `C:\projects\myapp\src\main.py` and the server will map them to `/workspace/src/main.py`. Example override:

```yaml
# docker-compose.override.yml
services:
  tapps-mcp:
    environment:
      TAPPS_MCP_HOST_PROJECT_ROOT: "C:\\projects\\myapp"
    volumes:
      - C:\projects\myapp:/workspace:ro
```

### 2. Connect Cursor (or another client) to the Docker MCP

The server speaks **Streamable HTTP** at **http://localhost:8000/mcp**.

- **Cursor**: In **Settings → Tools & MCP**, add an MCP server that uses the **HTTP/SSE** transport (not stdio) and set the URL to **http://localhost:8000/mcp**.
- **File paths**: You can send **relative paths** (e.g. `src/main.py`) or, if `TAPPS_MCP_HOST_PROJECT_ROOT` is set to your project path, **absolute host paths** (e.g. `C:\projects\myapp\src\main.py`); the server will map them to the project root.

### 3. Optional: config in the other project

In the other project you can add **`.tapps-mcp.yaml`** to set quality preset, timeouts, etc. The server will read it from the mounted `/workspace`.

---

## Connecting clients to the Docker MCP server

### Streamable HTTP (Cursor / other MCP clients)

Use the **Streamable HTTP** transport with base URL **http://localhost:8000** (endpoint **/mcp**).

- **Cursor**: Add an MCP server that uses the HTTP transport and URL `http://localhost:8000` (or `http://localhost:8000/mcp` per your client’s docs).
- **Other clients**: Configure the MCP server URL to `http://localhost:8000` and ensure the client uses the Streamable HTTP protocol.

### Stopping

```bash
docker compose down
```

---

## Build only (no compose)

```bash
docker build -t tappsmcp:local .
docker run --rm -p 8000:8000 -e TAPPS_MCP_PROJECT_ROOT=/workspace tappsmcp:local
```

---

## Image contents

- **Base:** `python:3.12-slim`
- **Preinstalled tools:** ruff, mypy, bandit, radon (for full scoring)
- **Transport:** HTTP only (stdio is not used in Docker)
- **Port:** 8000
- **Healthcheck:** GET http://127.0.0.1:8000/ (any response treated as healthy)

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| Port 8000 in use | Change `ports` in `docker-compose.yml` (e.g. `"8001:8000"`) |
| Container exits immediately | Run `docker compose logs` and fix any Python/env errors |
| Scoring fails for files | Ensure the project is mounted at `TAPPS_MCP_PROJECT_ROOT` (default `/workspace`) and paths are inside that directory |
| Healthcheck failing | Ensure curl is available in the image (it is in the current Dockerfile) and nothing is blocking localhost inside the container |

---

## File reference

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the TappsMCP image (Python 3.12, deps, ruff/mypy/bandit/radon) |
| `docker-compose.yml` | Runs the server, port 8000, optional volume, healthcheck |
| `.dockerignore` | Keeps build context small (excludes tests, docs, .venv, etc.) |

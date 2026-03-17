# DocsMCP — multi-stage Docker build (monorepo-aware)
# Stage 1: Builder — build tapps-core + docs-mcp wheels
# Stage 2: Production — slim image with pre-installed server
#
# Build from repo root:  docker build -f packages/docs-mcp/Dockerfile -t docs-mcp .
# Run:    docker run -v $(pwd):/workspace docs-mcp
# HTTP:   docker run -p 8000:8000 -v $(pwd):/workspace docs-mcp docsmcp serve --transport http --host 0.0.0.0 --port 8000

# ---- Builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --no-cache-dir hatchling==1.28.0

# Build tapps-core wheel first (dependency)
COPY packages/tapps-core/pyproject.toml packages/tapps-core/
COPY packages/tapps-core/src packages/tapps-core/src
RUN pip wheel --no-deps --wheel-dir /wheels packages/tapps-core/

# Build docs-mcp wheel (readme is docs/README.md per pyproject.toml)
COPY packages/docs-mcp/pyproject.toml packages/docs-mcp/
COPY packages/docs-mcp/docs packages/docs-mcp/docs
COPY packages/docs-mcp/src packages/docs-mcp/src
RUN pip wheel --no-deps --wheel-dir /wheels packages/docs-mcp/

# ---- Production ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="DocsMCP"
LABEL org.opencontainers.image.description="MCP server for documentation generation and maintenance"
LABEL org.opencontainers.image.source="https://github.com/tapps-mcp/tapps-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="TappsMCP"
LABEL org.opencontainers.image.version="1.9.0"

WORKDIR /app

# Install system deps (git required for git history analysis)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install tapps-core + docs-mcp from wheels built in builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Create non-root user and pre-create state mountpoint
RUN useradd --create-home --shell /bin/bash docsmcp \
    && mkdir -p /workspace \
    && chown docsmcp:docsmcp /workspace
USER docsmcp

# Config
ENV TAPPS_MCP_PROJECT_ROOT=/workspace
ENV PYTHONUNBUFFERED=1

# Default: stdio transport for MCP client integration
# HTTP: docker run -p 8000:8000 ... docsmcp serve --transport http --host 0.0.0.0 --port 8000
CMD ["docsmcp", "serve"]

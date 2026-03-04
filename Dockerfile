# TappsMCP — multi-stage Docker build (monorepo-aware)
# Stage 1: Builder — build tapps-core + tapps-mcp wheels
# Stage 2: Production — slim image with pre-installed tools
#
# Build:  docker build -t tapps-mcp .
# Run:    docker run -v $(pwd):/workspace tapps-mcp
# HTTP:   docker run -p 8000:8000 -v $(pwd):/workspace tapps-mcp tapps-mcp serve --transport http --host 0.0.0.0 --port 8000

# ---- Builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --no-cache-dir hatchling==1.28.0

# Build tapps-core wheel first (dependency)
COPY packages/tapps-core/pyproject.toml packages/tapps-core/README.md packages/tapps-core/
COPY packages/tapps-core/src packages/tapps-core/src
RUN pip wheel --no-deps --wheel-dir /wheels packages/tapps-core/

# Build tapps-mcp wheel
COPY packages/tapps-mcp/pyproject.toml packages/tapps-mcp/README.md packages/tapps-mcp/
COPY packages/tapps-mcp/src packages/tapps-mcp/src
RUN pip wheel --no-deps --wheel-dir /wheels packages/tapps-mcp/

# ---- Production ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="TappsMCP"
LABEL org.opencontainers.image.description="MCP server providing code quality tools"
LABEL org.opencontainers.image.source="https://github.com/tapps-mcp/tapps-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="TappsMCP"
LABEL org.opencontainers.image.version="0.8.0"

WORKDIR /app

# Install system deps and external checkers
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && pip install --no-cache-dir ruff==0.15.0 mypy==1.19.1 bandit==1.9.3 radon==6.0.1 \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install tapps-core + tapps-mcp from wheels built in builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Create non-root user and pre-create state mountpoint
RUN useradd --create-home --shell /bin/bash tapps \
    && mkdir -p /workspace/.tapps-mcp \
    && chown tapps:tapps /workspace/.tapps-mcp
USER tapps

# Config
ENV TAPPS_MCP_PROJECT_ROOT=/workspace
ENV PYTHONUNBUFFERED=1

# Expose for optional HTTP transport mode
EXPOSE 8000

# Default: stdio transport for MCP client integration
# HTTP: docker run -p 8000:8000 ... tapps-mcp serve --transport http --host 0.0.0.0 --port 8000
CMD ["tapps-mcp", "serve"]

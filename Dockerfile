# TappsMCP — multi-stage Docker build
# Stage 1: Builder — install dependencies
# Stage 2: Production — slim image with pre-installed tools

# ---- Builder ----
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --no-cache-dir hatchling==1.28.0

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Build wheel
RUN pip wheel --no-deps --wheel-dir /wheels .

# ---- Production ----
FROM python:3.14-slim

LABEL org.opencontainers.image.title="TappsMCP"
LABEL org.opencontainers.image.description="MCP server providing code quality tools"
LABEL org.opencontainers.image.source="https://github.com/tapps-mcp/tapps-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="TappsMCP"

WORKDIR /app

# Install system deps and external checkers
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && pip install --no-cache-dir ruff==0.15.0 mypy==1.19.1 bandit==1.9.3 radon==6.0.1 \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install app from wheel built in builder stage
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

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=5s \
    CMD curl -sf http://127.0.0.1:8000/ || exit 1

CMD ["tapps-mcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]

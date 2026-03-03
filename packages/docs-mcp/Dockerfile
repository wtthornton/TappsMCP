# DocsMCP - multi-stage Docker build
# Stage 1: Builder - install dependencies and build wheel
# Stage 2: Production - slim image with pre-installed server

# ---- Builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN pip install --no-cache-dir hatchling==1.28.0

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Build wheel
RUN pip wheel --no-deps --wheel-dir /wheels .

# ---- Production ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="DocsMCP"
LABEL org.opencontainers.image.description="MCP server for documentation generation and maintenance"
LABEL org.opencontainers.image.source="https://github.com/tapps-mcp/tapps-mcp"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="TappsMCP"

WORKDIR /app

# Install system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install app from wheel built in builder stage
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

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=5s \
    CMD curl -sf http://127.0.0.1:8000/ || exit 1

# Default: stdio transport for MCP client integration
# Override with: docker run ... docsmcp serve --transport http --host 0.0.0.0 --port 8000
ENTRYPOINT ["python", "-m", "docs_mcp"]
CMD ["serve"]

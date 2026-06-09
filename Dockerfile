# TappsMCP — multi-stage Docker build (monorepo-aware)
# Stage 1: Builder — build tapps-core + tapps-mcp wheels
# Stage 2: Production — slim image with pre-installed tools
#
# Build:  docker build -t tapps-mcp .
# Run:    docker run -v $(pwd):/workspace tapps-mcp
# HTTP:   docker run -p 8000:8000 -v $(pwd):/workspace tapps-mcp tapps-mcp serve --transport http --host 0.0.0.0 --port 8000

# Tool versions — keep in sync with pyproject.toml dev-dependencies
ARG TAPPS_VERSION=1.12.0
ARG TAPPS_BRAIN_REV=0a3e173181d4b3179244add93e5fb18ce1336fc5
ARG RUFF_VERSION=0.15.2
ARG MYPY_VERSION=1.19.1
ARG BANDIT_VERSION=1.9.3
ARG RADON_VERSION=6.0.1

# ---- Builder ----
FROM python:3.12-slim AS builder

ARG TAPPS_BRAIN_REV

WORKDIR /build

# Install build deps + git for tapps-brain
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir hatchling==1.28.0 \
    && rm -rf /var/lib/apt/lists/*

# Build tapps-brain wheel from git (private repo — requires BuildKit secret)
# Rev pinned to match [tool.uv.sources] in pyproject.toml (ADR-0013 floor >=3.24.0).
# Build with: docker build --secret id=github_token,env=GITHUB_TOKEN -t tapps-mcp .
RUN --mount=type=secret,id=github_token \
    TOKEN=$(cat /run/secrets/github_token 2>/dev/null || echo "") && \
    if [ -n "$TOKEN" ]; then \
        pip wheel --no-deps --wheel-dir /wheels \
            git+https://${TOKEN}@github.com/wtthornton/tapps-brain.git@${TAPPS_BRAIN_REV}; \
    else \
        pip wheel --no-deps --wheel-dir /wheels \
            git+https://github.com/wtthornton/tapps-brain.git@${TAPPS_BRAIN_REV}; \
    fi

# Build tapps-core wheel (dependency)
COPY packages/tapps-core/pyproject.toml packages/tapps-core/
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
LABEL org.opencontainers.image.version="${TAPPS_VERSION}"

WORKDIR /app

# Install system deps and external checkers
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && pip install --no-cache-dir ruff==${RUFF_VERSION} mypy==${MYPY_VERSION} bandit==${BANDIT_VERSION} radon==${RADON_VERSION} \
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

# ---- Dev (editable workspace — restart, don't rebuild, on src changes) ----
FROM python:3.12-slim AS dev

ARG RUFF_VERSION=0.15.2
ARG MYPY_VERSION=1.19.1
ARG BANDIT_VERSION=1.9.3
ARG RADON_VERSION=6.0.1

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && pip install --no-cache-dir \
        ruff==${RUFF_VERSION} mypy==${MYPY_VERSION} bandit==${BANDIT_VERSION} radon==${RADON_VERSION} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY docker/dev-entrypoint.sh /usr/local/bin/tapps-mcp-dev-entrypoint.sh
RUN chmod +x /usr/local/bin/tapps-mcp-dev-entrypoint.sh

ENV TAPPS_MCP_PROJECT_ROOT=/workspace
ENV PYTHONUNBUFFERED=1
ENV PATH="/workspace/.venv/bin:${PATH}"

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/tapps-mcp-dev-entrypoint.sh"]
CMD ["serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]

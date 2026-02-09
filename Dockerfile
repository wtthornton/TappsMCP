# TappMCP — MCP server for code quality (Docker)
# Single-stage: install deps + app, run HTTP MCP server.

FROM python:3.12-slim

WORKDIR /app

# Install system deps and external checkers for full scoring
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && pip install --no-cache-dir ruff mypy bandit radon \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Project and install (README.md required by pyproject.toml)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# MCP streamable HTTP; mount project at /workspace for scoring
ENV TAPPS_MCP_PROJECT_ROOT=/workspace
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["tapps-mcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]

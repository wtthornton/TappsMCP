"""Shared Pydantic v2 models for the Tapps platform."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Standard response envelope for all TappsMCP tools."""

    tool: str = Field(description="Name of the tool that produced this response.")
    success: bool = Field(description="Whether the tool executed successfully.")
    elapsed_ms: int = Field(description="Execution time in milliseconds.")
    data: dict[str, Any] = Field(default_factory=dict, description="Tool-specific result data.")
    error: ErrorDetail | None = Field(
        default=None, description="Error details if success is False."
    )
    degraded: bool = Field(
        default=False,
        description="True if some external tools were unavailable and results are partial.",
    )


class ErrorDetail(BaseModel):
    """Structured error detail for tool responses."""

    code: str = Field(description="Machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, Any] | None = Field(default=None, description="Additional error context.")


# Rebuild ToolResponse to resolve forward ref
ToolResponse.model_rebuild()


class InstalledTool(BaseModel):
    """Information about an installed external tool."""

    name: str = Field(description="Tool name (e.g. 'ruff', 'mypy').")
    version: str | None = Field(default=None, description="Installed version string.")
    available: bool = Field(description="Whether the tool is available on PATH.")
    install_hint: str | None = Field(
        default=None,
        description="Install command hint when tool is not available.",
    )


class SecurityIssue(BaseModel):
    """A single security finding from bandit or heuristic scan."""

    code: str = Field(description="Rule code, e.g. 'B101'.")
    message: str = Field(description="Description of the issue.")
    file: str = Field(description="File path.")
    line: int = Field(description="Line number.")
    severity: str = Field(default="medium", description="critical | high | medium | low | info.")
    confidence: str = Field(default="medium", description="high | medium | low.")
    owasp: str | None = Field(default=None, description="OWASP category if mapped.")


# ---------------------------------------------------------------------------
# Startup diagnostics models
# ---------------------------------------------------------------------------


class Context7Diagnostic(BaseModel):
    """Context7 API key availability check."""

    api_key_set: bool = Field(description="Whether TAPPS_MCP_CONTEXT7_API_KEY is configured.")
    status: str = Field(description="'available' if key is set, 'no_key' otherwise.")


class CacheDiagnostic(BaseModel):
    """Cache directory health check."""

    cache_dir: str = Field(description="Absolute path to the cache directory.")
    exists: bool = Field(description="Whether the cache directory exists.")
    writable: bool = Field(description="Whether the cache directory is writable.")
    entry_count: int = Field(default=0, description="Number of cached documentation entries.")
    total_size_bytes: int = Field(default=0, description="Total size of cached content in bytes.")
    stale_count: int = Field(default=0, description="Number of stale (past TTL) entries.")


class KnowledgeDomainInfo(BaseModel):
    """File count for a single knowledge domain."""

    domain: str = Field(description="Domain name.")
    file_count: int = Field(description="Number of markdown knowledge files.")


class KnowledgeBaseDiagnostic(BaseModel):
    """Knowledge base integrity check."""

    total_domains: int = Field(description="Number of expert domains with knowledge directories.")
    total_files: int = Field(description="Total markdown knowledge files across all domains.")
    expected_domains: int = Field(description="Number of domains defined in ExpertRegistry.")
    missing_domains: list[str] = Field(
        default_factory=list,
        description="Domains defined in the registry but missing knowledge directories.",
    )
    domains: list[KnowledgeDomainInfo] = Field(
        default_factory=list,
        description="Per-domain file counts.",
    )


class StartupDiagnostics(BaseModel):
    """Aggregate startup diagnostics for all subsystems."""

    context7: Context7Diagnostic = Field(description="Context7 API key status.")
    cache: CacheDiagnostic = Field(description="Cache directory health.")
    knowledge_base: KnowledgeBaseDiagnostic = Field(description="Knowledge base integrity.")

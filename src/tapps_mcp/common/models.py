"""Shared Pydantic v2 models for TappsMCP."""

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

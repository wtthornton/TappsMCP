"""Pydantic models for the knowledge & documentation system."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CacheEntry(BaseModel):
    """A cached documentation entry with metadata."""

    library: str = Field(description="Library name.")
    topic: str = Field(default="overview", description="Topic within the library.")
    content: str = Field(default="", description="Documentation content (markdown).")
    context7_id: str | None = Field(default=None, description="Context7 library ID.")
    snippet_count: int = Field(default=0, description="Number of code snippets.")
    token_count: int = Field(default=0, description="Estimated token count.")
    cached_at: str | None = Field(default=None, description="ISO timestamp of cache write.")
    fetched_at: str | None = Field(default=None, description="ISO timestamp of API fetch.")
    cache_hits: int = Field(default=0, description="Number of cache hits.")


class LookupResult(BaseModel):
    """Result from documentation lookup."""

    success: bool = Field(description="Whether lookup succeeded.")
    content: str | None = Field(default=None, description="Documentation content.")
    source: str = Field(
        default="cache",
        description="Data source: cache, api, fuzzy_match, stale_fallback.",
    )
    library: str | None = Field(default=None, description="Resolved library name.")
    topic: str | None = Field(default=None, description="Resolved topic.")
    context7_id: str | None = Field(default=None, description="Context7 library ID.")
    error: str | None = Field(default=None, description="Error message if failed.")
    response_time_ms: float = Field(default=0.0, description="Lookup latency.")
    cache_hit: bool = Field(default=False, description="Whether result came from cache.")
    fuzzy_score: float | None = Field(default=None, description="Fuzzy match score.")
    warning: str | None = Field(default=None, description="Non-fatal warning.")


class LibraryMatch(BaseModel):
    """A library match from Context7 resolution."""

    id: str = Field(description="Context7 library ID (e.g., '/vercel/next.js').")
    title: str = Field(default="", description="Library title.")
    description: str = Field(default="", description="Library description.")


class FuzzyMatch(BaseModel):
    """Result of a fuzzy match operation."""

    library: str = Field(description="Matched library name.")
    topic: str = Field(default="", description="Matched topic.")
    score: float = Field(description="Similarity score (0.0-1.0).")
    match_type: str = Field(default="library", description="library | topic | both.")


class ValidationFinding(BaseModel):
    """A single config validation finding."""

    severity: str = Field(description="critical | warning | info.")
    message: str = Field(description="Human-readable finding description.")
    line: int | None = Field(default=None, description="Line number if applicable.")
    category: str = Field(default="general", description="Finding category.")


class ConfigValidationResult(BaseModel):
    """Result of configuration file validation."""

    file_path: str = Field(description="Path to the validated file.")
    config_type: str = Field(description="Detected or explicit config type.")
    valid: bool = Field(description="True if no critical findings.")
    findings: list[ValidationFinding] = Field(default_factory=list, description="All findings.")
    suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions.")

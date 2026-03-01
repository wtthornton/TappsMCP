"""Pydantic v2 models for the project-context subsystem."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Language & Tech-Stack
# ---------------------------------------------------------------------------


class TechStack(BaseModel):
    """Detected technology stack for a project."""

    languages: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    context7_priority: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Project Profile
# ---------------------------------------------------------------------------


class ProjectProfile(BaseModel):
    """Full project profile combining tech-stack detection, type detection,
    and deployment/environment characterization."""

    # Tech stack
    tech_stack: TechStack = Field(default_factory=TechStack)

    # Project type archetype
    project_type: str | None = Field(
        default=None,
        description="Detected archetype: api-service, web-app, cli-tool, library, microservice.",
    )
    project_type_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    project_type_reason: str = ""

    # CI / Docker / deployment signals
    has_ci: bool = False
    ci_systems: list[str] = Field(default_factory=list)
    has_docker: bool = False
    has_tests: bool = False
    test_frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)

    # Quality recommendations
    quality_recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


class FunctionInfo(BaseModel):
    """Extracted function metadata from AST."""

    name: str
    line: int
    signature: str
    args: list[str] = Field(default_factory=list)
    returns: str | None = None
    docstring: str | None = None


class ClassInfo(BaseModel):
    """Extracted class metadata from AST."""

    name: str
    line: int
    bases: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    docstring: str | None = None


class ModuleInfo(BaseModel):
    """Extracted module metadata from AST."""

    imports: list[str] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    constants: list[tuple[str, Any]] = Field(default_factory=list)
    docstring: str | None = None


# ---------------------------------------------------------------------------
# Impact Analysis
# ---------------------------------------------------------------------------


class FileImpact(BaseModel):
    """Impact record for a single file."""

    file_path: str
    impact_type: str = Field(description="direct, transitive, or test")
    reason: str = ""


class ImpactReport(BaseModel):
    """Result of analyzing the blast radius of a file change."""

    changed_file: str
    change_type: str = Field(description="added, modified, or removed")
    direct_dependents: list[FileImpact] = Field(default_factory=list)
    transitive_dependents: list[FileImpact] = Field(default_factory=list)
    test_files: list[FileImpact] = Field(default_factory=list)
    total_affected: int = 0
    severity: str = "low"
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session Notes
# ---------------------------------------------------------------------------


class SessionNote(BaseModel):
    """A single session note entry."""

    key: str
    value: str
    created_at: str = ""
    updated_at: str = ""


class SessionNotesSnapshot(BaseModel):
    """Serialisable snapshot of all session notes."""

    session_id: str
    project_root: str
    notes: dict[str, SessionNote] = Field(default_factory=dict)
    session_started: str = ""

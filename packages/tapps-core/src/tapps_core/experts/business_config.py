"""YAML schema and loader for user-defined business experts."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tapps_core.experts.models import ExpertConfig

logger: structlog.stdlib.BoundLogger = structlog.get_logger()  # type: ignore[assignment]

_MAX_BUSINESS_EXPERTS: int = 20
_MAX_KEYWORDS_PER_EXPERT: int = 50


class BusinessExpertEntry(BaseModel):
    """Schema for a single expert entry in experts.yaml."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str = Field(description="Unique expert identifier (must start with 'expert-').")
    expert_name: str = Field(description="Human-readable expert name.")
    primary_domain: str = Field(description="Primary domain of authority.")
    description: str = Field(default="", description="Short description of the expert's focus.")
    keywords: list[str] = Field(
        default_factory=list,
        description="Custom keywords for domain detection routing.",
    )
    rag_enabled: bool = Field(default=True, description="Whether RAG retrieval is enabled.")
    knowledge_dir: str | None = Field(
        default=None,
        description="Override knowledge directory name.",
    )
    persona: str = Field(
        default="",
        description="Optional persona/voice for consultation responses.",
    )

    @field_validator("expert_id")
    @classmethod
    def _validate_expert_id(cls, v: str) -> str:
        if not v.startswith("expert-"):
            msg = f"expert_id must start with 'expert-', got: {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str]) -> list[str]:
        if len(v) > _MAX_KEYWORDS_PER_EXPERT:
            msg = f"Too many keywords ({len(v)}), max {_MAX_KEYWORDS_PER_EXPERT}"
            raise ValueError(msg)
        return v


class BusinessExpertsConfig(BaseModel):
    """Root schema for .tapps-mcp/experts.yaml."""

    model_config = ConfigDict(extra="forbid")

    _MAX_EXPERTS: ClassVar[int] = _MAX_BUSINESS_EXPERTS

    experts: list[BusinessExpertEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_experts(self) -> BusinessExpertsConfig:
        if len(self.experts) > _MAX_BUSINESS_EXPERTS:
            msg = f"Too many business experts ({len(self.experts)}), max {_MAX_BUSINESS_EXPERTS}"
            raise ValueError(msg)
        ids = [e.expert_id for e in self.experts]
        duplicates = [eid for eid in ids if ids.count(eid) > 1]
        if duplicates:
            msg = f"Duplicate expert_ids: {sorted(set(duplicates))}"
            raise ValueError(msg)
        return self


def load_business_experts(project_root: Path) -> list[ExpertConfig]:
    """Load user-defined business experts from .tapps-mcp/experts.yaml.

    Returns an empty list if the file does not exist (graceful degradation).
    Raises on malformed YAML or schema validation errors.
    """
    yaml_path = project_root / ".tapps-mcp" / "experts.yaml"

    if not yaml_path.exists():
        logger.debug("business_experts.file_not_found", path=str(yaml_path))
        return []

    raw_text = yaml_path.read_text(encoding="utf-8")

    try:
        raw_data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        msg = f"Malformed YAML in {yaml_path}: {exc}"
        raise ValueError(msg) from exc

    if raw_data is None:
        # Empty file
        return []

    if not isinstance(raw_data, dict):
        msg = f"Expected a mapping in {yaml_path}, got {type(raw_data).__name__}"
        raise ValueError(msg)

    config = BusinessExpertsConfig(**raw_data)

    results: list[ExpertConfig] = []
    for entry in config.experts:
        if entry.knowledge_dir is None:
            logger.info(
                "business_experts.no_knowledge_dir",
                expert_id=entry.expert_id,
                msg="No knowledge_dir specified; expert will have no RAG knowledge files.",
            )

        results.append(
            ExpertConfig(
                expert_id=entry.expert_id,
                expert_name=entry.expert_name,
                primary_domain=entry.primary_domain,
                description=entry.description,
                keywords=entry.keywords,
                rag_enabled=entry.rag_enabled,
                knowledge_dir=entry.knowledge_dir,
                is_builtin=False,
                persona=entry.persona,
            )
        )

    logger.info(
        "business_experts.loaded",
        count=len(results),
        expert_ids=[e.expert_id for e in results],
    )

    return results

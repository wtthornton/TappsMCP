"""Pydantic models for the expert system."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpertConfig(BaseModel):
    """Configuration for a single domain expert."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str = Field(description="Unique expert identifier (e.g., 'expert-security').")
    expert_name: str = Field(description="Human-readable expert name.")
    primary_domain: str = Field(description="Domain where this expert has primary authority.")
    description: str = Field(default="", description="Short description of the expert's focus.")
    rag_enabled: bool = Field(default=True, description="Whether RAG retrieval is enabled.")
    knowledge_dir: str | None = Field(
        default=None,
        description="Override knowledge directory name (default: derived from domain).",
    )


class KnowledgeChunk(BaseModel):
    """A chunk of knowledge retrieved via RAG search."""

    content: str = Field(description="Chunk text content.")
    source_file: str = Field(description="Relative path to the source knowledge file.")
    line_start: int = Field(description="Start line (1-indexed).")
    line_end: int = Field(description="End line.")
    score: float = Field(default=0.0, description="Relevance score (0.0-1.0).")


class ConfidenceFactors(BaseModel):
    """Factors used in confidence calculation."""

    rag_quality: float = Field(default=0.0, description="RAG retrieval quality (0.0-1.0).")
    domain_relevance: float = Field(
        default=1.0, description="How relevant the domain is (0.0-1.0)."
    )
    source_count: int = Field(default=0, description="Number of knowledge sources found.")
    chunk_coverage: float = Field(
        default=0.0, description="Fraction of query keywords covered by chunks."
    )


# Threshold below which we surface a low-confidence nudge to the AI
LOW_CONFIDENCE_THRESHOLD = 0.5

# Threshold above which expert guidance is considered high-confidence
HIGH_CONFIDENCE_THRESHOLD = 0.7


class ConsultationResult(BaseModel):
    """Result from an expert consultation."""

    domain: str = Field(description="Domain that handled the consultation.")
    expert_id: str = Field(description="Expert ID that responded.")
    expert_name: str = Field(description="Human-readable expert name.")
    answer: str = Field(description="Expert response text (markdown).")
    confidence: float = Field(description="Confidence score (0.0-1.0).")
    factors: ConfidenceFactors = Field(
        default_factory=ConfidenceFactors, description="Breakdown of confidence factors."
    )
    sources: list[str] = Field(default_factory=list, description="Knowledge file sources used.")
    chunks_used: int = Field(default=0, description="Number of RAG chunks used in response.")
    detected_domains: list[DomainMapping] = Field(
        default_factory=list,
        description="Top domain matches when auto-detecting (empty when domain was explicit).",
    )
    recommendation: str = Field(
        default="",
        description="Actionable next-step recommendation based on confidence level.",
    )
    low_confidence_nudge: str | None = Field(
        default=None,
        description="Actionable nudge when confidence is low (e.g. suggest tapps_lookup_docs).",
    )
    suggested_tool: str | None = Field(
        default=None,
        description="Suggested tool to call next when confidence/context is insufficient.",
    )
    suggested_library: str | None = Field(
        default=None,
        description="Suggested library name for documentation lookup.",
    )
    suggested_topic: str | None = Field(
        default=None,
        description="Suggested topic to look up for documentation fallback.",
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether automatic docs fallback content was merged into the answer.",
    )
    fallback_library: str | None = Field(
        default=None,
        description="Library used for automatic docs fallback lookup.",
    )
    fallback_topic: str | None = Field(
        default=None,
        description="Topic used for automatic docs fallback lookup.",
    )


class DomainMapping(BaseModel):
    """A detected domain with confidence score."""

    domain: str = Field(description="Expert domain name.")
    confidence: float = Field(description="Detection confidence (0.0-1.0).")
    signals: list[str] = Field(default_factory=list, description="Signal descriptions.")
    reasoning: str = Field(default="", description="Why this domain was detected.")


class StackDetectionResult(BaseModel):
    """Result of project stack detection."""

    detected_domains: list[DomainMapping] = Field(
        default_factory=list, description="Detected domains sorted by confidence."
    )
    primary_language: str | None = Field(default=None, description="Primary programming language.")
    primary_framework: str | None = Field(default=None, description="Primary framework detected.")


class ExpertInfo(BaseModel):
    """Public info about an expert (for tapps_list_experts)."""

    expert_id: str = Field(description="Unique expert identifier.")
    expert_name: str = Field(description="Human-readable name.")
    primary_domain: str = Field(description="Primary domain of authority.")
    description: str = Field(default="", description="Short description.")
    rag_enabled: bool = Field(default=True, description="Whether RAG is active.")
    knowledge_files: int = Field(default=0, description="Number of knowledge files loaded.")

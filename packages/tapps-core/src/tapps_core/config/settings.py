"""TappsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``TAPPS_MCP_*``)
    2. Project-level ``.tapps-mcp.yaml``
    3. Built-in defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)


class ScoringWeights(BaseSettings):
    """Weights for the 7-category scoring system.  Must sum to ~1.0."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_WEIGHT_")

    complexity: float = Field(default=0.18, ge=0.0, le=1.0)
    security: float = Field(default=0.27, ge=0.0, le=1.0)
    maintainability: float = Field(default=0.24, ge=0.0, le=1.0)
    test_coverage: float = Field(default=0.13, ge=0.0, le=1.0)
    performance: float = Field(default=0.08, ge=0.0, le=1.0)
    structure: float = Field(default=0.05, ge=0.0, le=1.0)
    devex: float = Field(default=0.05, ge=0.0, le=1.0)


class QualityPreset(BaseSettings):
    """Quality gate thresholds."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_GATE_")

    overall_min: float = Field(default=70.0, ge=0.0, le=100.0)
    security_min: float = Field(default=0.0, ge=0.0, le=100.0)
    maintainability_min: float = Field(default=0.0, ge=0.0, le=100.0)


# Standard presets
PRESETS: dict[str, dict[str, float]] = {
    "standard": {"overall_min": 70.0, "security_min": 0.0, "maintainability_min": 0.0},
    "strict": {"overall_min": 80.0, "security_min": 8.0, "maintainability_min": 7.0},
    "framework": {"overall_min": 75.0, "security_min": 8.5, "maintainability_min": 7.5},
}


class AdaptiveSettings(BaseSettings):
    """Settings for the adaptive learning subsystem."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_ADAPTIVE_")

    enabled: bool = Field(
        default=False,
        description="Enable adaptive weight adjustment.",
    )
    learning_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Learning rate for weight adjustment (0.0-1.0).",
    )
    min_outcomes: int = Field(
        default=5,
        ge=1,
        description="Minimum outcome records before adaptive adjustment activates.",
    )


class MemoryDecaySettings(BaseSettings):
    """Decay half-life configuration for the memory subsystem."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_MEMORY_DECAY_")

    architectural_half_life_days: int = Field(
        default=180, ge=1, description="Half-life for architectural memories (days)."
    )
    pattern_half_life_days: int = Field(
        default=60, ge=1, description="Half-life for pattern memories (days)."
    )
    procedural_half_life_days: int = Field(
        default=30, ge=1, description="Epic 65.11: Half-life for procedural memories (workflows, steps)."
    )
    context_half_life_days: int = Field(
        default=14, ge=1, description="Half-life for context memories (days)."
    )
    confidence_floor: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Minimum decayed confidence."
    )


class MemoryConsolidationSettings(BaseSettings):
    """Settings for memory consolidation (Epic 58)."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_MEMORY_CONSOLIDATION_")

    auto_consolidate: bool = Field(
        default=True,
        description="Enable automatic consolidation of similar memories on save.",
    )
    threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for consolidation (0.0-1.0).",
    )
    min_entries: int = Field(
        default=3,
        ge=2,
        description="Minimum entries required to trigger consolidation.",
    )
    scan_interval_days: int = Field(
        default=7,
        ge=1,
        description="Days between periodic consolidation scans at session start.",
    )
    scan_on_session_start: bool = Field(
        default=True,
        description="Run periodic consolidation scan at session start.",
    )


class MemoryWriteRules(BaseModel):
    """Write rules for memory saves (Epic 65.3). Used by optional validation gate (Epic 65.17)."""

    block_sensitive_keywords: list[str] = Field(
        default_factory=lambda: ["password", "secret", "api_key", "token"],
        description="Memory keys/values containing these substrings are blocked.",
    )
    min_value_length: int = Field(
        default=10,
        ge=0,
        description="Minimum allowed value length (characters).",
    )
    max_value_length: int = Field(
        default=4096,
        ge=1,
        description="Maximum allowed value length (characters).",
    )
    enforced: bool = Field(
        default=False,
        description="When True, block saves that violate write rules. Default: false (opt-in).",
    )


class MemorySafetySettings(BaseModel):
    """Content safety enforcement for memory saves."""

    enforcement: Literal["warn", "block"] = Field(
        default="warn",
        description=(
            "How to handle flagged content in memory saves. "
            "'warn': log and allow the write. "
            "'block': reject the save and return an error."
        ),
    )
    allow_bypass: bool = Field(
        default=False,
        description=(
            "Allow safety_bypass=True from any source. "
            "When False (default), only source='system' may bypass safety checks. "
            "When True, any source may use safety_bypass=True."
        ),
    )


class MemoryAutoRecallSettings(BaseModel):
    """Settings for the auto-recall hook (Epic 65.4)."""

    enabled: bool = Field(
        default=True,
        description=(
            "Enable auto-recall hook that injects relevant memories before agent prompt. "
            "Default true for POC; set false in .tapps-mcp.yaml to disable."
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum memories to inject (1-10). Default: 5.",
    )
    min_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum confidence (0-1). Default: 0.3.",
    )
    min_prompt_length: int = Field(
        default=50,
        ge=0,
        description="Skip recall if prompt/query shorter than N chars. Default: 50.",
    )


class MemoryAutoCaptureSettings(BaseModel):
    """Settings for the auto-capture hook (Epic 65.5)."""

    enabled: bool = Field(
        default=True,
        description=(
            "Enable auto-capture hook that extracts durable facts on session stop. "
            "Default true for POC; set false in .tapps-mcp.yaml to disable."
        ),
    )
    max_facts: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum facts to extract per session (1-10). Default: 5.",
    )


class MemoryHooksSettings(BaseModel):
    """Settings for memory-related hooks (Epic 65.4, 65.5)."""

    auto_recall: MemoryAutoRecallSettings = Field(
        default_factory=MemoryAutoRecallSettings,
        description="Auto-recall hook: inject relevant memories before agent prompt.",
    )
    auto_capture: MemoryAutoCaptureSettings = Field(
        default_factory=MemoryAutoCaptureSettings,
        description="Auto-capture hook: extract durable facts on session stop.",
    )


class MemoryHybridSettings(BaseModel):
    """Settings for hybrid BM25+vector search with RRF (Epic 65.8)."""

    top_bm25: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of top BM25 results to fetch for RRF fusion.",
    )
    top_vector: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of top vector results to fetch for RRF fusion.",
    )
    rrf_k: int = Field(
        default=60,
        ge=1,
        le=200,
        description="RRF constant: score = 1/(k+rank). Typical default 60.",
    )


class MemorySemanticSearchSettings(BaseModel):
    """Settings for optional vector/semantic search (Epic 65.7)."""

    enabled: bool = Field(
        default=False,
        description="Enable semantic search via optional embedding provider. Default: false.",
    )
    provider: str = Field(
        default="sentence_transformers",
        description="Provider name: sentence_transformers (openai future).",
    )
    model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Model name for sentence_transformers provider.",
    )


class MemoryRerankerSettings(BaseModel):
    """Settings for optional cross-encoder reranking (Epic 65.9)."""

    enabled: bool = Field(
        default=False,
        description="Enable reranking of top retrieval candidates (default: false).",
    )
    provider: str = Field(
        default="noop",
        description="Reranker provider: 'noop' (passthrough) or 'cohere'.",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of results to return after reranking (1-50). Default: 10.",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for Cohere reranker (required when provider=cohere).",
    )


class MemoryDocValidationSettings(BaseModel):
    """Settings for Context7-assisted memory validation (Epic 62)."""

    enabled: bool = Field(
        default=False,
        description="Enable doc validation of stale memories at session start.",
    )
    validate_on_session_start: bool = Field(
        default=True,
        description="Run validation during tapps_session_start.",
    )
    max_entries_per_session: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum memories to validate per session start.",
    )
    confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Only validate entries with confidence below this threshold.",
    )
    dry_run: bool = Field(
        default=False,
        description="When True, report results without applying changes.",
    )


class MemorySessionIndexSettings(BaseModel):
    """Settings for session indexing (Epic 65.10)."""

    enabled: bool = Field(
        default=False,
        description="Enable session indexing (default: false). Trade-off: more coverage, more noise.",
    )
    max_chunks_per_session: int = Field(
        default=50, ge=1, le=200, description="Maximum chunks per session (default: 50)."
    )
    max_chars_per_chunk: int = Field(
        default=500, ge=50, le=2000, description="Maximum characters per chunk (default: 500)."
    )
    ttl_days: int | None = Field(
        default=7,
        description="TTL in days (default: 7). None = no expiry.",
    )


class MemoryRelationSettings(BaseModel):
    """Settings for entity/relationship extraction (Epic 65.12)."""

    enabled: bool = Field(
        default=False,
        description="Enable entity/relationship extraction during consolidation.",
    )
    expand_queries: bool = Field(
        default=True,
        description="Use relation expansion for 'who/what handles X' queries (Epic 65.13).",
    )
    max_relations_per_entry: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum relations to extract per memory entry.",
    )


class MemoryRetrievalPolicy(BaseModel):
    """Retrieval policy for memory searches (Epic 65.14)."""

    block_sensitive_tags: list[str] = Field(
        default_factory=lambda: ["pii", "secret", "credentials"],
        description="Entries with these tags are excluded from search unless explicitly requested.",
    )
    min_confidence: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Filter out entries below this confidence threshold.",
    )
    include_debug_trace: bool = Field(
        default=False,
        description="Add _used_memory_keys to response for debugging.",
    )


class MemoryMaintenanceSettings(BaseModel):
    """Settings for memory maintenance schedule (Epic 65.15)."""

    on_session_start: bool = Field(
        default=False,
        description="Run maintenance on session_start when capacity > threshold.",
    )
    interval_hours: int = Field(
        default=24,
        ge=1,
        description="Minimum hours between automatic maintenance runs.",
    )
    capacity_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Run maintenance when capacity exceeds this fraction.",
    )


class MemorySettings(BaseSettings):
    """Settings for the shared memory subsystem."""

    model_config = SettingsConfigDict(env_prefix="TAPPS_MCP_MEMORY_")

    enabled: bool = Field(default=True, description="Enable the memory subsystem.")
    profile: str = Field(
        default="",
        description=(
            "Memory profile override. Empty string means auto-detect from project type. "
            "Set to a built-in profile name (e.g., 'repo-brain', 'research-knowledge', "
            "'project-management') to force a specific profile."
        ),
    )
    gc_enabled: bool = Field(default=True, description="Enable garbage collection.")
    contradiction_check_on_start: bool = Field(
        default=True, description="Run contradiction detection at session start."
    )
    max_memories: int = Field(
        default=1500, ge=1, description="Maximum number of active memories per project."
    )
    gc_auto_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Run GC at session start when usage exceeds this fraction of max_memories.",
    )
    inject_into_experts: bool = Field(
        default=True,
        description="Inject relevant memories into expert consultations (Epic 25).",
    )
    auto_save_quality: bool = Field(
        default=True,
        description=(
            "When True, persist successful expert consultations (tapps_consult_expert / "
            "tapps_research) as pattern-tier memories for pipeline recall (Epic M4.1). "
            "Default true for POC; set false to disable."
        ),
    )
    track_recurring_quick_check: bool = Field(
        default=True,
        description=(
            "When True, consecutive tapps_quick_check gate failures on the same file and "
            "category trigger procedural memory save or reinforce (Epic M4.2). "
            "Default true for POC; set false to disable."
        ),
    )
    recurring_quick_check_threshold: int = Field(
        default=3,
        ge=2,
        le=50,
        description="Consecutive gate failures per file+category before procedural memory (M4.2).",
    )
    enrich_impact_analysis: bool = Field(
        default=True,
        description=(
            "When True and memory is enabled, tapps_impact_analysis includes memory_context "
            "from a project-relative search for the target file (Epic M4.4)."
        ),
    )
    auto_supersede_architectural: bool = Field(
        default=True,
        description=(
            "When True and memory is enabled, tapps_memory save with tier=architectural "
            "supersedes the active architectural head for the key chain (store.history) "
            "via MemoryStore.supersede instead of overwriting in place (Epic M4.3). "
            "Default true for POC; set false to disable."
        ),
    )
    capture_prompt: str = Field(
        default=(
            "Store durable memories: architectural (project structure, key decisions), "
            "pattern (coding conventions, recurring solutions), procedural (how-to workflows), context "
            "(session-specific facts that matter next week). "
            "Skip: raw action logs, transient state, sensitive data. "
            "If it won't change future decisions, don't store it."
        ),
        description="Prompt for auto-capture (Epic 65.5) and manual save guidance (Epic 65.3).",
    )
    write_rules: MemoryWriteRules = Field(
        default_factory=MemoryWriteRules,
        description="Rules for memory write validation (Epic 65.3).",
    )
    safety: MemorySafetySettings = Field(
        default_factory=MemorySafetySettings,
        description="Content safety enforcement for memory saves.",
    )
    decay: MemoryDecaySettings = Field(default_factory=MemoryDecaySettings)
    consolidation: MemoryConsolidationSettings = Field(default_factory=MemoryConsolidationSettings)
    reranker: MemoryRerankerSettings = Field(
        default_factory=MemoryRerankerSettings,
        description="Optional reranking of retrieval results (Epic 65.9).",
    )
    semantic_search: MemorySemanticSearchSettings = Field(
        default_factory=MemorySemanticSearchSettings,
        description="Optional vector/semantic search (Epic 65.7).",
    )
    doc_validation: MemoryDocValidationSettings = Field(default_factory=MemoryDocValidationSettings)
    session_index: MemorySessionIndexSettings = Field(
        default_factory=MemorySessionIndexSettings,
        description="Session indexing for searchable past sessions (Epic 65.10).",
    )
    hybrid: MemoryHybridSettings = Field(
        default_factory=MemoryHybridSettings,
        description="Hybrid BM25+vector RRF settings (Epic 65.8).",
    )
    injection_max_tokens: int = Field(
        default=2000,
        ge=100,
        description="Maximum tokens for memory injection context. Approximate: 1 token ~ 4 chars.",
    )
    retrieval_policy: MemoryRetrievalPolicy = Field(
        default_factory=MemoryRetrievalPolicy,
        description="Retrieval policy for memory searches (Epic 65.14).",
    )
    maintenance: MemoryMaintenanceSettings = Field(
        default_factory=MemoryMaintenanceSettings,
        description="Memory maintenance schedule (Epic 65.15).",
    )
    relations: MemoryRelationSettings = Field(
        default_factory=MemoryRelationSettings,
        description="Entity/relationship extraction settings (Epic 65.12).",
    )

    # EPIC-102: auto-recall hook for tapps_validate_changed
    recall_on_validate: bool = Field(
        default=False,
        description=(
            "When True, tapps_validate_changed searches the insights memory_group "
            "for entries relevant to the files being validated and attaches them "
            "under 'recalled_insights' in the response. Requires tapps-brain. "
            "Env: TAPPS_MCP_MEMORY_RECALL_ON_VALIDATE."
        ),
    )

    # EPIC-95: tapps-brain v3 Postgres connection (BrainBridge)
    database_url: str = Field(
        default="",
        description=(
            "Postgres DSN for tapps-brain v3 (e.g. postgresql://user:pass@host/db). "
            "Falls back to TAPPS_BRAIN_DATABASE_URL env var when empty. "
            "Required to enable BrainBridge memory backend. "
            "Env: TAPPS_MCP_MEMORY_DATABASE_URL."
        ),
    )
    hive_dsn: str = Field(
        default="",
        description=(
            "Optional separate Postgres DSN for the hive namespace. "
            "When set, enables hive_search and hive_propagate across agents. "
            "Env: TAPPS_MCP_MEMORY_HIVE_DSN."
        ),
    )


class DocSourceConfig(BaseModel):
    """Custom documentation source for a specific library."""

    url: str | None = Field(default=None, description="URL to fetch documentation from.")
    file: str | None = Field(
        default=None,
        description="Local file path (relative to project root) containing documentation.",
    )
    format: str = Field(default="markdown", description="Content format: markdown or text.")


class TappsMCPSettings(BaseSettings):
    """Root settings for TappsMCP server."""

    model_config = SettingsConfigDict(
        env_prefix="TAPPS_MCP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Core
    project_root: Path = Field(
        default_factory=Path.cwd,
        description="Project root boundary - all file paths must be within this directory.",
    )
    host_project_root: str | None = Field(
        default=None,
        description=(
            "Optional host path the client uses for the same project "
            "(e.g. C:\\projects\\myapp). When set, absolute paths under "
            "this are mapped to project_root so Cursor/Docker work together."
        ),
    )
    quality_preset: str = Field(
        default="standard",
        description="Quality gate preset: standard, strict, or framework.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level.",
    )
    log_json: bool = Field(
        default=False,
        description="Output JSON-formatted logs.",
    )

    # API keys
    context7_api_key: SecretStr | None = Field(
        default=None,
        description="Context7 API key (optional).",
    )

    # Scoring
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    quality_gate: QualityPreset = Field(default_factory=QualityPreset)

    # Adaptive learning
    adaptive: AdaptiveSettings = Field(default_factory=AdaptiveSettings)

    # Tool timeouts
    tool_timeout: int = Field(
        default=30,
        ge=5,
        description="Timeout for individual external tool invocations (seconds).",
    )

    # Dead code detection
    dead_code_enabled: bool = Field(
        default=True,
        description="Enable dead code detection via vulture in scoring.",
    )
    dead_code_min_confidence: int = Field(
        default=80,
        ge=0,
        le=100,
        description="Minimum confidence threshold for dead code findings (0-100).",
    )
    dead_code_whitelist_patterns: list[str] = Field(
        default_factory=lambda: ["test_*", "conftest.py"],
        description="File name patterns to exclude from dead code findings (fnmatch).",
    )

    # Dependency vulnerability scanning
    dependency_scan_enabled: bool = Field(
        default=True,
        description="Enable dependency vulnerability scanning via pip-audit.",
    )
    dependency_scan_severity_threshold: str = Field(
        default="medium",
        description="Minimum severity to include: critical, high, medium, low, unknown.",
    )
    dependency_scan_ignore_ids: list[str] = Field(
        default_factory=list,
        description="Vulnerability IDs to exclude (e.g. CVE-2024-12345).",
    )
    dependency_scan_source: str = Field(
        default="auto",
        description="Scan source: auto, environment, requirements, pyproject.",
    )

    # LLM engagement level (Epic 18)
    llm_engagement_level: Literal["high", "medium", "low"] = Field(
        default="medium",
        description=(
            "How intensely the LLM should use TappsMCP tools. "
            "'high' = mandatory enforcement, 'medium' = balanced, 'low' = optional guidance."
        ),
    )

    # Checklist policy (tapps_checklist)
    checklist_strict_unknown_task_types: bool = Field(
        default=False,
        description=(
            "When True, tapps_checklist rejects unknown task_type values instead of falling "
            "back to the review policy. Env: TAPPS_MCP_CHECKLIST_STRICT_UNKNOWN_TASK_TYPES."
        ),
    )
    checklist_require_success: bool = Field(
        default=False,
        description=(
            "When True, the latest failed tool call does not satisfy checklist requirements. "
            "Env: TAPPS_MCP_CHECKLIST_REQUIRE_SUCCESS."
        ),
    )

    # Upgrade skip list (Issue #86)
    upgrade_skip_files: list[str] = Field(
        default_factory=list,
        description=(
            "File paths (relative to project root) to skip during tapps_upgrade. "
            "Use this to protect project-specific customizations from being overwritten. "
            "Example: ['CLAUDE.md', '.claude/rules/tapps-pipeline.md']"
        ),
    )

    # Destructive command guard (opt-in PreToolUse hook)
    destructive_guard: bool = Field(
        default=False,
        description=(
            "When True, generate a PreToolUse hook that blocks Bash commands "
            "containing destructive patterns (rm -rf, format c:, etc.). Opt-in only."
        ),
    )

    # Business experts (Epic 43)
    business_experts_enabled: bool = Field(
        default=True,
        description="Enable loading business experts from .tapps-mcp/experts.yaml.",
    )
    business_experts_max: int = Field(
        default=20,
        ge=0,
        le=50,
        description="Maximum number of business experts to load.",
    )

    # Memory subsystem (Epic 23-25)
    memory: MemorySettings = Field(default_factory=MemorySettings)

    # Memory hooks (Epic 65.4)
    memory_hooks: MemoryHooksSettings = Field(
        default_factory=MemoryHooksSettings,
        description="Settings for memory-related hooks (auto-recall).",
    )

    # Knowledge cache
    cache_max_mb: int = Field(
        default=100,
        ge=1,
        description="Maximum knowledge cache size in MB before LRU eviction triggers.",
    )

    # Expert/doc coupling
    expert_auto_fallback: bool = Field(
        default=True,
        description=(
            "Enable automatic Context7 lookup hints/content when expert RAG has no matches."
        ),
    )
    expert_fallback_max_chars: int = Field(
        default=1200,
        ge=200,
        description="Maximum number of characters merged from Context7 fallback content.",
    )

    # Custom documentation sources (Epic 54)
    doc_sources: dict[str, DocSourceConfig] = Field(
        default_factory=dict,
        description=(
            "Custom documentation sources keyed by library name. "
            "These take priority over Context7/LlmsTxt providers."
        ),
    )

    # Tech stack RAG boost (Epic 54)
    tech_stack_boost: float = Field(
        default=1.2,
        ge=1.0,
        le=3.0,
        description="Boost multiplier for RAG chunks matching the project tech stack domains.",
    )

    # Tool curation (Epic 79.1): server-side allow/deny list and presets
    enabled_tools: list[str] | None = Field(
        default=None,
        description=(
            "Allow list: when non-empty, only these tools are exposed. "
            "Empty/missing = all tools (backward compatible). "
            "Env: TAPPS_MCP_ENABLED_TOOLS (comma-separated)."
        ),
    )
    disabled_tools: list[str] = Field(
        default_factory=list,
        description=(
            "Deny list: excluded from the exposed set. "
            "Applied when enabled_tools is empty; ignored when enabled_tools is set. "
            "Env: TAPPS_MCP_DISABLED_TOOLS (comma-separated)."
        ),
    )
    tool_preset: Literal[
        "full", "core", "pipeline",
        "reviewer", "planner", "frontend", "developer",
        "quality", "admin",
    ] | None = Field(
        default=None,
        description=(
            "Predefined tool set: 'full' = all tools, 'core' = Tier 1 (7 tools), "
            "'pipeline' = Tier 1 + Tier 2; 'reviewer'|'planner'|'frontend'|'developer' = role presets (Epic 79.5); "
            "'quality' = coding session tools (TAP-485); 'admin' = setup/troubleshooting tools (TAP-485). "
            "Used when enabled_tools is not set. Env: TAPPS_MCP_TOOL_PRESET."
        ),
    )

    @field_validator("enabled_tools", mode="before")
    @classmethod
    def _parse_enabled_tools(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = [s.strip() for s in v.split(",") if s.strip()]
            return v if v else None
        if isinstance(v, list):
            return v if v else None
        return None

    @field_validator("disabled_tools", mode="before")
    @classmethod
    def _parse_disabled_tools(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return list(v)
        return []


# Settings cache - only the no-arg (default) case is cached.
_cached_settings: TappsMCPSettings | None = None


def _reset_settings_cache() -> None:
    """Reset the cached settings singleton.

    Call in test teardown or when environment/YAML config changes mid-process.
    """
    global _cached_settings
    _cached_settings = None


def _load_yaml_config(project_root: Path) -> dict[str, Any]:
    """Load project-level ``.tapps-mcp.yaml`` if it exists."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return {}

    try:
        with config_path.open(encoding="utf-8-sig") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("mcp_config_load_failed", path=str(config_path), reason=str(e))
        return {}


def load_settings(project_root: Path | None = None) -> TappsMCPSettings:
    """Load settings with correct precedence.

    When *project_root* is ``None`` (the default), returns a cached singleton
    created on the first call.  Pass an explicit *project_root* to bypass the
    cache entirely.

    Args:
        project_root: Override for project root.  When ``None``, uses CWD.

    Returns:
        Fully resolved ``TappsMCPSettings``.
    """
    global _cached_settings

    if project_root is None and _cached_settings is not None:
        return _cached_settings

    # Determine root: explicit arg > env var > CWD
    if project_root:
        root = Path(project_root)
    else:
        import os

        env_root = os.environ.get("TAPPS_MCP_PROJECT_ROOT")
        root = Path(env_root) if env_root else Path.cwd()

    yaml_data = _load_yaml_config(root)

    # Merge YAML defaults, then let env vars override via pydantic-settings.
    # Only inject project_root if neither YAML nor env var sets it,
    # so the env var takes priority over CWD.
    if "project_root" not in yaml_data:
        yaml_data["project_root"] = str(root)

    result = TappsMCPSettings(**yaml_data)

    if project_root is None:
        _cached_settings = result

    return result

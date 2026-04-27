"""Verify tapps-mcp re-exports resolve to the same objects as tapps-core.

This replaces ~60 duplicate test files that only differed in import paths.
The actual behavioral tests live in packages/tapps-core/tests/unit/.
"""

from __future__ import annotations

import importlib

import pytest

# Each tuple: (tapps_core module path, tapps_mcp module path, list of symbols to check)
_REEXPORT_PAIRS: list[tuple[str, str, list[str]]] = [
    # --- adaptive ---
    (
        "tapps_core.adaptive.models",
        "tapps_mcp.adaptive.models",
        [
            "AdaptiveWeightsSnapshot",
            "CodeOutcome",
            "ExpertPerformance",
            "ExpertWeightMatrix",
            "ExpertWeightsSnapshot",
            "_utc_now_iso",
        ],
    ),
    (
        "tapps_core.adaptive.persistence",
        "tapps_mcp.adaptive.persistence",
        ["FileOutcomeTracker", "FilePerformanceTracker", "save_json_atomic"],
    ),
    (
        "tapps_core.adaptive.scoring_engine",
        "tapps_mcp.adaptive.scoring_engine",
        [
            "AdaptiveScoringEngine",
            "DEFAULT_LEARNING_RATE",
            "MIN_OUTCOMES_FOR_ADJUSTMENT",
            "_get_default_weights",
            "_pearson_correlation",
        ],
    ),
    (
        "tapps_core.adaptive.scoring_wrapper",
        "tapps_mcp.adaptive.scoring_wrapper",
        ["AdaptiveScorerWrapper"],
    ),
    (
        "tapps_core.adaptive.voting_engine",
        "tapps_mcp.adaptive.voting_engine",
        ["AdaptiveVotingEngine"],
    ),
    (
        "tapps_core.adaptive.weight_distributor",
        "tapps_mcp.adaptive.weight_distributor",
        ["WeightDistributor"],
    ),
    # --- common ---
    (
        "tapps_core.common.exceptions",
        "tapps_mcp.common.exceptions",
        [
            "ConfigurationError",
            "FileOperationError",
            "PathValidationError",
            "QualityGateError",
            "SecurityError",
            "TappsMCPError",
            "ToolExecutionError",
            "ToolNotFoundError",
        ],
    ),
    (
        "tapps_core.common.models",
        "tapps_mcp.common.models",
        [
            "CacheDiagnostic",
            "Context7Diagnostic",
            "ErrorDetail",
            "InstalledTool",
            "KnowledgeBaseDiagnostic",
            "KnowledgeDomainInfo",
            "SecurityIssue",
            "StartupDiagnostics",
            "ToolResponse",
        ],
    ),
    (
        "tapps_core.common.utils",
        "tapps_mcp.common.utils",
        ["SKIP_DIRS", "ensure_dir", "read_text_utf8", "should_skip_path", "utc_now"],
    ),
    # --- config ---
    (
        "tapps_core.config.settings",
        "tapps_mcp.config.settings",
        [
            "AdaptiveSettings",
            "MemoryDecaySettings",
            "MemorySettings",
            "PRESETS",
            "QualityPreset",
            "ScoringWeights",
            "TappsMCPSettings",
            "_load_yaml_config",
            "_reset_settings_cache",
            "load_settings",
        ],
    ),
    # --- knowledge ---
    (
        "tapps_core.knowledge.cache",
        "tapps_mcp.knowledge.cache",
        [
            "CacheStats",
            "DEFAULT_STALENESS_POLICIES",
            "DEFAULT_TTL_SECONDS",
            "KBCache",
            "_safe_name",
        ],
    ),
    (
        "tapps_core.knowledge.circuit_breaker",
        "tapps_mcp.knowledge.circuit_breaker",
        [
            "CircuitBreaker",
            "CircuitBreakerConfig",
            "CircuitBreakerOpenError",
            "CircuitBreakerStats",
            "CircuitState",
            "get_context7_circuit_breaker",
        ],
    ),
    (
        "tapps_core.knowledge.content_normalizer",
        "tapps_mcp.knowledge.content_normalizer",
        [
            "CodeSnippet",
            "NormalizationResult",
            "ReferenceCard",
            "apply_token_budget",
            "deduplicate_snippets",
            "extract_snippets",
            "normalize_content",
            "rank_snippets",
        ],
    ),
    (
        "tapps_core.knowledge.context7_client",
        "tapps_mcp.knowledge.context7_client",
        [
            "CONTEXT7_BASE_URL",
            "Context7Client",
            "Context7Error",
            "DEFAULT_MAX_TOKENS",
            "DEFAULT_TIMEOUT",
        ],
    ),
    (
        "tapps_core.knowledge.fuzzy_matcher",
        "tapps_mcp.knowledge.fuzzy_matcher",
        [
            "CONFIDENCE_HIGH",
            "CONFIDENCE_LOW",
            "CONFIDENCE_MEDIUM",
            "LANGUAGE_HINTS",
            "LIBRARY_ALIASES",
            "combined_score",
            "confidence_band",
            "did_you_mean",
            "edit_distance",
            "edit_distance_similarity",
            "fuzzy_match_library",
            "fuzzy_match_topic",
            "lcs_length",
            "lcs_similarity",
            "multi_signal_score",
            "resolve_alias",
            "token_overlap_score",
        ],
    ),
    (
        "tapps_core.knowledge.import_analyzer",
        "tapps_mcp.knowledge.import_analyzer",
        ["_detect_project_package", "extract_external_imports", "find_uncached_libraries"],
    ),
    (
        "tapps_core.knowledge.library_detector",
        "tapps_mcp.knowledge.library_detector",
        [
            "_clean_package_name",
            "_parse_package_json",
            "_parse_pyproject",
            "_parse_requirements",
            "detect_libraries",
        ],
    ),
    (
        "tapps_core.knowledge.lookup",
        "tapps_mcp.knowledge.lookup",
        ["LookupEngine", "_build_provider_registry"],
    ),
    (
        "tapps_core.knowledge.models",
        "tapps_mcp.knowledge.models",
        [
            "CacheEntry",
            "ConfigValidationResult",
            "FuzzyMatch",
            "LibraryMatch",
            "LookupResult",
            "ValidationFinding",
        ],
    ),
    (
        "tapps_core.knowledge.providers.base",
        "tapps_mcp.knowledge.providers.base",
        ["DocumentationProvider", "ProviderResult"],
    ),
    (
        "tapps_core.knowledge.providers.llms_txt_provider",
        "tapps_mcp.knowledge.providers.llms_txt_provider",
        ["LlmsTxtProvider"],
    ),
    (
        "tapps_core.knowledge.providers.registry",
        "tapps_mcp.knowledge.providers.registry",
        ["ProviderRegistry", "_FAILURE_THRESHOLD", "_ProviderState", "_RECOVERY_SECONDS"],
    ),
    (
        "tapps_core.security.content_safety",
        "tapps_mcp.knowledge.rag_safety",
        ["SafetyCheckResult", "_INJECTION_PATTERNS", "_sanitise_content", "check_content_safety"],
    ),
    (
        "tapps_core.knowledge.warming",
        "tapps_mcp.knowledge.warming",
        ["MAX_WARM_LIBRARIES", "WARM_DELAY_SECONDS", "warm_cache"],
    ),
    # --- metrics ---
    (
        "tapps_core.metrics.alerts",
        "tapps_mcp.metrics.alerts",
        ["Alert", "AlertCondition", "AlertManager", "AlertSeverity"],
    ),
    (
        "tapps_core.metrics.collector",
        "tapps_mcp.metrics.collector",
        ["MetricsHub", "get_metrics_hub", "reset_metrics_hub"],
    ),
    (
        "tapps_core.metrics.confidence_metrics",
        "tapps_mcp.metrics.confidence_metrics",
        ["ConfidenceMetric", "ConfidenceMetricsTracker", "ConfidenceStatistics"],
    ),
    (
        "tapps_core.metrics.consultation_logger",
        "tapps_mcp.metrics.consultation_logger",
        ["ConsultationEntry", "ConsultationLogger"],
    ),
    (
        "tapps_core.metrics.dashboard",
        "tapps_mcp.metrics.dashboard",
        ["DashboardGenerator"],
    ),
    (
        "tapps_core.metrics.execution_metrics",
        "tapps_mcp.metrics.execution_metrics",
        ["ToolBreakdown", "ToolCallMetric", "ToolCallMetricsCollector", "ToolCallSummary"],
    ),
    (
        "tapps_core.metrics.otel_export",
        "tapps_mcp.metrics.otel_export",
        ["export_otel_trace", "export_to_file"],
    ),
    (
        "tapps_core.metrics.outcome_tracker",
        "tapps_mcp.metrics.outcome_tracker",
        ["CodeOutcome", "OutcomeTracker"],
    ),
    (
        "tapps_core.metrics.quality_aggregator",
        "tapps_mcp.metrics.quality_aggregator",
        ["AggregateReport", "FileScore", "QualityAggregator"],
    ),
    (
        "tapps_core.metrics.rag_metrics",
        "tapps_mcp.metrics.rag_metrics",
        ["RAGMetricsTracker", "RAGPerformanceMetrics", "RAGQueryMetric", "RAGQueryTimer"],
    ),
    (
        "tapps_core.metrics.trends",
        "tapps_mcp.metrics.trends",
        ["TrendData", "calculate_trend", "detect_trends"],
    ),
    (
        "tapps_core.metrics.visualizer",
        "tapps_mcp.metrics.visualizer",
        ["AnalyticsVisualizer"],
    ),
    # --- security ---
    (
        "tapps_core.security.governance",
        "tapps_mcp.security.governance",
        ["FilterResult", "GovernanceLayer", "GovernancePolicy"],
    ),
    (
        "tapps_core.security.io_guardrails",
        "tapps_mcp.security.io_guardrails",
        ["detect_likely_prompt_injection", "sanitize_for_log"],
    ),
    (
        "tapps_core.security.path_validator",
        "tapps_mcp.security.path_validator",
        ["PathValidator", "assert_write_allowed"],
    ),
    (
        "tapps_core.security.secret_scanner",
        "tapps_mcp.security.secret_scanner",
        ["SecretFinding", "SecretScanResult", "SecretScanner"],
    ),
]


@pytest.mark.parametrize(
    ("core_mod", "mcp_mod", "symbols"),
    _REEXPORT_PAIRS,
    ids=[pair[1] for pair in _REEXPORT_PAIRS],
)
def test_reexport_identity(core_mod: str, mcp_mod: str, symbols: list[str]) -> None:
    """Re-exported symbol is the same object as the source."""
    core = importlib.import_module(core_mod)
    mcp = importlib.import_module(mcp_mod)
    for sym in symbols:
        core_obj = getattr(core, sym)
        mcp_obj = getattr(mcp, sym)
        assert core_obj is mcp_obj, f"{mcp_mod}.{sym} is not {core_mod}.{sym}"

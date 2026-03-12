# Module Map

**Total modules:** 316  
**Total packages:** 38  
**Public API count:** 817

|-- **docs_mcp/** - Docs MCP: Documentation MCP server for the Tapps platform.
|   |-- **analyzers/** - Code analysis engines for DocsMCP.; 14 public APIs
|   |   |-- api_surface - Public API surface detector for source modules (Python + multi-language).; 5 public APIs
|   |   |-- commit_parser - Conventional commit parser and heuristic classifier for DocsMCP.; 3 public APIs
|   |   |-- dependency - Import dependency graph builder for Python projects.; 3 public APIs
|   |   |-- git_history - Git log parser for DocsMCP.; 3 public APIs
|   |   |-- models - Data models for code analysis results.; 2 public APIs
|   |   |-- module_map - Module structure analyzer that builds a hierarchical map of a project.; 1 public APIs
|   |   `-- version_detector - Tag/version boundary detection for DocsMCP.; 2 public APIs
|   |-- cli - DocsMCP CLI - documentation MCP server management.; 6 public APIs
|   |-- **config/** - DocsMCP configuration system.
|   |   `-- settings - DocsMCP configuration system.; 2 public APIs
|   |-- **extractors/** - Code extraction engines for DocsMCP.; 6 public APIs
|   |   |-- base - Base protocol for source code extractors.; 1 public APIs
|   |   |-- dispatcher - Extractor dispatcher -- selects the best extractor for a given file.; 1 public APIs
|   |   |-- docstring_parser - Docstring parser supporting Google, NumPy, and Sphinx styles.; 6 public APIs
|   |   |-- generic - Regex-based fallback extractor for any text-based source file.; 2 public APIs
|   |   |-- models - Data models for code extraction results.; 6 public APIs
|   |   |-- python - Python AST-based source code extractor.; 1 public APIs
|   |   |-- treesitter_base - Base class for tree-sitter powered source code extractors.; 1 public APIs
|   |   |-- treesitter_go - Tree-sitter based Go extractor.; 1 public APIs
|   |   |-- treesitter_java - Tree-sitter based Java extractor.; 1 public APIs
|   |   |-- treesitter_rust - Tree-sitter based Rust extractor.; 1 public APIs
|   |   |-- treesitter_typescript - Tree-sitter based TypeScript/TSX extractor.; 1 public APIs
|   |   `-- type_annotations - Type annotation extraction and resolution for Python AST nodes.; 4 public APIs
|   |-- **generators/** - DocsMCP generators - README generation, metadata extraction, and smart merge.
|   |   |-- adr - Architecture Decision Record (ADR) generation in MADR and Nygard formats.; 2 public APIs
|   |   |-- api_docs - Per-module API reference documentation generator.; 5 public APIs
|   |   |-- changelog - Changelog generation in Keep-a-Changelog and Conventional formats.; 3 public APIs
|   |   |-- diagrams - Diagram generation for Python project structures.; 2 public APIs
|   |   |-- guides - Onboarding and contributing guide generation.; 2 public APIs
|   |   |-- metadata - Project metadata extraction from pyproject.toml, package.json, and Cargo.toml.; 2 public APIs
|   |   |-- readme - README generation with Jinja2 templates and section generators.; 2 public APIs
|   |   |-- release_notes - Release notes generation for a specific version.; 2 public APIs
|   |   |-- smart_merge - Smart merge engine for preserving human-written README sections.; 2 public APIs
|   |   `-- specs - Product Requirements Document (PRD) generation with phased requirements.; 3 public APIs
|   |-- **integrations/** - DocsMCP integrations - optional enrichment from external tools.
|   |   `-- tapps - TappsMCP integration for optional quality enrichment in DocsMCP.; 5 public APIs
|   |-- server - DocsMCP MCP server entry point.; 4 public APIs
|   |-- server_analysis - DocsMCP analysis tools — docs_module_map and docs_api_surface.; 2 public APIs
|   |-- server_gen_tools - DocsMCP generation tools.; 9 public APIs
|   |-- server_git_tools - DocsMCP git analysis tools -- docs_git_summary.; 1 public APIs
|   |-- server_helpers - Helper functions for DocsMCP server — response builders and singleton caches.; 2 public APIs
|   |-- server_resources - MCP resources and workflow prompts for DocsMCP.
|   |-- server_val_tools - DocsMCP validation tools -- docs_check_drift, docs_check_completeness,; 4 public APIs
|   `-- **validators/** - Documentation validation engine for DocsMCP.; 8 public APIs
|       |-- completeness - Documentation completeness checker.; 3 public APIs
|       |-- drift - Drift detection: identify code changes not reflected in documentation.; 3 public APIs
|       |-- freshness - Documentation freshness scoring based on file modification times.; 3 public APIs
|       `-- link_checker - Internal link validator for documentation files.; 3 public APIs

|-- **tapps_core/** - Tapps Core: Shared infrastructure library for the Tapps platform.
|   |-- **adaptive/** - Adaptive learning and intelligence subsystem.
|   |   |-- models - Pydantic models for the adaptive learning subsystem.; 5 public APIs
|   |   |-- persistence - File-based implementations of the adaptive tracking protocols.; 3 public APIs
|   |   |-- protocols - Protocol interfaces for metrics tracking.; 2 public APIs
|   |   |-- scoring_engine - Adaptive scoring engine using Pearson correlation analysis.; 1 public APIs
|   |   |-- scoring_wrapper - Thin adapter wiring adaptive weights into CodeScorer.; 1 public APIs
|   |   |-- voting_engine - Adaptive voting engine for expert weight adjustment.; 1 public APIs
|   |   `-- weight_distributor - Expert weight distribution utility.; 1 public APIs
|   |-- **common/** - Common utilities shared across Tapps platform modules.
|   |   |-- constants - Shared constants used across Tapps platform modules.
|   |   |-- exceptions - Exception hierarchy for the Tapps platform.; 8 public APIs
|   |   |-- logging - Structured logging setup using structlog.; 2 public APIs
|   |   |-- models - Shared Pydantic v2 models for the Tapps platform.; 10 public APIs
|   |   |-- pipeline_models - Pipeline stage definitions shared across Tapps platform modules.; 1 public APIs
|   |   `-- utils - Shared utility functions to eliminate cross-module duplication.; 4 public APIs
|   |-- **config/** - Configuration: settings, defaults, YAML loading.
|   |   |-- feature_flags - Unified feature flags for optional dependencies.; 1 public APIs
|   |   `-- settings - TappsMCP configuration system.; 8 public APIs
|   |-- **experts/** - Expert system — 16-domain RAG-backed expert consultation.
|   |   |-- adaptive_domain_detector - Adaptive domain detector for expert routing.; 2 public APIs
|   |   |-- business_config - YAML schema and loader for user-defined business experts.; 3 public APIs
|   |   |-- business_knowledge - Business expert knowledge directory utilities.; 4 public APIs
|   |   |-- business_loader - Business expert auto-loading integration.; 2 public APIs
|   |   |-- business_templates - Starter templates for business expert knowledge directories.; 2 public APIs
|   |   |-- confidence - Confidence scoring for expert consultations.; 3 public APIs
|   |   |-- domain_detector - Lightweight domain detector — maps questions and repo signals to expert domains.; 1 public APIs
|   |   |-- domain_utils - Utility functions for domain name handling.; 1 public APIs
|   |   |-- engine - Expert consultation engine — orchestrates RAG lookup and confidence scoring.; 2 public APIs
|   |   |-- hot_rank - Hot-rank — adaptive ranking from usage + feedback signals.; 4 public APIs
|   |   |-- knowledge_freshness - Knowledge file freshness tracking.; 2 public APIs
|   |   |-- knowledge_ingestion - Knowledge ingestion pipeline for project documentation.; 3 public APIs
|   |   |-- knowledge_validator - Knowledge base file validator.; 3 public APIs
|   |   |-- models - Pydantic models for the expert system.; 7 public APIs
|   |   |-- query_expansion - Query expansion with synonym matching for improved domain detection.; 2 public APIs
|   |   |-- rag - Simple file-based RAG system for expert knowledge retrieval.; 1 public APIs
|   |   |-- rag_chunker - Markdown-aware document chunker for RAG knowledge retrieval.; 2 public APIs
|   |   |-- rag_embedder - Embedding interface and optional sentence-transformers implementation.; 3 public APIs
|   |   |-- rag_index - FAISS-based vector index for RAG knowledge retrieval.; 2 public APIs
|   |   |-- rag_warming - Expert RAG index warming — pre-build vector indices from tech stack.; 3 public APIs
|   |   |-- registry - Built-in expert registry — 17-domain expert catalogue + business experts.; 1 public APIs
|   |   |-- retrieval_eval - Retrieval evaluation harness — benchmark queries, metrics, and quality gates.; 5 public APIs
|   |   `-- vector_rag - Vector RAG knowledge base with automatic FAISS fallback.; 1 public APIs
|   |-- **knowledge/** - Knowledge & documentation lookup system (Epic 2).
|   |   |-- cache - KB cache — file-based documentation cache with TTL and atomic writes.; 2 public APIs
|   |   |-- circuit_breaker - Circuit breaker — fail-fast wrapper for external API calls.; 6 public APIs
|   |   |-- content_normalizer - Context7 code-reference quality normalization.; 8 public APIs
|   |   |-- context7_client - Context7 API client — async HTTP client for documentation lookup.; 2 public APIs
|   |   |-- fuzzy_matcher - Fuzzy matcher v2 — multi-signal library name resolution.; 12 public APIs
|   |   |-- import_analyzer - Analyze Python file imports to detect uncached external libraries.; 2 public APIs
|   |   |-- library_detector - Library detector — extract project dependencies from manifest files.; 1 public APIs
|   |   |-- lookup - Lookup orchestration — ties cache, fuzzy matcher, providers, and circuit brea...; 1 public APIs
|   |   |-- models - Pydantic models for the knowledge & documentation system.; 6 public APIs
|   |   |-- **providers/** - Documentation provider abstraction for multi-backend lookup.; 3 public APIs
|   |   |   |-- base - Base protocol and models for documentation providers.; 2 public APIs
|   |   |   |-- context7_provider - Context7 documentation provider - wraps the existing Context7Client.; 1 public APIs
|   |   |   |-- llms_txt_provider - llms.txt provider - zero-dependency fallback using the llms.txt standard.; 1 public APIs
|   |   |   `-- registry - Provider registry with fallback chain and per-provider circuit breakers.; 1 public APIs
|   |   |-- rag_safety - RAG safety - backward-compatible re-export from security.content_safety.; 4 public APIs
|   |   `-- warming - Cache warming — pre-fetch documentation for project dependencies.; 1 public APIs
|   |-- **memory/** - Shared memory subsystem for persistent cross-session knowledge.
|   |   |-- bm25 - BM25 scoring engine for memory retrieval.; 3 public APIs
|   |   |-- contradictions - Contradiction detection for memory entries.; 2 public APIs
|   |   |-- decay - Time-based decay engine for memory confidence.; 4 public APIs
|   |   |-- gc - Garbage collection and archival for memory entries.; 2 public APIs
|   |   |-- injection - Memory injection into expert and research responses.; 2 public APIs
|   |   |-- io - Import and export for shared memory entries.; 2 public APIs
|   |   |-- models - Pydantic v2 models for the shared memory subsystem.; 5 public APIs
|   |   |-- persistence - SQLite-backed persistence layer for the shared memory subsystem.; 1 public APIs
|   |   |-- reinforcement - Reinforcement system for memory entries.; 1 public APIs
|   |   |-- retrieval - Ranked memory retrieval with composite scoring.; 2 public APIs
|   |   |-- seeding - Profile-based memory seeding.; 2 public APIs
|   |   `-- store - In-memory cache backed by SQLite for the shared memory subsystem.; 1 public APIs
|   |-- **metrics/** - TappsMCP metrics, observability, and dashboard subsystem (Epic 7).
|   |   |-- alerts - Analytics alerting system.; 4 public APIs
|   |   |-- business_metrics - Business and aggregate metrics collection.; 7 public APIs
|   |   |-- collector - Central metrics collector singleton.; 3 public APIs
|   |   |-- confidence_metrics - Confidence metrics tracker.; 3 public APIs
|   |   |-- consultation_logger - Consultation history logger.; 2 public APIs
|   |   |-- dashboard - Dashboard generation for metrics visualization.; 1 public APIs
|   |   |-- execution_metrics - Execution metrics collector for MCP tool calls.; 4 public APIs
|   |   |-- expert_metrics - Expert performance tracking and analysis.; 3 public APIs
|   |   |-- expert_observability - Expert observability system.; 3 public APIs
|   |   |-- feedback - User feedback tracker.; 2 public APIs
|   |   |-- otel_export - OpenTelemetry trace export.; 2 public APIs
|   |   |-- outcome_tracker - Outcome tracker for code quality lifecycle.; 2 public APIs
|   |   |-- quality_aggregator - Quality aggregator for multi-file scoring.; 3 public APIs
|   |   |-- rag_metrics - RAG (Retrieval-Augmented Generation) metrics tracker.; 4 public APIs
|   |   |-- trends - Trend detection for metrics over time.; 3 public APIs
|   |   `-- visualizer - ASCII chart visualizer for text-based dashboards.; 1 public APIs
|   |-- **prompts/** - TAPPS pipeline prompt content, loaded via importlib.resources.
|   |   `-- prompt_loader - Load TAPPS pipeline prompt content from package markdown files.; 5 public APIs
|   `-- **security/** - Security modules: path validation, IO guardrails, content safety, governance.; 2 public APIs
|       |-- api_keys - Secure API key handling.; 1 public APIs
|       |-- content_safety - Content safety - prompt injection detection for retrieved documentation.; 2 public APIs
|       |-- governance - Governance & safety layer.; 3 public APIs
|       |-- io_guardrails - I/O guardrails: sanitisation and prompt-injection heuristics.; 2 public APIs
|       |-- path_validator - Path validation for file operations.; 2 public APIs
|       `-- secret_scanner - Secret scanning - detect hardcoded secrets, API keys, and credentials.; 3 public APIs

`-- **tapps_mcp/** - TappsMCP: MCP server providing code quality tools.
    |-- **adaptive/** - Backward-compatible re-export — delegates to tapps_core.adaptive.
    |   |-- models - Backward-compatible re-export.
    |   |-- persistence - Backward-compatible re-export.
    |   |-- protocols - Backward-compatible re-export.
    |   |-- scoring_engine - Backward-compatible re-export.
    |   |-- scoring_wrapper - Backward-compatible re-export.
    |   |-- voting_engine - Backward-compatible re-export.
    |   `-- weight_distributor - Backward-compatible re-export.
    |-- **benchmark/** - Benchmark infrastructure for evaluating TappsMCP context file effectiveness.
    |   |-- ablation - Section ablation testing for template optimization.; 3 public APIs
    |   |-- adaptive_feedback - Adaptive weight feedback loop from benchmark measurements.; 2 public APIs
    |   |-- analyzer - Results aggregation and comparison for benchmark runs.; 1 public APIs
    |   |-- call_patterns - Call pattern analysis for MCP tool benchmarks.; 4 public APIs
    |   |-- checklist_calibrator - Data-driven checklist tier calibration.; 3 public APIs
    |   |-- cli_commands - CLI commands for the benchmark subsystem.; 3 public APIs
    |   |-- config - Benchmark configuration loading and defaults.; 2 public APIs
    |   |-- context_injector - Context injection engine for the benchmark subsystem.; 3 public APIs
    |   |-- dataset - Dataset loader for AGENTBench benchmark instances.; 4 public APIs
    |   |-- docker_runner - Docker container management for benchmark evaluation.; 3 public APIs
    |   |-- engagement_calibrator - Engagement level optimization and calibration.; 3 public APIs
    |   |-- evaluator - Benchmark evaluation orchestrator.; 2 public APIs
    |   |-- expert_tracker - Expert domain effectiveness tracking for MCP tool benchmarks.; 3 public APIs
    |   |-- failure_analyzer - Failure pattern analysis for benchmark results.; 3 public APIs
    |   |-- memory_tracker - Memory subsystem effectiveness tracking for MCP tool benchmarks.; 3 public APIs
    |   |-- mock_evaluator - Mock evaluator for benchmark testing without Docker or API access.; 2 public APIs
    |   |-- models - Pydantic v2 models for the benchmark subsystem.; 9 public APIs
    |   |-- promotion - Template promotion gate for version management.; 4 public APIs
    |   |-- redundancy - Enhanced redundancy analysis with per-section scoring and TF-IDF.; 3 public APIs
    |   |-- reporter - Persistence and reporting for benchmark results.; 2 public APIs
    |   |-- template_versions - Template version tracking with SQLite persistence.; 2 public APIs
    |   |-- tool_evaluator - Tool impact measurement and effectiveness evaluation.; 6 public APIs
    |   |-- tool_report - Dashboard integration and reporting for tool effectiveness benchmarks.; 2 public APIs
    |   `-- tool_task_models - MCPMark-inspired tool evaluation task definitions.; 4 public APIs
    |-- cli - CLI entry point for tapps-mcp.; 9 public APIs
    |-- **common/** - Common utilities shared across TappsMCP modules.
    |   |-- constants - Shared constants - re-exported from tapps_core.common.constants.
    |   |-- developer_workflow - Canonical developer workflow content: Setup, Update, Daily, and when-to-use.; 2 public APIs
    |   |-- elicitation - MCP elicitation helpers for interactive user input.; 14 public APIs
    |   |-- exceptions - Exception hierarchy - re-exported from tapps_core.common.exceptions.
    |   |-- logging - Structured logging - re-exported from tapps_core.common.logging.
    |   |-- models - Shared Pydantic v2 models - re-exported from tapps_core.common.models.
    |   |-- nudges - Next-step nudge engine - computes actionable suggestions based on session state.; 3 public APIs
    |   |-- output_schemas - Structured output schemas for MCP tool responses.; 23 public APIs
    |   |-- pipeline_models - Pipeline stage definitions - re-exported from tapps_core.common.pipeline_models.
    |   `-- utils - Shared utility functions - re-exported from tapps_core.common.utils.
    |-- **config/** - Configuration - re-exported from tapps_core.config for backward compatibility.
    |   `-- settings - TappsMCP configuration system - re-exported from tapps_core.config.settings.
    |-- diagnostics - Startup diagnostics - local-only health checks for TappsMCP subsystems.; 5 public APIs
    |-- **distribution/** - Distribution and setup utilities for TappsMCP.
    |   |-- doctor - TappsMCP doctor: diagnose configuration, rules, and connectivity.; 21 public APIs
    |   |-- exe_manager - Rename-then-replace exe upgrade for PyInstaller frozen binaries.; 4 public APIs
    |   |-- plugin_builder - Plugin package builder for Claude Code marketplace distribution.; 1 public APIs
    |   |-- rollback - Backup and rollback manager for TappsMCP upgrade operations.; 2 public APIs
    |   `-- setup_generator - One-command setup generator for TappsMCP across MCP hosts.; 2 public APIs
    |-- **experts/** - Backward-compatible re-export — expert system.
    |   |-- adaptive_domain_detector - Backward-compatible re-export.
    |   |-- confidence - Backward-compatible re-export.
    |   |-- domain_detector - Backward-compatible re-export.
    |   |-- domain_utils - Backward-compatible re-export.
    |   |-- engine - Backward-compatible re-export.
    |   |-- hot_rank - Backward-compatible re-export.
    |   |-- knowledge_freshness - Backward-compatible re-export.
    |   |-- knowledge_ingestion - Backward-compatible re-export.
    |   |-- knowledge_validator - Backward-compatible re-export.
    |   |-- models - Backward-compatible re-export.
    |   |-- rag - Backward-compatible re-export.
    |   |-- rag_chunker - Backward-compatible re-export.
    |   |-- rag_embedder - Backward-compatible re-export.
    |   |-- rag_index - Backward-compatible re-export.
    |   |-- rag_warming - Backward-compatible re-export.
    |   |-- registry - Backward-compatible re-export.
    |   |-- retrieval_eval - Backward-compatible re-export.
    |   `-- vector_rag - Backward-compatible re-export.
    |-- **gates/** - Quality gates: pass/fail evaluation, presets, enforcement.
    |   |-- evaluator - Quality gate evaluator.; 2 public APIs
    |   `-- models - Pydantic models for quality gate evaluation.; 3 public APIs
    |-- **knowledge/** - Knowledge & documentation lookup system (Epic 2).
    |   |-- cache - Backward-compatible re-export.
    |   |-- circuit_breaker - Backward-compatible re-export.
    |   |-- content_normalizer - Backward-compatible re-export.
    |   |-- context7_client - Backward-compatible re-export.
    |   |-- fuzzy_matcher - Backward-compatible re-export.
    |   |-- import_analyzer - Backward-compatible re-export.
    |   |-- library_detector - Backward-compatible re-export.
    |   |-- lookup - Backward-compatible re-export.
    |   |-- models - Backward-compatible re-export.
    |   |-- **providers/** - Backward-compatible re-export.
    |   |   |-- base - Backward-compatible re-export.
    |   |   |-- context7_provider - Backward-compatible re-export.
    |   |   |-- llms_txt_provider - Backward-compatible re-export.
    |   |   `-- registry - Backward-compatible re-export.
    |   |-- rag_safety - RAG safety - backward-compatible re-export from security.content_safety.
    |   `-- warming - Backward-compatible re-export.
    |-- **memory/** - Shared memory subsystem for persistent cross-session knowledge.
    |   |-- contradictions - Backward-compatible re-export.
    |   |-- decay - Backward-compatible re-export.
    |   |-- gc - Backward-compatible re-export.
    |   |-- injection - Backward-compatible re-export.
    |   |-- io - Backward-compatible re-export.
    |   |-- models - Backward-compatible re-export.
    |   |-- persistence - Backward-compatible re-export.
    |   |-- reinforcement - Backward-compatible re-export.
    |   |-- retrieval - Backward-compatible re-export.
    |   |-- seeding - Backward-compatible re-export.
    |   `-- store - Backward-compatible re-export.
    |-- **metrics/** - Backward-compatible re-export — delegates to tapps_core.metrics.
    |   |-- alerts - Backward-compatible re-export.
    |   |-- business_metrics - Backward-compatible re-export.
    |   |-- collector - Backward-compatible re-export.
    |   |-- confidence_metrics - Backward-compatible re-export.
    |   |-- consultation_logger - Backward-compatible re-export.
    |   |-- dashboard - Backward-compatible re-export.
    |   |-- execution_metrics - Backward-compatible re-export.
    |   |-- expert_metrics - Backward-compatible re-export.
    |   |-- expert_observability - Backward-compatible re-export.
    |   |-- feedback - Backward-compatible re-export.
    |   |-- otel_export - Backward-compatible re-export.
    |   |-- outcome_tracker - Backward-compatible re-export.
    |   |-- quality_aggregator - Backward-compatible re-export.
    |   |-- rag_metrics - Backward-compatible re-export.
    |   |-- trends - Backward-compatible re-export.
    |   `-- visualizer - Backward-compatible re-export.
    |-- **pipeline/** - TAPPS pipeline orchestration - models, handoff, and bootstrap.
    |   |-- agents_md - AGENTS.md validation and smart-merge logic for tapps_init.; 4 public APIs
    |   |-- github_ci - Enhanced GitHub Actions CI workflow generators.; 6 public APIs
    |   |-- github_copilot - GitHub Copilot agent integration generators.; 5 public APIs
    |   |-- github_governance - GitHub governance and security configuration generators.; 5 public APIs
    |   |-- github_templates - GitHub Issue forms, PR templates, and Dependabot configuration generators.; 4 public APIs
    |   |-- handoff - Render and parse TAPPS handoff markdown files.; 3 public APIs
    |   |-- init - Bootstrap TAPPS pipeline files in a consuming project.; 3 public APIs
    |   |-- models - Pipeline data models for handoff state and run log tracking.; 3 public APIs
    |   |-- platform_bundles - Plugin bundle generators, agent teams hooks, and CI workflow.; 8 public APIs
    |   |-- platform_generators - Platform-specific generators for hooks, subagents, and skills.; 31 public APIs
    |   |-- platform_hook_templates - Hook script templates and configuration for Claude Code and Cursor.
    |   |-- platform_hooks - Hook generation logic for Claude Code and Cursor.; 3 public APIs
    |   |-- platform_rules - Rule and instruction generators for Cursor, Copilot, and BugBot.; 3 public APIs
    |   |-- platform_skills - Skill definition templates for Claude Code and Cursor.; 1 public APIs
    |   |-- platform_subagents - Subagent definition templates for Claude Code and Cursor.; 1 public APIs
    |   `-- upgrade - Upgrade pipeline for refreshing TappsMCP-generated files.; 1 public APIs
    |-- **platform/** - TappsPlatform — combined MCP server composition layer.
    |   |-- cli - TappsPlatform CLI -- serve combined or individual MCP servers.; 5 public APIs
    |   `-- combined_server - Combined TappsPlatform MCP server.; 3 public APIs
    |-- **project/** - Project context, profiling, session notes, and impact analysis.
    |   |-- ast_parser - AST parser - extracts code structure from Python files.; 1 public APIs
    |   |-- coupling_metrics - Module coupling analysis based on import graphs.; 3 public APIs
    |   |-- cycle_detector - Cycle detection for Python import graphs.; 4 public APIs
    |   |-- impact_analyzer - Impact analysis - AST-based blast-radius detection for file changes.; 2 public APIs
    |   |-- import_graph - Build a Python import graph from AST analysis.; 3 public APIs
    |   |-- models - Pydantic v2 models for the project-context subsystem.; 9 public APIs
    |   |-- profiler - Project profiler - combines tech-stack, type, and environment detection.; 1 public APIs
    |   |-- report - Report generation - JSON / Markdown / HTML quality reports.; 1 public APIs
    |   |-- session_notes - Session notes - lightweight key-value store per MCP session.; 1 public APIs
    |   |-- tech_stack - Tech-stack detection - languages, libraries, frameworks, and domains.; 1 public APIs
    |   |-- type_detector - Project-type detection - detects archetype (api-service, web-app, etc.).; 1 public APIs
    |   `-- vulnerability_impact - Cross-reference vulnerability findings with import graph data.; 3 public APIs
    |-- **prompts/** - TAPPS pipeline prompt content, loaded via importlib.resources.
    |   `-- prompt_loader - Load TAPPS pipeline prompt content from package markdown files.; 2 public APIs
    |-- **scoring/** - Scoring engine: file scoring, metrics, pattern detection.
    |   |-- constants - Score constants and normalisation utilities.; 2 public APIs
    |   |-- dead_code - Dead code scoring integration.; 2 public APIs
    |   |-- dependency_security - Scoring helpers for dependency vulnerability integration.; 2 public APIs
    |   |-- models - Pydantic models for the scoring engine.; 4 public APIs
    |   |-- scorer - Main scoring engine — 7-category code quality scoring.; 1 public APIs
    |   `-- suggestions - Actionable suggestions for each scoring category.; 7 public APIs
    |-- **security/** - Security modules - re-exported from tapps_core.security for backward compatib...
    |   |-- api_keys - Secure API key handling - re-exported from tapps_core.security.api_keys.
    |   |-- content_safety - Content safety - re-exported from tapps_core.security.content_safety.
    |   |-- governance - Governance & safety layer - re-exported from tapps_core.security.governance.
    |   |-- io_guardrails - I/O guardrails - re-exported from tapps_core.security.io_guardrails.
    |   |-- path_validator - Path validation - re-exported from tapps_core.security.path_validator.
    |   |-- secret_scanner - Secret scanning - re-exported from tapps_core.security.secret_scanner.
    |   `-- security_scanner - Unified security scanner — bandit + secret detection with OWASP mapping.; 2 public APIs
    |-- server - TappsMCP MCP server entry point.; 9 public APIs
    |-- server_analysis_tools - Analysis and inspection tool handlers for TappsMCP.; 7 public APIs
    |-- server_expert_tools - Business expert management tool handlers for TappsMCP.; 2 public APIs
    |-- server_helpers - Helper functions extracted from server.py to reduce complexity and duplication.; 9 public APIs
    |-- server_memory_tools - Memory tool handlers for TappsMCP.; 2 public APIs
    |-- server_metrics_tools - Metrics, dashboard, feedback, and research tool handlers for TappsMCP.; 5 public APIs
    |-- server_pipeline_tools - Pipeline orchestration and validation tool handlers for TappsMCP.; 7 public APIs
    |-- server_resources - MCP resources and prompts for TappsMCP.; 1 public APIs
    |-- server_scoring_tools - Scoring and quality-gate tool handlers for TappsMCP.; 5 public APIs
    |-- **tools/** - External tool wrappers: subprocess utilities, ruff, mypy, bandit.
    |   |-- bandit - Bandit security scanner wrapper.; 4 public APIs
    |   |-- batch_validator - Batch validation - detect changed Python files and validate them.; 3 public APIs
    |   |-- checklist - Session-level tool call tracking for ``tapps_checklist``.; 4 public APIs
    |   |-- dependency_scan_cache - Session-level cache for dependency vulnerability scan results.; 3 public APIs
    |   |-- mypy - mypy type-checker wrapper — scoped single-file execution.; 4 public APIs
    |   |-- parallel - Parallel external-tool execution.; 2 public APIs
    |   |-- pip_audit - Dependency vulnerability scanner wrapper using pip-audit.; 3 public APIs
    |   |-- radon - Radon complexity / maintainability wrapper.; 8 public APIs
    |   |-- radon_direct - Direct radon library analysis - no subprocess required.; 3 public APIs
    |   |-- ruff - Ruff linter wrapper — check, fix, and JSON output parsing.; 6 public APIs
    |   |-- ruff_direct - Direct ruff execution - synchronous subprocess in thread pool.; 1 public APIs
    |   |-- subprocess_runner - Centralised subprocess execution.; 2 public APIs
    |   |-- subprocess_utils - Cross-platform subprocess helpers.; 2 public APIs
    |   |-- tool_detection - Detect installed external quality tools and their versions.; 2 public APIs
    |   `-- vulture - Vulture dead code detection wrapper.; 9 public APIs
    `-- **validators/** - Configuration file validators (Epic 2).
        |-- base - Base config validator and auto-detection logic.; 2 public APIs
        |-- docker_compose - Docker Compose validator — structure and best-practice checks.; 1 public APIs
        |-- dockerfile - Dockerfile validator — best-practice and security checks.; 1 public APIs
        |-- influxdb - InfluxDB validator — Flux query, connection, and data modelling checks.; 1 public APIs
        |-- mqtt - MQTT validator — connection and topic pattern checks.; 1 public APIs
        `-- websocket - WebSocket validator — connection pattern checks for Python/JS/TS code.; 1 public APIs

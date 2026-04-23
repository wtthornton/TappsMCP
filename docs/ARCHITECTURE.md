# TappsMCP Architecture Reference

Detailed internal architecture for developers working on TappsMCP itself.
For quick-start guidance, see [CLAUDE.md](../CLAUDE.md).

## Package dependency graph

```
tapps-brain (standalone library - memory system)
    ^
    |
tapps-core (shared infrastructure)
    ^              ^
    |              |
tapps-mcp      docs-mcp
(26 tools)     (32 tools)
```

**tapps-brain** is the standalone memory service extracted from tapps-core. It runs as a Dockerized PostgreSQL-backed service that tapps-mcp reaches over HTTP (default `localhost:8080`) via `BrainBridge`. Persistence engine, retrieval (BM25 + boosts), time-based decay, contradiction detection, consolidation, federation, and GC all live in the [tapps-brain repo](https://github.com/wtthornton/tapps-brain) — refer there for the authoritative description. tapps-brain has its own repository, release cycle, and test suite.

Shared infrastructure (config, security, logging, knowledge, experts, metrics, adaptive) lives in `tapps-core`. Both MCP servers depend on it. Server files in tapps-mcp import from `tapps_core` directly for extracted packages.

tapps-core's `memory/` package contains thin re-export shims delegating to tapps-brain. The one exception is `injection.py`, a bridge adapter that reads TappsMCP settings and constructs tapps-brain's `InjectionConfig`. Imports from `tapps_core.memory.*` emit a `DeprecationWarning` pointing users to `tapps_brain.*` directly.

## Server module split (tapps-mcp)

The MCP server is split across eight files (server.py + 7 modules) sharing the same `mcp` FastMCP instance created in `server.py`:

- **`server.py`** -- Creates the `FastMCP("TappsMCP")` instance and 5 core tools (`tapps_server_info`, `tapps_security_scan`, `tapps_lookup_docs`, `tapps_validate_config`, `tapps_checklist`). Imports the other modules which register their tools/resources on the shared `mcp` object.
- **`server_scoring_tools.py`** -- `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`
- **`server_pipeline_tools.py`** -- `tapps_validate_changed`, `tapps_session_start`, `tapps_init`, `tapps_set_engagement_level`, `tapps_upgrade`, `tapps_doctor`
- **`server_metrics_tools.py`** -- `tapps_dashboard`, `tapps_stats`, `tapps_feedback`, `tapps_research` (deprecated stub), `tapps_consult_expert` (deprecated stub)
- **`server_memory_tools.py`** -- `tapps_memory` (33 actions)
- **`server_analysis_tools.py`** -- `tapps_session_notes`, `tapps_impact_analysis`, `tapps_report`, `tapps_dead_code`, `tapps_dependency_scan`, `tapps_dependency_graph`
- **`server_resources.py`** -- MCP resources (knowledge, config) and prompts (pipeline, workflow)
- **`server_helpers.py`** -- Shared utilities: `emit_ctx_info()`, response builders, singleton caches

## Module map (tapps-mcp)

```
src/tapps_mcp/
├── __init__.py, cli.py, diagnostics.py, server.py, server_helpers.py, py.typed
├── server_scoring_tools.py, server_pipeline_tools.py, server_metrics_tools.py
├── server_memory_tools.py, server_analysis_tools.py, server_resources.py
├── common/     constants.py, developer_workflow.py, elicitation.py,
│               exceptions.py, logging.py, models.py, nudges.py,
│               output_schemas.py, pipeline_models.py, utils.py
├── config/     settings.py, default.yaml
├── security/   path_validator.py, io_guardrails.py, governance.py, api_keys.py,
│               secret_scanner.py, security_scanner.py, content_safety.py
├── scoring/    models.py, constants.py, scorer_base.py, scorer.py,
│               scorer_typescript.py, scorer_go.py, scorer_rust.py,
│               language_detector.py, dead_code.py, dependency_security.py,
│               suggestions.py
├── gates/      models.py, evaluator.py
├── tools/      subprocess_utils.py, subprocess_runner.py, tool_detection.py,
│               ruff.py, ruff_direct.py, mypy.py, bandit.py,
│               radon.py, radon_direct.py, parallel.py, checklist.py,
│               batch_validator.py, vulture.py, pip_audit.py,
│               dependency_scan_cache.py
├── knowledge/  models.py, cache.py, fuzzy_matcher.py, context7_client.py,
│               rag_safety.py, lookup.py, circuit_breaker.py,
│               library_detector.py, warming.py, import_analyzer.py,
│               content_normalizer.py
│   └── providers/ base.py, registry.py, context7_provider.py,
│                  llms_txt_provider.py
├── experts/    models.py, registry.py, domain_utils.py,
│               domain_detector.py, adaptive_domain_detector.py,
│               rag.py, rag_chunker.py, rag_embedder.py, rag_index.py,
│               vector_rag.py, rag_warming.py, confidence.py, engine.py,
│               hot_rank.py, retrieval_eval.py, query_expansion.py,
│               knowledge_freshness.py, knowledge_validator.py,
│               knowledge_ingestion.py,
│               business_config.py, business_knowledge.py,
│               business_loader.py, business_templates.py,
│               auto_generator.py  (tapps-core only)
│               knowledge/ (174 markdown files across 17 domains)
├── adaptive/   models.py, protocols.py, persistence.py,
│               scoring_engine.py, scoring_wrapper.py,
│               voting_engine.py, weight_distributor.py
├── metrics/    collector.py, execution_metrics.py, outcome_tracker.py,
│               expert_metrics.py, confidence_metrics.py, rag_metrics.py,
│               consultation_logger.py, expert_observability.py,
│               business_metrics.py, quality_aggregator.py,
│               alerts.py, trends.py, visualizer.py,
│               dashboard.py, otel_export.py, feedback.py
├── memory/     Re-export shims delegating to tapps-brain library.
│               injection.py is a bridge adapter (TappsMCP settings → brain config).
│               All other modules (models, persistence, store, decay, etc.)
│               are thin re-exports from tapps_brain.*
├── prompts/    prompt_loader.py, overview.md, discover.md, research.md,
│               develop.md, validate.md, verify.md, templates...
├── project/    models.py, ast_parser.py, tech_stack.py,
│               type_detector.py, profiler.py, session_notes.py,
│               impact_analyzer.py, report.py, import_graph.py,
│               cycle_detector.py, coupling_metrics.py,
│               vulnerability_impact.py
├── pipeline/   models.py, init.py, upgrade.py, handoff.py, agents_md.py,
│               platform_generators.py, platform_hooks.py,
│               platform_hook_templates.py, platform_rules.py,
│               platform_skills.py, platform_subagents.py,
│               platform_bundles.py,
│               github_templates.py, github_ci.py, github_copilot.py,
│               github_governance.py
├── distribution/ setup_generator.py, doctor.py, exe_manager.py,
│               plugin_builder.py, rollback.py
├── benchmark/  models.py, config.py, dataset.py, evaluator.py,
│               analyzer.py, reporter.py, cli_commands.py, ...
├── platform/   __init__.py, cli.py, combined_server.py
├── validators/ base.py, dockerfile.py, docker_compose.py,
│               influxdb.py, mqtt.py, websocket.py
```

## Tool registration flow

To add a new MCP tool:
1. Add the handler in the appropriate `server_*.py` file using `@mcp.tool()`
2. Call `_record_call("tool_name")` at the top of the handler (for checklist tracking)
3. Register the tool in the checklist task map (`tools/checklist.py`)
4. Add to AGENTS.md and README.md tools reference
5. Add tests in `packages/tapps-mcp/tests/unit/` and optionally `tests/integration/`

## Benchmark subsystem (Epics 30-32)

**Epic 30 -- Benchmark Infrastructure:** AGENTBench dataset loading, context injection with redundancy analysis, Docker-isolated evaluation, results aggregation with McNemar's statistical significance test, JSONL/CSV persistence.

**Epic 31 -- Template Self-Optimization:** SQLite-backed template version tracking, TF-IDF + Jaccard redundancy scoring, section ablation runner, engagement level cost-benefit calibrator, failure pattern analysis, non-regression promotion gate.

**Epic 32 -- MCP Tool Effectiveness:** 21 builtin evaluation tasks across 5 categories, ALL_MINUS_ONE evaluation methodology, call pattern analysis, data-driven checklist calibration, expert/memory effectiveness tracking, adaptive feedback.

## Dual CLI / MCP tool pattern

Several features exist as both a CLI command and an MCP tool:
- `tapps-mcp init` (CLI) -> `pipeline/init.py` <- `tapps_init` (MCP tool)
- `tapps-mcp upgrade` (CLI) -> `pipeline/upgrade.py` <- `tapps_upgrade` (MCP tool)
- `tapps-mcp doctor` (CLI) -> `distribution/doctor.py` <- `tapps_doctor` (MCP tool)
- `tapps-mcp build-plugin` (CLI-only) -> `distribution/plugin_builder.py`
- `tapps-mcp rollback` (CLI-only) -> `distribution/rollback.py`

## Caching and singletons

Five module-level caches require reset in tests (done by autouse fixture in `conftest.py`):
- **Settings**: `load_settings()` -- reset via `_reset_settings_cache()`
- **CodeScorer**: `_get_scorer()` -- reset via `_reset_scorer_cache()`
- **MemoryStore**: `_get_memory_store()` -- reset via `_reset_memory_store_cache()`
- **Tool detection**: `detect_installed_tools()` -- reset via `_reset_tools_cache()`
- **Feature flags**: `feature_flags` -- reset via `feature_flags.reset()`

## Scoring pipeline

Multi-language architecture with `ScorerBase` abstract class. Language scorers: Python (ruff, mypy, bandit, radon), TypeScript (tree-sitter/regex), Go (tree-sitter/regex), Rust (tree-sitter/regex). Quick mode runs ruff only. Missing tools produce `degraded: true` results.

## Security model

All file I/O through `security/path_validator.py` (sandboxed to `TAPPS_MCP_PROJECT_ROOT`). Secret scanning, IO guardrails, governance checks, content safety (prompt injection filtering). Subprocess calls protected by `_ALLOWED_CHECKER_PACKAGES` allowlist.

## Expert system (deprecated — EPIC-94)

The RAG-based expert consultation system was removed in EPIC-94. `tapps_consult_expert` and `tapps_research` are registered as deprecation stubs returning structured `TOOL_DEPRECATED` errors with migration guidance. The `experts/` module in tapps-core retains only the tech-stack-to-domain mapping (`rag_warming.py`) used by session start for domain hints. Knowledge files remain in the repository for reference but are no longer queried at runtime.

## Memory subsystem

Backed by **tapps-brain** — see the [tapps-brain repo](https://github.com/wtthornton/tapps-brain) for the canonical description of storage, retrieval (BM25 + boosts), time-based confidence decay, contradiction detection, and garbage collection. Per-project entry cap is controlled by tapps-brain's `TAPPS_BRAIN_MAX_ENTRIES`. tapps-core/memory/ modules are re-export shims; `injection.py` is a bridge adapter translating TappsMCP settings into brain's config.

Two deployment modes via `BrainBridge` (server_helpers.py):
- **HTTP mode** (default): Connects to tapps-brain HTTP service at `TAPPS_BRAIN_HTTP_URL` (default `http://localhost:8080`). Supports offline write-queue drain, circuit breaker with half-open recovery, graceful `BrainBridgeUnavailable` degraded payloads. Runtime version check validates installed brain meets the floor version.
- **In-process mode**: `AgentBrain` with SQLite + WAL + FTS5. Federation via central hub at `~/.tapps-mcp/memory/federated.db`. TappsMCP passes `store_dir=".tapps-mcp"` for backward compat (brain defaults to `.tapps-brain`).

`BrainBridge` exposes a unified async API regardless of mode. Stable agent identity (UUIDv4) persisted to `.tapps-mcp/agent.id` is attached to every write for cross-session traceability.

## Platform generation

Split across `pipeline/` modules: hooks, rules, skills, subagents, bundles. AGENTS.md smart-merge preserves custom sections. Three engagement levels (high/medium/low) for all templates.

## Quality gate evaluation

6 category scores + overall against thresholds. Failures sorted by weight (security 0.27 > maintainability 0.24 > complexity 0.18 > test coverage 0.13 > performance 0.08 > structure/devex 0.05). Security floor: 50.

## Hook system and MCP server lifecycle

TappsMCP generates platform-specific hooks at `tapps_init()` that run at key moments during a Claude Code or Cursor session:

- **SessionStart** (`tapps-session-start.sh`): Fires on session startup/resume. Kills stale tapps-mcp and docsmcp processes (older than 2 hours) to prevent zombie process accumulation. Claude Code spawns a new MCP server process per session but does not clean up old ones; this hook prevents resource leaks over multiple sessions.
- **PostToolUse** (after edits, file writes): Runs `tapps-post-edit.sh` for quick quality feedback.
- **Stop** (on session end): Saves session notes and memories.

Each hook is a Bash script on macOS/Linux or PowerShell on Windows (auto-detected by `tapps_init`).

## Doctor diagnostics

The `tapps_doctor` tool/CLI command runs configuration and connectivity checks:

- **Binary availability**: `tapps-mcp` on PATH (or frozen exe detection)
- **MCP client configs**: Claude Code, Cursor, VS Code (project + user scope)
- **Platform rules**: CLAUDE.md, `.cursor/rules/tapps-pipeline.md`
- **AGENTS.md**: Version parity with installed TappsMCP
- **Hooks**: Script presence, `.cursor/hooks.json` schema, Windows .sh detection. On Windows, warns if hooks are still configured as `.sh` (they should be `.ps1`)
- **Settings**: `.claude/settings.json` permissions and hook key validation
- **Quality tools**: ruff, mypy, bandit, radon installation
- **tapps-brain library**: Importability check for the memory subsystem
- **Stale exe backups**: Cleanup detection for frozen exe updates
- **Config scope**: Warns when tapps-mcp is in user-scoped `~/.claude.json`

## Config scope (Epic 47)

Default is `"project"` scope (`.mcp.json` in project root). The `doctor` command warns when tapps-mcp is in user-scope `~/.claude.json`.

## Docker Distribution (Epic 46)

Docker images and registry artifacts in `docker-mcp/`. Servers are registered as `tapps-mcp` and `docs-mcp` using direct stdio transport.

## MCP Context progress notifications (Epics 39-41)

Long-running tools use `ctx.info()` and `ctx.report_progress()`. Shared `emit_ctx_info()` helper in `server_helpers.py`. Sidecar progress files for hook-based feedback.

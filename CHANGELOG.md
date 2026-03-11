# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Memory cap** — Increased default `max_memories` from 500 to 1500 per project
- **Memory documentation** — Comprehensive 20-action reference added to AGENTS.md templates (high/medium/low), all 6 platform rules, and skill templates
- **Memory system docs** — All templates now document 4 tiers, 4 scopes, federation, consolidation, and configuration examples

### Fixed

- **Dockerfile.platform** — Fixed missing README references for docs-mcp wheel build
- **PyInstaller bundle** — Rebuilt exe to include all engagement-level template files (agents_template_medium.md, platform_cursor_medium.md, etc.)

## [1.3.0] - 2026-03-11

### Fixed

- **Claude Code settings** — Init and upgrade now write only schema-supported hook keys to `.claude/settings.json`; unsupported keys (e.g. `PostCompact`) are stripped so the file is not skipped by Claude Code. Added `SUPPORTED_CLAUDE_HOOK_KEYS` from the official schema.
- **Cursor settings** — Init and upgrade filter `.cursor/hooks.json` to only supported event keys; added `SUPPORTED_CURSOR_HOOK_KEYS` from the Cursor hooks schema. Unsupported keys are removed on merge.
- **Doctor** — `check_claude_settings` validates hook keys in `.claude/settings.json`; `check_hooks` validates `.cursor/hooks.json` keys and requires the file when Cursor hook scripts exist. Fix hints aligned (`upgrade --host claude-code` / `upgrade --host cursor`).

### Changed

- Version bump: tapps-mcp 1.2.0 → 1.3.0, docs-mcp 1.2.0 → 1.3.0.

## [1.0.0] - 2026-03-06

### Highlights

**TappsMCP reaches v1.0.0** — All 55 TappsMCP epics, 17 DocsMCP epics, and Platform epics complete. Production-ready release with:

- **48 MCP tools** (29 TappsMCP + 19 DocsMCP)
- **5,995+ tests passing**
- **Comprehensive code quality + documentation pipeline**

### Added

- **ROADMAP.md** — Forward-looking document consolidating future enhancement opportunities
- **Proposed Epics 56-58** — Non-Python Language Scoring, Adaptive Business Domain Learning, Memory Consolidation
- **Architecture Report Generator** (`docs_generate_architecture`) — Self-contained HTML report with embedded SVG diagrams

### Changed

- **EPIC_PRIORITIZATION.md** — Updated to reflect all epics complete
- **epics/README.md** — Added "Proposed Future Epics" section
- Version bump: tapps-core 1.0.4 → 1.0.5, tapps-mcp 0.8.5 → 1.0.0, docs-mcp 0.1.5 → 1.0.0

### Fixed

- **docker-publish.yml** — Use build step digest instead of meta step for cosign signing
- **MCP registry commit pins** — Updated to latest commit (a435701)

## [0.8.5] - 2026-03-05

### Fixed

- **AST complexity scoring** — `_ast_complexity` now computes per-function cyclomatic complexity (max) instead of cumulative global count; returns neutral 5.0 for unparseable files instead of 10.0 which incorrectly rewarded broken code.
- **Jaccard similarity for empty sets** — Both `context_injector.py` and `redundancy.py` now return 1.0 (identical) for two empty sets instead of 0.0.
- **TF-IDF IDF formula** — `_build_idf` in `redundancy.py` uses smoothed IDF (`log((N+1)/(count+1)) + 1.0`) to avoid producing 0.0 for single-document collections.
- **R-squared clamping** — `trends.py` clamps R-squared to `max(0.0, ...)` to prevent negative values when linear fit is poor.
- **Memory retrieval type error** — `retrieval.py` no longer calls `.isoformat()` on `updated_at` which is already a `str`.
- **Quality aggregator worst files** — `quality_aggregator.py` guard changed from `> 3` to `> 1` so small projects (1-3 files) still get worst-file analysis.
- **Branch name parsing** — `contradictions.py` uses `removeprefix("* ")` instead of `lstrip("* ")` which could mangle branch names starting with `*` or space characters.
- **Failure analyzer keyword matching** — `failure_analyzer.py` uses word-boundary regex instead of substring matching to prevent false-positive classifications (e.g., "key" matching "keyboard").
- **Completeness validator subdirectory scanning** — `completeness.py` uses `rglob("*")` instead of `iterdir()` to find docs in subdirectories like `docs/guides/`.
- **Drift detector UTC timestamps** — `drift.py` uses `gmtime` instead of `localtime` for consistent UTC ISO timestamps.

### Changed

- Version bump: tapps-core 1.0.3 → 1.0.4, tapps-mcp 0.8.4 → 0.8.5, docs-mcp 0.1.4 → 0.1.5.

## [0.8.4] - 2026-03-05

### Changed

- Version bump: tapps-core 1.0.2 → 1.0.3, tapps-mcp 0.8.3 → 0.8.4, docs-mcp 0.1.3 → 0.1.4.
- Documentation and release prep; exe build and local deploy for both MCPs.

## [0.8.1] - 2026-03-05

### Added

- **Comprehensive analysis tools API documentation** — Rewrote `docs/api/tapps-mcp-analysis_tools.md` from bare function signatures to full-featured documentation covering all 6 analysis tools: response structures, configuration options, severity levels, progress reporting (MCP context + sidecar files), vulnerability cross-referencing, degraded mode behavior, and session note promotion to memory.
- **Epic 50 planning doc** — `docs/TAPPS_MCP_REQUIREMENTS.md` for next development phase.

### Changed

- **Doctor enhancements** — Expanded diagnostic checks in `distribution/doctor.py` for improved troubleshooting.
- **Upgrade pipeline** — Updated `pipeline/upgrade.py` with additional validation.
- **AGENTS.md templates** — Updated high/medium/low engagement templates with latest tool documentation.
- Version bump: tapps-core 1.0.0 → 1.0.1, tapps-mcp 0.8.0 → 0.8.1, docs-mcp 0.1.0 → 0.1.1

## [0.8.0] - 2026-03-04

### Added

- **Epic 43: Business Expert Foundation** — YAML configuration schema (`BusinessExpertEntry`, `BusinessExpertsConfig`) for defining custom business-domain experts in `.tapps-mcp/experts.yaml`. Knowledge directory validation and scaffolding (`business_knowledge.py`). `ExpertRegistry` extended with merged access methods (`get_all_experts_merged`, `get_expert_for_domain_merged`, `is_business_domain`). Auto-loading integration via `business_loader.py` in `tapps_session_start`. Settings: `business_experts_enabled`, `business_experts_max`.
- **Epic 44: Business Expert Consultation** — Domain detection merged scoring (`detect_from_question_merged`) routes queries to both built-in and business experts using shared `_score_keywords` helper with word-boundary regex and multi-word bonus weighting. Three-tier confidence scoring (technical=1.0, business=0.9, unknown=0.7). Engine routing updated to use merged methods. Knowledge path resolution (`_resolve_knowledge_path`) supports both bundled and project-local knowledge directories. RAG warming extended for business expert knowledge. `tapps_consult_expert` response includes `is_builtin` and `expert_type` fields.
- **Epic 45: Business Expert Lifecycle** — New `tapps_manage_experts` MCP tool (29th tool) with 5 actions: list, add, remove, scaffold, validate. Atomic YAML writes via temp file + rename. `tapps_init` integration with `scaffold_experts` parameter. Business expert starter templates (`business_templates.py`). `tapps_checklist` updated with `tapps_manage_experts` entry.
- 108 new tests in tapps-core (1,377 total), 50+ new tests in tapps-mcp

### Fixed

- Pre-existing template test failures: added `RECOMMENDED:` marker to medium AGENTS.md template and `OPTIONAL:` marker to low template for engagement-level differentiation

### Changed

- `tapps_consult_expert` docstring updated to mention business experts
- `tapps_list_experts` returns both built-in and business experts via `get_all_experts_merged`
- `tapps_research` uses merged domain detection for business expert routing
- AGENTS.md templates updated with business expert documentation and tool count 28→29

## [0.7.4] - 2026-03-03

### Added

- **Epic 42: tapps_memory 2026 Enhancements** — 4 new actions (`contradictions`, `reseed`, `import`, `export`) wired into MCP tool from existing tapps-core infrastructure. Ranked BM25 search (`ranked=True` default) returns composite scores, effective_confidence, and stale flags per result. Outcome-oriented responses with `total_count`/`returned_count`, configurable `limit`, and summary truncation past threshold to avoid context-window bloat. Dispatch refactored from `**kwargs`/`globals()` to typed `_Params` dataclass + direct function reference table. `_VALID_ACTIONS` now has all 11 entries matching AGENTS.md. 21 new tests.

### Changed

- **server_memory_tools.py** — Dispatch pattern replaced with typed `_Params` frozen dataclass and direct `_DISPATCH` dict (eliminates all ANN401 lint issues). List response keys changed from `count` to `total_count`/`returned_count`. Search defaults to ranked BM25 mode.

## [0.7.3] - 2026-03-03

### Added

- **Developer workflow (Setup / Update / Daily)** — Single reference for onboarding: `common/developer_workflow.py` with `DAILY_STEPS`, `SETUP_STEPS`, `UPDATE_STEP`, and `WHEN_TO_USE`. `tapps_session_start` uses shared `quick_start` and `recommended_workflow`. `tapps_init` response now includes `developer_workflow` (setup_done, daily_steps, update_step, when_to_use). `tapps_init` generates `docs/TAPPS_WORKFLOW.md` with Setup (once), Update (after upgrading TappsMCP), Daily (5-step), and when-to-use-other-tools.

### Changed

- **Session start / init** — `quick_start` and `recommended_workflow` are sourced from `developer_workflow` for a single source of truth.

## [0.7.2] - 2026-03-03

### Added

- **Tool contract** — New "Tool contract" section in AGENTS.md templates (full and medium) stating: session start returns server info only (no project profile); `tapps_validate_changed` default = score + gate only (security when `quick=false` or `security_depth='full'`); `tapps_quick_check` has no `quick` parameter; `tapps_research` for expert + docs in one call.
- **recommended_next** — `tapps_session_start` response now includes `recommended_next` so clients that only read JSON know to call `tapps_project_profile` when project context is needed.
- **tapps_research** in checklist — `TOOL_REASONS` and workflow text now mention `tapps_research` as the single-call option for expert + docs (instead of consult_expert + lookup_docs).

### Changed

- **Tool docstrings** — Clarified `tapps_project_profile` (on-demand, not "required at session start"); `tapps_server_info` (prefer session_start); expert count 16→17; side-effect notes for `tapps_init`, `tapps_upgrade`, `tapps_set_engagement_level`, `tapps_memory`.
- **tapps_validate_changed** docstring — Explicitly states default quick mode runs score + gate only; security runs when `quick=false` or `security_depth='full'`.
- **Checklist TOOL_REASONS** — Corrected `tapps_session_start` (server info only; call project_profile when needed) and `tapps_validate_changed` (score + gate; security when quick=false or security_depth='full').
- **Platform rules** — Session Start sections (Cursor/Claude high/medium/low) no longer claim session start "detects project tech stack"; project context comes from `tapps_project_profile`.
- **AGENTS templates** — Workflow steps for validate_changed now say "score + gate" with optional security via params; "When in doubt" recommends `tapps_research` for expert + docs.

## [0.7.1] - 2026-03-03

### Fixed

- **PyInstaller exe** — Build now includes all prompt templates (agents_template_*.md, platform_*_*.md) and tapps_core prompts. Previously, `build-exe.ps1` used CLI-only PyInstaller args, producing an exe with `datas=[]`; templates were missing and `tapps-mcp upgrade` failed with "No such file or directory". Now uses `tapps_mcp.spec` with monorepo paths for full data bundling.

### Changed

- **build-exe.ps1** — Uses `PyInstaller tapps_mcp.spec` instead of CLI args so prompts and data files are bundled.
- **tapps_mcp.spec** — Updated for monorepo paths (`packages/tapps-mcp`, `packages/tapps-core`) and entry point `scripts/run_tapps_mcp.py`.

### Removed (Epic 29: Doc Provider Simplification)

- **Epic 29**: Removed `deepcon_api_key` and `docfork_api_key`. Doc lookup now uses Context7 + LlmsTxt only. Users with those keys set will have them ignored (no runtime error).

### Added (P0-P4 Tool Tier Promotions)

- `tapps_dead_code`: `scope` parameter supporting `"file"`, `"project"`, and `"changed"` modes for cross-file dead code analysis (P3)
- `tapps_checklist`: `auto_run` parameter that automatically runs missing required validations (P1)
- `tapps_research`: `file_context` parameter for inferring library from file imports (P2)
- `tapps_validate_changed`: `security_depth` parameter (`"basic"`/`"full"`) and `include_impact` parameter for blast radius analysis (P0)
- `tapps_feedback`: Tool name validation, 5-minute deduplication, and real-time scoring weight adjustment (P4)
- `tapps_stats`: Actionable `recommendations` field based on usage patterns (P4)


### Fixed (P0-P4 Tool Tier Promotions)

- `tapps_dashboard`: `time_range` parameter now actually filters underlying data instead of being label-only (P4)
- 9 pre-existing test failures (tool count, version, engagement level template assertions)

### Changed (P0-P4 Tool Tier Promotions)

- `tapps_research`: Docs are now always fetched alongside expert consultation (no longer gated on confidence threshold) (P2)
- `tapps_dead_code`: Returns `degraded` flag when vulture is not installed

### Added (Epic 13: Structured Outputs — partial, Epic 14: Dead Code — complete)

- **Structured outputs for 6 tools** — `tapps_security_scan`, `tapps_validate_changed`, and `tapps_validate_config` now return `structuredContent` alongside human-readable text. Combined with existing scoring tools (`tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`), 6 tools provide machine-parseable JSON for programmatic consumption.
- **ValidateConfigOutput model** — New `ConfigFindingOutput` and `ValidateConfigOutput` in `output_schemas.py` for `tapps_validate_config` structured responses.
- **Dead code whitelist** — `dead_code_whitelist_patterns` setting (default: `["test_*", "conftest.py"]`) filters vulture findings by file basename via fnmatch. Configurable via `TAPPS_MCP_DEAD_CODE_WHITELIST_PATTERNS` or `.tapps-mcp.yaml`.
- **Dead code whitelist tests** — `TestMatchesWhitelist` and `TestWhitelistFiltering` in `test_vulture.py`.

### Added (Performance)

- **`load_settings()` caching** — singleton cached on first no-arg call, eliminating ~20+ YAML parses and Pydantic constructions per session. `_reset_settings_cache()` for test isolation.
- **`CodeScorer` singleton** — `_get_scorer()` in `server_helpers.py` lazily initializes one `CodeScorer`, replacing 5 per-call constructions. `_reset_scorer_cache()` for test isolation.
- **`detect_installed_tools()` caching** — tool detection results (6 subprocess calls) cached for process lifetime. `_reset_tools_cache()` for test isolation and post-install re-detection.
- **`tests/conftest.py`** — autouse fixture resets all 3 caches after each test for isolation.

### Changed

- **`tapps_research` is now async** — replaced `asyncio.run()` (new event loop per call) with direct `await engine.lookup()`. Eliminates event loop creation overhead.
- **run_vulture_async** — Now accepts `whitelist_patterns: list[str] | None`; findings matching patterns are excluded.
- **run_all_tools** — Accepts `vulture_whitelist_patterns` and passes it to `run_vulture_async`.
- **CodeScorer** — Passes `settings.dead_code_whitelist_patterns` to `run_all_tools`. Uses singleton via `_get_scorer()` instead of per-call construction.
- **tapps_dead_code** — Uses `dead_code_whitelist_patterns` from settings when scanning.
- **Epic 14** — Marked complete. Epic 13 status updated: 6/8 tools wired, outputSchema not yet in tool registration.

## [0.4.4] - 2026-02-27

### Added (Epic 18: LLM Engagement Level)

- **LLM engagement level** — Control how strongly the AI is prompted to use TappsMCP tools: **high** (mandatory), **medium** (balanced, default), or **low** (optional). Set via `.tapps-mcp.yaml` (`llm_engagement_level`), `TAPPS_MCP_LLM_ENGAGEMENT_LEVEL`, or the **`tapps_set_engagement_level(level)`** MCP tool.
- **AGENTS.md and platform rules variants** — Templates `agents_template_high|medium|low.md` and `platform_{cursor|claude}_{high|medium|low}.md`; init and upgrade select by engagement level. High uses MUST/REQUIRED language; low uses optional/consider language.
- **Checklist by engagement level** — `TASK_TOOL_MAP_HIGH`, `TASK_TOOL_MAP_MEDIUM`, `TASK_TOOL_MAP_LOW` vary required vs recommended tools; `tapps_checklist` and `tapps_workflow` accept `engagement_level`.
- **Hooks and skills by engagement level** — Generated hook and skill content adjusts wording (mandatory vs optional) per level.
- **`tapps_doctor`** — Reports `llm_engagement_level` in structured output and CLI when set in project config.
- **CLI** — `tapps-mcp init --engagement-level high|medium|low` to bootstrap with a specific level.
- **Documentation** — README reorganized (GitHub-style feature tables), "LLM Engagement Level" section; CLAUDE.md engagement-level template variants; AGENTS.md and tool tables updated for `tapps_set_engagement_level` and 27 tools.

## [0.4.3] - 2026-02-25

### Changed

- **`tapps_session_start` is now lightweight** — Returns server info only (version, checkers, configuration); no project profile, dependency cache warm, or git diff. Call `tapps_project_profile` when you need project context (tech stack, type, CI/Docker/tests). Reduces cold-start latency to ~1s.

## [0.4.2] - 2026-02-25

### Removed

- **Cursor stop hook** — Removed the Cursor `stop` hook and script (tapps-stop.ps1/.sh). Validation before session end is now manual via `tapps-mcp validate-changed` or the MCP tool.

### Added

- **`tapps-mcp validate-changed` CLI** — New subcommand to run the same validation as the MCP tool from the terminal: `tapps-mcp validate-changed [--quick|--full] [--project-root PATH]`. Exits with code 1 if the gate fails.

### Changed

- **Cursor hook generation** — Init/upgrade no longer add a stop hook; existing stop scripts are removed on upgrade.
- **Pipeline rule** — `.cursor/rules/tapps-pipeline.mdc` mentions the CLI alternative for pre-completion validation.

## [0.3.0] - 2026-02-23

### Added (Epic 18: MCP Upgrade Tool & Exe Path Handling)

- **`tapps_upgrade` MCP tool** - validates and refreshes all generated files (AGENTS.md, platform rules, hooks, agents, skills, settings) from within an AI session. Uses `upgrade_mode` internally to preserve custom command paths (e.g. PyInstaller exe). Accepts `platform`, `force`, and `dry_run` parameters.
- **`tapps_doctor` MCP tool** - structured diagnostic checks (binary, MCP configs, rules, AGENTS.md, settings, hooks, quality tools) returning per-check pass/fail with remediation hints. MCP equivalent of `tapps-mcp doctor` CLI.
- **Auto-detect exe path** - `_detect_command_path()` uses `sys.frozen` for PyInstaller builds and `shutil.which` for PATH-based installs. MCP config `command` field is now set automatically instead of hardcoded.
- **`_is_valid_tapps_command()` helper** - validates command as `tapps-mcp` or path to `tapps-mcp`/`tapps-mcp.exe` for doctor and config validation.
- **`run_doctor_structured()`** - returns machine-parseable `{checks, pass_count, fail_count, all_passed}` dict for MCP consumption.

### Changed (Epic 18)

- **Non-blocking stop/task-completed hooks** - `tapps-stop.sh` and `tapps-task-completed.sh` now use `exit 0` instead of `exit 2`. Hooks still print reminders to stderr but do not block the session.
- **Command preservation during upgrade** - `_merge_config()` and `_generate_config()` accept `upgrade_mode` parameter. When `True`, existing `command` and `args` are preserved, only `env` and `instructions` are updated.
- **EXPECTED_TOOLS** updated from 24 to 26 (added `tapps_upgrade`, `tapps_doctor`).
- **Version bump** 0.2.1 -> 0.3.0.

### Changed (Performance - 2026-02-23)

- **tapps_validate_changed parallel file processing** - files are now scored concurrently via `asyncio.gather` with a semaphore (max 5 concurrent), replacing the sequential loop. Expected ~4-5x speedup on multi-file changesets.
- **tapps_validate_changed bandit deduplication** - eliminated redundant `run_security_scan()` call that re-ran bandit per file. Bandit results from `scorer.score_file()` are now reused; only `SecretScanner` runs separately for secret detection.

### Added (Init/Upgrade/Permissions - 2026-02-23)

- **`tapps-mcp upgrade` CLI command** - validates and updates all generated files (AGENTS.md, platform rules, hooks, agents, skills, `.claude/settings.json`) after upgrading TappsMCP.
- **Dual permission entries** - `_bootstrap_claude_settings()` now adds both `mcp__tapps-mcp` (bare server match, reliable) and `mcp__tapps-mcp__*` (wildcard, Claude Code 2.0.70+) to work around known Claude Code permission bugs (#3107, #13077, #27139).
- **AGENTS.md troubleshooting section** - new "Troubleshooting: MCP tool permissions" section with permission fix instructions and fallback guidance.
- **Doctor checks** - `check_agents_md()`, `check_claude_settings()` (validates both permission entries), `check_hooks()` for comprehensive diagnostics.
- **Tool fallback guidance** - `tapps_validate_changed` and `tapps_quality_gate` docstrings now include fallback instructions when the tool is rejected.
- **AGENTS.md smart-merge** - `_bootstrap_claude()` overwrite bug fixed (was duplicating TAPPS content instead of replacing).
- **Template version injection** - `load_agents_template()` dynamically prepends version marker instead of hardcoding.

### Changed (Init/Upgrade/Permissions - 2026-02-23)

- EXPECTED_TOOLS updated from 17 to 21 (added `tapps_session_start`, `tapps_quick_check`, `tapps_validate_changed`, `tapps_research`).
- EXPECTED_SECTIONS updated from 5 to 8 (added `tapps_session_start vs tapps_init`, `Platform hooks and automation`, `Troubleshooting: MCP tool permissions`).
- agents_template.md rewritten to match production AGENTS.md (99 lines to 217 lines).
- Platform rules (platform_claude.md, platform_cursor.md) now reference `tapps_workflow` MCP prompt correctly.
- Handoff and runlog templates updated with `tapps_session_start` and `tapps_validate_changed`.

### Removed (Documentation Cleanup - 2026-02-23)

- Deleted 7 completed planning/task docs from `docs/`: CLARITY_RECOMMENDATIONS.md, COVERAGE_METRICS_IMPLEMENTATION_TASK.md, FEEDBACK_ISSUES_PLAN.md, REVIEW_TRACKING.md, CRITICAL_HIGH_REVIEW_PLAN.md, IMPLEMENTATION_PLAN_CRITICAL_HIGH_MEDIUM.md, SELF_REVIEW_FINDINGS.md.
- Deleted 18 completed Epic 12 story files from `docs/planning/epics/EPIC-12-PLATFORM-INTEGRATION/stories/` (research/ and README retained for architectural context).

### Added (Implementation Plan Execution - 2026-02-22)

- **Docker Compose explicit networks** — `docker-compose.yml` now defines `tapps-network` and assigns the `tapps-mcp` service to it.
- **Expert RAG relevance threshold** — `SimpleKnowledgeBase` and `VectorKnowledgeBase` filter chunks below `relevance_threshold` (default 0.2/0.3); reduces irrelevant expert consultation results.
- **MCP-specific knowledge** — New `testing/mcp-testing-patterns.md` and `software-architecture/mcp-server-architecture.md` for improved RAG relevance on MCP architecture/testing questions.
- **tapps_lookup_docs expert fallback** — When Context7 and cache fail, returns expert knowledge base content as `expert_fallback` so users get useful guidance without API key.
- **tapps_lookup_docs error improvement** — No-API-key error now suggests `tapps_init` with `warm_cache_from_tech_stack=True` as alternative.
- **tapps_report max_files and parallel scoring** — New `max_files` parameter (default 20); project-wide report uses `asyncio.gather` for parallel file scoring.

### Changed (Implementation Plan Execution — 2026-02-22)

- **adaptive/persistence.py** — Extracted `_parse_consultation_line` and `_passes_consultation_filter`; reduced cyclomatic complexity.
- **adaptive/voting_engine.py** — Extracted `_normalize_domain_column` and `_enforce_primary_floor`; simplified `_normalize_matrix`.
- **Adaptive min_outcomes** — Lowered from 10 to 5 so adaptive weights activate sooner (scoring_engine, settings, default.yaml).
- **bootstrap_pipeline** — Accepts optional `config: BootstrapConfig` to reduce parameter branching; kwargs still supported.

### Added (Critical/High Review — 2026-02-22)

- **Checklist persistence** — `CallTracker` now persists call records to `.tapps-mcp/sessions/checklist_calls.jsonl`; `set_persist_path` is invoked on first tool call so state survives server restarts.
- **Expert RAG error surfacing** — `tapps_init` appends expert RAG `failed_domains` to `errors` so `success` reflects subsystem failure.
- **Dry-run for init** — `tapps_init` (MCP tool) and `tapps-mcp init` (CLI) support `dry_run` / `--dry-run` to preview what would be created without writing.
- **Feedback → AdaptiveScoringEngine** — `AdaptiveScoringEngine` accepts optional `metrics_dir`; when provided, feedback records from `tapps_feedback` are merged so negative feedback influences weight recalibration.

### Added (Epic 12: Platform Integration — Tiers 1-4, Complete)

- **Claude Code hooks generation** — 7 hook scripts in `.claude/hooks/`: session start, session compact, post-edit, stop (exit 2 blocks until validated), task-completed (exit 2 blocks premature completion), pre-compact (context backup), subagent-start. Deep-merges into `.claude/settings.json` preserving existing entries.
- **Cursor hooks generation** — 3 hook scripts in `.cursor/hooks/`: before-MCP-execution (logging), after-file-edit (fire-and-forget reminder), stop (followup_message JSON). Merges into `.cursor/hooks.json`.
- **Subagent definitions** — 3 agents per platform (tapps-reviewer, tapps-researcher, tapps-validator) with platform-specific frontmatter: Claude Code uses comma-separated tools/permissionMode/memory; Cursor uses YAML array tools/readonly.
- **Skills generation** — 3 SKILL.md files per platform (tapps-score, tapps-gate, tapps-validate) with platform-specific tool references: Claude Code uses `mcp__tapps-mcp__` prefixed names; Cursor uses short names.
- **Cursor rule types** — 3 distinct `.mdc` rule files: `tapps-pipeline.mdc` (alwaysApply), `tapps-python-quality.mdc` (autoAttach via `globs: "*.py"`), `tapps-expert-consultation.mdc` (agentRequested via description). Reduces context bloat by targeting rules to relevant moments.
- **Claude Code plugin bundle** — `generate_claude_plugin_bundle()` creates complete plugin directory with `.claude-plugin/plugin.json`, agents, skills, hooks, `.mcp.json`, README.
- **Cursor plugin bundle** — `generate_cursor_plugin_bundle()` creates complete plugin directory with `.cursor-plugin/plugin.json` (7 required fields), agents, skills, hooks, rules, `mcp.json`, logo.png, README, LICENSE.
- **Agent Teams integration** — Optional `agent_teams=True` flag on `tapps_init` generates TeammateIdle and TaskCompleted hooks for quality watchdog teammate pattern. CLAUDE.md template now documents `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` workflow.
- **New module `pipeline/platform_generators.py`** — Centralizes all platform artifact generation (hooks, agents, skills, rules, plugins) separate from `init.py`. Used by both `tapps_init` (MCP tool) and `tapps-mcp init` (CLI).
- **VS Code / Copilot instructions** — `generate_copilot_instructions()` creates `.github/copilot-instructions.md` with TappsMCP tool guidance, workflow steps, and scoring categories for GitHub Copilot in VS Code.
- **Cursor BugBot rules** — `generate_bugbot_rules()` creates `.cursor/BUGBOT.md` with quality standards, security requirements, style rules, and testing requirements for automated PR review.
- **MCP elicitation support** — `tapps_quality_gate` and `tapps_init` now accept an optional MCP `Context` parameter. When `preset` is empty, quality gate prompts the user via elicitation; `tapps_init` asks for confirmation before writing files. Gracefully degrades on unsupported clients.
- **CI/Headless documentation** — `generate_ci_workflow()` creates `.github/workflows/tapps-quality.yml` GitHub Actions workflow. CLAUDE.md template now includes CI Integration section covering headless mode, `--init-only`, and `enableAllProjectMcpServers`.
- **Cursor marketplace plugin** — Complete `plugin/cursor/` directory with `marketplace.json`, `.cursor-plugin/plugin.json`, skills, agents, hooks, rules, mcp.json, logo, CHANGELOG, README with install deep link.
- **Agent SDK examples** — `examples/agent-sdk/` with Python and TypeScript examples for basic quality check, CI pipeline, and subagent registration via Claude Agent SDK.
- **Validation script** — `scripts/validate-cursor-plugin.sh` for CI validation of Cursor plugin manifest and required files.

**Upgrade path for consuming projects:** After upgrading TappsMCP, run `tapps_init` with `platform="claude"` (or `"cursor"`) and `overwrite_platform_rules=True` to generate hooks, agents, skills, and enhanced rules. Use `agent_teams=True` for Agent Teams support.

---

## [0.2.1] - 2026-02-21

### Added (Epic 10: Expert + Context7 Integration)

- **Expert + doc lookup coupling** — Workflow guidance for combining `tapps_consult_expert` with `tapps_lookup_docs` for testing/library questions (AGENTS.md, recommended_workflow)
- **Structured hints when RAG is empty** — `suggested_tool`, `suggested_library`, `suggested_topic` in `tapps_consult_expert` response for machine-parseable follow-up
- **Auto-fallback to Context7** — When expert RAG returns no chunks, automatically calls lookup_docs and merges content (configurable via `expert_auto_fallback` and `expert_fallback_max_chars` settings)
- **Broader testing-strategies KB** — Knowledge on test config, base URLs, env vars, fixtures, monkeypatch (`test-configuration-and-urls.md`)
- **`tapps_research` tool** — Single tool combining expert consultation + Context7 documentation in one call

### Added (Epic 11: Retrieval Optimization)

- **Hybrid fusion + rerank** — `VectorKnowledgeBase._hybrid_fuse()` combines vector and keyword results with weighted scoring and structural bonus
- **Hot-rank adaptive ranking** — `compute_hot_rank()` uses recency decay, helpfulness, confidence trend, and exploration bonus to prioritize domains
- **Fuzzy matcher v2** — Multi-signal matching (LCS + edit distance + token overlap + alias + prefix + confidence bands + "did you mean" + manifest priors)
- **Context7 code-reference normalization** — Snippet extraction, ranking, deduplication, reference cards, and token budgets (`content_normalizer.py`)
- **Retrieval evaluation harness** — 10 benchmark queries across 8 domains with quality gates (pass rate, latency, keyword coverage)

**Upgrade path for consuming projects:** After upgrading TappsMCP, run `tapps_init` with `overwrite_agents_md=True` and `overwrite_platform_rules=True` to refresh AGENTS.md and pipeline rules. See [docs/INIT_AND_UPGRADE_FEATURE_LIST.md](docs/INIT_AND_UPGRADE_FEATURE_LIST.md).

---

## [0.2.0] - 2026-02-10

### Added
- **Direct scoring mode** (`tapps_score_file(mode="direct")`) bypasses async subprocess entirely for radon, using `radon.complexity` and `radon.metrics` as Python libraries in-process
- `tools/radon_direct.py` - pure library analysis via `cc_direct()` and `mi_direct()`, zero subprocess calls
- `tools/ruff_direct.py` - synchronous `subprocess.run` in `asyncio.to_thread` for reliable ruff execution in MCP async contexts
- `mode` parameter on `tapps_score_file` tool (`"subprocess"`, `"direct"`, or `"auto"`)
- `mode` parameter on `run_all_tools` in parallel executor
- 28 new unit tests for direct mode (radon_direct, ruff_direct, parallel)
- Radon subprocess fallback with diagnostic logging (Story 9.1)
- Test coverage fuzzy glob matching (`test_*{stem}*.py`) with graduated scoring (Story 9.2)
- Blended complexity formula (`0.7 * max_cc + 0.3 * avg_cc`) replacing max-only (Story 9.3)
- Per-tool error details in `tool_errors` dict with human-readable reasons (Story 9.4)
- Actionable suggestions per scoring category with specific function names and thresholds (Story 9.6)

### Changed
- `tapps_score_file` default mode is `"auto"` (subprocess with direct fallback)
- `ParallelResults` now includes `tool_errors: dict[str, str]` for per-tool failure diagnosis
- `ScoreResult` now includes `tool_errors` field surfaced in MCP responses
- Complexity score uses blended max/avg CC instead of max-only
- Test coverage heuristic upgraded from exact-match-only to three-tier (exact, fuzzy, none)
- `tapps_quality_gate` response includes suggestions for failing categories

## [0.1.1] - 2026-02-09

### Fixed
- Path traversal prevention in MCP resource handler (regex whitelist + resolve boundary check)
- Thread safety for `CallTracker` shared state in checklist module
- Thread safety for singleton patterns (circuit breaker, vector RAG, session notes)
- `asyncio.CancelledError` propagation in circuit breaker (no longer swallowed by generic except)
- PII detection now flags single SSN occurrences (was requiring 2+)
- Credential redaction handles multi-group regex patterns correctly
- Negative variance guard in Pearson correlation (floating-point safety)
- Silent exception logging upgraded from debug to warning in report generation
- Shell injection prevention in npm wrapper (`shell: false` on non-Windows)
- TOCTOU race condition removed from symlink check in path validator
- Unreachable `except BaseException` narrowed to `except OSError` in session notes
- Async subprocess runner catches `OSError` alongside `FileNotFoundError`
- Lookup engine properly awaits cancelled background tasks on shutdown

### Added
- `SECURITY.md` with vulnerability reporting process, response timeline, and scope
- `LICENSE` file (MIT)
- JSONL rotation (`rotate()`) for outcome tracker and expert metrics
- Overall safety timeout on `asyncio.gather` in parallel tool execution
- Docker OCI vendor label and writable state volume
- CI concurrency group with cancel-in-progress
- Error handler for npm wrapper child process spawn failures

### Changed
- `format` parameter renamed to `output_format` in `tapps_dashboard` to avoid shadowing builtin
- Tool enumeration catch narrowed from `Exception` to `AttributeError` with full fallback list
- RAG safety regex improved: `role_manipulation` pattern accepts "an" article; added `malicious`/`jailbroken` keywords
- Cache hit counter update moved inside file lock for atomicity

## [0.1.0] - 2026-02-09

### Added
- Initial release of TappsMCP
- Code scoring across 7 quality categories (complexity, security, maintainability, test coverage, performance, structure, devex)
- Security scanning with Bandit integration and secret detection
- Quality gates with configurable presets (standard, strict, framework)
- Documentation lookup via Context7 with fuzzy matching and local cache
- Config validation for Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
- 16 domain experts with RAG-backed answers and confidence scoring
- Project profiling: tech stack detection, type classification
- Session notes for persisting decisions across AI sessions
- Impact analysis via AST-based import graph
- Quality reports in JSON, Markdown, and HTML
- Adaptive scoring and expert weight adjustment
- TAPPS 5-stage pipeline orchestration (discover, research, develop, validate, verify)
- Metrics dashboard with execution tracking, alerts, and trends
- User feedback collection for continuous improvement
- Path safety: all file operations restricted to configurable project root
- Docker support with Streamable HTTP transport
- CI/CD with GitHub Actions (Windows, Linux, macOS x Python 3.12, 3.13)

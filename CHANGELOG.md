# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

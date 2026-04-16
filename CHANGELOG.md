# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.8.0] - 2026-04-16

### Fixed

- **Hive init error messaging** — `tapps_session_start`'s `hive_status` previously returned a generic `"Hive singleton initialization failed"` that masked three distinct causes: missing `TAPPS_BRAIN_DATABASE_URL`, unsupported DSN scheme, or a `create_hive_backend` exception that was being silently swallowed by `contextlib.suppress(Exception)`. `_ensure_hive_singletons` now surfaces an actionable reason for each case (naming the env var, the scheme, or the underlying exception), and caches backend-init failures so we don't retry a known-broken DSN on every call. ([packages/tapps-mcp/src/tapps_mcp/server_helpers.py](packages/tapps-mcp/src/tapps_mcp/server_helpers.py))

### Changed

- **Removed stale `propagation_config` field** from `hive_status` responses — the payload asserted tapps-brain didn't expose profile-sourced tier rules (`auto_propagate_tiers` / `private_tiers`) and framed that as a client-side gap. It is not a gap: tapps-brain's `PropagationEngine` enforces tier rules server-side on every `hive_propagate` / `hive_push` call; mirroring the rules client-side would have been two-sources-of-truth drift. Clients read propagation outcomes from `hive_propagate` / `hive_push` responses instead. Removes `propagation_config` from `tapps_session_start.hive_status` and `tapps_memory(action="hive_status")`. Deletes `_hive_propagation_config_payload`.

### Added

- **`memory.project_id` setting** (EPIC-069 / ADR-010) — new `TAPPS_MCP_MEMORY_PROJECT_ID` setting on `MemoryConfig`. When set, `create_brain_bridge` exports it to `TAPPS_BRAIN_PROJECT` before constructing `AgentBrain`, so tapps-brain's multi-tenant project registry (v3.5.0+) resolves to the registered slug instead of falling back to `derive_project_id(project_dir)` per-directory hash. Register with `tapps-brain project register` first.
- **Postgres pool-tuning pass-through** (tapps-brain v3.7.0 knobs) — new `memory.pg_pool_max_waiting` and `memory.pg_pool_max_lifetime_seconds` settings. When non-zero, exported as `TAPPS_BRAIN_PG_POOL_MAX_WAITING` / `TAPPS_BRAIN_PG_POOL_MAX_LIFETIME_SECONDS` so the Postgres connection-pool queue depth and connection lifetime can be tuned from `.tapps-mcp.yaml` without forking the brain config. Zero leaves operator-provided env values untouched.
- **tapps-brain pin floor → 3.7.2** — bumped `tapps-core` dependency from `>=3.7.0,<4` to [`>=3.7.2,<4`](https://github.com/wtthornton/tapps-brain/releases/tag/v3.7.2). 3.7.1 fixed a `RuntimeError: Task group is not initialized` crash in the MCP streamable-HTTP `/mcp` transport lifespan ordering and a 404 bug in `TappsBrainClient`/`AsyncTappsBrainClient` against unimplemented `/v1/tools/*` REST routes. 3.7.2 fixed the client path (`/mcp` → `/mcp/mcp`) since FastMCP's mounted sub-app serves at the nested path. Not load-bearing for tapps-mcp today (in-process `AgentBrain` via `BrainBridge`, not the HTTP network client), but any future migration to remote brain-as-a-service now gets a working client.

- Version bump: tapps-core 2.7.3 → 2.8.0, tapps-mcp 2.7.3 → 2.8.0, docs-mcp 2.7.3 → 2.8.0

## [2.7.3] - 2026-04-14

### Changed

- **Actionable error envelope** (STORY-101.4, EPIC-101) — `error_response` now auto-injects `category`, `retryable`, and `remediation` fields derived from a code registry in `server_helpers.py`. Categories: `user_input`, `environment`, `timeout`, `deprecated`, `unsupported`, `internal` (fallback). Known codes covered today: `path_denied`, `file_error`, `missing_params`, `invalid_library`, `unsupported_language`, `scoring_failed`, `TOOL_DEPRECATED`, `timeout`. Caller-supplied `extra` still wins on key collision, so existing overrides (e.g. deprecation `alternatives`) keep working. Lets agents branch on `retryable` / `category` instead of parsing free-form messages.
- Version bump: tapps-core 2.7.2 → 2.7.3, tapps-mcp 2.7.2 → 2.7.3, docs-mcp 2.7.2 → 2.7.3

## [2.7.2] - 2026-04-14

### Changed

- **Safer `tapps_validate_changed` auto-detect** (STORY-101.3, EPIC-101) — when `file_paths=""` the tool now enforces a 30s wall-clock budget (configurable via `_AUTO_DETECT_BUDGET_S`). On expiry it returns a partial-result envelope with `timed_out: true`, a `files_remaining` count, a `files_remaining_paths` list, and a copy-paste `next_steps` hint directing the agent to re-invoke with explicit paths. Content-hash cache (STORY-101.1, `KIND_QUICK_CHECK`) is consulted per file first — cache hits are reported with `cache_hit: true` and never consume the budget. Explicit `file_paths` mode is unchanged and ignores the cap.
- Version bump: tapps-core 2.7.1 → 2.7.2, tapps-mcp 2.7.1 → 2.7.2, docs-mcp 2.7.1 → 2.7.2

## [2.7.1] - 2026-04-14

### Added

- **SHA-256 content-hash cache** (STORY-101.1, EPIC-101) — new `tapps_mcp.tools.content_hash_cache` module providing a per-process LRU-ish cache keyed on `(kind, sha256(file_bytes))`. Path-independent: renaming or copying a file hits the cache. Bounded (2000 entries, FIFO eviction), with 1h default TTL, and hit/miss/set/eviction telemetry. First real consumer: `tapps_quick_check` single-file mode now serves cached results with `cache_hit: true` when the file's bytes haven't changed, and populates the cache on miss. `fix=True` bypasses the cache since it mutates the file.

### Changed

- Version bump: tapps-core 2.7.0 → 2.7.1, tapps-mcp 2.7.0 → 2.7.1, docs-mcp 2.7.0 → 2.7.1

## [2.7.0] - 2026-04-14

### Added

- **`tapps_pipeline` one-call orchestrator** (STORY-101.2, EPIC-101) — new MCP tool that collapses the recommended `session_start → quick_check → validate_changed → checklist` loop into a single call. Takes comma-separated `file_paths` and `task_type`; returns a unified envelope with a `stages` array (name / success / elapsed_ms / summary per stage) and a top-level `pipeline_passed`. Short-circuits `validate_changed` on security-floor failure (no point re-running gates when security is below 50). Added to `ALL_TOOL_NAMES` and `TOOL_PRESET_CORE`.

### Changed

- Version bump: tapps-core 2.6.3 → 2.7.0, tapps-mcp 2.6.3 → 2.7.0, docs-mcp 2.6.3 → 2.7.0

## [2.6.3] - 2026-04-14

### Added

- **C4 Mermaid role styling** (STORY-100.4) — `c4_context`, `c4_container`, and `c4_component` Mermaid renderers now emit `UpdateElementStyle(element, $bgColor=..., $fontColor=..., $borderColor=...)` per element, colored by semantic role. Containers and components are classified by package name; context actors map by kind (Person→presentation, Database→data, ExternalAPI→infra, system→business). ER diagram still deferred — Mermaid `erDiagram` has no styling directive and requires either a PlantUML-side render or a rewrite to `classDiagram`.

### Changed

- Version bump: tapps-core 2.6.2 → 2.6.3, tapps-mcp 2.6.2 → 2.6.3, docs-mcp 2.6.2 → 2.6.3

## [2.6.2] - 2026-04-14

### Added

- **`pattern_card` auto-embedded in comprehensive READMEs** (STORY-100.5) — `docs_generate_readme(style="comprehensive")` now prepends the archetype poster to the Architecture section. Renders as a fenced Mermaid block with the classified archetype, confidence, top packages colored by semantic role, and legend. Degrades silently for projects the classifier can't label (empty tree / no packages).

### Changed

- Version bump: tapps-core 2.6.1 → 2.6.2, tapps-mcp 2.6.1 → 2.6.2, docs-mcp 2.6.1 → 2.6.2

## [2.6.1] - 2026-04-14

### Added

- **Role palette applied across Mermaid renderers** (STORY-100.2) — `dependency`, `module_map`, and `class_hierarchy` Mermaid output now tag each node with `:::presentation|:::business|:::data|:::infra` and emit the shared `classDef` block, so every `docs_generate_diagram` visual reads with the same semantic coloring as `pattern_card`. ER and C4 renderers use their own DSLs (`erDiagram`, `C4Context`) that do not accept Mermaid `classDef`; those receive dedicated treatment in a future slice.

### Changed

- Version bump: tapps-core 2.6.0 → 2.6.1, tapps-mcp 2.6.0 → 2.6.1, docs-mcp 2.6.0 → 2.6.1

## [2.6.0] - 2026-04-14

### Added

- **`pattern_card` diagram type** (docs-mcp) — new value for `docs_generate_diagram(diagram_type="pattern_card")` renders a single-page archetype poster: header with the classified archetype and confidence, top packages colored by semantic role (presentation / business / data / infra), and a legend. README-embeddable (≤ 8 nodes, fits one screen). Calls `PatternClassifier().classify()` under the hood and surfaces evidence in the header. Deterministic, no LLM, no network (STORY-100.3, EPIC-100).
- **Shared role palette** — `_ROLE_COLORS` and `_ROLE_KEYWORDS` constants in `docs_mcp.generators.diagrams` establish the fixed four-role semantic palette that STORY-100.2 will apply across the other 7 diagram types.

### Changed

- Version bump: tapps-core 2.5.0 → 2.6.0, tapps-mcp 2.5.0 → 2.6.0, docs-mcp 2.5.0 → 2.6.0

## [2.5.0] - 2026-04-14

### Added

- **Architectural pattern classifier** (docs-mcp) — new `docs_mcp.analyzers.pattern.PatternClassifier` deterministically labels a project as `layered`, `hexagonal`, `microservice`, `event_driven`, `pipeline`, `monolith`, or `unknown`. Returns `ArchetypeResult(archetype, confidence, evidence, alternatives)` with citation evidence per verdict. No LLM, no network. Foundation for poster-style diagrams (EPIC-100, STORY-100.1).
- **Planning: EPIC-100 Architecture Pattern Recognition & Poster Diagrams** — 7-story plan to add archetype-aware, semantic-colored, one-page "poster" diagrams. Inspired by the Amigoscode software-architectural-patterns infographic.
- **Planning: EPIC-101 Zero-Friction Quality Pipeline** — 7-story plan to collapse the 26 tapps-mcp tools into a frictionless edit → check → validate → done loop via a shared content-hash cache, a `tapps_pipeline` orchestrator, top-1 nudges, and skipped-step telemetry.
- **Planning: EPIC-102 Unified Brain & Cross-Project Intelligence** — 7-story plan to make tapps-brain the shared substrate both tapps-mcp and docs-mcp read and write, with auto-recall hooks and a unified insight schema.
- **Flagship stories** — STORY-100.1 (SHIPPED), STORY-101.2 (pipeline orchestrator), STORY-102.3 (auto-recall hook) with Gherkin acceptance criteria.

### Changed

- Version bump: tapps-core 2.4.0 → 2.5.0, tapps-mcp 2.4.0 → 2.5.0, docs-mcp 2.4.0 → 2.5.0

## [2.4.0] - 2026-04-08

### Added

- **Halstead metrics integration** — radon's Halstead analysis (volume, difficulty, effort, predicted bugs) now feeds the performance scoring category, providing per-function complexity signals beyond cyclomatic complexity. Uses existing radon dependency with dual-mode execution (subprocess + direct library fallback).
- **Perflint anti-pattern detection** — new optional pylint plugin integration catches 11 concrete performance anti-patterns: loop-invariant statements, unnecessary list casts, incorrect dictionary iterators, dotted imports in loops, global variable usage in loops, and more. Findings are capped at 3.0 penalty to prevent overwhelming the score.
- **`perf` optional dependency group** — `pip install tapps-mcp[perf]` adds pylint + perflint for full performance scoring.
- **`perflint` feature flag** — `tapps_core.config.feature_flags.perflint` detects perflint availability.
- **Pylint tool detection** — `tapps_doctor` and `tapps_session_start` now probe for pylint and report its availability alongside other checkers.
- **13 new performance penalty entries** — `PERFORMANCE_PENALTY_MAP` extended with Halstead thresholds (`halstead_high_volume`, `halstead_very_high_volume`, `halstead_high_difficulty`, `halstead_high_effort`, `halstead_high_bugs`) and perflint labels (`perflint_loop_invariant`, `perflint_dotted_import_in_loop`, `perflint_unnecessary_list_cast`, `perflint_incorrect_dict_iterator`, `perflint_loop_global_usage`, `perflint_memoryview_over_bytes`, `perflint_use_tuple_over_list`, `perflint_use_comprehension`).
- **13 new actionable suggestions** — context-specific improvement guidance for each new issue type.

### Changed

- **Performance scoring uses three signals** — `_score_performance_category` now combines AST heuristics + Halstead metrics + perflint findings (all additive, clamped to 0-10). Details include source breakdown: `ast_issues`, `halstead_issues`, `perflint_issues`.
- **`ParallelResults` extended** — new `radon_hal` and `perflint` fields for Halstead and perflint data.
- **`run_all_tools()` extended** — new `run_perflint` parameter; Halstead task added alongside existing radon CC/MI tasks.
- Version bump: tapps-core 2.3.0 → 2.4.0, tapps-mcp 2.3.0 → 2.4.0, docs-mcp 2.3.0 → 2.4.0

## [2.3.0] - 2026-04-08

### Fixed

- **Documentation accuracy audit** — corrected tool counts across all user-facing docs: TappsMCP has **26 tools** (not 30), total platform is **58 tools** (not 62). Affected files: README.md, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, ARCHITECTURE.md, ONBOARDING.md, TECH_STACK.md, docker readme, .ralph/AGENT.md, and all AGENTS.md templates (high/medium/low).
- **Ghost tool references removed** — removed `tapps_project_profile`, `tapps_manage_experts`, and `tapps_get_canonical_persona` from README tools reference (not registered as MCP tools).
- **Ghost server files removed from ARCHITECTURE.md** — removed references to non-existent `server_expert_tools.py` and `server_persona_tools.py`; corrected server module count from "10 files" to "8 files".
- **Test counts corrected** — README badge and text updated to reflect actual counts: tapps-core 960+, tapps-mcp 3,790+, docs-mcp 2,170+ (6,900+ total).
- **Git clone URL fixed** — CONTRIBUTING.md and ONBOARDING.md now use correct `github.com/wtthornton/TappsMCP.git` (was `tapps-mcp/tapps-mcp.git`) and correct `cd tapps-mcp` (was `cd TappMCP`).
- **Duplicate feature row removed** — "Documentation lookup" appeared twice in README Knowledge & context table.
- **Broken links fixed** — ONBOARDING.md no longer links to non-existent `api/` and `diagrams/` directories.

### Changed

- Version bump: tapps-core 2.2.0 → 2.3.0, tapps-mcp 2.2.0 → 2.3.0, docs-mcp 2.2.0 → 2.3.0

## [2.2.0] - 2026-04-08

### Fixed

- **tapps-mcp: `tapps_consult_expert` deprecation stub (#82)** — The tool was removed in EPIC-94 but no MCP stub was registered, causing unhandled `ImportError` for callers. Now returns a structured `TOOL_DEPRECATED` error with alternatives and `deprecated_since` metadata.
- **tapps-mcp: `tapps_research` opaque error (#83)** — Improved error code from generic `DEPRECATED` to `TOOL_DEPRECATED` with structured `alternatives` array and `deprecated_since` field for machine-readable deprecation context.
- **docs-mcp: `docs_check_style` silent 0-file false positive (#84)** — When explicitly-requested files could not be resolved, the tool silently returned `aggregate_score: 100` with `total_files: 0`. Now returns `NO_FILES_FOUND` error when all files are missing, adds `warnings` for partial matches, and reports `aggregate_score: 0.0` (not 100) for zero files.

### Changed

- **tapps-mcp + docs-mcp: `error_response()` enhanced** — Added optional `extra` keyword parameter for structured error metadata (e.g. `alternatives`, `deprecated_since`, `requested_files`). Backward compatible — existing callers are unaffected.
- **tapps-mcp: `ALL_TOOL_NAMES` updated** — Now includes `tapps_consult_expert` and `tapps_research` as registered deprecated stubs (26 total, including 2 deprecated).
- **tapps-core: Pipeline stage cleanup** — Removed stale `tapps_consult_expert` and `tapps_list_experts` from `PipelineStage.RESEARCH` in `pipeline_models.py`.

### Removed

- **docs-mcp: Dead expert enrichment code** — Removed ~100 lines of unreachable code in `epics.py` and `stories.py` `_enrich_experts()` methods (dead since EPIC-94). Methods retained as documented no-ops for pipeline interface compatibility.
- **tapps-mcp: Stale `tapps_consult_expert` reference** — Removed from `developer_workflow.py` `WHEN_TO_USE` list.

### Added

- **Tests:** 18 new tests across 4 files covering deprecation stubs, error_response extra metadata, path validation, and no-op enrichment methods.
- Version bump: tapps-core 2.1.0 → 2.2.0, tapps-mcp 2.1.0 → 2.2.0, docs-mcp 2.1.0 → 2.2.0

## [1.18.0] - 2026-04-06

### Fixed

- **tapps-mcp: Context-aware install hints (#80.1)** — When running in a uv tool venv, checker install hints now say `uv tool install tapps-mcp --with bandit` instead of the incorrect `pip install bandit`. Detects uv environment via `uv-receipt.toml` in `sys.prefix`.
- **tapps-mcp: docs-mcp init path placeholder (#79 sub-issue)** — `--with-docs-mcp` now uses the same `uv run` launch pattern as the tapps-mcp entry for consumer uv projects, instead of falling back to an unresolved `<PATH_TO_TAPPS_MCP_MONOREPO_ROOT>` placeholder.

### Added

- **tapps-mcp: `--with-context7` init flag (#79)** — New `tapps-mcp init --with-context7 KEY` option writes `${TAPPS_MCP_CONTEXT7_API_KEY}` env-var interpolation to the MCP config (never stores plaintext) and prints an `export` reminder. Pass `prompt` for interactive input.
- **tapps-mcp: Doctor uv PATH mismatch check (#77)** — `tapps_doctor` now warns when MCP config uses bare `tapps-mcp` command but the project has `tapps-mcp` in a uv optional-dependency extra. Suggests re-running `init --force` for auto-detection.
- Version bump: tapps-core 1.17.1 → 1.18.0, tapps-mcp 1.17.1 → 1.18.0, docs-mcp 1.17.1 → 1.18.0

## [1.17.1] - 2026-04-06

### Fixed

- **tapps-mcp: Fix unreachable code detection in `tapps_dead_code`** — vulture's `unreachable code after 'return'` findings were silently dropped because the parser regex only matched the `unused <type> '<name>'` format. Added `_VULTURE_UNREACHABLE_RE` pattern to catch `unreachable code after '<keyword>'` findings. These now correctly parse as `finding_type="unreachable_code"` and feed into the scoring pipeline's unreachable code penalty.
- Version bump: tapps-core 1.17.0 → 1.17.1, tapps-mcp 1.17.0 → 1.17.1, docs-mcp 1.17.0 → 1.17.1

## [1.17.0] - 2026-04-06

### Changed

- **docs-mcp: Three-tier output for all generator tools** — generators now use `finalize_output()` for consistent output handling:
  - **Tier 1 (write-first):** writable filesystem — write to disk, return metadata only (`written_to`, `output_path`, `content_length`, `section_count`). Never returns `content` key, saving client context window.
  - **Tier 2 (inline):** read-only + content < 20K chars — return `content` directly.
  - **Tier 3 (manifest):** read-only + content >= 20K chars — return `FileManifest` for client-side apply.
- **docs-mcp: Auto-computed output paths** — all 15 file-writing generators now compute sensible default paths when `output_path` is omitted (e.g. `CHANGELOG.md`, `docs/api/reference.md`, `docs/epics/EPIC-{number}.md`, `docs/PURPOSE.md`, `docs/INDEX.md`).
- **docs-mcp: ~300 lines of duplicated write/response boilerplate eliminated** — consolidated into `server_helpers.finalize_output()`.
- Version bump: tapps-core 1.16.0 → 1.17.0, tapps-mcp 1.16.0 → 1.17.0, docs-mcp 1.16.0 → 1.17.0

## [1.16.0] - 2026-04-06

### Changed

- **deps: upgrade tapps-brain v2.0.3 → v2.0.4**
  - EPIC-052 code review sweep: write-through consistency + hygiene fixes
  - EPIC-042–050: Embeddings v17, hybrid profile RRF, SQLite busy tuning, decay/FSRS, injection tokenizer hook, consolidation sweep CLI, GC metrics, save-conflict export, merge undo, per-group entry caps
  - Hive: group agent_scope, recall union, publisher memory_group propagation
  - Observability: Save-path phase latency histograms, operator docs
- **tapps-core**: Removed stale `_RAG_BLOCK_THRESHOLD` re-export from `memory/store.py` (removed upstream in v2.0.4)
- **tapps-mcp**: Fixed cross-platform Windows path parsing in `_is_valid_tapps_command`
- **tapps_mcp.spec**: Added 2 missing hidden imports (`quick_check_recurring`, `tools.checklist_policy`)
- **tests**: Fixed 89 test failures caused by tapps-brain v2.0.4 API changes:
  - Updated enum counts (MemoryTier 4→6, MemoryScope 4→5), schema version (4→17)
  - Fixed `_frequency_score`/`_normalize_relevance` calls (staticmethod → instance method)
  - Fixed `detect_installed_tools` → `detect_installed_tools_async` mock patch
  - Fixed `_get_scorer` → `_get_scorer_for_file` rename
  - Fixed `_record_call` mock to accept new `success` kwarg
  - Fixed event loop pollution (`asyncio.get_event_loop()` → `asyncio.run()`)
  - Fixed mock stores/settings with real numeric values for v2.0.4 validation
  - Updated error response format (`error_code` → `error.code`)
  - Relaxed seeding/eviction assertions for auto-consolidation and profile-based caps
- Version bump: tapps-core 1.15.0 → 1.16.0, tapps-mcp 1.15.0 → 1.16.0, docs-mcp 1.15.0 → 1.16.0

## [1.15.0] - 2026-04-05

### Changed

- **Epic 93: Full Code Review — first pass across monorepo**
  - **Security (93.1)**: Bandit 0 HIGH/MEDIUM (was 2 HIGH + 1 MEDIUM). Fixed Jinja `autoescape=False` annotations in `docs-mcp` generators (markdown output, safe) and added configurable `dataset_revision` pinning for HuggingFace benchmark loader
  - **Async I/O (93.4)**: Wrapped all 26 blocking file-I/O calls in async MCP tool handlers with `asyncio.to_thread`. Covers `docs-mcp` generators, `docs_config`, scoring (py/go/rust/ts), pipeline wizard, and knowledge lookup
  - **Type safety (93.2, partial)**: Removed 70 unused `# type: ignore` comments surfaced by `mypy --strict`; added missing module overrides for `datasets`/`pyarrow`/`pandas`; replaced broken `tapps_core.project.models` import with local `TechStack` Protocol; fixed tree-sitter `Language = None` guards; hoisted dispatcher extractor type annotations; fixed `ClassVar` at module scope; fixed `FastMCP` forward references; fixed broken `click.echo(...) or ctx.exit()` pattern
  - **Ruff hygiene**: Cleaned 218 lint issues to 0; normalized CRLF → LF on touched files
  - **Dependencies (93.7)**: `pip-audit` clean (0 CVEs)
  - **Tests**: Fixed 12 memory test failures from `MagicMock` cascade into `MemoryRetriever` scoring weights and stale `verify_integrity` mock expectations. `docs-mcp` test_stories keyword-match fallback disambiguated
  - **Docs (93.8)**: Corrected `CLAUDE.md` tapps-brain pin reference (v1.4.3 → v2.0.3); verified MCP tool counts (tapps-mcp=30, docs-mcp=32)
- Version bump: tapps-core 1.14.0 → 1.15.0, tapps-mcp 1.14.0 → 1.15.0, docs-mcp 1.14.0 → 1.15.0

### Known Issues (deferred from Epic 93)

- **mypy --strict**: ~60 genuine type errors remain (mostly `attr-defined`/`call-arg` against drifted `tapps-brain` v2.0.3 API surface). Each requires per-site investigation and is tracked as follow-up work
- **tapps-mcp tests**: ~80 pre-existing failures remain, concentrated in memory-related tests with stale `MagicMock` expectations against `tapps-brain` v2.0.3. `test_memory_safety_enforcement.py` also exhibits test pollution (passes in isolation)
- **Broad `except Exception:` catches**: 144 occurrences remain as defensive patterns at MCP tool boundaries; per-case narrowing deferred
- **High cyclomatic complexity**: 81 functions at CC > 20 identified; individual refactors deferred to dedicated stories

## [1.14.0] - 2026-03-25

### Changed

- **tapps-brain upgraded from v1.3.1 to v1.4.3** — Picks up SQL hardening (f-string SQL eliminated), profile limit recalibration (research benchmarks), `ephemeral` and `session` tiers added to `MemoryTier` enum, sliding window rate limiter, source trust scoring, graph-boosted recall, integrity HMAC-SHA256, and OpenClaw SDK migration
- Version bump: tapps-core 1.13.0 → 1.14.0, tapps-mcp 1.13.0 → 1.14.0, docs-mcp 1.13.0 → 1.14.0

## [1.13.0] - 2026-03-25

### Added

- **Epic 89: PLANOPT Feedback (TappsMCP)** — `tapps_impact_analysis` accepts `project_root` parameter for cross-project analysis (Story 89.1); `tapps_session_start` returns top-level `project_root` in response (Story 89.2); `tapps_session_start` annotates `installed_checkers` with `environment` context field (Story 89.3)
- **Epic 90: Epic Validator Completeness** — `tapps_checklist` resolves `epic_file_path` relative to `project_root` (Story 90.1); `docs_validate_epic` parses linked headings and table-linked story references (Story 90.2); `docs_validate_epic` cross-file story validation and completeness reporting (Story 90.3)
- **Epic 91: Epic Generator Quality Gaps** — Context-aware placeholder prose replacing generic `[TBD]` tokens (Story 91.1); quick-start mode for title-only epic generation (Story 91.2); adaptive detail level with auto/minimal styles (Story 91.3); story and risk suggestion engine from project context (Story 91.4); always-render Performance Targets with config-derived metrics (Story 91.5)
- **Epic 92: Story Generator Quality Gaps** — Performance fixes ported from epic generator (Story 92.1); context-aware story placeholders (Story 92.2); `quick_start` mode for `docs_generate_story` (Story 92.3); task suggestion engine (Story 92.4); improved Gherkin scaffolding with context derivation (Story 92.5)
- **Shell/CLI project detection** — `type_detector` now detects shell-heavy projects (3+ `.sh` files, `bin/` directories, `install.sh`/`setup.sh`/`Makefile`) as `cli-tool` type with appropriate confidence weighting
- **Epic 80 (archive): Consumer Init & Bootstrap Hardening** — PostToolUse `script_event_map` includes `tapps-post-validate` / `tapps-post-report`; `tapps-mcp doctor` checks Claude hook script paths and treats project `.mcp.json` as sufficient vs user `~/.claude.json`; init refuses `.../packages/tapps-mcp` without `--allow-package-init` / `TAPPS_MCP_ALLOW_PACKAGE_INIT`; non-TTY MCP merge skips overwrite with log (`--force`, `TAPPS_MCP_INIT_ASSUME_YES`); MCP config uses `uv run` + monorepo placeholder when `tapps-mcp` not on PATH and merges existing `env`; CLI `--with-docs-mcp`; TECH_STACK low-confidence callout; README + troubleshooting updates

### Changed

- **StoryGenerator refactoring** — Expert confidence threshold extracted to class-level constant `_EXPERT_CONFIDENCE_THRESHOLD`; `server_gen_tools.py` import cleanup (structlog logger, TYPE_CHECKING for FastMCP); `can_write_to_project()` now receives `root` parameter for purpose/doc_index generators
- Version bump: tapps-core 1.12.0 → 1.13.0, tapps-mcp 1.12.0 → 1.13.0, docs-mcp 1.12.0 → 1.13.0

## [1.12.0] - 2026-03-21

### Added

- **Epic M1: Memory security surface** - 2 new `tapps_memory` actions: `safety_check` (pre-flight prompt injection detection using 6 OWASP-aligned patterns) and `verify_integrity` (SHA-256 tamper detection across all entries). Doctor now warns when `tapps-brain-mcp` is configured alongside TappsMCP (split-brain risk). Session start enriched with active profile name and source.
- **Epic M2: Memory profile & lifecycle management** - 3 new `tapps_memory` actions: `profile_info` (active profile layers, decay config, scoring weights), `profile_list` (6 built-in profiles), `profile_switch` (switch profile, persist to `.tapps-brain/profile.yaml`, reset store singleton). Added `memory.profile` config setting for explicit override. Profile auto-detection from project type at session start. Promotion events surfaced in `reinforce` responses via PromotionEngine.
- **Planning docs** - `TAPPS_BRAIN_INTEGRATION_RECOMMENDATIONS.md` (2026 industry research, OWASP ASI06, competitor analysis, 18 cross-repo recommendations) and `TAPPS_MCP_MEMORY_ROADMAP.md` (TappsMCP-only implementation plan, 7 epics, 15 planned new actions)
- **23 new unit tests** - `test_memory_m1_security.py` (9 tests) and `test_memory_m2_profiles.py` (14 tests) covering all new actions, doctor checks, config settings, and promotion surfacing

### Changed

- **tapps_memory action count: 23 → 28** - Updated all documentation, prompt templates, skills, and platform rules to reflect the new action count
- **MemoryStore singleton** now resolves profile from `memory.profile` setting or auto-detect via `tapps_brain.profile.resolve_profile()`, with graceful fallback for tapps-brain < 1.1.0

## [1.11.0] - 2026-03-19

### Added

- **Tests for uncovered modules** - Added dedicated test files for `common/logging.py`, `common/pipeline_models.py`, `security/api_keys.py`, `metrics/feedback.py`, and `adaptive/protocols.py` in tapps-core (24 new tests)
- **Integration test conftest files** - Created `conftest.py` with heavier fixtures (real project trees) for integration test directories in all 3 packages
- **pytest-randomly** - Added `pytest-randomly>=3.16.0` to dev dependencies with `--randomly-seed=last` for reproducible test order randomization
- **tapps-brain v1.0.1 integration** - Updated all Dockerfiles and `[tool.uv.sources]` from v1.0.0 to v1.0.1 with CI fixes (ruff, mypy, formatting, build job)
- **Doctor: tapps-brain health check** - `tapps_doctor` now verifies that the tapps-brain library is importable, catching broken installations before runtime memory failures
- **Deprecation warnings on tapps_core.memory** - Importing from `tapps_core.memory` now emits a `DeprecationWarning` directing users to `tapps_brain.*` imports

### Changed

- **Test suite quality Phase 2** - Comprehensive test infrastructure improvements across all 3 packages (7,244 tests passing)
- **Deduplicated test_rag_safety.py** - Reduced tapps-core `test_rag_safety.py` from 121 lines of duplicated behavioral tests to a 28-line import-identity test; all behavioral coverage remains in `test_content_safety.py`
- **Native async tests in docs-mcp** - Migrated 14 test files (69 call sites) from `run_async()` sync wrapper to native `async def` / `await`, leveraging the already-configured `asyncio_mode = "auto"`
- **Parallel CI test execution** - Wired `pytest-xdist` (`-n auto --dist worksteal`) into the GitHub Actions CI workflow for parallel test execution across all packages
- **Integration tests marked slow** - Applied `@pytest.mark.slow` to all 16 integration test files (44 test classes) enabling `pytest -m "not slow"` for fast local feedback
- **Public API assertions** - Replaced private attribute assertions (`_cache`, `_tracker`) in `test_feature_flags.py` and `test_voting_engine.py` with observable behavior checks
- **Memory test dedup** - Replaced 6 duplicate tapps-core memory test files (~1,480 lines) with lightweight re-export verification in `test_memory_reexport.py`. Behavioral tests live in tapps-brain (521+ tests)
- **docs-mcp async test fix** - Converted 6 tests in `test_content_return.py` from broken `asyncio.get_event_loop().run_until_complete()` to proper `async def` + `@pytest.mark.asyncio` + `await`
- **Documentation refresh** - Updated README, ARCHITECTURE.md, and package READMEs with tapps-brain extraction details, updated test counts (7,900+), and dependency graph
- **tree-sitter promoted to dev dependency** - Added `tree-sitter` + 4 language grammars (Go, Java, Rust, TypeScript) to root dev-dependencies. 15 previously-skipped docs-mcp multi-language extraction tests now run in all dev environments. Total skipped tests reduced from 25 to 10
- **optional_deps pytest marker** - Added `optional_deps` marker for tests requiring sentence-transformers, faiss-cpu, or cohere. Allows CI jobs to target optional-dep tests via `pytest -m optional_deps`
- **CI hardening** - Hardened GitHub Actions workflows and Docker builds
- **Platform PRD archived** - Marked TAPPS_PLATFORM_PRD.md as delivered with residual items noted
- Version bump: tapps-core 1.10.0 -> 1.11.0, tapps-mcp 1.10.0 -> 1.11.0, docs-mcp 1.10.0 -> 1.11.0

## [1.4.1] - 2026-03-12

### Fixed

- **Read-only filesystem detection** - `tapps_upgrade` and `tapps_init` now detect read-only filesystems (common in Docker containers with read-only workspace mounts) and return a clear error with actionable remediation options instead of cascading permission-denied errors on every component
- Version bump: tapps-mcp 1.4.0 -> 1.4.1, docs-mcp 1.4.0 -> 1.4.1

## [1.4.0] - 2026-03-12

### Added

- **Container detection** — `tapps_core.common.utils.is_running_in_container()` detects Docker/OCI environments via env var, sentinel file, and cgroup inspection
- **Docker pipeline** — Epic 75 (Docker reliability), Epic 78 (profiles), Epic 79 (catalog) complete

### Changed

- **Memory cap** — Increased default `max_memories` from 500 to 1500 per project
- **Memory documentation** — Comprehensive 20-action reference added to AGENTS.md templates (high/medium/low), all 6 platform rules, and skill templates
- **Memory system docs** — All templates now document 4 tiers, 4 scopes, federation, consolidation, and configuration examples
- **Docs archive** — Archived 200+ historical docs, fixed all stale counts to match code truth
- Version bump: tapps-core 1.2.0 → 1.3.0, tapps-mcp 1.3.1 → 1.4.0, docs-mcp 1.3.1 → 1.4.0

### Fixed

- **Dockerfile.platform** — Fixed missing README references for docs-mcp wheel build
- **PyInstaller bundle** — Rebuilt exe to include all engagement-level template files

## [1.3.1] - 2026-03-11

### Fixed

- **tapps-core**
  - `test_schema_version_persists` — Avoid calling `get_schema_version()` on closed DB; capture version before close
  - `test_no_weights_when_adaptive_disabled`, `test_apply_adaptive_weights_disabled` — Patch `load_settings` so project `.tapps-mcp.yaml` (adaptive.enabled) does not override test expectations
- **tapps-mcp**
  - `test_secret_scanner_still_runs`, `test_security_combines_bandit_and_secrets` — Set `mock_scorer.language = "python"` so security branch runs; secret scanner now invoked correctly
  - `test_claude_hooks_merge::test_result_dict`, `test_claude_hooks_scripts_windows::test_result_dict` — Expect 10 scripts (includes memory hooks tapps-memory-capture.sh, tapps-memory-auto-capture.sh)
- **docs-mcp**
  - `test_enabled_tools_config` — Bump expected tool count 23 → 24 for `docs_generate_prompt`
  - `test_output_dir_env_var_resolves` — Skip on Windows (Unix `${VAR}` expansion)
  - `test_dockerfile_has_entrypoint` — Accept CMD or ENTRYPOINT; `test_dockerfile_has_healthcheck` — Accept CMD as alternative to HEALTHCHECK

### Changed

- Version bump: tapps-core 1.1.0 → 1.2.0, tapps-mcp 1.3.0 → 1.3.1, docs-mcp 1.3.0 → 1.3.1

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

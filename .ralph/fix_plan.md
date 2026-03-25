# TappsMCP Pre-Deployment Fix Plan

<!-- Each ## section is an "epic". QA runs when the last task in a section is completed. -->

## Phase 1: Critical Deploy Blockers (Quick Fixes)

- [x] C1: Replace `import logging` with `structlog` in `packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py` (lines 11, 47). Change `_logger = logging.getLogger(__name__)` to `logger = structlog.get_logger(__name__)`. Update all `_logger.debug/error` calls to `logger.debug/error`.
- [x] C2: Remove tag trigger from `.github/workflows/docker.yml` -- delete the `tags: - "v*"` block under `push:`. Keep PR trigger only. `docker-publish.yml` owns all tag-triggered builds.
- [x] C3: Fix path filter in `.github/workflows/docker.yml` -- replace `src/**` with `packages/*/src/**`. Add `packages/docs-mcp/Dockerfile` and `packages/*/pyproject.toml` to the paths list.
- [x] C4: Add ImportError guard to `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py:1430` -- wrap `from tapps_brain.safety import check_content_safety` in try/except ImportError, return `{"error": "unsupported", "degraded": true, "message": "Safety module not available in installed tapps-brain version."}` on failure.
- [x] H1: Update `expected_tools` in `.github/workflows/docker-publish.yml` -- line 32: change 28 to 30, line 36: change 18 to 32.
- [x] H5: Add logging to `packages/tapps-mcp/src/tapps_mcp/cli.py:620` -- add `logger.debug("memory_search_failed", exc_info=True)` before `sys.exit(0)` in the bare `except Exception:` handler.

## Phase 2: tapps-brain Version & Profile (Requires tapps-brain repo)

- [x] H2a: Tag v1.1.0 in tapps-brain repo (`C:\cursor\tapps-brain`) and push tag to GitHub.
- [x] H2b: Update root `pyproject.toml` -- change `tag = "v1.0.1"` to `tag = "v1.1.0"` for tapps-brain dependency.
- [x] H2c: Run `uv sync --all-packages` and verify profile/promotion imports work without try/except fallback. ✓ tapps-brain 1.1.0 installed, profile (6 profiles) and promotion modules import cleanly.
- [x] H2d: Add profile management documentation to AGENTS.md memory section. (Added profiles subsection, security/profile actions, updated count to 28.)

## Phase 3: Security Hardening (OWASP ASI06)

- [x] H3a: Wire `check_content_safety()` into `_handle_save()` in `server_memory_tools.py`. Call before store.save(). In warn mode: log flagged patterns but allow the write. Include safety results in save response.
- [x] H3b: Add `safety.enforcement` setting to `.tapps-mcp.yaml` config schema (values: `warn` | `block`, default: `warn`). Read in `_handle_save()` to determine behavior.
- [x] H3c: Implement bypass access control -- only allow `safety_bypass=True` when source is `"system"` (not `"agent"` or `"inferred"`). Added `safety_bypass` param to `_Params`, `tapps_memory()`, and `_handle_save()`. Added `allow_bypass` config to `MemorySafetySettings`. Bypass denied with warning log for non-system sources. Extended safety enforcement to `_handle_save_bulk()` with per-entry checks, bypass access control, and `blocked` count.
- [x] H3d: Add tests for safety enforcement in save path (6 known injection patterns from MINJA test suite + false positive rate check). ✓ 22 tests in `test_memory_safety_enforcement.py`: 6 MINJA patterns, bypass access control (system/agent/inferred/human/config), false positives (10 parametrized), warn mode, bulk save safety. Also extended `_handle_save_bulk` with per-entry safety checks.
- [x] H4a: (tapps-brain) Add `integrity_hash` nullable column to `memories` table. Compute HMAC-SHA256 on save. Key stored at `~/.tapps-brain/integrity.key`. ✓ Created `integrity.py` (key mgmt + compute/verify), added `integrity_hash` field to `MemoryEntry`, schema v8 migration, hash computed on save in `persistence.py`, hash read back in `_row_to_entry`.
- [x] H4b: (tapps-brain) Add `verify_integrity()` method that scans entries and reports tampered ones. Added `MemoryStore.verify_integrity()` in `store.py` — scans all entries, verifies HMAC-SHA256 via `verify_integrity_hash()`, returns `{total, verified, tampered, no_hash, tampered_keys}`.
- [x] H4c: Surface integrity violations in `tapps_memory(action="verify_integrity")` response and in `memory_health()`. ✓ Updated `_handle_verify_integrity` in `server_memory_tools.py` to delegate to `store.verify_integrity()` (HMAC-SHA256). Added `integrity_verified/tampered/no_hash/tampered_keys` fields to `StoreHealthReport` in tapps-brain. `store.health()` now includes integrity scan results.
- [x] H6a: (tapps-brain) Add sliding window rate limiter to `MemoryStore.save()`. Default: 20 writes/min, 100/session. Warn-only. ✓ Created `rate_limiter.py` (SlidingWindowRateLimiter, RateLimiterConfig, RateLimitResult, RateLimiterStats). Wired into `MemoryStore.__init__` and `save()`. Added `batch_context` param to `save()` for H6b exemptions. 18 tests in `test_rate_limiter.py`. Exported from `__init__.py`.
- [x] H6b: (tapps-brain) Add batch_context exemption for `import_markdown`, `seed`, `federation_sync`, `consolidate`. ✓ Wired `batch_context` param into all `store.save()` calls: seeding.py (7 calls, "seed"), markdown_import.py (3 calls, "import_markdown"), auto_consolidation.py (1 call, "consolidate"), federation.py (1 call, "federation_sync").
- [x] H6c: Surface anomaly counts in `memory_health()` response. ✓ Added `rate_limit_minute_anomalies`, `rate_limit_session_anomalies`, `rate_limit_total_writes`, `rate_limit_exempt_writes` fields to `StoreHealthReport` in tapps-brain. Populated from `rate_limiter.stats` in `store.health()`. Surfaced in `_handle_health()` in TappsMCP with `getattr` fallback for older tapps-brain versions.

## Phase 4: Medium Priority Fixes

- [x] M1: Wire `ablated_template` parameter into `evaluator.evaluate_batch()` in `packages/tapps-mcp/src/tapps_mcp/benchmark/ablation.py:219`.
- [x] M4: Enable promotion engine in default `repo-brain` profile (requires tapps-brain v1.1.0). Set thresholds: context->procedural (3 accesses, 7d), procedural->pattern (5, 14d), pattern->architectural (10, 30d). ✓ Updated repo-brain.yaml thresholds (context: 5→3, procedural: 8→5). Added explicit `profile: repo-brain` to both tapps-mcp and tapps-core default.yaml configs.
- [x] M3: Enable graph-boosted recall when store has >= 10 relation triples. Set `graph_boost_factor=0.1`. Add relation count to `memory_health()` output. ✓ Added `relation_count` to `StoreHealthReport` in tapps-brain, `count_relations()` to `MemoryStore`, populated in `health()`. Added density-gated graph boost in `_ranked_search()` (>= 10 relations → boost factor 0.1, inversely proportional to hop distance). Surfaced `relation_count` in `_handle_health()` and `graph_boost_active` flag in ranked search response.
- [x] M2: Add `source_trust` signal to composite retrieval scoring in tapps-brain. Defaults: human=1.0, system=0.9, agent=0.7, inferred=0.5. ✓ tapps-brain: `ScoringConfig.source_trust` in `profile.py`, `_DEFAULT_SOURCE_TRUST` in `retrieval.py`, post-composite multiplier in `MemoryRetriever.search()`, `repo-brain.yaml` profile, 13 tests in `test_source_trust.py`. TappsMCP: wired profile `scoring_config` into `_ranked_search()`, `_find_entries_by_query()`, and CLI search. Added `source_trust_active` to search response, `source_trust` dict to `profile_info` response.

## Phase 5: Cross-Project Tool Parity (Epic 89)

<!-- Epic: docs/planning/epics/EPIC-89-CROSS-PROJECT-TOOL-PARITY.md -->
<!-- Source: https://github.com/wtthornton/TappsMCP/issues/76 -->

- [x] 89.1: Execute story — docs/planning/epics/EPIC-89/story-89.1-impact-analysis-project-root.md
- [x] 89.2: Execute story — docs/planning/epics/EPIC-89/story-89.2-session-start-project-root.md
- [x] 89.3: Execute story — docs/planning/epics/EPIC-89/story-89.3-installed-checkers-environment-context.md ✓ Added `checker_environment` ("mcp_server") and `checker_environment_note` fields to `_build_server_info_data`, full session start, quick session start, and `SessionStartOutput` schema. Backward compatible — new fields have defaults.
- [x] 89.4: Execute story — docs/planning/epics/EPIC-89/story-89.4-shell-bash-project-detection.md ✓ Added `_has_shell_scripts()` (3+ .sh files), `_has_bin_directory()`, `_has_install_script()` indicators to `cli-tool` type. Rebalanced weights (7 indicators). Added .sh to source file extensions in `_has_few_source_files()`. Added negative signal in `documentation` docs_focused composite. 5 tests: pure shell, shell+bin+install, mixed shell+python, few scripts (no misclass), ralph-like structure (>0.7 confidence).

## Phase 6: Epic Validation Enhancements (Epic 90)

<!-- Epic: docs/planning/epics/EPIC-90-EPIC-VALIDATION-ENHANCEMENTS.md -->
<!-- Source: https://github.com/wtthornton/TappsMCP/issues/76 -->
<!-- Note: Stories are sequential — 90.1 enables 90.2, 90.2 enables 90.3 -->

- [x] 90.1: Execute story — docs/planning/epics/EPIC-90/story-90.1-epic-file-path-relative-resolution.md ✓ `evaluate_epic()` now extracts `project_root` from `eval_kwargs`, resolves relative `file_path` against it, and raises `FileNotFoundError` with both resolved and original paths. 4 new tests: relative+project_root, relative+cwd fallback, absolute unchanged, nonexistent error message.
- [x] 90.2: Execute story — docs/planning/epics/EPIC-90/story-90.2-table-linked-story-parsing.md ✓ Added `linked_file` field to `EpicStoryInfo` (checklist.py) and `StoryInfo` (epic_validator.py). Added `_LINKED_HEADING_RE` for `### [X.Y](path) -- Title` format and `_TABLE_STORY_RE` for table-linked rows. Updated `_parse_epic_markdown()` and `_parse_stories()` with 3-tier parsing: classic headings → linked headings → table fallback. Added `_parse_table_size_priority()` helper. 7 test classes covering linked headings, table rows, mixed formats, missing columns, plain text exclusion.
- [x] 90.3: Execute story — docs/planning/epics/EPIC-90/story-90.3-cross-file-story-validation.md ✓ Added `CrossFileSummary` model and `cross_file_summary` field to both `EpicValidationReport` (docs-mcp) and `EpicValidation` (tapps-mcp). Added `_check_story_file_structure()` helper and `_validate_linked_stories()` in both packages. Added `validate_linked_stories` parameter to `EpicValidator.validate()` and `validate_epic_markdown()`. Wired `epic_file_path` through call site. Linked files resolved relative to epic parent dir. Missing files produce warnings, structural gaps produce info findings. 8 tests in docs-mcp, 7 tests in tapps-mcp.

## Phase 7: Epic Generator - Close LLM Quality Gaps (Epic 91)

<!-- Epic: docs/epics/EPIC-91-epic-generator-quality-gaps.md -->
<!-- Perf fix landed in commit 31237f1; these stories close remaining quality gaps -->
<!-- Implementation order: 91.1 → 91.3 → 91.2 → 91.4 → 91.5 -->

- [x] 91.1: Execute story — docs/epics/stories/STORY-91.1-context-aware-placeholders.md ✓ Refactored `_render_goal`, `_render_motivation`, `_render_technical_notes`, `_render_non_goals`, `_render_acceptance_criteria` to interpolate `config.title` (and enrichment tech_stack) into placeholder text. Added `_NON_GOAL_KEYWORD_HINTS` dict and `_derive_non_goal_hints()` for keyword-based boundary suggestions. Empty/whitespace title falls back to generic text. Updated 5 existing tests, added 16 new tests in `TestContextAwarePlaceholders`.
- [x] 91.3: Execute story — docs/epics/stories/STORY-91.3-adaptive-detail-level.md ✓ Added "minimal" and "auto" to VALID_STYLES. Implemented `_auto_detect_style(config)`: stories>5/risks/files>3/success_metrics→comprehensive, stories≤1 no risks no files→minimal, else standard. Added minimal rendering path (title, metadata, purpose, goal, AC, stories, DoD) and `_render_definition_of_done()`. Updated server_gen_tools.py docstring. 10 new tests in TestEpicAutoDetectStyle + 1 test for explicit minimal.
- [x] 91.2: Execute story — docs/epics/stories/STORY-91.2-quick-start-mode.md ✓ Added `quick_start` bool parameter to `docs_generate_epic` and `EpicGenerator.generate/generate_with_timing`. Added `_infer_quick_start_defaults()` static method that fills goal, motivation, 3 story stubs (Foundation & Setup/Core Implementation/Testing & Documentation), AC, priority (P2), and style (auto) from title. Explicit params always override. 6 unit tests + 2 MCP tool tests.
- [x] 91.4: Execute story — docs/epics/stories/STORY-91.4-suggestion-engine.md ✓ Added `_STORY_PATTERNS` and `_RISK_PATTERNS` ClassVar dicts to EpicGenerator. Implemented `_suggest_stories(title, goal)` (keyword-to-pattern, first-match, (suggested) suffix, generic fallback) and `_suggest_risks(title, goal)` (deduped). Integrated into `_render_stories` and `_render_risk_assessment` when config lists are empty. User-provided values always override. 22 tests in TestSuggestionEngineStories, TestSuggestionEngineRisks, TestSuggestionEngineIntegration. Updated test_stories_placeholder to expect new fallback format.
- [x] 91.5: Execute story — docs/epics/stories/STORY-91.5-performance-targets.md ✓ Enhanced `_render_performance_targets` to always render with config-derived targets: test coverage (always), AC pass rate (AC>5), quality gate (files>3), story completion (stories>3). Expert guidance rendered before derived table when available. 11 unit tests in TestPerformanceTargets.

## Phase 8: Story Generator - Performance Parity and Quality Gaps (Epic 92)

<!-- Epic: docs/epics/EPIC-92-story-generator-quality-gaps.md -->
<!-- Dependencies: Epic 91 (shared patterns for context-aware prose and quick-start) -->
<!-- Implementation order: 92.1 → 92.2 → 92.3 → 92.4 → 92.5 -->

- [x] 92.1: Execute story — docs/epics/stories/STORY-92.1-port-performance-fixes.md
- [ ] 92.2: Execute story — docs/epics/stories/STORY-92.2-context-aware-story-placeholders.md
- [ ] 92.3: Execute story — docs/epics/stories/STORY-92.3-quick-start-story-mode.md
- [ ] 92.4: Execute story — docs/epics/stories/STORY-92.4-task-suggestion-engine.md
- [ ] 92.5: Execute story — docs/epics/stories/STORY-92.5-improved-gherkin-scaffolding.md

## Completed
- [x] Project reviewed and fix plan created (2026-03-22)
- [x] Phase 1-4 completed (2026-03-22 to 2026-03-23)

## Notes
- Phase 1 items are independent quick fixes (no external dependencies)
- Phase 2 requires access to tapps-brain repo at C:\cursor\tapps-brain
- Phase 3 requires tapps-brain changes to land first (R01-R03 from recommendations)
- Phase 4 items are enhancements, not blocking deployment
- Phase 5-8 use pointer convention: read the story file for full spec, tasks, and AC
- Phase 5 stories are independent (can parallelize 89.2-89.4 after 89.1)
- Phase 6 stories are sequential (90.1 -> 90.2 -> 90.3)
- Phase 7 stories follow implementation order: 91.1 → 91.3 → 91.2 → 91.4 → 91.5 (91.4/91.5 can parallel)
- Phase 8 depends on Phase 7 patterns; stories are sequential except 92.4/92.5 can parallel
- QA runs at epic boundaries (when a section's last task in a `##` section is completed)
- This is the primary fix plan (canonical copy)
- See docs/planning/TAPPS_BRAIN_INTEGRATION_RECOMMENDATIONS.md for R01-R18 details

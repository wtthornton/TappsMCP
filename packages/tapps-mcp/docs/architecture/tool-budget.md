# MCP Tool Budget — Per-Server Daily Drivers

This document defines the **eager-load budget** for each MCP server in the
TappsMCP platform. Tools on the daily-driver list are loaded eagerly at
session start. All other tools carry `defer_loading: true` and must be
fetched via the [Tool Search BETA](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
mechanism before they can be called.

**Cap:** 12 eager tools per server. Any exception must be noted in a review comment.

---

## tapps-mcp — Code Quality Server

**Eager count: 8 / 12**

| Tool | Justification |
|---|---|
| `tapps_session_start` | Session bootstrap — must be called first; everything else runs in degraded mode without it |
| `tapps_quick_check` | After-edit quality gate — single call runs score + gate + security scan; used after every Python file change |
| `tapps_lookup_docs` | API doc lookup before using any external library — prevents hallucinated APIs |
| `tapps_impact_analysis` | Blast-radius analysis before any refactor or delete — catches silent breakage |
| `tapps_validate_changed` | Pre-completion batch validation on all changed files — mandatory before declaring work done |
| `tapps_checklist` | Final verification step — confirms no required pipeline tools were skipped |
| `tapps_quality_gate` | Standalone quality gate for granular control (e.g. per-file gate after scoring) |
| `tapps_score_file` | Per-file scoring — feeds the quality gate and surfaces category-level breakdowns |

**Deferred (loaded via Tool Search):** `tapps_audit_campaign`,
`tapps_dashboard`, `tapps_dead_code`, `tapps_dependency_graph`,
`tapps_dependency_scan`, `tapps_doctor`, `tapps_feedback`, `tapps_init`,
`tapps_linear_count`, `tapps_linear_snapshot_get`,
`tapps_linear_snapshot_invalidate`, `tapps_linear_snapshot_put`,
`tapps_memory`, `tapps_pipeline`, `tapps_release_update`, `tapps_report`,
`tapps_security_scan`, `tapps_server_info`, `tapps_session_notes`,
`tapps_set_engagement_level`, `tapps_stats`, `tapps_upgrade`,
`tapps_validate_config`

---

## docs-mcp — Documentation Server

**Eager count: 6 / 12**

| Tool | Justification |
|---|---|
| `docs_generate_epic` | Daily Linear write — every new feature starts with an epic |
| `docs_generate_story` | Daily Linear write — every story under an epic uses this |
| `docs_validate_linear_issue` | Gate before every `save_issue` call — the pre-linear-write hook requires a sentinel < 30 min old |
| `docs_lint_linear_issue` | Pre-update lint — surfaces formatting violations before pushing to Linear |
| `docs_generate_changelog` | Used on every release to produce a versioned changelog from git history |
| `docs_release_gate` | Pre-release validation — confirms all required docs are present before shipping |

**Deferred (loaded via Tool Search):** `docs_api_surface`,
`docs_check_completeness`, `docs_check_cross_refs`, `docs_check_diataxis`,
`docs_check_drift`, `docs_check_freshness`, `docs_check_links`,
`docs_check_style`, `docs_config`, `docs_generate_adr`,
`docs_generate_api`, `docs_generate_architecture`,
`docs_generate_contributing`, `docs_generate_diagram`,
`docs_generate_doc_index`, `docs_generate_frontmatter`,
`docs_generate_interactive_diagrams`, `docs_generate_llms_txt`,
`docs_generate_onboarding`, `docs_generate_prd`, `docs_generate_prompt`,
`docs_generate_purpose`, `docs_generate_readme`,
`docs_generate_release_notes`, `docs_generate_release_update`,
`docs_git_summary`, `docs_linear_triage`, `docs_module_map`,
`docs_project_scan`, `docs_session_start`, `docs_validate_epic`,
`docs_validate_release_update`

---

## tapps-brain — Memory Server

**Eager count: 6 / 12**

| Tool | Justification |
|---|---|
| `brain_recall` | Task-start retrieval — surfaces prior learnings before implementation |
| `brain_remember` | Save non-obvious fixes and workarounds for future sessions |
| `brain_learn_success` | Epic-boundary debrief — records what worked |
| `brain_learn_failure` | Epic-boundary debrief — records what failed and why |
| `memory_supersede` | Invalidates stale knowledge when an approach changes |
| `memory_find_related` | Fuzzy semantic search for adjacent patterns before writing new code |

**Deferred (loaded via Tool Search):** All other brain/memory actions
(federation, hive propagation, batch ops, health probes, profile
management, etc.) are infrequent enough to defer.

---

## Tool Search BETA context

Claude Code supports a Tool Search header that allows clients to request
tools by name rather than requiring servers to register all tools eagerly.
Servers that implement `defer_loading: true` on non-daily-driver tools
shrink the default tool catalog (and thus the system prompt) while keeping
those tools accessible on demand.

Reference: [Tool Search — Anthropic Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)

The implementation for tapps-mcp and docs-mcp is tracked in TAP-1986 and
TAP-1987 respectively. This document is the prerequisite spec that those
stories reference.

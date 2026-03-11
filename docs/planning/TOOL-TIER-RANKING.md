# TappsMCP & DocsMCP Tool Tier Ranking

A tiered ranking of all **TappsMCP** (29 tools) and **DocsMCP** (22 tools) by **importance** and **impact**—what actually moves the needle for quality, safety, and documentation.

**Criteria:**
- **Impact** — Does using this tool materially improve outcomes (correctness, security, consistency, doc accuracy)?
- **Workflow role** — Required vs recommended vs situational vs optional.
- **Differentiation** — Does it address what LLMs are bad at or what’s hard to get elsewhere?

---

## Tier 1 — Critical / Game-changers

*Use these routinely; they prevent real failure modes and are central to the pipeline.*

### TappsMCP

| Tool | Why Tier 1 |
|------|------------|
| **tapps_session_start** | First call every session; establishes server/project context. Required by pipeline rules. |
| **tapps_quick_check** | Single call: score + gate + security after edits. Catches regressions and security issues before “done.” |
| **tapps_validate_changed** | Batch-validates all changed files before declaring work complete. Blocking gate in pipeline. |
| **tapps_quality_gate** | Pass/fail against preset; enforces minimum bar before merge/complete. |
| **tapps_checklist** | Ensures required steps (score, gate, security, etc.) weren’t skipped. Final verification. |
| **tapps_lookup_docs** | **Prevents hallucinated APIs.** Looking up real library docs before coding is one of the highest-impact moves. |
| **tapps_security_scan** | Dedicated bandit + secrets scan. Security issues are high-impact; this is the main security tool. |

### DocsMCP

| Tool | Why Tier 1 |
|------|------------|
| **docs_session_start** | First call in docs workflow; doc inventory and recommendations. Anchors the docs pipeline. |
| **docs_check_drift** | **Detects code–docs mismatch.** Surfaces when code changed but docs didn’t—directly improves doc accuracy. |
| **docs_generate_readme** | README is the face of the project. Smart merge preserves human sections while updating generated parts. |
| **docs_project_scan** | Full doc state + completeness score. Drives “what’s missing” and prioritization. |

---

## Tier 2 — High value

*Strongly recommended; clear quality or documentation benefit; used often in workflows.*

### TappsMCP

| Tool | Why Tier 2 |
|------|------------|
| **tapps_score_file** | Granular 7-category score. Required in checklist for feature/bugfix/refactor/review; guides fixes. |
| **tapps_consult_expert** | Domain advice (security, testing, API design, etc.) when the model is unsure. Reduces wrong patterns. |
| **tapps_research** | Expert + docs in one call. Efficient when you need both domain guidance and library usage. |
| **tapps_memory** | Search at session start; save at end. Persists decisions and patterns across sessions. |
| **tapps_project_profile** | Project type, tech stack, CI, test frameworks. Informs “how to work in this repo.” |
| **tapps_impact_analysis** | Before changing a file’s public API—shows callers and impact. Prevents breaking changes. |
| **tapps_validate_config** | Validates Dockerfile, docker-compose, infra. Catches misconfig before deploy. |

### DocsMCP

| Tool | Why Tier 2 |
|------|------------|
| **docs_generate_changelog** | CHANGELOG from git; standard artifact for releases and users. |
| **docs_generate_api** | API reference from source (markdown/mkdocs/sphinx_rst). Keeps API docs aligned with code. |
| **docs_check_completeness** | 0–100 doc coverage score. Drives “what to write next.” |
| **docs_module_map** | Hierarchical module tree. Understanding structure before writing or refactoring. |
| **docs_api_surface** | Public API of a file + docstring coverage. Essential before updating API docs or README. |
| **docs_git_summary** | Git history + conventional commits. Needed for changelogs, release notes, and context. |
| **docs_check_links** | Broken internal links. Quick win before publish/merge. |
| **docs_check_freshness** | Classifies docs as fresh/aging/stale/ancient. Prioritizes what to update. |

---

## Tier 3 — Situational

*Very useful for specific tasks (refactor, release, planning, deep dives) but not daily defaults.*

### TappsMCP

| Tool | Why Tier 3 |
|------|------------|
| **tapps_dead_code** | Unused code during refactors. High value when cleaning up, not for every edit. |
| **tapps_dependency_graph** | Import graph, circular deps. Before major refactors or architecture work. |
| **tapps_dependency_scan** | CVE scan. Important before releases, not every session. |
| **tapps_report** | Multi-file quality report (JSON/MD/HTML). For audits and reviews. |
| **tapps_session_notes** | In-session decisions; can promote to memory. Helpful in long sessions. |
| **tapps_list_experts** | List expert domains before consulting. Use when you don’t know which domain to pick. |
| **tapps_init** | One-time (or rare) pipeline bootstrap. Critical for new projects, irrelevant after setup. |
| **tapps_upgrade** | After TappsMCP version bumps. Occasional maintenance. |

### DocsMCP

| Tool | Why Tier 3 |
|------|------------|
| **docs_generate_release_notes** | Per-version release notes. Release-time use. |
| **docs_generate_adr** | Architecture Decision Records. When recording a decision. |
| **docs_generate_onboarding** | Getting-started guide. New-project or major onboarding updates. |
| **docs_generate_contributing** | CONTRIBUTING.md. When setting or refreshing contribution workflow. |
| **docs_generate_prd** | Product Requirements Documents. Planning and product work. |
| **docs_generate_diagram** | Mermaid/PlantUML (dependency, class, module, ER). When you need a diagram. |
| **docs_generate_architecture** | Self-contained HTML architecture report. Deeper architecture documentation. |
| **docs_generate_epic** / **docs_generate_story** | Epic/story docs with AC and expert enrichment. Planning and product backlogs. |
| **docs_validate_epic** | Validates epic/story structure. When using epic/story workflows. |

---

## Tier 4 — Support / Optional

*Config, diagnostics, metrics, and optional enrichment. Use when needed.*

### TappsMCP

| Tool | Why Tier 4 |
|------|------------|
| **tapps_doctor** | Diagnose config and environment. When something is broken or unclear. |
| **tapps_set_engagement_level** | Switch enforcement (high/medium/low). When user explicitly wants stricter or lighter checks. |
| **tapps_dashboard** | TappsMCP metrics and trends. Observability, not daily workflow. |
| **tapps_stats** | Tool usage and call counts. Analytics and tuning. |
| **tapps_feedback** | Report tool effectiveness for adaptive learning. Optional improvement signal. |
| **tapps_manage_experts** | Manage expert knowledge (list, add, remove, validate). Admin/maintenance. |
| **tapps_server_info** | Server version and installed checkers. Usually covered by session_start. |

### DocsMCP

| Tool | Why Tier 4 |
|------|------------|
| **docs_config** | View or update DocsMCP settings. When changing defaults or debugging config. |

---

## Summary

| Tier | TappsMCP count | DocsMCP count | Use |
|------|----------------|---------------|-----|
| **1 – Critical** | 7 | 4 | Always in core workflow; prevent failures and hallucination. |
| **2 – High value** | 7 | 8 | Strongly recommended; clear quality/doc impact. |
| **3 – Situational** | 8 | 10 | For refactors, releases, planning, and specific doc types. |
| **4 – Support** | 7 | 1 | Config, diagnostics, metrics, admin. |

**What actually makes a difference:**
- **TappsMCP:** Session start → quick_check after edits → validate_changed + checklist before done; lookup_docs before using libraries; security_scan for security-sensitive work. Score and experts when you need depth.
- **DocsMCP:** Session start → project_scan and check_drift to see state and drift; generate_readme and generate_api for core artifacts; check_completeness, check_links, check_freshness to maintain quality.

Prioritizing Tier 1 and Tier 2 tools in prompts and automation will maximize impact; Tier 3 and 4 remain available for specific needs and operations.

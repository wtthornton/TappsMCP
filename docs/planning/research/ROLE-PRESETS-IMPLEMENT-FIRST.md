# Role presets to implement first (full list)

**Source:** Expanded from [DISCUSSION-PERSONA-ENVIRONMENT-AUTO-TOOLS.md](DISCUSSION-PERSONA-ENVIRONMENT-AUTO-TOOLS.md)  
**Use for:** Epic 79 server config (`tool_preset` / `default_role`) and Docker MCP profile names + tools.yaml.

---

## 1. Priority order

| Order | Preset slug    | Description              | Phase | Rationale |
|-------|----------------|--------------------------|-------|-----------|
| 1     | **reviewer**   | Code review & security   | 1     | User-requested; aligns with checklist "review" and tapps-reviewer subagent. |
| 2     | **planner**    | Epics, stories, planning | 1     | User-requested; needs DocsMCP epic/story + TappsMCP checklist/validate. |
| 3     | **frontend**   | Frontend / UX work       | 1     | User-requested; light quality set + lookup_docs + UX expert. |
| 4     | **developer**  | Daily feature/bugfix dev | 1     | Most common workflow; aligns with checklist feature/bugfix. |
| 5     | **full**       | General / all tools      | 1     | Fallback; current behavior when no role is set. |
| 6     | **security**   | Security audits          | 2     | Dedicated security workflow; checklist already has "security" task type. |
| 7     | **refactor**   | Refactoring & cleanup    | 2     | dead_code, dependency_graph, impact_analysis. |
| 8     | **docs**       | Documentation-only      | 2     | DocsMCP-heavy; minimal TappsMCP for repo quality. |
| 9     | **release**    | Release preparation      | 2     | validate_changed, dependency_scan, changelog, release_notes, check_links. |

- **Phase 1** (ship with Epic 79 or first follow-on): reviewer, planner, frontend, developer, full.  
- **Phase 2** (add when demand is clear): security, refactor, docs, release.

---

## 2. Preset definitions and tool sets

### reviewer — Code review & security

- **Primary use:** PR/code review, security checks, quality gates, checklist verification.
- **TappsMCP:** `tapps_session_start`, `tapps_quick_check`, `tapps_validate_changed`, `tapps_quality_gate`, `tapps_checklist`, `tapps_security_scan`, `tapps_score_file`, `tapps_dead_code`, `tapps_dependency_scan`, `tapps_project_profile`.
- **DocsMCP:** (none)
- **Approx. tools:** 10

### planner — Epics, stories & planning

- **Primary use:** Writing epics, stories, PRDs; planning docs; checklist and validate_changed for traceability.
- **TappsMCP:** `tapps_session_start`, `tapps_checklist`, `tapps_validate_changed`, `tapps_quality_gate`, `tapps_score_file`, `tapps_memory`, `tapps_consult_expert`, `tapps_project_profile`.
- **DocsMCP:** `docs_session_start`, `docs_project_scan`, `docs_check_drift`, `docs_generate_readme`, `docs_generate_epic`, `docs_generate_story`, `docs_generate_prd`, `docs_check_completeness`, `docs_module_map`, `docs_git_summary`.
- **Approx. tools:** 8 + 10 = 18

### frontend — Frontend / UX work

- **Primary use:** UI components, design systems, UX; light quality loop and library docs.
- **TappsMCP:** `tapps_session_start`, `tapps_quick_check`, `tapps_score_file`, `tapps_lookup_docs`, `tapps_consult_expert`, `tapps_quality_gate`, `tapps_project_profile`.
- **DocsMCP:** (none, or minimal: `docs_session_start`, `docs_api_surface` if documenting components)
- **Approx. tools:** 7

### developer — Daily feature/bugfix development

- **Primary use:** Feature work, bugfixes; full pipeline loop (quick_check, validate_changed, checklist, gate).
- **TappsMCP:** `tapps_session_start`, `tapps_quick_check`, `tapps_validate_changed`, `tapps_quality_gate`, `tapps_checklist`, `tapps_score_file`, `tapps_security_scan`, `tapps_lookup_docs`, `tapps_memory`, `tapps_consult_expert`, `tapps_project_profile`, `tapps_impact_analysis`.
- **DocsMCP:** (none)
- **Approx. tools:** 12

### full — General / all tools

- **Primary use:** No restriction; current default (all TappsMCP and, if connected, all DocsMCP).
- **TappsMCP:** (all 29)
- **DocsMCP:** (all 22 if combined)
- **Approx. tools:** 29 or 51 combined

### security — Security audits

- **Primary use:** Security-focused review; CVE scan, bandit, secrets, expert.
- **TappsMCP:** `tapps_session_start`, `tapps_security_scan`, `tapps_quality_gate`, `tapps_score_file`, `tapps_dependency_scan`, `tapps_consult_expert`, `tapps_validate_changed`, `tapps_checklist`, `tapps_project_profile`.
- **DocsMCP:** (none)
- **Approx. tools:** 9

### refactor — Refactoring & cleanup

- **Primary use:** Refactors; dead code, dependency graph, impact analysis before/after.
- **TappsMCP:** `tapps_session_start`, `tapps_quick_check`, `tapps_validate_changed`, `tapps_quality_gate`, `tapps_score_file`, `tapps_dead_code`, `tapps_dependency_graph`, `tapps_impact_analysis`, `tapps_memory`, `tapps_checklist`, `tapps_project_profile`.
- **DocsMCP:** `docs_session_start`, `docs_check_drift`, `docs_api_surface`, `docs_module_map` (optional).
- **Approx. tools:** 11 + 0–4 = 11–15

### docs — Documentation-only

- **Primary use:** Writing and maintaining docs; minimal code-quality tools.
- **TappsMCP:** `tapps_session_start`, `tapps_project_profile` (optional: `tapps_quick_check` if editing doc tooling).
- **DocsMCP:** `docs_session_start`, `docs_project_scan`, `docs_check_drift`, `docs_generate_readme`, `docs_generate_changelog`, `docs_generate_api`, `docs_generate_adr`, `docs_check_completeness`, `docs_check_links`, `docs_check_freshness`, `docs_module_map`, `docs_api_surface`, `docs_git_summary`.
- **Approx. tools:** 2 + 13 = 15

### release — Release preparation

- **Primary use:** Pre-release: validate changed files, CVE scan, changelog, release notes, link check.
- **TappsMCP:** `tapps_session_start`, `tapps_validate_changed`, `tapps_quality_gate`, `tapps_dependency_scan`, `tapps_checklist`, `tapps_project_profile`.
- **DocsMCP:** `docs_session_start`, `docs_git_summary`, `docs_generate_changelog`, `docs_generate_release_notes`, `docs_check_links`, `docs_check_freshness`.
- **Approx. tools:** 6 + 6 = 12

---

## 3. Implementation checklist (by preset)

| Preset     | Server config (`tool_preset` / `default_role`) | Docker MCP profile name   | tools.yaml or profile export |
|------------|-------------------------------------------------|----------------------------|------------------------------|
| reviewer   | Yes                                             | `tapps-reviewer`          | Yes                          |
| planner    | Yes                                             | `tapps-planning`          | Yes (tapps-mcp + docs-mcp)   |
| frontend   | Yes                                             | `tapps-frontend`          | Yes                          |
| developer  | Yes                                             | `tapps-developer`         | Yes                          |
| full       | Yes (no filter)                                 | (use existing full/minimal)| —                            |
| security   | Yes                                             | `tapps-security`          | Yes                          |
| refactor   | Yes                                             | `tapps-refactor`          | Yes                          |
| docs       | Yes                                             | `tapps-docs`              | Yes (docs-mcp heavy)         |
| release    | Yes                                             | `tapps-release`           | Yes                          |

---

## 4. Config and profile naming

- **Server config:** `tool_preset: reviewer | planner | frontend | developer | full | security | refactor | docs | release` and/or `default_role: <slug>` in `.tapps-mcp.yaml`.
- **Docker MCP profiles:** One profile per Phase 1/2 preset, e.g. `tapps-reviewer`, `tapps-planning`, `tapps-frontend`, `tapps-developer`, `tapps-security`, `tapps-refactor`, `tapps-docs`, `tapps-release`. Use existing `tapps-minimal` / `tapps-standard` / `tapps-full` for server selection; role presets add the **tool filter** (tools.yaml) per profile.

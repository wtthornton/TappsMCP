# Open Epics and Stories — Review

> **Superseded / update:** As of **2026-03-23**, use **`docs/planning/epics/README.md`** as the source of truth for active DocsMCP epics (80–88). Epic 84 (style validation) is **complete** in code and planning docs. This file remains a historical snapshot of epics 74–79 and related reconciliation.

**Date:** 2026-03-12
**Source:** `docs/planning/epics/README.md`, epic metadata, and implementation verification.

**Historical note (2026-03-12):** The summary below claimed all work complete; Epic 84 was later finished under `docs/planning/epics/`.

---

## Summary Table

| Epic | Name | Priority | LOE | Stories | Implementation status |
|------|------|----------|-----|---------|------------------------|
| **74** | Consumer Feedback — Automation & Pipeline UX | P1–P2 | ~2–3 wk | 5 | **Complete** (2026-03-11) |
| **79** | MCP Tool Count & Curation | P1–P2 | ~2–3 wk | 6 | **Complete** (2026-03-11) |
| **65** | Memory 2026 Best Practices (parent) | P1 | ~12–16 wk | 17 sub-epics | **Complete** (17/17, reconciled 2026-03-11) |
| **66** | Tool UX Improvements | P2–P3 | 2–5 days | 2 | **Complete** (both stories implemented) |
| **75** | LLM Artifact Structure & Prompt Generation | P2 | ~3–4 wk | 4 | **Complete** (2026-03-11) |
| **75-Docker** | Docker Pipeline Reliability & Tool Output UX | P1–P2 | ~2–3 wk | 5 | **Complete** (2026-03-12) |
| **76** | Skills Spec Compliance & Validation | P2 | ~1.5–2 wk | 4 | **Complete** (2026-03-11) |
| **77** | Agency-Agents Integration | P3 | ~2–4 days | 2 | **Complete** (2026-03-11) |
| **78** | Canonical Persona Injection (Prompt-Injection Defense) | P2 | ~1–2 wk | 4 | **Complete** (2026-03-12) |
| **70–73** | Expert Personas / Critical Rules / Enrichment / Communication | P2–P3 | 0 | **Complete** (all four) | See research doc |

---

## Epic 74: Consumer Feedback — Automation & Pipeline UX

- **Status (epic doc):** Proposed  
- **Goal:** Make TappsMCP first-class in automation/CI: batch quick_check, compact/JSON checklist, validate_changed guardrails, traceability, MCP config validation.
- **Priority:** P1–P2 | **LOE:** ~2–3 weeks

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 74.1 | tapps_quick_check batch mode | P2 | 3–5 days | **Done** — `file_paths` (comma-separated), per-file results, aggregate summary in `server_scoring_tools.py` |
| 74.2 | tapps_checklist compact/JSON output | P2 | 2–3 days | **Done** — `output_format` markdown/json/compact, `next_steps` + `full` in response; tests in `test_checklist_output_format.py` |
| 74.3 | tapps_validate_changed base_ref zero-diff warning | P1 | 1–2 days | **Done** — `_handle_no_changed_files` warns when `base_ref=HEAD` and 0 files; story doc: Complete |
| 74.4 | tapps_validate_changed optional traceability | P2 | 2–3 days | **Done** — `correlation_id` param echoed in response; `per_file_results` with stable keys; tests in `test_composite_tools.py` |
| 74.5 | MCP config file validation | P2 | 2–4 days | **Done** — `validators/mcp_config.py` + `base.py` dispatch; `tapps_validate_config` with `config_type="auto"` validates mcp.json/.mcp.json |

**Recommendation:** Update epic and README to **Complete**; all acceptance criteria are met.

---

## Epic 79: MCP Tool Count & Curation (2026 Best Practices)

- **Status (epic doc):** Proposed  
- **Goal:** Server-side tool subsets, Docker core-tools profile, docs for recommended subsets and role presets so tool count stays &lt;30.
- **Priority:** P1–P2 | **LOE:** ~2–3 weeks

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 79.1 | TappsMCP enabled_tools / disabled_tools | P1 | 3–5 days | **Done** — `TappsMCPSettings` + conditional registration; presets core/pipeline/full; tests `test_enabled_tools_config.py` |
| 79.2 | DocsMCP enabled_tools config | P2 | 2–3 days | **Done** — DocsMCP settings + conditional registration; preset core; tests in docs-mcp |
| 79.3 | Docker MCP core-tools profile + example tools.yaml | P1 | 2–3 days | **Done** — `docker-mcp/profiles/tapps-core-tools.yaml`, `examples/tools-core-tier1*.yaml`, `tapps-mcp-core` in catalog; README + DOCKER_MCP_TOOLKIT.md |
| 79.4 | Document recommended tool subsets and Docker tool filtering | P2 | 1–2 days | **Open** — Partially covered in README; dedicated doc or AGENTS.md section still useful |
| 79.5 | Role presets (tool_preset by role slug) in server config | P1 | 2–3 days | **Open** — Extend config with role slugs (reviewer, planner, etc.) per ROLE-PRESETS-IMPLEMENT-FIRST.md |
| 79.6 | Docker MCP role-named profiles (Phase 1) | P1 | 2–3 days | **Open** — Named profiles reviewer, planner, frontend, developer in Docker MCP |

**Recommendation:** Mark 79.1–79.3 complete in story docs; proceed with 79.4 (doc), 79.5 (role presets in config), 79.6 (Docker role profiles).

---

## Epic 65: Memory 2026 Best Practices (Parent)

- **Status (README):** Proposed  
- **Goal:** Memory stats in dashboard, markdown export, configurable capture prompt, auto-recall/auto-capture hooks, optional vector provider, hybrid search (RRF), reranking, session indexing, procedural tier, entity/relationship extraction, relationship-aware retrieval, retrieval policy, maintenance schedule, context budget, write-rules validation.
- **Priority:** P1 | **LOE:** ~12–16 weeks (17 sub-epics)

Many sub-epic markdown files list **Status: Complete** (e.g. 65.1, 65.2, 65.3, 65.5, 65.6, 65.9, 65.10, 65.12, 65.14, 65.15, 65.17). The README still shows all as Proposed.

| Sub-epic | Name | Priority | LOE | Notes |
|----------|------|----------|-----|--------|
| 65.1 | Memory Stats in Dashboard | P1 | 3–5 days | Doc: Complete |
| 65.2 | Markdown Export & Curation | P1 | 3–5 days | Doc: Complete |
| 65.3 | Configurable Capture Prompt & Write Rules | P1 | 4–6 days | Doc: Complete |
| 65.4 | Auto-Recall Hook | P1 | 1–1.5 wk | Complete (code: hook template, generation, tapps_init) |
| 65.5 | Auto-Capture Hook | P1 | 1.5–2 wk | Doc: Complete |
| 65.6 | Hook Integration in tapps_init | P1 | 2–3 days | Doc: Complete |
| 65.7 | Optional Vector/Embedding Provider | P1 | 1.5–2 wk | Complete (embeddings.py, persistence, config, retrieval) |
| 65.8 | Hybrid Search with RRF | P1 | 2–2.5 wk | Complete (fusion.py RRF, hybrid path in MemoryRetriever) |
| 65.9 | Optional Reranking | P2 | 1 wk | Doc: Complete |
| 65.10 | Session Indexing | P2 | 1.5–2 wk | Doc: Complete |
| 65.11 | Procedural Memory Tier | P2 | 1 wk | Complete (MemoryTier.procedural, decay, consolidation) |
| 65.12 | Entity/Relationship Extraction | P2 | 2–2.5 wk | Doc: Complete |
| 65.13 | Relationship-Aware Retrieval | P2 | 1–1.5 wk | Complete (expand_via_relations, retrieval integration) |
| 65.14 | Memory Retrieval Policy | P2 | 3–5 days | Doc: Complete |
| 65.15 | Memory Maintenance Schedule | P2 | 3–5 days | Doc: Complete |
| 65.16 | Context Budget for Memory Injection | P2 | 2–3 days | **Complete** (2026-03-11) |
| 65.17 | Optional Write Rules Validation | P2 | 2–3 days | Doc: Complete |

**Recommendation:** Epic 65 fully reconciled 2026-03-11. All 17 sub-epics Complete. No remaining Epic 65 work.

---

## Epic 66: Tool UX Improvements

- **Status:** Proposed  
- **Goal:** Better path hints for validate_changed; checklist validation note when 0 files.
- **Priority:** P2–P3 | **LOE:** 2–5 days

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 66.1 | validate_changed path mapping hints | P2 | 2–3 days | **Complete** (per README; no work left) |
| 66.2 | Checklist validation note for 0 files | P3 | 1–2 days | Story doc: Complete (note appended in checklist flow) |

**Recommendation:** Both stories complete; Epic 66 can be marked **Complete** in README when convenient.

---

## Epic 75: LLM Artifact Structure & Prompt Generation

- **Status:** **Complete** (2026-03-11)  
- **Goal:** Unified schema (Common, Epic, Story, Prompt); PromptConfig and prompt generator; `docs_generate_prompt`; optional compact LLM view.
- **Priority:** P2 | **LOE:** ~3–4 weeks  
- **Dependencies:** DocsMCP epic/story generators; design doc LLM-ARTIFACT-STRUCTURE-COMMON-EPIC-STORY-PROMPT.md

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 75.1 | PromptConfig and prompt schema | P2 | 2–3 days | **Complete** |
| 75.2 | PromptGenerator and docs_generate_prompt | P2 | 3–4 days | **Complete** |
| 75.3 | Common schema docs and epic/story alignment | P2 | 1–2 days | **Complete** — LLM-ARTIFACT-COMMON-SCHEMA.md, AGENTS.md reference |
| 75.4 | Optional compact LLM view | P3 | 2–3 days | **Complete** — `generate_compact()`, `docs_generate_prompt(compact_llm_view=True)`, tests |

---

## Epic 76: Skills Spec Compliance & Validation

- **Status:** Proposed  
- **Goal:** Description ≤1024 chars; Claude allowed-tools space-delimited; Cursor allowed-tools vs mcp_tools; optional skills spec validator.
- **Priority:** P2 | **LOE:** ~1.5–2 weeks  
- **Dependencies:** Epic 36 (skills)

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 76.1 | Description length validation (≤1024 chars) | P2 | 1 day | Open |
| 76.2 | Claude allowed-tools: space-delimited | P2 | 1–2 days | Open |
| 76.3 | Cursor: allowed-tools vs mcp_tools | P2 | 1 day | Open |
| 76.4 | Optional skills spec validator (test or CLI) | P3 | 1–2 days | Open |

---

## Epic 77: Agency-Agents Integration

- **Status:** Proposed  
- **Goal:** Document TappsMCP + agency-agents coexistence; optional init/AGENTS.md hint for “more agents.”
- **Priority:** P3 | **LOE:** ~2–4 days (docs + optional hint)

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 77.1 | Document TappsMCP + agency-agents coexistence | P3 | 1–2 days | Open |
| 77.2 | Optional init/AGENTS.md hint for agency-agents | P3 | 0.5 day | Open |

---

## Epic 78: Canonical Persona Injection (Prompt-Injection Defense)

- **Status:** Proposed  
- **Goal:** Tool to resolve persona name → allowlisted path and return markdown; rule to prepend canonical persona; document as prompt-injection defense; optional audit log.
- **Priority:** P2 | **LOE:** ~1–2 weeks  
- **Dependencies:** Epic 12; path validator

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| 78.1 | Tool: tapps_get_canonical_persona | P2 | 3–5 days | Open |
| 78.2 | Rule/instruction: prepend canonical persona | P2 | 1–2 days | Open |
| 78.3 | Document canonical persona injection | P2 | 0.5 day | Open |
| 78.4 | Optional audit log (persona request + risk pattern) | P3 | 0.5 day | Open |

---

## Epics 70–73: Expert Agency-Personas Leverage

- **Status:** **All four epics Complete.** See [2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md](../research/2026-EXPERT-PERSONAS-EPICS-70-73-RESEARCH.md) and [EPIC-72/story-72-content-plan.md](EPIC-72/story-72-content-plan.md).
- **Goal:** Complete expert personas, critical rules/stance, knowledge enrichment (metrics, workflow, templates), optional communication style.
- **Priority:** P2–P3 | **LOE:** 0 (all done)

| Epic | Name | Priority | LOE | Stories (examples) | Status |
|------|------|----------|-----|-------------------|--------|
| 70 | Expert Persona Completion | P2 | 0 | 70.1 done; 70.2 persona guidelines in knowledge README | **Complete** |
| 71 | Expert Critical Rules & Default Stance | P2 | 0 | 71.1–71.3 done (schema, engine, Security/Testing/Accessibility pilots) | **Complete** |
| 72 | Expert Knowledge Enrichment | P2 | 0 | 72.1–72.4 done (5/5/3 domains + README; content plan confirms) | **Complete** |
| 73 | Expert Communication Style | P3 | 0 | 73.1 done (schema, engine, Security/Testing pilots) | **Complete** |

---

## Status (2026-03-12)

**Historical snapshot only.** For current DocsMCP Documentation Excellence epics (80–88), see `docs/planning/epics/README.md` (Epic 84 completed 2026-03-23).

- **Epics 0–79 (TappsMCP):** All complete, including Docker Pipeline Reliability (75-Docker) and Canonical Persona Injection (78) completed 2026-03-12.
- **Epics 0–21 (DocsMCP):** All complete.
- **Platform Epics 12–13:** All complete.
- **Promotion tiers P0–P4:** All complete.
- **Epic 65 sub-epics (17/17):** All reconciled Complete.
- See [ROADMAP.md](../ROADMAP.md) for future enhancement opportunities.

---

## References

- **Epic index:** `docs/planning/epics/README.md`
- **Roadmap:** `docs/planning/ROADMAP.md`
- **Epic 74:** `EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md`
- **Epic 79:** `EPIC-79-MCP-TOOL-COUNT-CURATION.md`
- **Role presets:** `docs/planning/research/ROLE-PRESETS-IMPLEMENT-FIRST.md`
- **Tool tiers:** `docs/planning/TOOL-TIER-RANKING.md`

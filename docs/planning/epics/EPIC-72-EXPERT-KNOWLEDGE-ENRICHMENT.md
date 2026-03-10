# Epic 72: Expert Knowledge Enrichment (Agency-Personas Leverage)

<!-- docsmcp:start:metadata -->
**Status:** Draft
**Priority:** P2
**Estimated LOE:** ~1–2 weeks (1 developer, content-heavy)
**Dependencies:** None (knowledge content only; no schema change)
**Source:** [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md)
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Enrich built-in expert knowledge bases so RAG retrieval returns **success metrics**, **workflow hints**, **deliverable templates**, and **when-to-use** guidance. No ExpertConfig or engine changes; all improvements are additive Markdown content in existing knowledge directories. This makes consultation answers more actionable, process-oriented, and aligned with "what good looks like" per domain.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Agency-agents define Success Metrics ("Page load <3s," "Lighthouse >90"), Workflow Process ("Step 1 → Step 2 → …"), and Technical Deliverables (report templates, checklists). TappMCP experts today have strong pattern/checklist content but often lack explicit success thresholds, step-by-step process sections, and copy-pasteable templates. Adding these as standard sections in knowledge files lets RAG retrieve them and improves answer quality without changing tooling.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] At least 5 domains have a "Success metrics" or "Definition of done" section in at least one key knowledge file
- [ ] At least 5 domains have "Typical steps" or "Recommended process" (workflow hints) in at least one knowledge file
- [ ] At least 3 domains have a deliverable template (report, checklist, or snippet) in knowledge (new or existing file, e.g. `_templates.md`)
- [ ] Knowledge README documents the enrichment pattern (success metrics, workflow hints, templates) for maintainers
- [ ] RAG index rebuild picks up changes (no code change to ingestion; existing behavior)
- [ ] All existing expert tests pass
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### Story 72.1: Add Success metrics / Definition of done sections to key knowledge files

> **As a** user of tapps_consult_expert, **I want** expert answers to cite measurable success criteria when relevant, **so that** I know what "good" looks like (e.g. coverage thresholds, latency, WCAG level).

**Points:** 2 | **Size:** M

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/testing/` (e.g. best-practices.md or new success-metrics.md)
- `packages/tapps-core/src/tapps_core/experts/knowledge/performance/` (e.g. optimization or anti-patterns)
- `packages/tapps-core/src/tapps_core/experts/knowledge/accessibility/` (e.g. wcag-2.1.md or testing-accessibility.md)
- `packages/tapps-core/src/tapps_core/experts/knowledge/code-quality-analysis/` (e.g. quality-gates.md)
- `packages/tapps-core/src/tapps_core/experts/knowledge/security/` (e.g. one key file)

**Tasks:**
- [ ] Add a "## Success metrics" or "## Definition of done" section to at least one file per domain above (5 domains). Include concrete thresholds where applicable (e.g. test coverage ≥80%, LCP <2.5s, WCAG 2.1 AA, zero high/critical findings).
- [ ] Use clear headers so RAG chunking preserves the section
- [ ] Keep sections concise (bullet list or short paragraph)

**Acceptance Criteria:**
- [ ] At least 5 domains have success metrics/definition-of-done content
- [ ] Content is retrievable (headers and wording consistent with existing style)
- [ ] Knowledge README updated to describe this pattern

**Definition of Done:**
- [ ] Content added, README updated, no code changes

---

### Story 72.2: Add workflow hints (Typical steps / Recommended process) to knowledge

> **As a** user of tapps_consult_expert, **I want** experts to suggest a sequence of steps when relevant, **so that** I get a process (e.g. "1. Identify scope 2. Choose strategy 3. Write tests 4. Run and iterate") not only isolated facts.

**Points:** 2 | **Size:** M

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/testing/` (e.g. test-strategies.md or best-practices.md)
- `packages/tapps-core/src/tapps_core/experts/knowledge/security/` (e.g. threat-modeling.md or secure-coding)
- `packages/tapps-core/src/tapps_core/experts/knowledge/api-design-integration/` (e.g. restful-api-design.md)
- `packages/tapps-core/src/tapps_core/experts/knowledge/database-data-management/` (e.g. migration-strategies or database-design)
- `packages/tapps-core/src/tapps_core/experts/knowledge/development-workflow/` (e.g. ci-cd-patterns)

**Tasks:**
- [ ] Add "## Typical steps" or "## Recommended process" sections to at least one file per domain above (5 domains). Use numbered steps; keep each step to one line where possible.
- [ ] Ensure sections are self-contained enough for RAG to retrieve and cite

**Acceptance Criteria:**
- [ ] At least 5 domains have workflow-hint content
- [ ] Knowledge README documents the "workflow hints" pattern

**Definition of Done:**
- [ ] Content added, README updated

---

### Story 72.3: Add deliverable templates (report / checklist) to selected domains

> **As a** user of tapps_consult_expert, **I want** experts to reference or paste report/checklist templates when relevant, **so that** I get consistent, copy-pasteable outputs (e.g. security review report, testing checklist).

**Points:** 2 | **Size:** M

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/security/` — e.g. new `security-review-template.md` or section in existing file
- `packages/tapps-core/src/tapps_core/experts/knowledge/testing/` — e.g. `testing-checklist.md` or section in best-practices.md
- `packages/tapps-core/src/tapps_core/experts/knowledge/accessibility/` — e.g. accessibility-audit-checklist.md or section in testing-accessibility.md

**Tasks:**
- [ ] Add at least one deliverable template per domain above (3 domains). Options: dedicated `_templates.md` per domain or a "## Template" / "## Checklist" section in an existing file. Use markdown (headers, lists, code blocks for snippets).
- [ ] Templates should be short and actionable (e.g. 10–20 line checklist or report outline)
- [ ] Document in knowledge README that templates are intended for RAG retrieval and copy-paste by users

**Acceptance Criteria:**
- [ ] At least 3 domains have a template or checklist in knowledge
- [ ] Content is structured so RAG can retrieve and the answer can reference or include it

**Definition of Done:**
- [ ] Templates added, README updated

---

### Story 72.4: Document when-to-use and knowledge enrichment patterns in README

> **As a** maintainer adding or editing expert knowledge, **I want** the knowledge README to describe success metrics, workflow hints, templates, and when-to-use, **so that** new content follows a consistent pattern.

**Points:** 1 | **Size:** S

**Files:**
- `packages/tapps-core/src/tapps_core/experts/knowledge/README.md`

**Tasks:**
- [ ] Add section "Knowledge enrichment patterns" (or extend existing "Knowledge Base Best Practices") with: Success metrics / Definition of done; Typical steps / Recommended process; Deliverable templates; When-to-use (one-line "Use this expert when…" can live in description or first file). Reference agency-personas summary as inspiration, not requirement.
- [ ] Keep guidance concise; point to 1–2 example files if helpful

**Acceptance Criteria:**
- [ ] README explains all four enrichment types and where they fit
- [ ] Future contributors can add similar content without guessing structure

**Definition of Done:**
- [ ] README updated and reviewed
<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **No schema or engine changes.** All work is additive Markdown in `tapps_core/experts/knowledge/<domain>/`.
- **RAG:** Existing chunking and indexing; rebuild index after content changes (delete `.tapps-mcp/rag_index/<domain>/` or full `rag_index/` as per ARCHITECTURE_CACHE_AND_RAG.md).
- **AGENTS.md:** "Domain hints for tapps_consult_expert" already maps context → domain; optional "when to use this expert" in knowledge is for RAG retrieval when user query is ambiguous.
<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope

- Changing ExpertConfig or engine
- Adding new expert domains
- Automating RAG index refresh on file edit (manual delete/rebuild remains)
<!-- docsmcp:end:non-goals -->

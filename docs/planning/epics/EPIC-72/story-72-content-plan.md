# Epic 72: Content Plan — Success Metrics, Workflow Hints, Templates

**Date:** 2026-03-11  
**Purpose:** Concrete file + section assignments for 72.1, 72.2, 72.3.  
**Source:** Grep audit of `packages/tapps-core/src/tapps_core/experts/knowledge/`.

---

## 1. Current coverage (audit)

### 72.1 Success metrics / Definition of done

| Domain | File | Section | Status |
|--------|------|---------|--------|
| testing | best-practices.md | ## Success metrics | ✓ |
| code-quality-analysis | quality-gates.md | ## Success metrics | ✓ |
| security | secure-coding-practices.md | ## Success metrics | ✓ |
| performance | optimization-patterns.md | ## Success metrics | ✓ |
| accessibility | testing-accessibility.md | ## Success metrics | ✓ |

**Verdict:** 5 domains — **acceptance criteria met.** Optional: add to api-design-integration, database-data-management for stronger coverage.

### 72.2 Typical steps / Recommended process

| Domain | File | Section | Status |
|--------|------|---------|--------|
| api-design-integration | restful-api-design.md | ## Typical steps | ✓ |
| database-data-management | migration-strategies.md | ## Typical steps | ✓ |
| security | threat-modeling.md | ## Recommended process | ✓ |
| development-workflow | ci-cd-patterns.md | ## Typical steps | ✓ |
| testing | test-strategies.md | ## Typical steps | ✓ |

**Verdict:** 5 domains — **acceptance criteria met.** Optional: add to accessibility, cloud-infrastructure for stronger coverage.

### 72.3 Deliverable templates (checklist / report outline)

| Domain | File | Section | Status |
|--------|------|---------|--------|
| security | secure-coding-practices.md | ## Checklist | ✓ |
| testing | best-practices.md | ## Checklist | ✓ |
| accessibility | testing-accessibility.md | ## Checklist | ✓ |

**Verdict:** 3 domains — **acceptance criteria met.** Optional: add `_templates.md` or ## Template section to api-design-integration, code-quality-analysis for stronger coverage.

---

## 2. Epic 72 status: acceptance criteria met

All three stories (72.1–72.3) already meet the acceptance criteria:
- 72.1: 5 domains with Success metrics ✓
- 72.2: 5 domains with Typical steps / Recommended process ✓
- 72.3: 3 domains with Checklist ✓

**72.4** (Knowledge README enrichment patterns) was already done before this plan.

**Recommended action:** Mark Epic 72 **Complete** in epic doc and README. Optional follow-up: add sections to additional domains (see §3) for richer coverage.

---

## 3. Optional enhancements (post-completion)

If you want to extend beyond the minimum:

### Success metrics — add to 1–2 more domains

| Domain | Target file | Section to add |
|--------|-------------|----------------|
| api-design-integration | restful-api-design.md | `## Success metrics` — e.g. latency <200ms, availability 99.9%, deprecation notice ≥6 months |
| database-data-management | migration-strategies.md | `## Success metrics` — e.g. zero data loss, rollback tested, downtime <5 min |

### Typical steps — add to 1–2 more domains

| Domain | Target file | Section to add |
|--------|-------------|----------------|
| accessibility | testing-accessibility.md | `## Typical steps` — e.g. 1. Keyboard nav 2. Screen reader 3. Color contrast 4. Form labels 5. Focus order |
| cloud-infrastructure | kubernetes-patterns.md (or infrastructure-as-code.md) | `## Typical steps` — e.g. 1. Define resources 2. Apply 3. Verify 4. Rollback path |

### Templates — add to 1–2 more domains

| Domain | Target file | Section to add |
|--------|-------------|----------------|
| api-design-integration | restful-api-design.md | `## API design checklist` — 10–15 item copy-pasteable checklist |
| code-quality-analysis | quality-gates.md | `## Gate checklist` — copy-pasteable pre-merge checklist |

---

## 4. Implementation notes

- **RAG rebuild:** After editing any knowledge file, delete `{project_root}/.tapps-mcp/rag_index/{domain}/` (or full `rag_index/`) so the next `tapps_consult_expert` call rebuilds the index.
- **Section format:** Use `## Success metrics`, `## Typical steps`, `## Recommended process`, or `## Checklist` — these headers are what RAG chunking preserves.
- **Knowledge README:** Already documents all four patterns in "Knowledge Enrichment Patterns" (72.4 done).

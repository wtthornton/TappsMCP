# Epic 17: Documentation Polish & Validation

**Status:** Open
**Priority:** P2
**Estimated LOE:** ~1 week
**Dependencies:** Epics 14–16 (best applied after core generation improvements)
**Blocks:** None

---

## Goal

Final quality pass on DocsMCP output: filter re-export noise, fix grammar patterns, add freshness metadata, and compute documentation quality scores.

## Acceptance Criteria

- [ ] Re-export-only `__init__.py` modules detected and deduplicated in API docs
- [ ] Grammar/formatting issues (pluralization, heading levels, whitespace) fixed
- [ ] Generated docs include freshness metadata (last modified date, generation timestamp)
- [ ] Documentation quality score computed and included in generation results
- [ ] All existing DocsMCP tests pass; new tests for each story

---

## Stories

### 17.1 — Re-Export Detection and Filtering

**Priority:** High | **Points:** 3

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/api_docs.py` — filtering
- `packages/docs-mcp/src/docs_mcp/extractors/python.py` — detection

**Tasks:**
- Detect `__init__.py` files that only contain `from X import Y` statements (no original definitions)
- Mark re-exported symbols with source module reference instead of duplicating documentation
- Add `include_reexports` parameter (default `False`) to control behavior
- Estimate size reduction and include in metrics

**Definition of Done:** API docs for monorepos with re-export wrappers are ~30% smaller.

---

### 17.2 — Grammar and Formatting Fixes

**Priority:** Medium | **Points:** 2

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/readme.py` — pluralization
- `packages/docs-mcp/src/docs_mcp/generators/api_docs.py` — heading levels
- `packages/docs-mcp/src/docs_mcp/generators/guides.py` — whitespace

**Tasks:**
- Fix `"1 public APIs"` → `"1 public API"` (and similar count+noun patterns)
- Ensure no skipped heading levels in generated markdown (h1 → h2 → h3, not h1 → h3)
- Normalize trailing whitespace and double blank lines

**Definition of Done:** Generated docs pass common markdown linting rules.

---

### 17.3 — Documentation Freshness Hints

**Priority:** Medium | **Points:** 3

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/api_docs.py` — footer
- `packages/docs-mcp/src/docs_mcp/analyzers/git_history.py` — last modified dates

**Tasks:**
- Include `last_modified` date from git history per module in API docs
- Add "Auto-generated on {date} by DocsMCP" footer to generated docs
- In validation tools, warn when source file changed after doc generation date

**Definition of Done:** Generated docs include freshness context; stale docs detectable.

---

### 17.4 — Documentation Quality Score

**Priority:** Low | **Points:** 2

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/api_docs.py` — scoring
- `packages/docs-mcp/src/docs_mcp/validators/completeness.py` — metrics

**Tasks:**
- After generation, compute: documented vs total public APIs (coverage %)
- Compute: avg docstring length, count of missing returns, count of missing examples
- Include score in generation result metadata
- Render as `*Documentation coverage: X%*` footer (already partially exists)

**Definition of Done:** Every API doc generation includes a quality score in metadata.

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Re-export detection misses complex patterns | Low | Focus on common `from X import Y` pattern |
| Git history unavailable in CI | Low | Gracefully degrade to "unknown" date |
| Quality score too strict for small projects | Low | Score is informational, not a gate |

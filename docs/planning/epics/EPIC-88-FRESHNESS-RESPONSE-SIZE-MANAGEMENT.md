# Epic 88: Freshness Tool Response Size Management

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** None (docs-mcp validators fully implemented)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that `docs_check_freshness` can scale to large projects without exceeding MCP response size limits. Today, calling this tool on a project with hundreds of doc files returns a 131K+ character JSON payload that breaches the protocol's token ceiling, producing an error instead of actionable results. Every other validation tool in docs-mcp already has truncation or filtering — freshness is the sole outlier. Fixing this brings freshness into parity with the validation suite and makes it reliable for real-world monorepos.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Add response size management to `docs_check_freshness` — including pagination (`max_items`), path scoping, staleness-first sorting, summary-only mode, and category distribution metadata — so the tool returns bounded, actionable results regardless of project size, consistent with the patterns established by `docs_check_drift`, `docs_check_diataxis`, and `docs_check_cross_refs`.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

- **Production failure observed:** HomeIQ's `docs_check_freshness` call returned 131,165 characters, exceeding MCP's maximum allowed response size. The tool returned an error instead of results.
- **Inconsistency in validation suite:** `docs_check_drift` has `max_items` + `total_items`/`showing` metadata. `docs_check_diataxis` and `docs_check_cross_refs` hardcode `[:50]` truncation. `docs_check_freshness` returns all items unbounded — the only validation tool without size management.
- **2026 MCP best practices:** The MCP `2025-11-25` protocol has NO built-in pagination for `tools/call` results (only for `tools/list`, `resources/list`, `prompts/list`). Response size management must be a tool parameter convention. Progressive disclosure and bounded responses are standard for MCP tools targeting LLM consumers. LLMs benefit from stalest-first ordering (most actionable items first), a human-readable `summary` string in every response, and category summaries over raw item dumps.
- **Established internal patterns:** tapps-mcp's memory tools use progressive summarization (full entries for first N, then summaries). The `tapps_report` tool caps at `max_files=20`. The memory injection system uses token-budget-aware truncation (`estimate_tokens` + budget loop). These patterns should be adopted consistently.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `docs_check_freshness` accepts `max_items` parameter (default 50, 0 = unlimited)
- [ ] `docs_check_freshness` accepts `path` parameter to scope scan to a subdirectory
- [ ] Response includes `total_items`, `total_unfiltered`, and `showing` metadata fields (matching `docs_check_drift` pattern)
- [ ] Items are sorted by `age_days` descending (stalest first) before truncation
- [ ] `docs_check_freshness` accepts `summary_only` parameter that returns only aggregate scores and category counts without per-file items
- [ ] Response includes `category_counts` breakdown (`{"fresh": N, "aging": N, "stale": N, "ancient": N}`)
- [ ] Response includes a human-readable `summary` string for LLM consumption
- [ ] All existing tests pass; new tests cover each new parameter and edge case
- [ ] `mypy --strict` passes on all changed files
- [ ] `ruff check` and `ruff format --check` pass on all changed files
- [ ] HomeIQ-scale projects (500+ doc files) return bounded responses under MCP limits

<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### [88.1](EPIC-88/story-88.1-staleness-sort-and-category-counts.md) -- Staleness-First Sort & Category Counts

**Points:** 3

Add staleness-descending sort to `FreshnessChecker.check()` and include a `category_counts` dict in `FreshnessReport`. This is the foundational change — sorting ensures truncation always keeps the most actionable (stalest) items, and category counts provide the aggregate view that survives truncation.

**Tasks:**
- [ ] Add `category_counts: dict[str, int]` field to `FreshnessReport` model
- [ ] Compute category counts during the check loop in `FreshnessChecker.check()`
- [ ] Sort `items` by `age_days` descending before returning the report
- [ ] Update existing tests to expect sorted order and category counts
- [ ] Add new tests: empty project, single file, mixed categories

**Definition of Done:** `FreshnessReport` always returns items sorted stalest-first with accurate `category_counts`.

---

### [88.2](EPIC-88/story-88.2-max-items-pagination.md) -- max_items Pagination

**Points:** 5

Add `max_items` parameter to the `docs_check_freshness` tool handler, following the exact pattern from `docs_check_drift`. Apply truncation after sorting, and include `total_items` / `total_unfiltered` / `showing` metadata in the response envelope.

**Tasks:**
- [ ] Add `max_items: int = 0` parameter to `docs_check_freshness()` in `server_val_tools.py`
- [ ] Update docstring to document the parameter (0 = default 50, explicit value overrides)
- [ ] Apply `items[:max_items]` truncation after staleness sort
- [ ] Add `total_items`, `total_unfiltered`, `showing` fields to response data dict
- [ ] Default to 50 when `max_items` is 0 (consistent with cross_refs/diataxis hardcoded 50)
- [ ] Add a `summary` string to the response (e.g., `"47 docs: 12 fresh, 8 aging, 15 stale, 12 ancient (score: 42.3)"`)
- [ ] Add tests: default truncation at 50, explicit max_items override, max_items=-1 or 0 edge cases, summary string format

**Definition of Done:** Response size is bounded by default; callers can override with explicit `max_items`.

---

### [88.3](EPIC-88/story-88.3-path-scoping.md) -- Path Scoping

**Points:** 3

Add a `path` parameter to scope the freshness scan to a specific subdirectory. This lets callers check freshness of `docs/` without scanning the entire project tree.

**Tasks:**
- [ ] Add `path: str = ""` parameter to `docs_check_freshness()` in `server_val_tools.py`
- [ ] Update docstring to document path scoping behavior
- [ ] Resolve `path` relative to `project_root` and validate it exists
- [ ] Pass scoped root to `FreshnessChecker.check()` (or filter items post-scan)
- [ ] Ensure `file_path` in items remains relative to `project_root` (not the scoped path)
- [ ] Add tests: scoped to subdirectory, invalid path error, empty subdirectory

**Definition of Done:** Callers can scope freshness checks to any subdirectory.

---

### [88.4](EPIC-88/story-88.4-summary-only-mode.md) -- Summary-Only Mode

**Points:** 3

Add a `summary_only` boolean parameter that returns only aggregate metrics (freshness score, average age, category counts) without per-file items. This is ideal for dashboard use cases where the caller only needs the headline numbers.

**Tasks:**
- [ ] Add `summary_only: bool = False` parameter to `docs_check_freshness()` in `server_val_tools.py`
- [ ] Update docstring to document summary-only behavior
- [ ] When `summary_only=True`, set `items` to empty list in response and skip serialization
- [ ] Always include `total_items` count even in summary mode so caller knows how many files exist
- [ ] Add tests: summary_only returns no items but has scores and counts

**Definition of Done:** `summary_only=True` returns a compact response suitable for dashboards.

---

### [88.5](EPIC-88/story-88.5-freshness-filter.md) -- Freshness Category Filter

**Points:** 3

Add a `freshness` parameter to filter items by category (e.g., `freshness="stale,ancient"` to see only files needing attention). This complements `max_items` by letting callers focus on specific staleness tiers.

**Tasks:**
- [ ] Add `freshness: str = ""` parameter to `docs_check_freshness()` in `server_val_tools.py`
- [ ] Parse comma-separated values, validate against known categories
- [ ] Filter items after sorting, before truncation
- [ ] `total_items` reflects filtered count; `total_unfiltered` reflects pre-filter count
- [ ] Add tests: single category filter, multiple categories, invalid category ignored

**Definition of Done:** Callers can filter to specific freshness categories for targeted remediation.

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **Follow `docs_check_drift` pattern exactly** for `max_items` / `total_items` / `total_unfiltered` / `showing` fields. This ensures consuming LLMs get a consistent response shape across all validation tools.
- **Sort at the checker level** (in `FreshnessChecker.check()`), not in the tool handler. The report should always be sorted — unsorted reports are never useful.
- **Category counts belong in the Pydantic model** (`FreshnessReport`), not added ad-hoc in the handler. This keeps the data contract clean.
- **Default `max_items` of 50** aligns with the hardcoded limits in `docs_check_diataxis` (50) and `docs_check_cross_refs` (50). Using 0-means-default matches the `docs_check_drift` convention.
- **Path scoping:** Prefer passing the scoped path directly to `_find_doc_files()` rather than post-filtering, to avoid scanning the entire tree unnecessarily.
- **Progressive disclosure for LLMs (2026 pattern):** The combination of `summary_only` (headline metrics), `freshness` filter (targeted categories), and `max_items` (bounded items) gives LLMs three levels of detail — they can start with a summary and drill down only when needed.
- **Include a `summary` string in every response** — a one-liner like `"47 docs scanned: 12 fresh, 8 aging, 15 stale, 12 ancient (score: 42.3/100)"`. This gives the LLM a human-readable read before parsing structured data. Already done well in `tapps_dead_code`; replicate here.
- **MCP `structuredContent` (future):** The SDK's `CallToolResult` supports separating text content (for LLM context) from `structuredContent` (machine-readable). This is a cross-cutting concern for all tools and out of scope for this epic, but the `summary` field we add here will map naturally to the text content slot when adopted.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- **Cursor-based pagination** — while 2026 best practice for mutable backing stores (SQLite, live APIs), freshness results are scanned from a stable filesystem. `max_items` with staleness-first ordering covers the primary use case. If cross-tool cursor pagination is adopted later (e.g., base64-encoded opaque tokens as in `tapps_core/memory`), freshness can adopt it then.
- **Streaming/SSE responses** — MCP `2025-11-25` `CallToolResult` is atomic (no streaming). Streamable HTTP transport exists but doesn't support incremental tool results.
- **Token-budget-aware truncation utility** — the research identified `tapps_core/memory/injection.py`'s budget loop as a candidate for promotion to `server_helpers.py` as a reusable `budget_truncate()`. This is a cross-cutting concern for all tools, not specific to freshness.
- **`structuredContent` migration** — separating summary text from machine-readable data in `CallToolResult` is a valuable cross-cutting improvement but affects all 31 tools.
- **Cross-tool response size middleware** — a generic response truncation layer across all docs-mcp tools. Useful long-term, but per-tool implementation is appropriate now.

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Max response size | 131K+ chars (unbounded) | <20K chars (default) | Measure response size with default params on 500+ file project |
| Response consistency | 1 of 7 val tools unbounded | 0 of 7 unbounded | Audit all validation tool response shapes |
| Error rate on large projects | 100% (always exceeds limit) | 0% | Call tool on HomeIQ-scale project |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. **Story 88.1** — Sort + category counts (foundation for all other stories)
2. **Story 88.2** — max_items pagination (fixes the production error)
3. **Story 88.3** — Path scoping (reduces scan scope)
4. **Story 88.4** — Summary-only mode (dashboard use case)
5. **Story 88.5** — Freshness filter (targeted remediation)

Stories 3-5 are independent of each other and can be parallelized after Story 88.2.

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Breaking existing callers expecting full item list | Low | Medium | Default behavior returns 50 items (generous), `max_items` allows override |
| Category counts mismatch with filtered items | Low | Low | Compute counts before filtering; include both `total_unfiltered` and `total_items` |
| Path scoping returns items with wrong relative paths | Medium | Medium | Test that `file_path` is always relative to `project_root`, not scoped path |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/validators/freshness.py` | 88.1 | Update — add `category_counts` to model, sort items |
| `packages/docs-mcp/src/docs_mcp/server_val_tools.py` | 88.2, 88.3, 88.4, 88.5 | Update — add parameters, truncation, filtering |
| `packages/docs-mcp/tests/unit/test_freshness.py` | 88.1 | Update — test sort order and category counts |
| `packages/docs-mcp/tests/unit/test_validators.py` | 88.2, 88.3, 88.4, 88.5 | Update — test new tool parameters |

<!-- docsmcp:end:files-affected -->

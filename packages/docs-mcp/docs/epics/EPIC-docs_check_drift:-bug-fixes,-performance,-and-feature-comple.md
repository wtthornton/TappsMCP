# docs_check_drift: Bug fixes, performance, and feature completeness

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** 2
**Estimated LOE:** ~4-5 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are improving docs_check_drift so that it correctly detects code-documentation drift with accurate scoring, covers all public API symbols, and scales efficiently to large projects.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Eliminate correctness bugs in drift detection, implement the `since` parameter for incremental checks, optimize file I/O and memory usage, and extend coverage to public constants and missing docstring guidance.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The current drift detector has 15 documented issues spanning correctness (inverted score semantics, broken filters), performance (triple file reads, flat doc corpus), and missing features (unimplemented `since` parameter). Users cannot reliably identify undocumented changes, and large projects hit performance cliffs. Fixing these issues is load-bearing for adoption.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] 1. All HIGH-severity bugs resolved and tested
2. Performance improvements reduce file I/O by 60%+ and memory usage for doc scanning
3. `since` parameter gates work on changed files only
4. Public constants included in drift detection
5. All stories closed and merged to master

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 0.1 -- docs_check_drift: Fix drift_score docstring and search_names filter bugs

**Points:** 5

Fix three HIGH-severity bugs: (1) drift_score docstring says 'higher=less drift' but should say 'higher=more drift', (2) search_names filter searches truncated description only showing first 5 symbols, (3) _qualify function ignores src/ layout prefix breaking ignore_patterns for src-layout projects.

**Tasks:**
- [ ] Implement docs_check_drift: fix drift_score docstring and search_names filter bugs
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Fix drift_score docstring and search_names filter bugs is implemented, tests pass, and documentation is updated.

---

### 0.2 -- docs_check_drift: Eliminate triple file read per Python file

**Points:** 8

Each Python file is read and parsed 3 times: once for empty-file check, once in APISurfaceAnalyzer, and once in _collect_docstrings. Refactor to single AST parse, share results across drift and docstring analysis.

**Tasks:**
- [ ] Implement docs_check_drift: eliminate triple file read per python file
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Eliminate triple file read per Python file is implemented, tests pass, and documentation is updated.

---

### 0.3 -- docs_check_drift: Optimize doc corpus scanning from flat string to inverted index

**Points:** 5

Replace single concatenated doc string with inverted index (token → bool). Current approach loads entire project docs into memory and does naive substring scans. New approach is faster and uses far less memory, especially for large projects.

**Tasks:**
- [ ] Implement docs_check_drift: optimize doc corpus scanning from flat string to inverted index
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Optimize doc corpus scanning from flat string to inverted index is implemented, tests pass, and documentation is updated.

---

### 0.4 -- docs_check_drift: Implement `since` parameter for incremental drift checking

**Points:** 8

The `since` parameter is a documented but unimplemented stub. Implement via git log to scope which files changed since a given ref/date, reducing scan scope for CI/incremental workflows.

**Tasks:**
- [ ] Implement docs_check_drift: implement `since` parameter for incremental drift checking
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Implement `since` parameter for incremental drift checking is implemented, tests pass, and documentation is updated.

---

### 0.5 -- docs_check_drift: Replace single aggregate doc_mtime with per-file precision

**Points:** 5

Current drift detector uses max(doc_mtime) for all docs, making age classification imprecise. Extend to track which doc mentions each symbol and use that doc's mtime for severity assessment.

**Tasks:**
- [ ] Implement docs_check_drift: replace single aggregate doc_mtime with per-file precision
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Replace single aggregate doc_mtime with per-file precision is implemented, tests pass, and documentation is updated.

---

### 0.6 -- docs_check_drift: Add public constants to drift detection

**Points:** 3

_get_public_names ignores constants, skipping public API constants like MAX_RETRIES. Add constants to drift coverage and include them in ignore_patterns defaults for test/internal constants.

**Tasks:**
- [ ] Implement docs_check_drift: add public constants to drift detection
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Add public constants to drift detection is implemented, tests pass, and documentation is updated.

---

### 0.7 -- docs_check_drift: Apply source_filter as pre-filter, not post-filter

**Points:** 3

When source_files parameter is given, detector still scans entire project then filters results. Add source_files parameter to DriftDetector.check() to scope the scan upfront, avoiding wasteful full-project scans.

**Tasks:**
- [ ] Implement docs_check_drift: apply source_filter as pre-filter, not post-filter
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Apply source_filter as pre-filter, not post-filter is implemented, tests pass, and documentation is updated.

---

### 0.8 -- docs_check_drift: Make file scanning async to unblock event loop

**Points:** 5

DriftDetector.check() does synchronous blocking I/O in an async MCP handler. Wrap in asyncio.to_thread() to prevent large project scans from blocking other requests.

**Tasks:**
- [ ] Implement docs_check_drift: make file scanning async to unblock event loop
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Make file scanning async to unblock event loop is implemented, tests pass, and documentation is updated.

---

### 0.9 -- docs_check_drift: Code quality improvements (conditions, next_steps, getattr)

**Points:** 3

Minor fixes: deduplicate severity/drift_type condition check, add next_steps guidance to response, remove getattr fallback on known Pydantic field, narrow hardcoded 'test' path skip.

**Tasks:**
- [ ] Implement docs_check_drift: code quality improvements (conditions, next_steps, getattr)
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Code quality improvements (conditions, next_steps, getattr) is implemented, tests pass, and documentation is updated.

---

### 0.10 -- docs_check_drift: Remove or populate removed_stale drift_type

**Points:** 2

drift_type='removed_stale' is documented but never produced. Either implement stale doc detection or remove the enum value from docstring. Document rationale if deferred.

**Tasks:**
- [ ] Implement docs_check_drift: remove or populate removed_stale drift_type
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** docs_check_drift: Remove or populate removed_stale drift_type is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **docs_check_drift: Bug fixes, performance, and feature completeness**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Rewrite the entire drift detection algorithm
- Add support for non-Python languages (out of scope for MVP)
- Historical drift tracking (git blame per symbol)

<!-- docsmcp:end:non-goals -->

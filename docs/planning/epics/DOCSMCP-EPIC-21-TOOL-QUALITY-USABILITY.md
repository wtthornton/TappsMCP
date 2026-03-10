# DocsMCP Epic 21: Tool Quality & Usability Improvements

<!-- docsmcp:start:metadata -->
- **Status:** Open
- **Priority:** P1
- **Estimated LOE:** ~2 weeks (1 developer)
- **Dependencies:** None (all improvements are to existing tools)
- **Blocks:** None
- **Source:** MCP tool usage reviews (EPIC-67 review on TappMCP, Epic 9 review on TheStudio)
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Fix the docs-mcp tools that returned low or zero value in two independent MCP tool usage reviews — specifically `docs_session_start` env var resolution, `docs_check_links` backtick reference support, `docs_check_drift` output filtering, `docs_generate_story` test naming, and a new `docs_validate_epic` structural validation tool.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Two independent reviews (Epic 67 review on TappMCP, Epic 9 review on TheStudio) found consistent issues:

1. **`docs_session_start`** returned `"${DOCS_MCP_PROJECT_ROOT}"` literally — env var not resolved. Session context was useless; downstream tools only worked because they accepted explicit `project_root`.
2. **`docs_check_links`** returned 0 links on 200+ line epic documents because epics use backtick file references (`` `upgrade.py` ``), not markdown links (`[text](url)`). Both reviews flagged this as wasted tool calls.
3. **`docs_check_drift`** returned 57KB of unfiltered JSON. No filtering parameters exist, making the output unusable without external grep.
4. **`docs_generate_story`** produced truncated, unusable test case names like `test_upgradepipeline_calls_generateallgithubtemplates_and_ge`.
5. **No `docs_validate_epic` tool exists** to structurally validate epic documents (story completeness, dependency DAG, files-affected table).

Overall: `docs_check_links` scored D in both reviews, `docs_session_start` scored D, and the test naming got explicitly called out as the worst auto-generated content.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `docs_session_start` resolves `${VAR}` patterns in project root before use
- [ ] `docs_check_links` detects and validates backtick file references (`` `path/to/file.py` ``)
- [ ] `docs_check_links` warns when scanning a file with zero links
- [ ] `docs_check_drift` accepts `source_files` and `search_names` filter parameters
- [ ] `docs_generate_story` produces short, valid Python test names (≤ 80 chars, snake_case)
- [ ] New `docs_validate_epic` tool validates epic document structure
- [ ] All existing tests pass; new tests cover each story
<!-- docsmcp:end:acceptance-criteria -->

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| `docs_check_links` on epic files | 0 findings | ≥ 3 backtick refs detected | Run on EPIC-67 doc |
| `docs_check_drift` output size (filtered) | 57KB | < 5KB for targeted query | Filter by 5 file names |
| Test name length | 60+ chars, truncated | ≤ 80 chars, complete | `docs_generate_story` output |
| `docs_session_start` env var handling | Literal `${VAR}` | Resolved path | Set DOCS_MCP_PROJECT_ROOT and call |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Backtick ref parsing false positives (code blocks) | Medium | Low | Skip fenced code blocks; only match inline backticks with path-like content |
| Drift filter changes break existing consumers | Low | Medium | Filters are additive — unfiltered is still the default |
| Epic validation too strict for non-standard formats | Medium | Low | Validation is advisory (warnings), not blocking |

---

<!-- docsmcp:start:stories -->
## Stories

### Story 21.1: Fix `docs_session_start` Environment Variable Resolution

> **As a** docs-mcp user, **I want** `docs_session_start` to resolve environment variables in the project root, **so that** I get correct project context without manually passing `project_root`.

**Points:** 2 | **Size:** S | **Priority:** P0

**Files:**
- `packages/docs-mcp/src/docs_mcp/config/settings.py`
- `packages/docs-mcp/src/docs_mcp/server.py` (lines 271-320)
- `packages/docs-mcp/tests/unit/test_settings.py`

#### Problem

When `DOCS_MCP_PROJECT_ROOT` is set as an environment variable, `load_docs_settings()` stores the raw `${DOCS_MCP_PROJECT_ROOT}` string if it comes from a config file that uses shell variable syntax. The settings loader doesn't call `os.path.expandvars()`.

#### Tasks

- [ ] Add `os.path.expandvars()` call in `load_docs_settings()` for the `project_root` field
- [ ] Also expand `~` via `os.path.expanduser()` for home-relative paths
- [ ] Add validation: if the expanded path doesn't exist, return a clear error
- [ ] Add test: set `DOCS_MCP_PROJECT_ROOT` env var, verify it resolves
- [ ] Add test: `~/projects/foo` expands to full path

#### Acceptance Criteria

- [ ] `${DOCS_MCP_PROJECT_ROOT}` resolves to actual path
- [ ] `~` in paths expands to home directory
- [ ] Non-existent expanded paths produce clear error message

---

### Story 21.2: Add Backtick File Reference Detection to `docs_check_links`

> **As a** docs-mcp user checking links in planning documents, **I want** the link checker to detect backtick-wrapped file references and validate they exist on disk, **so that** epic and story documents with code-style file references get meaningful validation.

**Points:** 5 | **Size:** M | **Priority:** P1

**Files:**
- `packages/docs-mcp/src/docs_mcp/validators/link_checker.py`
- `packages/docs-mcp/tests/unit/test_link_checker.py`

#### Problem

The link checker only parses markdown link syntax `[text](target)`. Epic documents conventionally use backtick formatting (`` `src/foo/bar.py` ``) for file references. Both reviews showed 0 links found on 200+ line documents, making the tool call a waste.

#### Tasks

- [ ] Add regex for backtick file references: single backtick wrapping a path-like string (contains `/` or `.py`/`.md`/`.yaml`/`.toml`/`.json`)
- [ ] Skip backtick refs inside fenced code blocks (``` ``` ```) to avoid false positives
- [ ] Validate backtick file refs exist on disk relative to project root
- [ ] Report as separate category: `backtick_references` with `found`/`missing` counts
- [ ] Add `warn_on_zero_links` flag (default true): emit warning when no links AND no backtick refs found
- [ ] Return advisory message: "No links found — consider adding cross-references" when appropriate

#### Acceptance Criteria

- [ ] Backtick file references like `` `pipeline/upgrade.py` `` are detected and validated
- [ ] Refs inside fenced code blocks are skipped
- [ ] Zero-link documents get a warning
- [ ] Existing markdown link validation unchanged
- [ ] Report includes `backtick_references` section

---

### Story 21.3: Add Filtering to `docs_check_drift`

> **As a** docs-mcp user validating specific file references in an epic, **I want** to filter drift results by source files or public names, **so that** I get a targeted report instead of a 57KB JSON blob.

**Points:** 3 | **Size:** S | **Priority:** P1

**Files:**
- `packages/docs-mcp/src/docs_mcp/server_val_tools.py` (docs_check_drift handler)
- `packages/docs-mcp/src/docs_mcp/validators/drift.py`
- `packages/docs-mcp/tests/unit/test_drift.py`

#### Problem

`docs_check_drift` returns the full project drift report (188 items, 57KB JSON in the TheStudio review). There are no filtering parameters to narrow results to specific files or names. Users must grep the output externally.

#### Tasks

- [ ] Add `source_files` parameter: comma-separated list of file paths to limit drift analysis to
- [ ] Add `search_names` parameter: comma-separated list of public names (functions, classes, endpoints) to search for in drift items
- [ ] Add `max_items` parameter: limit output to top N drift items (default: 50)
- [ ] Apply filters before JSON serialization to reduce response size
- [ ] Add summary counts even when filtered: `total_unfiltered`, `total_filtered`, `showing`

#### Acceptance Criteria

- [ ] `docs_check_drift(source_files="server.py,upgrade.py")` returns only drift for those files
- [ ] `docs_check_drift(search_names="/webhook/github,/admin/health")` returns only matching names
- [ ] `docs_check_drift(max_items=10)` limits output to 10 items with summary counts
- [ ] Unfiltered call still works (backward compatible)

---

### Story 21.4: Fix `docs_generate_story` Test Case Naming

> **As a** docs-mcp user generating user stories, **I want** auto-generated test case names to be short, valid Python identifiers, **so that** I can use them directly without manual rewriting.

**Points:** 2 | **Size:** S | **Priority:** P2

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/stories.py`
- `packages/docs-mcp/tests/unit/test_stories.py`

#### Problem

Auto-generated test names are mechanical truncations of acceptance criteria text:
```
test_upgradepipeline_calls_generateallgithubtemplates_and_ge
test_results_stored_in_result_components_githubtemplates_and
```

These are too long (60+ chars), truncated mid-word, and don't follow Python naming conventions.

#### Tasks

- [ ] Rewrite test name generation: extract key verb and noun from acceptance criterion
- [ ] Enforce max 80 characters for test names
- [ ] Use pattern: `test_<verb>_<noun>_<qualifier>` (e.g., `test_upgrade_generates_github_templates`)
- [ ] Never truncate mid-word — if too long, drop qualifiers from the end
- [ ] Add stopword list to remove filler words (the, and, is, are, should, that)
- [ ] When acceptance criteria have numbered items, use the number: `test_ac1_generates_templates`

#### Acceptance Criteria

- [ ] All generated test names are ≤ 80 characters
- [ ] No test names are truncated mid-word
- [ ] Test names are valid Python identifiers
- [ ] Test names are descriptive enough to understand what they test

---

### Story 21.5: Improve `docs_generate_epic` Auto-Populate with File Hints

> **As a** docs-mcp user generating comprehensive epics, **I want** `auto_populate` to accept file path hints and produce file-specific enrichment, **so that** the generated metadata is relevant to my epic scope rather than generic project stats.

**Points:** 3 | **Size:** S | **Priority:** P2

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` (docs_generate_epic handler)
- `packages/docs-mcp/tests/unit/test_epics.py`

#### Problem

With `auto_populate=true`, the epic gains generic project metadata (`47 packages, 794 modules, 3096 public APIs`) that isn't useful for a scoped epic. It doesn't identify specific files affected, cross-reference related epics, or pull git history for affected modules.

#### Tasks

- [ ] Add `files` parameter to `docs_generate_epic`: comma-separated list of file paths the epic affects
- [ ] When `files` is provided with `auto_populate=true`:
  - Pull git history for those specific files (last 10 commits)
  - Extract public API surface for those files
  - Cross-reference against existing epics that mention the same files
- [ ] Auto-populate the "Files Affected" table from the `files` parameter
- [ ] Scan story descriptions for file paths and add to files-affected if not already listed

#### Acceptance Criteria

- [ ] `docs_generate_epic(files="upgrade.py,init.py", auto_populate=true)` includes file-specific git history
- [ ] Files-affected table auto-populated from file hints
- [ ] Story descriptions scanned for additional file paths
- [ ] Generic project stats still available when no file hints provided

---

### Story 21.6: New `docs_validate_epic` Tool

> **As a** docs-mcp user writing epic documents, **I want** a validation tool that checks structural completeness of my epic, **so that** I can catch missing sections, incomplete stories, and dependency issues before starting implementation.

**Points:** 5 | **Size:** M | **Priority:** P2

**Files:**
- `packages/docs-mcp/src/docs_mcp/validators/epic_validator.py` (new)
- `packages/docs-mcp/src/docs_mcp/server_val_tools.py` (register new tool)
- `packages/docs-mcp/tests/unit/test_epic_validator.py` (new)

#### Problem

There is no programmatic way to validate epic documents. Both reviews identified the need to check:
- Whether all stories have acceptance criteria
- Whether story sizes are consistent with point estimates
- Whether the implementation order respects dependency chains
- Whether the files-affected table is complete
- Whether dependencies form a DAG (no cycles)

#### Tasks

- [ ] Create `EpicValidator` class that parses epic markdown
- [ ] Validate required sections: Goal, Motivation, Acceptance Criteria, Stories
- [ ] For each story, validate: points, size, priority, files, acceptance criteria, tasks
- [ ] Check point/size consistency: S=1-2, M=3-5, L=8-13
- [ ] Parse implementation order and verify it respects story dependencies
- [ ] Check files-affected table covers all files mentioned in stories
- [ ] Register as `@mcp.tool()` named `docs_validate_epic`
- [ ] Return structured validation report with severity levels (error, warning, info)

#### Acceptance Criteria

- [ ] `docs_validate_epic(file_path="docs/planning/epics/EPIC-67.md")` returns validation report
- [ ] Missing required sections flagged as errors
- [ ] Stories without AC flagged as errors
- [ ] Point/size mismatches flagged as warnings
- [ ] Dependency cycles flagged as errors
- [ ] Files mentioned in stories but missing from files-affected table flagged as warnings
- [ ] Passing validation on well-formed epics returns clean report

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:implementation-order -->
## Implementation Order

```
21.1 (env var fix) — independent, quick win
         │
21.2 (backtick refs) ──→ 21.6 (epic validator, can use link checking)
         │
21.3 (drift filtering) — independent
         │
21.4 (test naming) — independent
         │
21.5 (auto_populate) ──→ 21.6 (validator can check file hints)
```

1. **21.1** first — quick fix, highest user impact
2. **21.3** second — independent, high value from TheStudio review
3. **21.4** third — independent, straightforward
4. **21.2** fourth — requires careful regex work and code block detection
5. **21.5** fifth — enrichment improvements
6. **21.6** last — builds on all other improvements
<!-- docsmcp:end:implementation-order -->

---

## Files Affected

| File | Stories | Change Type |
|------|---------|-------------|
| `docs_mcp/config/settings.py` | 21.1 | Modify |
| `docs_mcp/server.py` | 21.1 | Modify |
| `docs_mcp/validators/link_checker.py` | 21.2 | Modify |
| `docs_mcp/server_val_tools.py` | 21.3, 21.6 | Modify |
| `docs_mcp/validators/drift.py` | 21.3 | Modify |
| `docs_mcp/generators/stories.py` | 21.4 | Modify |
| `docs_mcp/generators/epics.py` | 21.5 | Modify |
| `docs_mcp/server_gen_tools.py` | 21.5 | Modify |
| `docs_mcp/validators/epic_validator.py` | 21.6 | New |

# Epic 67: MCP Tool Usage Review

**Date:** 2026-03-10
**Context:** Used docs-mcp and tapps-mcp tools to review and improve Epic 67 (Init & Upgrade Hardening) — an epic with 6 stories covering dead code fixes, parity gaps, version markers, and parameter simplification.

---

## Tool Calls Made (Chronological)

| # | Tool | Purpose | Result |
|---|------|---------|--------|
| 1 | `docs_session_start` | Initialize docs-mcp session | Success, but returned empty project (wrong root) |
| 2 | `docs_check_links` | Validate internal links in Epic 67 | Success: 0 links found (file had no markdown links) |
| 3 | `docs_generate_epic` | Generate comprehensive epic for structural comparison | Success: got template with success metrics, risk assessment, files-affected, implementation order |
| 4 | `docs_generate_story` x6 | Generate comprehensive stories with INVEST checklist, test cases, DoD | Success: all 6 stories generated with proper format |
| 5 | `tapps-research` (skill) | Research 3 technical questions about async patterns, version markers, API surfaces | Success: provided critical counterpoint that changed the epic |
| 6 | `docs_check_links` (reused from #2) | Already done above | N/A |

**Total MCP calls:** 9 (1 session start + 1 link check + 1 epic gen + 6 story gen)
**Skill calls:** 1 (tapps-research)
**tapps-mcp direct tool calls:** 0

---

## What Worked Well

### 1. `tapps-research` was the highest-value call

The single tapps-research call produced the most impactful finding of the entire review: **Story 67.2 should be dropped**. The research correctly identified that the `asyncio.run()` + `RuntimeError` guard pattern is actually the right approach for `asyncio.to_thread()` contexts, and converting to sync would lose `wait_for` timeout control.

Without this call, the epic would have shipped with a story that actively worsened the code.

The research also correctly narrowed Story 67.4 (version markers) from "all file types" to "Markdown only", providing the reasoning that YAML files should be write-once and JSON should use structural validation. This prevented over-engineering.

**Verdict:** Essential. Should always be used when an epic contains technical design decisions.

### 2. `docs_generate_epic` (comprehensive) revealed structural gaps

The generated epic template showed me what my hand-written epic was missing:
- Success Metrics table (baseline → target → measurement)
- Implementation Order section
- Files Affected cross-reference table
- Risk Assessment with probability/impact columns (vs my flat table)
- `docsmcp` section markers for future re-generation

All of these were incorporated into the final epic.

**Verdict:** High value as a structural review tool. The generated content itself was generic (placeholder text like "Document architecture decisions and key dependencies..."), but the **structure** was the real deliverable.

### 3. `docs_generate_story` (comprehensive) added INVEST checklists and test cases

The generated stories added:
- Proper "As a / I want / So that" user story format
- INVEST checklist (Independent, Negotiable, Valuable, Estimable, Small, Testable)
- Test case stubs
- Definition of Done references back to the parent epic
- `docsmcp` section markers

The INVEST checklists were informative — Story 67.3 correctly flagged `Independent` as unchecked (it depends on 67.4 for idempotent upgrades).

**Verdict:** Moderate value. The format/structure was useful. The auto-generated test case names were poor (truncated identifiers like `test_upgradepipeline_calls_generateallgithubtemplates_and_ge`). I used the story details I provided, not the generated names.

---

## What Did Not Work Well

### 1. `docs_session_start` returned wrong project context

`docs_session_start` returned `project_name: "${DOCS_MCP_PROJECT_ROOT}"` — it didn't resolve the environment variable. The missing docs recommendations (README, LICENSE, etc.) were for the wrong root. This meant the session context was essentially useless.

**Impact:** Low — the subsequent tool calls accepted explicit `project_root` parameters and worked correctly.

**Root cause:** The docs-mcp server's project root isn't configured to point at TappMCP. The `project_root` override parameter exists but `docs_session_start` doesn't accept one as a required field (it's optional with empty default).

### 2. `docs_check_links` returned 0 links — not useful

The epic file had no markdown links (only backtick code references like `` `upgrade.py` ``), so the link checker correctly returned 0 links / 0 broken. But this means the tool provided zero signal — it didn't tell me "you should add links" or "these code references aren't hyperlinked."

**Impact:** Wasted a tool call.

**Improvement idea:** `docs_check_links` could optionally flag files with code references that could be converted to links, or warn when scanning a file with no links at all.

### 3. tapps-mcp tools were never directly called

I used the `tapps-research` **skill** (which internally uses tapps-mcp), but I never called any tapps-mcp tools directly (e.g., `tapps_checklist`, `tapps_consult_expert`, `tapps_session_start`). This happened because:

- The tapps-mcp MCP server tools weren't discoverable via `ToolSearch` — searching for "tapps session_start", "tapps checklist", "tapps_mcp" etc. all returned 0 results from the deferred tools list
- The tapps-mcp server appears to not be registered as a deferred tool provider in this VSCode extension session, even though docs-mcp was
- I fell back to the `tapps-research` skill (which works via the skill system, not MCP tool discovery)

**Impact:** High. I should have been able to:
- Call `tapps_checklist(task_type="feature")` to validate the epic against TappsMCP's own feature checklist
- Call `tapps_consult_expert(domain="python", question="...")` for the async/sync design question
- Call `tapps_session_start()` to get project context

**Root cause:** The `.cursor/mcp.json` configuration may not have tapps-mcp registered, or the MCP server wasn't running. This is a configuration gap, not a tool gap.

### 4. `docs_generate_story` test case names were unusable

The auto-generated test case names were mechanical truncations of acceptance criteria:
```
test_upgradepipeline_calls_generateallgithubtemplates_and_ge
test_results_stored_in_result_components_githubtemplates_and
```

These are too long, truncated mid-word, and don't follow Python test naming conventions. I discarded all generated test names and wrote my own.

**Improvement idea:** Test case generation should produce short, descriptive names or skip auto-naming entirely when acceptance criteria are already provided.

### 5. `docs_generate_epic` auto_populate was shallow

With `auto_populate=true`, the epic gained `Project Structure: 47 packages, 794 modules, 3096 public APIs` — but this is generic project-level metadata, not epic-specific enrichment. It didn't identify the specific files affected by the epic, didn't cross-reference related epics (e.g., Epic 46 Docker Distribution), and didn't pull in git history for the affected modules.

**Impact:** Low — the metadata was trivially available and not useful for an internal hardening epic.

**Improvement idea:** `auto_populate` could accept a `files` hint to focus enrichment on specific modules, or could scan the story descriptions for file paths and auto-populate the files-affected table.

### 6. No `tapps_score` or `tapps_validate_changed` on the epic document

Since the epic is a Markdown file (not Python), tapps-mcp's scoring tools don't apply. But there's no equivalent "document quality score" tool. I could not programmatically validate:
- Whether all stories have acceptance criteria
- Whether story sizes are consistent with point estimates
- Whether the implementation order respects dependency chains
- Whether the files-affected table is complete

**Improvement idea:** A `docs_validate_epic` tool that checks structural completeness of epic documents (all stories have AC, DoD, files, points; dependencies form a DAG; no orphan files).

---

## Recommendations

### For tapps-mcp

| # | Recommendation | Priority | Rationale |
|---|---------------|----------|-----------|
| 1 | **Ensure tapps-mcp tools are discoverable in VSCode extension sessions** | P0 | The entire tapps-mcp toolset was inaccessible via ToolSearch. Only the skill fallback worked. This defeats the purpose of having MCP tools. |
| 2 | **Add `tapps_checklist(task_type="epic")` variant** | P2 | Feature checklists exist but there's no epic-level validation. Would catch issues like missing acceptance criteria, undefined dependencies, or stories without test plans. |
| 3 | **Surface `tapps_consult_expert` as a standalone deferred tool** | P2 | Currently only accessible via the tapps-research skill. Direct MCP tool access would allow more targeted single-domain consultations without the skill wrapper overhead. |

### For docs-mcp

| # | Recommendation | Priority | Rationale |
|---|---------------|----------|-----------|
| 1 | **Fix `docs_session_start` to resolve env vars or require explicit `project_root`** | P1 | Session returned `${DOCS_MCP_PROJECT_ROOT}` literally. All downstream tools worked because they accepted explicit `project_root`, but the session context was wrong. |
| 2 | **Add `docs_validate_epic` tool** | P2 | Structural validation of epic documents: all stories have AC/DoD/files/points, dependencies form a DAG, files-affected table is complete, implementation order respects deps. |
| 3 | **Improve `docs_generate_story` test case naming** | P3 | Auto-generated names are truncated and unusable. Either generate short snake_case names or omit auto-naming when explicit criteria are provided. |
| 4 | **Make `docs_check_links` warn on zero-link documents** | P3 | Returning "0 links, 0 broken" on a 200-line document is a false sense of completeness. Should flag "no links found — consider adding cross-references." |
| 5 | **Improve `auto_populate` to accept file path hints** | P3 | Currently enriches with generic project metadata. Accepting file hints would let it pull relevant git history, module structure, and related epics for the specific scope. |

### For the workflow (process recommendations)

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 1 | **Always call `tapps-research` before finalizing technical design stories** | This session's single research call was the highest-value action — it killed a bad story and narrowed another. Should be mandatory for any epic with design decisions. |
| 2 | **Use `docs_generate_epic(style="comprehensive")` as a structural checklist, not a content generator** | The generated content was generic, but the structure (sections present/absent) was the real signal. Use it to audit your hand-written epic, not replace it. |
| 3 | **Don't bother with `docs_check_links` on planning documents** | Planning docs rarely have markdown links. The tool is designed for published documentation (README, API docs), not internal epics. |
| 4 | **Generate stories in parallel** | All 6 `docs_generate_story` calls were independent and could have been parallelized. The sequential execution added unnecessary latency. (Note: they were actually called in parallel in this session — this is a reminder for future workflows.) |
| 5 | **Verify MCP server availability before starting a review workflow** | Check `.cursor/mcp.json` and run `tapps-mcp doctor` to confirm both servers are registered and responsive before attempting tool calls. Would have caught the tapps-mcp discoverability issue early. |

---

## Summary Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| **tapps-research** | A | Single call changed 2 stories and killed 1. Highest ROI. |
| **docs_generate_epic** | B+ | Structural template was valuable; content was generic. |
| **docs_generate_story** | B | Format/INVEST useful; test names poor; content was what I provided. |
| **docs_check_links** | D | Zero signal on a planning document. |
| **docs_session_start** | D | Wrong project context; env var not resolved. |
| **tapps-mcp direct tools** | F | Never accessible. Configuration gap blocked all usage. |
| **Overall workflow** | B | Good outcomes despite tooling gaps. Research skill saved the epic from a bad story. |

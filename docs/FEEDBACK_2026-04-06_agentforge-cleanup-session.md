# Field Report: TappsMCP + DocsMCP Full-Session Usage

**Date:** 2026-04-06
**Project:** AgentForge (FastAPI + React agent orchestration platform)
**Session type:** Full cleanup/fortify/document pipeline across 4 phases
**TappsMCP version:** 1.14.0
**Claude model:** Opus 4.6 (1M context)
**Total TappsMCP tool calls:** 93
**Session duration:** ~30 minutes active work

---

## Executive Summary

Ran the complete TappsMCP 5-stage pipeline plus DocsMCP generation/validation across a 73-file Python backend with 137 uncommitted changes. TappsMCP was highly effective for quality scoring, security scanning, and project bootstrapping. DocsMCP generated useful documentation but had a critical `project_root` configuration issue that required workaround. Overall: strong tools, some friction at the edges.

---

## What Worked Well

### TappsMCP

#### `tapps_session_start` (quick mode)
- Fast (<500ms), returned useful session context immediately
- Quick mode is a good addition for repeat sessions

#### `tapps_init` — Excellent
- **Best single tool call of the session.** Generated 30 files in one invocation:
  - SECURITY.md, CODEOWNERS, dependabot.yml
  - 4 GitHub issue templates + PR template
  - 5 CI workflows (CodeQL, quality gate, dependabot auto-merge, reusable quality, agentic PR review)
  - Claude rules, hook scripts, memory auto-recall
  - Copilot instructions and agent profiles
- The governance scaffolding alone (SECURITY.md, CODEOWNERS, GitHub templates) saves significant manual setup time
- CI workflow generation is a standout feature — went from zero CI to production-grade quality gates in one call

#### `tapps_dead_code` (project scope)
- Fast (288ms for 82 files), correctly identified only 3 items
- The 3 findings were all `cls` in Pydantic `@validator` methods — false positives, but understandable given Vulture's limitations
- **Recommendation:** Consider whitelisting `cls` in Pydantic validator context or adding a note about common false positives in the output

#### `tapps_report` (project-wide)
- Clear, actionable output: 30 files scored, per-file breakdown by 7 categories
- Immediately identified the 5 weakest files and 2 security issues
- 1,263ms for 30 files is acceptable

#### `tapps_security_scan` + `tapps_dependency_scan`
- Security scan correctly found the 2 B608 SQL injection warnings in `stats.py`
- Dependency scan: 70 packages, 0 vulnerabilities, ~4s — clean result
- Both tools gave clear, actionable output with OWASP references

#### `tapps_dependency_graph`
- Fast (173ms), correctly reported 0 circular imports across 82 modules
- Coupling metrics identified `backend.main` as the only hub (expected for FastAPI entry point)
- The coupling suggestions were contextually appropriate

#### `tapps_doctor`
- 23 checks, clear pass/fail with remediation hints
- Correctly identified Cursor/VS Code configs as missing (not applicable to our setup)
- Memory pipeline effective config row is a nice touch for debugging

#### `tapps_checklist`
- Compact output mode is useful — one-line summary with clear pass/fail
- Correctly tracked 93 tool calls across the session and verified required tools were satisfied

### DocsMCP

#### `docs_generate_api` — Excellent
- Generated 83KB / 113 sections of API reference from Python source
- Extracted docstrings, parameters, return types, and usage examples from tests
- This is the single highest-value DocsMCP tool for a Python project

#### `docs_generate_architecture`
- Self-contained HTML with embedded SVG diagrams, no external dependencies
- Visual quality is good — gradient-styled component boxes, curved dependency arrows
- 446ms for 71 modules is fast

#### `docs_generate_doc_index`
- Categorized 50 files into 9 categories automatically
- Freshness indicators are a nice touch
- Useful as a living table of contents

#### `docs_check_diataxis`
- 98.6/100 balance score with per-file quadrant classification
- Confidence scores per file help identify ambiguous docs
- Genuinely useful for understanding documentation portfolio balance

#### `docs_check_freshness`
- 99.4/100, correctly identified all docs as fresh post-generation
- Summary-only mode is efficient for dashboards

#### `docs_check_cross_refs`
- 100/100, no orphans or broken refs — clean validation pass

---

## What Did Not Work

### DocsMCP: `project_root` Default Is Wrong

**Severity: High — Blocked all generation tools on first attempt**

All 6 `docs_generate_*` calls failed on the first attempt with:

```
WRITE_ERROR: Failed to write: '/home/wtthornton/code/tapps-mcp/packages/docs-mcp/docs/README.md'
is not in the subpath of '.'
```

DocsMCP defaulted its project root to its own install directory (`/home/wtthornton/code/tapps-mcp/packages/docs-mcp/`) instead of the working project (`/home/wtthornton/code/AgentForge/`).

**Workaround:** Passing `project_root="/home/wtthornton/code/AgentForge"` explicitly to every call.

**Expected behavior:** DocsMCP should inherit the project root from the MCP client's working directory, or from `TAPPS_MCP_PROJECT_ROOT` if set, or from git root detection. The `docs_session_start` call should establish this for the session.

**Impact:** 6 wasted tool calls, user confusion, and every subsequent call requires a verbose parameter. This is the #1 issue to fix.

### DocsMCP: `docs_session_start` Did Not Set Project Root

`docs_session_start()` returned successfully but did not establish the project context for subsequent calls. The session start should be the mechanism that resolves and caches the project root, so individual tool calls don't need to repeat it.

**Recommendation:** Either:
1. Make `docs_session_start(project_root=...)` persist the root for the session, OR
2. Read `TAPPS_MCP_PROJECT_ROOT` from environment (already set in `.mcp.json`), OR
3. Auto-detect via git root from the MCP client's CWD

### DocsMCP: `docs_check_completeness` Scanned Its Own Source

The completeness check returned `api_documentation` with 62 files — all from `src/docs_mcp/` (DocsMCP's own source code). It should have scanned the target project's source files.

Same root cause as the `project_root` issue above, but particularly confusing because the tool appeared to succeed while returning irrelevant data.

### DocsMCP: `docs_check_drift` Reported 121 Drift Items From Wrong Project

All 121 drift items were from `src/docs_mcp/` source files, not from AgentForge's backend. The drift analysis was technically correct for the wrong project.

### DocsMCP: `docs_check_style` — Output Too Large

The style check returned 110,418 characters, exceeding the MCP output limit and requiring file-based retrieval. For a 35-file project, this is excessive.

**Recommendation:**
- Add a `summary_only` parameter (like `docs_check_freshness` has)
- Or cap default output and require explicit `verbose=true` for full details
- The aggregate score + top issues + worst 5 files would be sufficient for most use cases

### DocsMCP: `docs_check_links` — Backtick References Are Noise

28 "missing backtick references" were reported — all false positives (references to code filenames like `server.py` in CLAUDE.md/AGENTS.md that are documentation references, not file links). These are not broken links.

**Recommendation:** Either:
1. Make backtick reference checking opt-in (`check_backtick_refs=false` default)
2. Only flag backtick refs that look like relative paths (contain `/`)
3. Separate backtick refs into their own section with a different severity

---

## Recommendations for Improvement

### TappsMCP

| Priority | Recommendation | Rationale |
|----------|---------------|-----------|
| Medium | Add Pydantic `cls` to dead code whitelist | 3/3 findings were false positives from `@validator` methods |
| Low | `tapps_report` should accept `scope="changed"` | Would be useful for PR reviews without scoring the entire project |
| Low | `tapps_init` dry-run should list files it would create | Helps users understand the blast radius before committing |

### DocsMCP

| Priority | Recommendation | Rationale |
|----------|---------------|-----------|
| **Critical** | Fix `project_root` resolution — inherit from env/CWD/git | Blocked all generation on first attempt, required manual workaround on every call |
| **Critical** | Make `docs_session_start` persist project root for session | Eliminates need to pass `project_root` to every subsequent call |
| High | `docs_check_style` needs `summary_only` mode | 110K chars exceeds MCP output limits, unusable without file retrieval |
| High | `docs_check_completeness` / `docs_check_drift` should respect `project_root` | Currently scans DocsMCP's own source instead of the target project |
| Medium | `docs_check_links` backtick refs should be opt-in or lower severity | 28 false positives add noise to an otherwise clean report |
| Medium | `docs_generate_changelog` should detect tags from target project | Generated minimal output despite target project having 25 commits with conventional format |
| Low | Add `docs_generate_security` for SECURITY.md generation | Currently only TappsMCP generates this; DocsMCP could offer a richer template |

### Cross-MCP Integration

| Priority | Recommendation | Rationale |
|----------|---------------|-----------|
| High | DocsMCP should read `TAPPS_MCP_PROJECT_ROOT` from environment | Both MCPs are configured in the same `.mcp.json`; they should share the project root |
| Medium | TappsMCP `tapps_init` should configure DocsMCP's project root | When init detects docs-mcp in `.mcp.json`, it could set the root for both |
| Low | Unified session start that initializes both MCPs | A single call that runs `tapps_session_start` + `docs_session_start` with shared context |

---

## Session Statistics

| Metric | Value |
|--------|-------|
| TappsMCP tool calls | 93 |
| DocsMCP tool calls | ~18 (6 failed + 12 succeeded) |
| Files generated by `tapps_init` | 30 |
| Files generated by `docs_generate_*` | 8 |
| Quality baseline (avg) | 77.33/100 |
| Gate pass rate | 83% |
| Security issues (HIGH/CRITICAL) | 0 |
| Vulnerable dependencies | 0 |
| Circular imports | 0 |
| Diataxis balance | 98.6/100 |
| Doc freshness | 99.4/100 |

---

## Verdict

**TappsMCP: 9/10** — Excellent tooling. `tapps_init` is a killer feature that generates production-grade CI, governance, and quality infrastructure in one call. Scoring, security, and dependency analysis are fast and actionable. Minor improvement opportunities around false positive handling.

**DocsMCP: 6/10** — Strong generation capabilities (especially `docs_generate_api` and `docs_generate_architecture`) held back by a critical `project_root` configuration bug that caused 100% failure rate on first attempt. Validation tools produced misleading results by scanning the wrong project. Once `project_root` was explicitly set, generation quality was good. Fix the root resolution and this becomes an 8/10.

**Combined: 7.5/10** — The two MCPs together provide genuine end-to-end coverage from code quality to documentation. The gap is in cross-MCP coordination — they don't share session context, requiring manual configuration bridging.

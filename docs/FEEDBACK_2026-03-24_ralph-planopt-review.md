# TappsMCP feedback — Ralph PLANOPT epic review session

**Date:** 2026-03-24
**Agent:** Claude Opus 4.6 (1M context)
**TappsMCP version:** v1.12.0
**Target project:** [ralph-claude-code](https://github.com/frankbria/ralph-claude-code) (bash/shell autonomous dev loop)
**GitHub issue:** https://github.com/wtthornton/TappsMCP/issues/76

## Session summary

Used TappsMCP + DocsMCP to review and validate a 6-file epic (RALPH-PLANOPT: Fix Plan
Optimization on Startup) with 5 stories. Session involved deep spec review,
research-backed redesign, Claude Code feature integration audit, and final validation.

### Tools called (10 unique)

| Tool | Calls | Helpful | Notes |
|------|-------|---------|-------|
| `tapps_session_start` | 1 | Yes | Quick mode, <30ms |
| `tapps_checklist` | 1 | Yes | Epic validation caught 3 structural issues |
| `tapps_project_profile` | 1 | Yes | project_root override worked |
| `tapps_impact_analysis` | 4 | **No** | All failed — no project_root param |
| `tapps_feedback` | 6 | Yes | All recorded successfully |
| `tapps_memory` | 1 | Yes | Saved full feedback report |
| `docs_check_cross_refs` | 1 | Yes | PLANOPT links all valid |
| `docs_check_style` | 1 | Yes | Score 58/100, mostly heading case (project convention) |

---

## What worked

### 1. tapps_session_start (quick=true)
Sub-30ms initialization. Returned server info, checklist session ID, and hive status
instantly. Quick mode is the right default for iterative sessions.

### 2. tapps_checklist (epic validation)
Caught 3 real structural issues in the epic:
- Missing required `## Goal` section
- Wrong heading for acceptance criteria (`## Success Criteria` vs expected)
- Story format mismatch (table links vs inline headings)

These were directly actionable and led to concrete fixes in the change list.

### 3. tapps_project_profile (with project_root override)
Correctly detected: languages (shell, python, markdown), test frameworks (pytest, bats),
CI (github-actions). The `project_root` parameter worked as expected — this is the
gold standard for cross-project usage.

### 4. tapps_feedback
Clean API, fast recording (<15ms per call), helpful_rate tracking across the session.
Good that it returns per-tool and overall stats. Session ended at 83% helpful rate.

### 5. tapps_memory
Flexible persistence with tiers, tags, and scope. Saved the full feedback report in
98ms with integrity hash. The 4096 char limit was sufficient.

---

## What did NOT work

### 1. tapps_impact_analysis — BLOCKED (critical)

**Every call failed** with "Path outside project root." The tool's project_root is
hardcoded to the MCP server's directory (`C:\cursor\TappMCP`) and does NOT accept a
`project_root` override parameter.

This is the **only tapps tool** without this parameter. All 4 calls failed:

```
tapps_impact_analysis(file_path="lib/import_graph.sh", change_type="added")
  -> Error: File not found: lib/import_graph.sh

tapps_impact_analysis(file_path="c:\cursor\ralph\ralph-claude-code\templates\hooks\on-session-start.sh")
  -> Error: Path outside project root. Project root: C:\cursor\TappMCP
```

**Impact:** Could not assess blast radius for ANY of the 15 files in the change list.
Had to rely entirely on manual analysis.

### 2. tapps_checklist epic_file_path — relative path silent failure

First call with `docs/specs/epic-plan-optimization.md` returned `[Errno 2] No such file
or directory`. Had to discover through trial that absolute Windows path was required.
Other tools resolve relative paths against project_root.

### 3. tapps_checklist story format

Expected `### Story X.Y:` inline headings but Ralph uses table-based story references:

```markdown
| PLANOPT-1 | [File dependency graph](story-planopt-1-file-dependency-graph.md) | Medium | Critical |
```

Validator reported "No stories found" because it doesn't parse markdown table links.

---

## Recommendations

### Priority 1 — Blocking

| # | Recommendation | Rationale |
|---|----------------|-----------|
| 1 | Add `project_root` parameter to `tapps_impact_analysis` | Only tool missing it. Completely unusable for cross-project MCP usage. |

### Priority 2 — Usability

| # | Recommendation | Rationale |
|---|----------------|-----------|
| 2 | Resolve `epic_file_path` relative to cwd or project_root | Relative paths work for every other tool |
| 3 | Support table-linked stories in epic validation | Common pattern — parse `[title](file.md)` links in tables |
| 4 | Note server vs target env for installed_checkers | All checkers showed unavailable but that's the MCP server env, not the target project |

### Priority 3 — Nice to have

| # | Recommendation | Rationale |
|---|----------------|-----------|
| 5 | Include resolved project_root in quick session_start | Agent can verify it's pointing at the right repo |
| 6 | Better shell/CLI project type detection | Shell tool repo classified as "documentation" at 0.6 confidence |
| 7 | Follow story links for cross-file completeness | Report "5/5 stories found, 3/5 have acceptance criteria" |

---

## DocsMCP feedback

### docs_check_cross_refs
- Correctly validated all PLANOPT epic-to-story links (no broken refs, no orphans)
- Found 39 broken refs in OTHER specs (pre-existing TheStudio/TappMCP references)
- Useful for verifying link integrity after restructuring stories

### docs_check_style
- Aggregate score 58/100 across 6 PLANOPT files
- 38 heading consistency warnings — all Title Case, matching project convention. False positives for this project.
- Recommendation: support a `heading_style: "title"` default per-project via `.docs-mcp.yaml` config
- 2 jargon hits ("actionable") were genuinely useful — fixed both
- Tense consistency checks were noisy (11 hits) but 3 were real mixed-tense issues

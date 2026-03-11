# Story 74.1: tapps_quick_check batch mode

**Epic:** [EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX](../EPIC-74-CONSUMER-FEEDBACK-AUTOMATION-PIPELINE-UX.md)  
**Priority:** P2 | **LOE:** 3–5 days

## Problem

`tapps_quick_check` accepts a single `file_path`. In automated pipelines (e.g. HomeIQ auto-bugfix) the script must call it once per file. Each call incurs full MCP/process startup. At 3 files overhead is acceptable; at 20+ files serial calls add 60–100s and per-call startup dominates. Consumer expectation: a native batch mode e.g. `tapps_quick_check(file_paths=["a.py","b.py",...])` returning per-file results in one invocation.

## Purpose & Intent

This story exists so that **automation and CI can run quick checks over many files without paying per-call startup cost**. One invocation per file is acceptable for a few files but does not scale; batch mode makes TappsMCP a practical choice for scripted pipelines (e.g. "check all changed files before commit") and reinforces that we design for both interactive and automated use.

## Tasks

- [ ] Extend `tapps_quick_check` to accept either `file_path: str` (single) or `file_paths: list[str]` (batch). If both provided, treat `file_paths` as authoritative or document single-file precedence.
- [ ] When `file_paths` is used, run scoring/gate/security (quick path) for each file, optionally with bounded concurrency to avoid resource spikes.
- [ ] Return a structure that includes per-file results (score, gate_passed, security_passed, issues) and an overall summary (all_passed, files_checked, failure_count).
- [ ] Preserve backward compatibility: single `file_path` behavior unchanged; batch is additive.
- [ ] Add unit tests: batch with 0, 1, N files; mixed pass/fail; concurrency limit.
- [ ] Document in AGENTS.md and tool docstring when to use batch in automation.

## Acceptance criteria

- [ ] Tool signature supports `file_path: str | None = None` and `file_paths: list[str] | None = None` with clear precedence.
- [ ] Batch invocation returns per-file results and aggregate summary; single-file behavior unchanged.
- [ ] Tests cover batch mode; existing quick_check tests still pass.
- [ ] AGENTS.md or tool description mentions batch usage for automation/CI.

## Files

- `packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py` (or server.py if quick_check lives there)
- `packages/tapps-mcp/tests/unit/test_server_scoring_tools.py` (or equivalent)
- `AGENTS.md` (optional doc update)

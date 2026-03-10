# Epic 75: Docker Pipeline Reliability & Tool Output UX

<!-- docsmcp:start:metadata -->
- **Status:** Proposed
- **Priority:** P1–P2 (mix by story)
- **Estimated LOE:** ~2–3 weeks (1 developer)
- **Dependencies:** Epic 46 (Docker MCP), Epic 52 (Session Startup Performance), Epic 74 (Pipeline UX)
- **Blocks:** None
- **Source:** HomeIQ `docs/tapps-feedback` (feedback-2026-03-10_153641.md, feedback-2026-03-10_154958.md) — automated bugfix runs on master branch
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Fix the highest-recurrence issues surfaced by consumer automated pipelines running TappsMCP via Docker: resolve the `/workspace` vs host path mismatch, improve `tapps_quick_check` cross-file type error detection, ensure the session cache directory is bootstrapped on cold start, add machine-readable per-file pass/fail output to `tapps_validate_changed`, and include git commit metadata in `tapps_checklist` output for audit trail linkage.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

HomeIQ runs automated bugfix pipelines that call TappsMCP tools via Docker MCP. Two consecutive sessions (8 bugs fixed, 7 files) surfaced 5 recurring issues:

1. **PATH MISMATCH P1 (Recurrence 4):** `tapps_session_start` resolves `project_root: /workspace` (Docker container path) instead of the host path `C:\cursor\HomeIQ`. All file-path arguments to subsequent tools must use container-relative paths, creating friction in automated runs where paths come from `git show` output on the host. No warning is surfaced.
2. **FALSE NEGATIVE P1 (Recurrence 2):** `tapps_quick_check` does not catch cross-file type errors (kwarg mismatches, incorrect method signatures) because mypy cross-package analysis requires the full package graph to be importable — which it isn't in the container. Bugs are found by a separate scanner, not by TappsMCP tools.
3. **COLD-START CACHE P2 (Recurrence 3):** `/workspace/.tapps-mcp-cache` does not exist and is not writable, so session start latency varies 1–4s with no caching benefit. Cache directory should be auto-created.
4. **OUTPUT FORMAT P2 (Recurrence 2):** `tapps_validate_changed` returns a consolidated narrative report but lacks per-file pass/fail rows (e.g. `PASS sandbox.py | FAIL processor.py`) that CI log parsers can grep.
5. **AUDIT LINKAGE P2 (Recurrence 2):** `tapps_checklist` output does not include the git branch or HEAD SHA, requiring manual correlation in run logs.

These issues compound in CI/automation contexts where multiple tools are called per session and output must be machine-parseable.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [ ] `tapps_session_start` correctly maps Docker `/workspace` to the host project root, or surfaces a clear warning with the path mapping so callers can adapt.
- [ ] `tapps_quick_check` detects cross-file type errors (kwarg mismatches, signature drift) via enhanced mypy configuration or AST-based cross-reference analysis.
- [ ] Session cache directory is auto-created and writable on first `tapps_session_start` call; subsequent cold starts benefit from cache.
- [ ] `tapps_validate_changed` includes machine-readable per-file pass/fail rows in its output alongside the narrative report.
- [ ] `tapps_checklist` output includes `branch` and `head_sha` metadata fields.
- [ ] All changes backward-compatible; existing tests pass; new tests for each story.
<!-- docsmcp:end:acceptance-criteria -->

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Path mismatch friction | Manual path translation required | Zero manual translation or clear warning | Consumer feedback recurrence drops to 0 |
| Cross-file type errors caught | 0 (false negative) | ≥ 80% of kwarg/signature mismatches | Pre-fix `tapps_quick_check` on known-bad files |
| Session cold-start (cached) | 1–4s variable | < 1.5s consistent | Timed `tapps_session_start` with warm cache |
| CI log parseability | Regex required on narrative | Grep-ready per-file rows | `validate_changed` output format |
| Audit trail linkage | Manual correlation | Automatic SHA in output | `tapps_checklist` response fields |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Docker volume mount paths vary by host OS | Medium | High | Support env var override (`TAPPS_HOST_ROOT`) + auto-detection heuristics |
| Cross-file mypy requires full package importable | High | Medium | Fall back to AST-based cross-reference when mypy fails; mark as `degraded: true` |
| Cache dir creation blocked by container permissions | Low | Medium | Fall back to `/tmp/.tapps-mcp-cache` if `/workspace` not writable |
| Per-file output format breaks existing parsers | Low | Low | Add rows alongside (not replacing) narrative; opt-in via `format` param |

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE |
|-------|--------|----------|-----|
| [75.1](EPIC-75/story-75.1-docker-path-mismatch.md) | Docker path mismatch resolution | P1 | 3–4 days |
| [75.2](EPIC-75/story-75.2-cross-file-type-detection.md) | Cross-file type error detection in quick_check | P1 | 4–6 days |
| [75.3](EPIC-75/story-75.3-session-cache-bootstrap.md) | Session start cache directory bootstrap | P2 | 1–2 days |
| [75.4](EPIC-75/story-75.4-validate-changed-per-file-rows.md) | validate_changed per-file pass/fail rows | P2 | 2–3 days |
| [75.5](EPIC-75/story-75.5-checklist-git-metadata.md) | Checklist git commit metadata linkage | P2 | 1–2 days |

<!-- docsmcp:end:stories -->

## Dependencies & Sequencing

```
75.1 (path mismatch) ──┐
75.3 (cache bootstrap) ─┤── can run in parallel
75.5 (checklist SHA)  ──┘

75.2 (cross-file types) ── depends on 75.1 (correct paths needed for mypy)
75.4 (per-file rows)   ── independent, can run anytime
```

## References

- **Source feedback:** `C:\cursor\HomeIQ\docs\tapps-feedback\feedback-2026-03-10_153641.md`, `feedback-2026-03-10_154958.md`
- **Related:** Epic 74 (Pipeline UX — batch mode, compact output, base_ref warning), Epic 46 (Docker MCP), Epic 52 (Session Startup Performance)

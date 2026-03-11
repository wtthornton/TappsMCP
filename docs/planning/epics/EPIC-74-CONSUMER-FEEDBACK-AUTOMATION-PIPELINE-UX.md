# Epic 74: Consumer Feedback — Automation & Pipeline UX

<!-- docsmcp:start:metadata -->
- **Status:** Complete (2026-03-11) — all 5 stories implemented
- **Priority:** P1–P2 (mix by story)
- **Estimated LOE:** ~2–3 weeks (1 developer)
- **Dependencies:** Epic 1, Epic 8 (core quality, pipeline tools)
- **Blocks:** None
- **Source:** HomeIQ `docs/tapps-feedback` (feedback-2026-03-10_093626.md, feedback-2026-03-10_111233.md) — automated bugfix runs using tapps_quick_check, tapps_validate_changed, tapps_checklist
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Address recurring consumer feedback from automated pipeline usage (e.g. HomeIQ auto-bugfix scripts): add batch mode for `tapps_quick_check`, compact/JSON output for `tapps_checklist`, base_ref guardrail for `tapps_validate_changed`, optional traceability in validate_changed output, and MCP config file validation so that TappsMCP tools are first-class in CI/automation contexts.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

HomeIQ runs automated bugfix pipelines that call TappsMCP tools per file or at the end of the run. Feedback identified:

1. **PERF P2:** `tapps_quick_check` has no batch mode — one call per file; at 20+ files serial calls add 60–100s and per-call startup dominates.
2. **UX P2:** `tapps_checklist` always returns a ~30-line markdown table; in CI/automated logs this is noisy; a compact or JSON format was requested.
3. **INTEGRATION P1:** When `tapps_validate_changed` is called with `base_ref=HEAD` and only staged (uncommitted) changes exist, the tool sees no diff and silently passes — no warning for misconfigured callers.
4. **ENHANCEMENT P2:** In automated runs there is no way to correlate which quality finding triggered which fix from validate_changed output (no bug_id/fix_ref).
5. **ENHANCEMENT P2:** MCP config files (`.cursor/mcp.json`, `.mcp.json`) are not validated by any TappsMCP tool; `tapps_validate_config` targets Dockerfile/docker-compose only.

Implementing these improvements increases value for any consumer using TappsMCP in scripts or CI.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that TappsMCP is a **first-class citizen in automation and CI**, not just in interactive IDE sessions. Real consumers (e.g. HomeIQ) already run our tools in automated bugfix pipelines; their feedback reflects real pain: latency from per-file calls, noisy logs, silent misconfigurations, and missing validation for the very config files that enable MCP. By addressing these gaps we signal that we take automation use cases seriously, reduce friction for adopters who script our tools, and close validation blind spots (MCP config) so that quality and correctness extend to the full pipeline—code and config alike. The intent is to deepen trust and adoption where it matters most: in repeatable, scripted workflows.
<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [x] `tapps_quick_check` accepts multiple files (batch) and returns per-file results with one process invocation.
- [x] `tapps_checklist` supports `compact=True` or `format="json"` for machine-readable output in CI.
- [x] `tapps_validate_changed` emits a warning when `base_ref=HEAD` and zero changed files are detected (staged-only scenario).
- [x] `tapps_validate_changed` optionally includes per-file or fix-ref traceability for automated correlation (story 74.4 can be minimal/optional).
- [x] MCP server config files (e.g. `.cursor/mcp.json`, `.mcp.json`) are validated — either via extended `tapps_validate_config` or via validate_changed flagging + validation path.
- [x] All changes backward-compatible; new parameters optional with sensible defaults.
- [x] New/updated tests for each story; existing tests pass.
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE | Status |
|-------|--------|----------|-----|--------|
| [74.1](EPIC-74/story-74.1-quick-check-batch-mode.md) | tapps_quick_check batch mode | P2 | 3–5 days | **Complete** |
| [74.2](EPIC-74/story-74.2-checklist-compact-json-output.md) | tapps_checklist compact/JSON output | P2 | 2–3 days | **Complete** |
| [74.3](EPIC-74/story-74.3-validate-changed-base-ref-warning.md) | tapps_validate_changed base_ref zero-diff warning | P1 | 1–2 days | **Complete** |
| [74.4](EPIC-74/story-74.4-validate-changed-traceability.md) | tapps_validate_changed optional traceability | P2 | 2–3 days | **Complete** |
| [74.5](EPIC-74/story-74.5-mcp-config-validation.md) | MCP config file validation | P2 | 2–4 days | **Complete** |

<!-- docsmcp:end:stories -->

## References

- **Source feedback:** `C:\cursor\HomeIQ\docs\tapps-feedback\feedback-2026-03-10_093626.md`, `feedback-2026-03-10_111233.md`
- **Related:** Epic 66 (Tool UX — path hints, checklist validation note), Epic 8 (Pipeline orchestration)

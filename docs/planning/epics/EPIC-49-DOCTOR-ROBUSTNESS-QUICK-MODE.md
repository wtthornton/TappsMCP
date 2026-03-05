# Epic 49: Doctor Robustness & Quick Mode

**Status:** Open
**Priority:** P2
**Estimated LOE:** ~1–1.5 weeks
**Dependencies:** None
**Blocks:** None
**Source:** Consuming project feedback — `OpenClawAgents/docs/tapps-mcp-feedback.md` (2026-03-05)

---

## Goal

Make `tapps-mcp doctor` more reliable on cold/slow environments and in timeout-sensitive contexts (e.g. agent runs with a 30s CLI timeout). Address mypy version check timeouts and add a fast “quick” or “skip-tools” mode so users and agents can get config/file validation without waiting for full tool probing.

## Problem Statement

Feedback from OpenClawAgents (session 2026-03-05) reported:

1. **Doctor: mypy version check timeout:** On first `tapps-mcp doctor` run, the mypy version check hit a 10s timeout. Doctor reported “PASS Tool: mypy: mypy (version unknown)” and a log line `command_timeout cmd=['mypy', '--version'] timeout=10`. Cause: `mypy --version` can be slow on first run or in a cold environment; 10s is tight on some machines.
2. **Doctor duration vs agent timeout:** When the agent ran `tapps-mcp doctor` in the project root, the command was still running after 30 seconds and was backgrounded. Doctor eventually completed with a full report, but in a strict 30s agent/CLI timeout it could be reported as failed or incomplete. Doctor runs several external tools (ruff, mypy, bandit, radon, vulture, pip-audit) and can exceed 30s, especially with mypy slow to start.

### Impact

| Issue | Severity | Workaround used in feedback |
|-------|----------|------------------------------|
| mypy version check timeout (10s) | Low | Re-run doctor; second run succeeded |
| Doctor run >30s | Low | Run in background or accept longer wait |

---

## Stories

### Story 49.1: Increase timeout for tool version checks (mypy)

**LOE:** S (~1–2 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/tools/tool_detection.py` (and optionally doctor if it calls tool detection with custom timeout)

The sync and async tool version probes use `timeout=10`. Increase the timeout for version-only checks so mypy (and other slow starters) have enough time on first run or cold environments.

**Options (choose one or combine):**

- **A:** Use a single higher default (e.g. 20s) for all tools in `run_command` / `run_command_async` when the command is a version check (e.g. `[name, "--version"]` or per-spec).
- **B:** Add a per-tool timeout override (e.g. mypy 20s, others 10s) in `_TOOL_SPECS` or in the detection helpers.
- **C:** Add a configurable timeout (env var or setting) for doctor/tool detection and default it to 15–20s for version checks.

**Acceptance Criteria:**

- `mypy --version` (and any other version probe) does not routinely hit the timeout on first run in a cold environment; either the default timeout is raised (e.g. 15–20s) or mypy has a dedicated longer timeout.
- Existing tests still pass; add or adjust tests if timeout constants change.
- No regression for fast tools (ruff, bandit, etc.); they should still complete well under the new limit.

---

### Story 49.2: Document doctor duration and timeout expectations

**LOE:** XS (~30–60 min)
**Files:** `AGENTS.md`, `README.md`, and/or `docs/` (troubleshooting, onboarding)

Document that `tapps-mcp doctor` may take **30–60+ seconds** depending on the environment (first run, cold mypy, many tools). Note that in automated or timeout-sensitive environments (e.g. agent CLI with a 30s cap), doctor might be reported as failed or incomplete; recommend running in background or using a longer timeout when full diagnostics are needed.

**Acceptance Criteria:**

- User-facing docs state that full doctor can take 30–60+ seconds.
- Guidance for timeout-sensitive use (e.g. “run in background” or “use quick mode when available”) is present where relevant.

---

### Story 49.3: Add doctor quick / skip-tools mode

**LOE:** M (~4–6 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py`, `packages/tapps-mcp/src/tapps_mcp/cli.py`

Add a “quick” or “skip-tools” mode that:

- Runs only config/file/connectivity checks (e.g. binary on PATH, MCP configs, AGENTS.md version, hooks, Docker daemon if applicable).
- Skips or shortens tool version checks (ruff, mypy, bandit, radon, vulture, pip-audit) so doctor returns in a few seconds.

**Implementation notes:**

- New CLI flag: e.g. `tapps-mcp doctor --quick` or `tapps-mcp doctor --skip-tools`.
- In quick mode, either omit `check_quality_tools()` (and any async tool checks) or run them with a very short timeout and report “skipped” or “quick mode”.
- Output should clearly indicate “Doctor (quick mode)” so users know tool versions were not fully probed.

**Acceptance Criteria:**

- `tapps-mcp doctor --quick` (or equivalent) completes in a few seconds (e.g. &lt; 10s) on a typical machine.
- Quick mode output states that tool version checks were skipped or abbreviated.
- Full `tapps-mcp doctor` (no flag) behavior unchanged.
- Tests added or updated for quick mode.

---

## Out of Scope

- Changing mypy’s own startup behavior or adding a “version-only” mode inside mypy (upstream).
- Changing agent or IDE timeout policies (host responsibility).

---

## Success Criteria

- Mypy version check no longer routinely times out at 10s on first/cold run.
- Users and docs know doctor can take 30–60+ s and have guidance for timeout-sensitive runs.
- A quick/skip-tools mode exists for fast config validation when full tool probing is not needed.

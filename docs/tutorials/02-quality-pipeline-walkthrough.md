# Tutorial: Run the quality pipeline against a fresh Python project

**Time:** ~10 minutes. **Outcome:** A new Python project bootstrapped with TappsMCP scaffolding, a deliberate quality issue introduced and detected, and the full validate-and-checklist flow run to green.

This walkthrough is the "first 30 minutes" experience for a consuming project. By the end you'll have seen each pipeline stage produce a structured response and you'll know what each tool is for.

## Prerequisites

- TappsMCP installed globally as an `uv tool` (or accessible via `uv run tapps-mcp`).
- An MCP-capable client (Claude Code, Cursor) — this tutorial uses Claude Code, but the tool calls are the same anywhere.

## Step 1 — Create a throwaway Python project

```bash
mkdir -p /tmp/tapps-tutorial && cd /tmp/tapps-tutorial
uv init --package tapps-tutorial --no-readme
```

You now have a minimal `pyproject.toml`, `src/tapps_tutorial/__init__.py`, and a virtualenv-ready layout.

## Step 2 — Bootstrap with `tapps_init`

Inside Claude Code (or any MCP client wired to tapps-mcp), call:

```
tapps_init(platform="claude", create_agents_md=True, create_tech_stack_md=True)
```

The tool writes:
- `AGENTS.md` — workflow guide for the next agent that opens this repo.
- `TECH_STACK.md` — placeholder you fill in with your stack.
- `.claude/` — platform rules, hooks, agents, skills.
- `.tapps-mcp.yaml` — config defaults.

**Verify:** `ls -la /tmp/tapps-tutorial` should show `AGENTS.md`, `.claude/`, and `.tapps-mcp.yaml`.

## Step 3 — Write a deliberately bad function

Create `src/tapps_tutorial/bad.py`:

```python
def process(data):
    result = []
    for item in data:
        if item:
            if item > 0:
                if item < 100:
                    if item % 2 == 0:
                        result.append(item * 2)
                        password = "hardcoded-secret-123"
    return result
```

Three problems baked in: missing type annotations, a hardcoded credential (security floor violation), and deeply nested conditionals (complexity hit).

## Step 4 — Score it with `tapps_quick_check`

```
tapps_quick_check(file_path="src/tapps_tutorial/bad.py")
```

Read the response. You should see:
- An overall score below 70.
- `gate_failed: true` because security drops below the floor of 50/100.
- A `next_steps` array with concrete remediation hints.
- A `categories` breakdown showing which of the seven categories pulled the score down (Complexity, Security, Maintainability, Test Coverage, Performance, Structure, DevEx).

`quick_check` is the per-file fast-feedback tool you call after every Python edit.

## Step 5 — Fix the file

Replace `bad.py` with a clean version:

```python
"""Tutorial example."""

from __future__ import annotations


def process(data: list[int]) -> list[int]:
    """Return doubled positive even numbers under 100."""
    return [item * 2 for item in data if 0 < item < 100 and item % 2 == 0]
```

Re-run `tapps_quick_check` on the same path. The score should now clear 70 and `gate_failed` should be `false`.

## Step 6 — Batch-validate the whole change

Multi-file changes go through `tapps_validate_changed` instead of one-quick-check-per-file:

```
tapps_validate_changed(file_paths="src/tapps_tutorial/bad.py")
```

**Always pass `file_paths` explicitly.** Auto-detect mode walks every git-changed file and is dramatically slower on large diffs (see [ADR-0006](../adr/0006-tapps-validate-changed-requires-explicit-file-paths.md)).

The response is the same shape as `quick_check` but aggregated across files, with a `gate_passed` summary at the top.

## Step 7 — Final checklist

```
tapps_checklist(task_type="feature")
```

The checklist tool consults the in-memory `_call_counter` (the thing `_record_call(...)` writes to) and reports whether each obligation was met for the current task type. For `task_type="feature"` you should see green checks against `tapps_session_start`, `tapps_quick_check`, and `tapps_validate_changed`. Any missing obligation appears with a fix hint.

**Verify:** the response includes `task_type: "feature"` and `summary.all_required_called: true`.

## What you learned

The four-stage feedback loop:

1. **Discover** — `tapps_session_start` once at the start of every session.
2. **Develop** — `tapps_quick_check` per Python file, in the edit-lint-fix loop.
3. **Validate** — `tapps_validate_changed` before declaring work complete.
4. **Verify** — `tapps_checklist(task_type)` as the final step.

Each stage's response carries `next_steps` — read them. They're how the deterministic tools nudge you toward the next correct call without needing an LLM in the loop.

## Cleanup

```bash
rm -rf /tmp/tapps-tutorial
```

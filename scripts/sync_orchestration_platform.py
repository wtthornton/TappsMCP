#!/usr/bin/env python3
"""Sync dev orchestration-prompt tree → platform_skill_orchestration.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DEV = ROOT / ".claude/skills/orchestration-prompt"
OUT = ROOT / "packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skill_orchestration.py"

FRONTMATTER = '''ORCHESTRATION_PROMPT_SKILL_FRONTMATTER = """\\
---
name: orchestration-prompt
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Generate a ready-to-run orchestration PROMPT: a verifiable Goal, a bounded loop,
  and an independent creator-verifier pass. Refuses foggy Goals — redirects to
  /tapps-wayfind. Use whenever the user wants to orchestrate multi-step, multi-repo,
  autonomous, or recurring work — "create a prompt to…", "orchestrate…", "make a
  goal for…", "work the backlog", "loop until X" — even if they don't say
  "orchestrate".
argument-hint: "[free-form objective]"
---
"""'''

HEADER = '''"""Platform ``orchestration-prompt`` skill — body + companion files."""

from __future__ import annotations

'''

LEARNINGS_SEED = '''_LEARNINGS_SEED = """\\
# orchestration-prompt learnings (project-scoped)

Append one-line lessons as you generate prompts. Keep them project-scoped; never
bleed across repos. This file is created once by the scaffolder and never
overwritten on upgrade — it's yours.

<!-- Example: -->
<!-- - Validation goals need a verified-correct-negative Done-when, or the loop chases an unreachable target. (2026-06-18) -->
"""'''

FOOTER = '''
ORCHESTRATION_PROMPT_COMPANION_FILES: dict[str, str] = {
    "assets/prompt-template.md": _PROMPT_TEMPLATE,
    "references/claude-feature-map.md": _FEATURE_MAP,
    "references/cold-start-and-verify.md": _COLD_START_AND_VERIFY,
    "references/host-feature-map.md": _HOST_FEATURE_MAP,
}

ORCHESTRATION_PROMPT_CREATE_ONLY_FILES: dict[str, str] = {
    "learnings.md": _LEARNINGS_SEED,
}

__all__ = [
    "ORCHESTRATION_PROMPT_COMPANION_FILES",
    "ORCHESTRATION_PROMPT_CREATE_ONLY_FILES",
    "ORCHESTRATION_PROMPT_SKILL_BODY",
]
'''


def _extract_skill_body(skill_md: str) -> str:
    start = skill_md.index("# orchestration-prompt")
    end = skill_md.index("<!-- END: tapps-skill -->")
    body = skill_md[start:end].rstrip()
    body = body.replace(
        "Selector table: `references/claude-feature-map.md`.",
        "Selector table: `references/claude-feature-map.md`. For host-specific "
        "Run-as, checkpoint lanes, and MCP scope, read `references/host-feature-map.md`.",
        1,
    )
    body = body.replace(
        "Checklists: `references/cold-start-and-verify.md`.",
        "Checklists: `references/cold-start-and-verify.md` (incl. "
        "`tapps_session_start()` as first MCP call).",
        1,
    )
    body = body.replace(
        "2. Read the workspace manifest",
        "2. Read `references/host-feature-map.md` when the runner host is Cursor "
        "or when Run-as / checkpoint lanes differ by host.\n"
        "3. Read the workspace manifest",
        1,
    )
    for old, new in (
        ("3. Fill `assets/prompt-template.md`", "4. Fill `assets/prompt-template.md`"),
        ("4. If any chunk is multi-stage", "5. If any chunk is multi-stage"),
        ("5. Save the prompt", "6. Save the prompt"),
        ("6. **Completeness self-check**", "7. **Completeness self-check**"),
        ("7. Tell the user exactly", "8. Tell the user exactly"),
    ):
        body = body.replace(old, new, 1)
    return body


def _py_raw_string(name: str, content: str) -> str:
    return f'{name} = r"""{content}"""'


def _patch_cold_start(content: str) -> str:
    insert = """
### 0. TAPPS session bootstrap (every loop)

Before any other TAPPS MCP tool in a fresh session (including after
`/tapps-continue-session`, which calls this internally): run `tapps_session_start()`.
Skipping it leaves the checker matrix and project context stale — a required-fail
cap when the loop depends on quality gates or `usage_gaps` telemetry.
`usage_gaps.recurring_validation_skips` is **7-day rolling fleet telemetry**, not
proof the current call failed; still run `tapps_validate_changed` + `tapps_checklist`
at epic boundaries in execution repos with full `nlt-build`.
"""
    if "### 0. TAPPS session bootstrap" in content:
        return content
    marker = "### 1. Capability preflight (every prompt)"
    return content.replace(marker, insert.strip() + "\n\n" + marker, 1)


def main() -> None:
    skill_md = (SKILL_DEV / "SKILL.md").read_text(encoding="utf-8")
    body = _extract_skill_body(skill_md)
    prompt_template = (SKILL_DEV / "assets/prompt-template.md").read_text(encoding="utf-8")
    if "tapps_session_start()" not in prompt_template:
        prompt_template = prompt_template.replace(
            "   - **Deploy freshness",
            "   - **TAPPS session bootstrap:** `tapps_session_start()` as the first MCP "
            "call (or `/tapps-continue-session` on resume).\n"
            "   - **Deploy freshness",
            1,
        )
    feature_map = (SKILL_DEV / "references/claude-feature-map.md").read_text(encoding="utf-8")
    cold_start = _patch_cold_start(
        (SKILL_DEV / "references/cold-start-and-verify.md").read_text(encoding="utf-8")
    )
    host_map = (SKILL_DEV / "references/host-feature-map.md").read_text(encoding="utf-8")

    parts = [
        HEADER,
        FRONTMATTER,
        "\nORCHESTRATION_PROMPT_SKILL_BODY = (\n"
        "    ORCHESTRATION_PROMPT_SKILL_FRONTMATTER\n"
        '    + r"""\n' + body + '\n"""\n)\n\n',
        _py_raw_string("_PROMPT_TEMPLATE", prompt_template) + "\n\n",
        _py_raw_string("_FEATURE_MAP", feature_map) + "\n\n",
        _py_raw_string("_COLD_START_AND_VERIFY", cold_start) + "\n\n",
        _py_raw_string("_HOST_FEATURE_MAP", host_map) + "\n\n",
        LEARNINGS_SEED,
        FOOTER,
    ]
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

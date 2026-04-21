"""Linear SDLC template renderer (TAP-410).

Templates are embedded as module-level strings with ``{{PREFIX}}`` /
``{{PREFIX_LOWER}}`` / ``{{AGENT_NAME}}`` / ``{{SKILL_PATH}}`` tokens.
We deliberately use double-braces rather than Python ``str.format``
placeholders because the hook scripts contain shell ``${...}`` syntax
and the workflow docs contain JSON fragments with literal ``{}`` — the
replacement scheme must not collide.
"""

from __future__ import annotations

from tapps_mcp.pipeline.linear_sdlc.config import LinearSDLCConfig

# ---------------------------------------------------------------------------
# Relative paths written into a consumer project. Order defines a stable
# rendering contract for the unit tests.
# ---------------------------------------------------------------------------

TEMPLATE_PATHS: tuple[str, ...] = (
    "docs/linear-sdlc/guides/WORKFLOW.md",
    "docs/linear-sdlc/guides/ISSUE_TEMPLATES.md",
    "docs/linear-sdlc/prompts/linear-sdlc-agent-guidance.md",
    ".claude/hooks/linear-sdlc-post-edit.sh",
    ".claude/hooks/linear-sdlc-post-commit.sh",
)


_WORKFLOW_MD = """\
# Linear SDLC Workflow

Real-time status update flow for every {{PREFIX}}-prefixed issue.

---

## The Core Rule

**Linear updates are part of the work — not cleanup after it.**

Status transitions happen at the moment they are true. Comments document
intent, decisions, and outcomes as they happen. Nothing is batched to the
end of a session.

---

## Full Issue Lifecycle

```
Issue in Backlog (+ needs-spec label if not agent-ready)
        |
        |  Spec written -> remove needs-spec, add spec-ready
        v
Issue is spec-ready (Goal / AC / Boundaries / DoD all present)
        |
        |  Agent picks up issue
        v
[ 1. Move to In Progress         ] <- FIRST action, before any code
[ 2. Remove spec-ready label     ]
[ 3. Post Template A (Kickoff)   ]
        |
        |  Implementation work
        v
[ 4. Post Template B (Checkpoint) ] <- At each major step / sub-issue
        |
        |  PR opened
        v
[ 5. Add in-review label         ]
[ 6. GitHub integration moves    ]
[    status (stays In Progress)  ]
        |
        |  Tests pass, PR ready
        v
[ 7. Run full test suite         ]
[ 8. Post Template C (Summary)   ] <- REQUIRED before Done
[ 9. Remove in-review label      ]
[10. Move to Done                ]
        |
        |  PR merged (GitHub auto-closes if wired)
        v
Issue Done - comment trail complete
```

---

## Status Transition Rules

| From | To | Trigger | Who |
|------|----|---------|-----|
| Backlog | In Progress | Agent starts work | Agent (manual) |
| In Progress | Done | Tests pass + Template C posted | Agent (manual) |
| Any | In Progress | Branch created with {{PREFIX_LOWER}}-XXX | GitHub integration (auto) |
| Any | Done | PR merged with closes {{PREFIX}}-XXX | GitHub integration (auto) |

**The GitHub integration is the backstop** — it catches cases where the
agent forgot to update manually. It does not replace the comment
requirement.

---

## Sub-Phase Label Rules

| Label | Add When | Remove When |
|-------|----------|-------------|
| `needs-spec` | Issue created without full template | Agent writes spec / retrofits sections |
| `spec-ready` | All 6 template sections complete | Agent picks up issue (starts work) |
| `in-review` | PR opened | PR merged or closed |
| `needs-tests` | Implementation done but coverage incomplete | Tests written and passing |

**Rule**: An issue with `needs-spec` is not agent-ready. Do not start work on it.

---

## EPIC Completion Rule

When the last story in an EPIC moves to Done:
1. Verify all sub-issues are Done
2. Post a summary comment on the EPIC parent issue
3. Move the EPIC parent to Done

---

## Enforcement Layers

```
Layer 1 - Policy    CLAUDE.local.md + SKILL.md (agent reads every session)
Layer 2 - Reminder  post-edit hook: fires on file edits referencing {{PREFIX}}-XXX
Layer 3 - Reminder  post-commit hook: fires on commits with {{PREFIX}}-XXX in message
Layer 4 - Backstop  GitHub integration: PR merge -> Done automatically
```

---

## Reference

| Document | Purpose |
|----------|---------|
| `ISSUE_TEMPLATES.md` | All comment templates (A, B, C) + issue description template |
| `prompts/linear-sdlc-agent-guidance.md` | Agent guidance prompt |
"""


_ISSUE_TEMPLATES_MD = """\
# Issue Templates

All templates used in the Linear SDLC workflow. Copy-paste ready.

---

## Issue Description Template

Use for every new story/task. All six sections are required.

```markdown
## Goal
[One sentence - what outcome is true when this is done?]

## Context
[Why this matters. 2-3 sentences of background or motivation.]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Tests pass: `uv run pytest -k 'test_name'`

## Technical Notes
- Files to touch: `path/...`
- Related issues: {{PREFIX}}-XXX

## Boundaries
- **Autonomous**: write code, create tests, edit existing files in scope
- **Ask first**: new dependencies, schema changes, public API surface changes
- **Never**: skip tests, touch prod config, commit credentials

## Definition of Done
- [ ] Implementation complete and working
- [ ] Tests written and passing (include count)
- [ ] Lint clean
- [ ] Type check clean
- [ ] Template C (Summary) comment posted on this issue
- [ ] Issue status set to Done
```

**Triage rule**: Issues missing any of these sections get the `needs-spec`
label and are not agent-ready.

---

## Template A - Kickoff Comment

Post as the **first action** when picking up an issue. Post before writing any code.

```markdown
## Work Starting - {{PREFIX}}-XXX

**Agent**: {{AGENT_NAME}}
**Started**: YYYY-MM-DD HH:MM
**Branch**: {{PREFIX_LOWER}}-XXX-short-title

### Approach
[1-2 sentences describing the implementation plan]

### Plan
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Status -> In Progress**
```

---

## Template B - Checkpoint Comment

Post at each **major implementation step**. Minimum one per issue.

```markdown
## Checkpoint - {{PREFIX}}-XXX

### Completed
- [Item completed]

### In Progress
- [Current item]

### Decisions / Notes
- [Any judgment calls, alternatives considered, or blockers]

### Up Next
- [Next step]
```

---

## Template C - Summary Comment

Post **before moving to Done**. Required - no issue closes without this.

```markdown
## Work Complete - {{PREFIX}}-XXX

**Agent**: {{AGENT_NAME}}
**Commit**: [SHA or branch]

### Changes
| File | Change |
|------|--------|
| `path/to/file.py` | [description of change] |

### Test Results
- **Backend**: N passed / 0 failed - `uv run pytest`
- **New tests**: [list key new test cases]

### Quality Gates
- [x] Lint: clean
- [x] Types: clean
- [x] Tests: all pass

### Decisions Made
- [Any architectural choices, tradeoffs, or alternatives rejected]

### Next Step
- [What a reviewer should check OR what issue picks up next]

**Status -> Done**
```

---

## Template D - Scope Update Comment

Post **immediately** when discovering the issue scope differs from the description.

```markdown
## Scope Discovery - {{PREFIX}}-XXX

### Finding
[What was discovered that changes the scope]

### Original Scope
[What the issue said to do]

### Actual Scope
[What actually needs to be done]

### Impact
- Stories added: [list, if any]
- Stories removed: [list, if any]
- Effort change: [more / less / same]

**Continuing with revised scope. No approval needed unless Boundaries are crossed.**
```

---

## Template E - EPIC Completion Comment

```markdown
## EPIC Complete - EPIC-N: Title

**Completed**: YYYY-MM-DD

### Stories Delivered
| Story | Issue | Summary |
|-------|-------|---------|
| N.1 | {{PREFIX}}-XXX | [one-line summary] |

### Outcome
[2-3 sentences: what the platform can now do that it couldn't before]

### Key Decisions
- [ADR or architectural decision made during this epic]

### Known Follow-ups
- [{{PREFIX}}-ZZZ]: [what was deferred and why]

**Status -> Done**
```
"""


_AGENT_GUIDANCE_MD = """\
# linear-sdlc-agent-guidance

When: Load whenever an agent picks up a {{PREFIX}}-prefixed Linear issue to
implement, fix, or review. Also injected into Linear's native Agent Guidance
settings and CLAUDE.local.md so it is always active.

## Purpose

This prompt is for agents working on {{PREFIX}}-prefixed Linear issues so
that Linear reflects true implementation state in real time, with every
issue's lifecycle fully documented via structured comments at each SDLC
transition - not batched at the end of a session.

## Success criteria

Every {{PREFIX}} issue shows: (1) status moved to In Progress at work
START; (2) at least one kickoff comment posted; (3) checkpoint comments
at each major step; (4) a summary comment with test results before Done;
(5) status moved to Done only after summary is posted.

## Steps

1. Read the issue description - it is the work contract. Do not start if
   `needs-spec` label is set.
2. Create a branch named `{{PREFIX_LOWER}}-NNN-short-title` (hyphens only,
   lowercase, no username prefix). This triggers the GitHub -> Linear
   auto-transition to In Progress.
3. Move issue to In Progress via MCP and post Template A (Kickoff comment) -
   even if GitHub already moved it.
4. Implement. Post Template B (Checkpoint) at each major step - minimum one
   per sub-issue completed.
5. Run full tests.
6. Post Template C (Summary) with actual test counts and changed files.
7. Move issue to Done only AFTER Template C is posted.
8. If all stories in an EPIC are Done, move the EPIC parent issue to Done.

## Rules

- Create branches as `{{PREFIX_LOWER}}-NNN-short-title` - this is mandatory
  for GitHub auto-transitions to fire.
- Move issue to In Progress BEFORE writing any code - not after.
- Post Template A (Kickoff) as first comment on any issue.
- Post Template B (Checkpoint) at each major implementation step.
- Run all tests before marking Done.
- Post Template C (Summary) with actual test counts and changed files
  before moving to Done.

## Don't

- batch Linear status updates to the end of a session
- mark Done without a summary comment
- skip tests before marking Done
- create issues without Goal/AC/Boundaries/DoD sections
- use statuses other than Backlog/In Progress/Done
- name branches with slashes, usernames, or uppercase (breaks auto-transitions)
"""


_POST_EDIT_HOOK_SH = """\
#!/bin/bash
# Linear SDLC - Post-Edit Hook
#
# Fires after every Write or Edit tool use. Detects {{PREFIX}}-XXX
# references in the edited file and prints a reminder if status may need
# updating.
#
# Install by adding to ~/.claude/settings.json:
#
# {
#   "hooks": {
#     "PostToolUse": [{
#       "matcher": "Write|Edit",
#       "hooks": [{
#         "type": "command",
#         "command": "bash {{SKILL_PATH}}/hooks/post-edit.sh"
#       }]
#     }]
#   }
# }

set -e

input=$(cat 2>/dev/null || echo "{}")
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")

if [ -z "$file_path" ]; then
  exit 0
fi

# Only process source code files
if [[ ! "$file_path" =~ \\.(ts|tsx|js|jsx|astro|py|go|rs|md)$ ]]; then
  exit 0
fi

# Skip test files, config, build artifacts
if [[ "$file_path" == *".test."* ]] || [[ "$file_path" == *".spec."* ]]; then exit 0; fi
if [[ "$file_path" == *"/test/"* ]] || [[ "$file_path" == *"/tests/"* ]]; then exit 0; fi
if [[ "$file_path" == *"node_modules"* ]]; then exit 0; fi
if [[ "$file_path" == *"/dist/"* ]] || [[ "$file_path" == *"/build/"* ]]; then exit 0; fi

filename="${file_path##*/}"

# Extract issue references from the file
issue_refs=""
if [ -f "$file_path" ]; then
  issue_refs=$(grep -oE '[A-Z]{2,5}-[0-9]+' "$file_path" 2>/dev/null | sort -u | head -10 | tr '\\n' ' ' || echo "")
fi

prefixed=$(echo "$issue_refs" | tr ' ' '\\n' | grep '^{{PREFIX}}-' | tr '\\n' ' ' | sed 's/ $//')

if [ -n "$prefixed" ]; then
  echo "[linear-sdlc] $filename references: $prefixed"
  echo "[linear-sdlc] If In Progress: have you posted a Checkpoint (Template B) recently?"
  echo "[linear-sdlc] If work complete: cd {{SKILL_PATH}} && npm run ops -- status Done ${prefixed// /,}"
fi

exit 0
"""


_POST_COMMIT_HOOK_SH = """\
#!/bin/bash
# Linear SDLC - Post-Commit Hook
#
# Fires after every git commit. Extracts {{PREFIX}}-XXX references from
# the commit message and prints a reminder to update Linear status if
# work is complete.

set -e

input=$(cat 2>/dev/null || echo "{}")
cmd=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# Only fire on git commit commands (Claude hook context)
if [ -n "$cmd" ] && ! echo "$cmd" | grep -qE 'git (commit|merge)'; then
  exit 0
fi

# Get the most recent commit message
msg=$(git log -1 --pretty=%B 2>/dev/null || echo "")
if [ -z "$msg" ]; then
  exit 0
fi

# Extract issue references
prefixed=$(echo "$msg" | grep -oE '{{PREFIX}}-[0-9]+' | sort -u | tr '\\n' ' ' | sed 's/ $//')

if [ -n "$prefixed" ]; then
  echo ""
  echo "[linear-sdlc] Commit references: $prefixed"
  echo "[linear-sdlc] SDLC checklist:"
  echo "[linear-sdlc]   - Posted Template C (Summary) on the issue? If not: post it now"
  echo "[linear-sdlc]   - Tests passing? If yes and PR is open, issue can move to Done"
  echo "[linear-sdlc]   Update status: cd {{SKILL_PATH}} && npm run ops -- status Done ${prefixed// /,}"
  echo ""
fi

exit 0
"""


_TEMPLATES: dict[str, str] = {
    "docs/linear-sdlc/guides/WORKFLOW.md": _WORKFLOW_MD,
    "docs/linear-sdlc/guides/ISSUE_TEMPLATES.md": _ISSUE_TEMPLATES_MD,
    "docs/linear-sdlc/prompts/linear-sdlc-agent-guidance.md": _AGENT_GUIDANCE_MD,
    ".claude/hooks/linear-sdlc-post-edit.sh": _POST_EDIT_HOOK_SH,
    ".claude/hooks/linear-sdlc-post-commit.sh": _POST_COMMIT_HOOK_SH,
}


def render_template(text: str, config: LinearSDLCConfig) -> str:
    """Apply ``{{PLACEHOLDER}}`` substitutions to a single template string."""
    return (
        text.replace("{{PREFIX_LOWER}}", config.prefix_lower)
        .replace("{{PREFIX}}", config.issue_prefix)
        .replace("{{AGENT_NAME}}", config.agent_name)
        .replace("{{SKILL_PATH}}", config.skill_path)
    )


def render_all(config: LinearSDLCConfig) -> dict[str, str]:
    """Return ``{relative_path: rendered_content}`` for all templates."""
    return {path: render_template(body, config) for path, body in _TEMPLATES.items()}

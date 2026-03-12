# Skills (SKILL.md) — Cross-Platform Reference

**Source:** Deep research conducted 2026-02-21
**Standard:** Open Agent Skills Standard (skill.md)

## Overview

Skills are modular, portable instruction sets that agents load only when relevant.
Both Claude Code and Cursor support the SKILL.md format. The open standard is
supported by 20+ coding agents.

## Directory Locations

### Claude Code
- **Project:** `.claude/skills/skill-name/SKILL.md`
- **User:** `~/.claude/skills/skill-name/SKILL.md`

### Cursor
- **Project:** `.cursor/skills/skill-name/SKILL.md`
- **User:** `~/.cursor/skills/skill-name/SKILL.md`

## SKILL.md Format

```yaml
---
name: skill-name
description: When this skill should be activated by the agent.
---

# Skill Title

## When to Use
- Trigger conditions

## Step-by-Step Instructions
1. First step
2. Second step

## Conventions and Best Practices
- Best practice 1

## Examples
- "User says X" triggers this skill

## Important Notes
- Dependencies and requirements
```

### Required Fields
- `description` (YAML frontmatter) — Agent decides activation based on this

### Optional Fields
- `name` — Defaults to folder name
- `license`, `compatibility`, `metadata` — Additional metadata

### Recommendations
- Under 5000 tokens / 500 lines for the markdown body
- Action-oriented descriptions for proactive activation

## Supporting Files

```
.cursor/skills/tapps-quality-gate/
  SKILL.md                    # Required
  references/                 # Additional context docs
    scoring-categories.md
    gate-presets.md
  scripts/                    # Automation scripts
    validate.sh
  assets/                     # Images, diagrams
```

## How Skills Interact with MCP Tools

Skills **can reference MCP tools by name** in their instructions. The agent
will invoke those MCP tools when executing the skill. Skills are effectively
"meta-prompts" that orchestrate MCP tool usage.

Example:
```markdown
## Step-by-Step Instructions
1. Call the `tapps_session_start` MCP tool
2. Call `tapps_quick_check` on the changed files
3. Call `tapps_quality_gate` with preset "production"
```

## TappsMCP Skills to Generate

### tapps-score (Both Platforms)

```yaml
---
name: tapps-score
description: Use this skill when the user asks to score, rate, or evaluate the quality of Python files.
---

# Score Python Files

## When to Use
- User asks to "score" or "rate" a file
- User asks about code quality of specific files
- User wants to know the quality of their code

## Step-by-Step Instructions
1. Call `tapps_session_start` if not already started
2. Call `tapps_score_file` with the target file path
3. Present the 7-category breakdown (complexity, security, style, etc.)
4. Highlight any category scoring below 70
5. For low-scoring categories, call `tapps_explain_score` for details

## Important Notes
- Scores range 0-100 across 7 categories
- If `degraded: true`, external tools were unavailable (AST fallback used)
```

### tapps-gate (Both Platforms)

```yaml
---
name: tapps-gate
description: Use this skill when the user wants to run a quality gate, check if code is ready to merge, or validate code against standards.
---

# Quality Gate Check

## When to Use
- User asks if code is "ready to merge"
- User wants to run a "quality gate"
- Before creating a PR
- User says "validate my changes"

## Step-by-Step Instructions
1. Call `tapps_session_start` if not already started
2. Call `tapps_validate_changed` to check all modified files
3. If failures found, report which files and categories need work
4. For passing results, confirm with summary scores
5. Suggest calling `tapps_quality_gate` with a specific preset if needed

## Gate Presets
- **development** — Lenient, for feature branches
- **staging** — Moderate, for pre-merge
- **production** — Strict, for releases
```

### tapps-validate (Both Platforms)

```yaml
---
name: tapps-validate
description: Use this skill before declaring any coding task complete to ensure all changes meet quality standards.
---

# Pre-Completion Validation

## When to Use
- Agent is about to declare work complete
- User says "I'm done" or "ship it"
- Before creating a commit or PR

## Step-by-Step Instructions
1. Call `tapps_validate_changed` to check all modified files
2. If any file fails, DO NOT declare work complete
3. Report failures with specific file paths and scores
4. Suggest fixes for the lowest-scoring categories
5. Re-validate after fixes are applied
6. Only declare complete when all files pass

## Important Notes
- This skill should be used EVERY TIME before completing work
- A passing gate is required for production-quality code
```

## Ecosystem

- **Vercel `npx skills`** CLI: Install, manage, discover skills across agents
- Skills are portable across Claude Code, Cursor, Codex, and 20+ other tools

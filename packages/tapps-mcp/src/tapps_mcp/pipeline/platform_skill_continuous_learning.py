"""Platform ``continuous-learning-v2`` skill — slim SKILL.md + companions.

Deep reference content lives in companion markdown so autoload stays under the
progressive-disclosure threshold (docs/SKILL_AUTHORING.md Rule 3 / ADR-0031).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared body prose (host-agnostic after frontmatter)
# ---------------------------------------------------------------------------

_BODY = r"""
# Continuous Learning v2.1 - Instinct-Based Architecture

Turns Claude Code sessions into reusable knowledge via atomic **instincts** —
small learned behaviors with confidence scoring.

**v2.1** adds **project-scoped instincts** so framework conventions stay in the
project that taught them, while universal patterns can still be global.

## When to Activate

- Setting up automatic learning from Claude Code sessions
- Configuring instinct-based extraction via hooks
- Tuning confidence thresholds or reviewing instinct libraries
- Evolving instincts into skills, commands, or agents
- Managing project vs global scope / promoting instincts

## Instincts (summary)

An instinct is one trigger -> one action, with confidence (0.3-0.9), domain tags,
evidence, and scope (`project` default or `global`).

Full YAML example and pipeline diagram:
[references/architecture.md](references/architecture.md).

## Commands

| Command | Description |
|---------|-------------|
| `/instinct-status` | Show instincts (project + global) with confidence |
| `/evolve` | Cluster instincts into skills/commands; suggest promotions |
| `/instinct-export` | Export instincts (filterable by scope/domain) |
| `/instinct-import <file>` | Import instincts with scope control |
| `/promote [id]` | Promote project instincts to global scope |
| `/projects` | List known projects and instinct counts |

## Quick Start

1. **Hooks** — wire `observe.sh` on PreToolUse/PostToolUse (plugin or
   `~/.claude/skills/...` path). Full JSON:
   [references/operations.md](references/operations.md#quick-start-hooks).
2. **Dirs** — created on first use under `~/.claude/homunculus/` (global +
   per-project hashes).
3. **Operate** — `/instinct-status`, `/evolve`, `/promote` as needed.

## Companions

| Topic | File |
|-------|------|
| Architecture, instinct model, project detection, what's new | [references/architecture.md](references/architecture.md) |
| Hooks setup, config, scope, promotion, confidence, privacy | [references/operations.md](references/operations.md) |

Load companions only when configuring or debugging the learning system.
"""

CONTINUOUS_LEARNING_CLAUDE_SKILL_BODY = """\
---
name: continuous-learning-v2
user-invocable: true
description: >-
  Instinct-based learning system that observes sessions via hooks, creates
  atomic instincts with confidence scoring, and evolves them into
  skills/commands/agents. v2.1 adds project-scoped instincts. Use when setting
  up continuous learning, tuning instincts, evolving learned behaviors, or
  managing project vs global instinct scope.
origin: ECC
version: 2.1.0
model: claude-sonnet-4-6
---
""" + _BODY

CONTINUOUS_LEARNING_CURSOR_SKILL_BODY = """\
---
name: continuous-learning-v2
description: >-
  Instinct-based learning system that observes sessions via hooks, creates
  atomic instincts with confidence scoring, and evolves them into
  skills/commands/agents. v2.1 adds project-scoped instincts. Use when setting
  up continuous learning, tuning instincts, evolving learned behaviors, or
  managing project vs global instinct scope.
origin: ECC
version: 2.1.0
---
""" + _BODY

_ARCHITECTURE = r"""# Continuous Learning — Architecture

## What's New in v2.1

| Feature | v2.0 | v2.1 |
|---------|------|------|
| Storage | Global (~/.claude/homunculus/) | Project-scoped (projects/<hash>/) |
| Scope | All instincts apply everywhere | Project-scoped + global |
| Detection | None | git remote URL / repo path |
| Promotion | N/A | Project → global when seen in 2+ projects |
| Commands | 4 (status/evolve/export/import) | 6 (+promote/projects) |
| Cross-project | Contamination risk | Isolated by default |

## What's New in v2 (vs v1)

| Feature | v1 | v2 |
|---------|----|----|
| Observation | Stop hook (session end) | PreToolUse/PostToolUse (100% reliable) |
| Analysis | Main context | Background agent (Haiku) |
| Granularity | Full skills | Atomic "instincts" |
| Confidence | None | 0.3-0.9 weighted |
| Evolution | Direct to skill | Instincts -> cluster -> skill/command/agent |
| Sharing | None | Export/import instincts |

## The Instinct Model

```yaml
---
id: prefer-functional-style
trigger: "when writing new functions"
confidence: 0.7
domain: "code-style"
source: "session-observation"
scope: project
project_id: "a1b2c3d4e5f6"
project_name: "my-react-app"
---

# Prefer Functional Style

## Action
Use functional patterns over classes when appropriate.

## Evidence
- Observed 5 instances of functional pattern preference
- User corrected class-based approach to functional on 2025-01-15
```

**Properties:**
- **Atomic** -- one trigger, one action
- **Confidence-weighted** -- 0.3 = tentative, 0.9 = near certain
- **Domain-tagged** -- code-style, testing, git, debugging, workflow, etc.
- **Evidence-backed** -- tracks what observations created it
- **Scope-aware** -- `project` (default) or `global`

## How It Works

```
Session Activity (in a git repo)
      |
      | Hooks capture prompts + tool use (100% reliable)
      | + detect project context (git remote / repo path)
      v
+---------------------------------------------+
|  projects/<project-hash>/observations.jsonl  |
|   (prompts, tool calls, outcomes, project)   |
+---------------------------------------------+
      |
      | Observer agent reads (background, Haiku)
      v
+---------------------------------------------+
|          PATTERN DETECTION                   |
|   * User corrections -> instinct             |
|   * Error resolutions -> instinct            |
|   * Repeated workflows -> instinct           |
|   * Scope decision: project or global?       |
+---------------------------------------------+
      |
      | Creates/updates
      v
+---------------------------------------------+
|  projects/<project-hash>/instincts/personal/ |
|   * prefer-functional.yaml (0.7) [project]   |
|   * use-react-hooks.yaml (0.9) [project]     |
+---------------------------------------------+
|  instincts/personal/  (GLOBAL)               |
|   * always-validate-input.yaml (0.85) [global]|
|   * grep-before-edit.yaml (0.6) [global]     |
+---------------------------------------------+
      |
      | /evolve clusters + /promote
      v
+---------------------------------------------+
|  projects/<hash>/evolved/ (project-scoped)   |
|  evolved/ (global)                           |
|   * commands/new-feature.md                  |
|   * skills/testing-workflow.md               |
|   * agents/refactor-specialist.md            |
+---------------------------------------------+
```

## Project Detection

1. **`CLAUDE_PROJECT_DIR` env var** (highest priority)
2. **`git remote get-url origin`** -- hashed to a portable project ID
3. **`git rev-parse --show-toplevel`** -- fallback (machine-specific)
4. **Global fallback** -- if no project is detected

Each project gets a 12-character hash ID. Registry:
`~/.claude/homunculus/projects.json`.
"""

_OPERATIONS = r"""# Continuous Learning — Operations

## Quick Start: Hooks

Add to `~/.claude/settings.json`.

**Plugin install** (recommended):

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }]
  }
}
```

**Manual install** under `~/.claude/skills`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/skills/continuous-learning-v2/hooks/observe.sh"
      }]
    }]
  }
}
```

### Initialize directories

```bash
# Global directories
mkdir -p ~/.claude/homunculus/{instincts/{personal,inherited},evolved/{agents,skills,commands},projects}

# Project directories are auto-created when the hook first runs in a git repo
```

## Configuration

Edit `config.json` to control the background observer:

```json
{
  "version": "2.1",
  "observer": {
    "enabled": false,
    "run_interval_minutes": 5,
    "min_observations_to_analyze": 20
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `observer.enabled` | `false` | Enable the background observer agent |
| `observer.run_interval_minutes` | `5` | How often the observer analyzes observations |
| `observer.min_observations_to_analyze` | `20` | Minimum observations before analysis runs |

Other behavior is configured via defaults in `instinct-cli.py` and `observe.sh`.

## Scope Decision Guide

| Pattern Type | Scope | Examples |
|-------------|-------|---------|
| Language/framework conventions | **project** | "Use React hooks", "Follow Django REST patterns" |
| File structure preferences | **project** | "Tests in `__tests__`/", "Components in src/components/" |
| Code style | **project** | "Use functional style", "Prefer dataclasses" |
| Error handling strategies | **project** | "Use Result type for errors" |
| Security practices | **global** | "Validate user input", "Sanitize SQL" |
| General best practices | **global** | "Write tests first", "Always handle errors" |
| Tool workflow preferences | **global** | "Grep before Edit", "Read before Write" |
| Git practices | **global** | "Conventional commits", "Small focused commits" |

## Instinct Promotion (Project -> Global)

**Auto-promotion criteria:**
- Same instinct ID in 2+ projects
- Average confidence >= 0.8

```bash
# Promote a specific instinct
python3 instinct-cli.py promote prefer-explicit-errors

# Auto-promote all qualifying instincts
python3 instinct-cli.py promote

# Preview without changes
python3 instinct-cli.py promote --dry-run
```

The `/evolve` command also suggests promotion candidates.

## Confidence Scoring

| Score | Meaning | Behavior |
|-------|---------|----------|
| 0.3 | Tentative | Suggested but not enforced |
| 0.5 | Moderate | Applied when relevant |
| 0.7 | Strong | Auto-approved for application |
| 0.9 | Near-certain | Core behavior |

**Increases** when the pattern is repeatedly observed, the user doesn't correct
it, or similar instincts agree. **Decreases** on explicit correction,
long absence, or contradicting evidence.

## Why Hooks vs Skills for Observation?

v1 skills were probabilistic (~50-80% fire rate). Hooks fire **100%** of the
time, so every tool call is observed and learning is comprehensive.

## Backward Compatibility

v2.1 remains compatible with v2.0 and v1:
- Existing global instincts still work as global
- Existing `~/.claude/skills/learned/` skills from v1 still work
- Stop hook still runs (and feeds v2)
- Gradual migration: run both in parallel

## Privacy

- Observations stay **local** on your machine
- Project-scoped instincts are isolated per project
- Only **instincts** (patterns) can be exported — not raw observations
- No actual code or conversation content is shared
- You control what gets exported and promoted
"""

CONTINUOUS_LEARNING_COMPANION_FILES: dict[str, str] = {
    "references/architecture.md": _ARCHITECTURE,
    "references/operations.md": _OPERATIONS,
}

__all__ = [
    "CONTINUOUS_LEARNING_CLAUDE_SKILL_BODY",
    "CONTINUOUS_LEARNING_COMPANION_FILES",
    "CONTINUOUS_LEARNING_CURSOR_SKILL_BODY",
]

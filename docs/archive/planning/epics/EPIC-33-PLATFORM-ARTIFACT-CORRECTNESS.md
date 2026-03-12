# Epic 33: Platform Artifact Correctness

**Status:** Complete (2026-03-01) — all 5 stories, 142 new tests
**Priority:** P0 — Critical (TappsMCP generates skills/subagents with incorrect or missing frontmatter fields per 2026 Claude Code docs)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 8 (Pipeline Orchestration)
**Blocks:** Epic 36 (Hook & Platform Generation Expansion), Epic 37 (Pipeline Onboarding & Distribution)

---

## Goal

Fix correctness issues in TappsMCP-generated platform artifacts (skills, subagents, rules) so they conform to the 2026 Claude Code specification. The current `platform_skills.py` uses `tools:` instead of `allowed-tools:` in skill frontmatter, and `platform_subagents.py` omits critical fields like `mcpServers` and `maxTurns` (note: `model` and `permissionMode` already exist on some subagents but need updating). These are not enhancements — they are correctness bugs that cause generated artifacts to behave incorrectly or sub-optimally in consuming projects.

## Rationale

| Issue | Impact on Consuming Projects |
|-------|------------------------------|
| `tools:` instead of `allowed-tools:` | Skill tool restrictions may not be enforced (non-standard field name) |
| No `mcpServers` on subagents | Spawned subagents cannot call TappsMCP MCP tools at all |
| Suboptimal `model` routing | Some subagents use correct model but `tapps-validator` uses `sonnet` when `haiku` suffices |
| No `maxTurns` on subagents | Runaway agents can consume unlimited turns/tokens |
| No `disable-model-invocation` | Workflow skills (validate, gate) get auto-invoked when they should be user-triggered |
| No `argument-hint` | No autocomplete hints in `/` skill menu |
| `permissionMode` inconsistencies | Researcher has no permissionMode; others use `dontAsk` instead of role-appropriate values |
| No `skills` preloading | Subagents don't preload relevant TappsMCP skills for quick access |

## 2026 Best Practices Applied (verified against Claude Code docs 2026-02-28)

- **2026 Skill frontmatter spec** — Verified fields: `name`, `description`, `allowed-tools` (NOT `tools`), `model`, `context` (`fork`), `disable-model-invocation`, `argument-hint`, `agent`, `hooks`, `user-invocable`. Source: [code.claude.com/docs/en/skills.md](https://code.claude.com/docs/en/skills.md)
- **2026 Subagent frontmatter spec** — Verified fields: `name`, `description`, `tools`, `disallowedTools`, `model` (`sonnet`/`opus`/`haiku`/`inherit`), `maxTurns`, `permissionMode` (`default`/`acceptEdits`/`dontAsk`/`bypassPermissions`/`plan`), `skills`, `mcpServers`, `hooks`, `memory` (`user`/`project`/`local`), `background`, `isolation` (`worktree`). Source: [code.claude.com/docs/en/sub-agents.md](https://code.claude.com/docs/en/sub-agents.md)
- **2026 `.claude/rules/` with `paths:` frontmatter** — Verified: path-scoped rules use `paths:` YAML frontmatter with glob patterns (e.g., `"**/*.py"`). Rules without `paths:` load unconditionally. Source: [code.claude.com/docs/en/memory.md](https://code.claude.com/docs/en/memory.md)
- **2026 Permission wildcards** — Verified: `mcp__tapps-mcp__*` wildcard syntax works in `.claude/settings.json`. Also supports `mcp__<server-name>` (all tools from server). Source: [code.claude.com/docs/en/permissions.md](https://code.claude.com/docs/en/permissions.md)
- **Model routing for cost optimization** — Read-only tasks (research, validation) use `model: haiku` (~5-10x cheaper than Opus). Code-writing tasks use `model: sonnet`.
- **Deterministic** — No LLM calls. Same input produces same output.

## Acceptance Criteria

- [ ] All 7 generated skills use `allowed-tools:` instead of `tools:` in frontmatter
- [ ] Skills that should be user-triggered only have `disable-model-invocation: true` (`tapps-gate`, `tapps-validate`)
- [ ] All skills have `argument-hint` for autocomplete UX
- [ ] `tapps-research` skill uses `context: fork` and `model: haiku`
- [ ] `tapps-review-pipeline` skill uses `context: fork` and `agent: general-purpose`
- [ ] All 4 generated subagents have `mcpServers: { tapps-mcp: {} }` in frontmatter
- [ ] Subagents specify appropriate `model:` (`tapps-researcher: haiku`, `tapps-reviewer: sonnet`)
- [ ] Subagents specify `maxTurns` to prevent runaway execution
- [ ] `tapps-researcher` subagent has `permissionMode: plan` (read-only)
- [ ] `tapps-reviewer` subagent preloads relevant skills via `skills:` field
- [ ] `tapps-review-fixer` subagent has `isolation: worktree`
- [ ] Generated `.claude/rules/python-quality.md` with `paths: ["**/*.py"]` scoping
- [ ] All existing tests updated; new tests for each frontmatter field
- [ ] Upgrade path: `tapps_upgrade` regenerates corrected artifacts

---

## Stories

### 33.1 — Fix Skill Frontmatter Fields

**Points:** 5

Fix all 7 generated skill templates to use correct 2026 Claude Code frontmatter field names and add missing fields.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`

**Tasks:**
- Rename `tools:` to `allowed-tools:` in all 7 skill templates (`CLAUDE_SKILLS` dict)
- Add `argument-hint:` to each skill:
  - `tapps-score`: `"[file-path]"`
  - `tapps-gate`: `"[file-path]"`
  - `tapps-validate`: (no hint — operates on changed files)
  - `tapps-review-pipeline`: (no hint — operates on changed files)
  - `tapps-research`: `"[question]"`
  - `tapps-memory`: `"[action] [key]"`
  - `tapps-security`: `"[file-path]"`
- Add `disable-model-invocation: true` to workflow-only skills:
  - `tapps-gate` — quality gate should be user-triggered, not auto-invoked
  - `tapps-validate` — validation should be user-triggered
- Add `context: fork` to heavy/isolated skills:
  - `tapps-review-pipeline` — spawns parallel agents, should be isolated
  - `tapps-research` — read-only research, benefits from fork isolation
- Add `model: haiku` to read-only skills:
  - `tapps-research` — lightweight research, haiku is sufficient
- Add `agent: general-purpose` to `tapps-review-pipeline` (specifies subagent type for fork)
- Update `generate_skills()` function if it applies any transformations to templates
- Update existing tests in `tests/unit/test_platform_skills.py` for new field assertions
- Write ~8 new tests: one per skill verifying all frontmatter fields are present and correct

**Definition of Done:** All 7 skills generate with correct frontmatter. `allowed-tools` used everywhere. Tests pass for every field.

---

### 33.2 — Fix Subagent Frontmatter Fields

**Points:** 5

Fix all 4 generated subagent templates to add missing fields and update incorrect field values per the 2026 spec.

**Current State (verified 2026-02-28):**
| Subagent | Has `model` | Has `permissionMode` | Has `memory` | Has `mcpServers` | Has `maxTurns` |
|----------|-------------|---------------------|--------------|-----------------|---------------|
| tapps-reviewer | `sonnet` | `dontAsk` | `project` | NO | NO |
| tapps-researcher | `haiku` | NO | `project` | NO | NO |
| tapps-validator | `sonnet` | `dontAsk` | `project` | NO | NO |
| tapps-review-fixer | (need verify) | (need verify) | (need verify) | NO | NO |

**Note:** The `tools:` field on subagents (e.g., `tools: Read, Glob, Grep`) is the correct 2026 Claude Code agent frontmatter field. Do NOT confuse this with skills' `allowed-tools:` field — they are different specs.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_subagents.py`

**Tasks:**
- **ADD** `mcpServers:` block to all 4 subagent templates:
  ```yaml
  mcpServers:
    tapps-mcp: {}
  ```
  This ensures spawned subagents can call TappsMCP MCP tools. Without this, subagents inherit parent connections which is not guaranteed across Claude Code versions.
- **UPDATE** `model:` where suboptimal (currently set but needs changing):
  - `tapps-researcher`: `model: haiku` (already correct)
  - `tapps-reviewer`: `model: sonnet` (already correct)
  - `tapps-validator`: CHANGE from `model: sonnet` to `model: haiku` (mechanical validation, doesn't need deep reasoning)
  - `tapps-review-fixer`: `model: sonnet` (verify and set)
- **ADD** `maxTurns:` to all subagents (currently missing from all):
  - `tapps-researcher`: `maxTurns: 15`
  - `tapps-reviewer`: `maxTurns: 20`
  - `tapps-validator`: `maxTurns: 10`
  - `tapps-review-fixer`: `maxTurns: 25`
- **UPDATE/ADD** `permissionMode:` to role-appropriate values:
  - `tapps-researcher`: ADD `permissionMode: plan` (currently missing — read-only agent)
  - `tapps-reviewer`: CHANGE from `dontAsk` to `permissionMode: acceptEdits` (can suggest fixes)
  - `tapps-validator`: CHANGE from `dontAsk` to `permissionMode: plan` (read-only validation)
  - `tapps-review-fixer`: SET `permissionMode: acceptEdits` (must edit to fix)
- **ADD** `skills:` preloading where relevant:
  - `tapps-reviewer`: `skills: [tapps-score, tapps-gate]`
  - `tapps-review-fixer`: `skills: [tapps-score, tapps-gate, tapps-validate]`
- **ADD** `isolation: worktree` to `tapps-review-fixer` (file editing should be isolated)
- `memory: project` already exists on reviewer, researcher, and validator — verify review-fixer has it too
- Update `generate_subagents()` function for new fields
- Update existing tests; write ~8 new tests: one per subagent verifying all frontmatter fields

**Definition of Done:** All 4 subagents generate with `mcpServers`, `maxTurns`, role-appropriate `permissionMode`, and `skills` preloading. Tests verify every field.

---

### 33.3 — Generate Path-Scoped Quality Rules

**Points:** 3

Generate `.claude/rules/python-quality.md` with `paths:` frontmatter so quality reminders only activate when Claude reads Python files, not on every conversation turn.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

**Tasks:**
- Create a new rule template in `platform_generators.py`:
  ```markdown
  ---
  paths:
    - "**/*.py"
  ---
  # Python Quality Rules (TappsMCP)
  - Run tapps_quick_check after editing Python files
  - Use tapps_research before using unfamiliar library APIs
  - Call tapps_validate_changed before declaring work complete
  - Do NOT mark tasks complete if quality gate has not passed
  ```
- Create engagement-level variants:
  - `high`: All rules are imperative ("MUST", "REQUIRED")
  - `medium`: Rules use "should" (default)
  - `low`: Rules use "consider" and are suggestions only
- Add rule generation to `tapps_init` (writes `.claude/rules/python-quality.md`)
- Add rule regeneration to `tapps_upgrade`
- Ensure `tapps_upgrade --dry-run` shows the new file would be created
- Write ~5 tests: rule content at each engagement level, path frontmatter correctness, init integration

**Definition of Done:** `tapps_init` generates path-scoped Python rules. Engagement-level variants work. Upgrade regenerates.

---

### 33.4 — Generate Permission Rules

**Points:** 3

Generate MCP tool permission rules in `.claude/settings.json` so consuming projects auto-approve TappsMCP tool calls without repeated permission prompts.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

**Tasks:**
- During `tapps_init`, generate or update `.claude/settings.json` with permission rules:
  ```json
  {
    "permissions": {
      "allow": [
        "mcp__tapps-mcp__*"
      ]
    }
  }
  ```
- Merge with existing settings.json if it already exists (do not clobber user rules)
- At `engagement_level: high`, optionally add:
  ```json
  {
    "permissions": {
      "allow": [
        "mcp__tapps-mcp__*",
        "Bash(uv run ruff *)",
        "Bash(uv run mypy *)"
      ]
    }
  }
  ```
- Respect `settings.local.json` precedence — only write to `.claude/settings.json` (project-shared)
- Write ~5 tests: permission rule generation, merge with existing, engagement-level variants

**Definition of Done:** `tapps_init` generates permission rules. Existing settings preserved. TappsMCP tools auto-approved.

---

### 33.5 — Upgrade Path & Tests

**Points:** 3

Ensure `tapps_upgrade` regenerates all corrected artifacts and verify end-to-end correctness.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py`
- `tests/unit/test_platform_skills.py`
- `tests/unit/test_platform_subagents.py`

**Tasks:**
- Update `tapps_upgrade` to regenerate skills with corrected frontmatter (replace existing)
- Update `tapps_upgrade` to regenerate subagents with new fields
- Update `tapps_upgrade` to generate `.claude/rules/python-quality.md` if missing
- Update `tapps_upgrade` to generate permission rules if missing
- Add `tapps_upgrade --dry-run` reporting for all new artifacts
- Integration tests: run `tapps_init` → verify artifacts → run `tapps_upgrade` → verify corrected
- Write ~8 tests: upgrade path for each artifact type, dry-run output, idempotency

**Definition of Done:** `tapps_upgrade` regenerates all corrected artifacts. Dry-run reports accurately. Tests pass.

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Skill generation (all 7) | < 50ms | Template string formatting |
| Subagent generation (all 4) | < 50ms | Template string formatting |
| Rule file generation | < 10ms | Single file write |
| Settings.json merge | < 20ms | JSON read + merge + write |
| Full `tapps_init` with new artifacts | < 2s | Including all existing artifacts |

## Key Design Decisions

1. **`allowed-tools` not `tools`** — The 2026 Claude Code skill frontmatter spec uses `allowed-tools`. The `tools` alias may work in some versions but is not guaranteed. Using the canonical name ensures forward compatibility.
2. **`mcpServers` is non-negotiable** — Without `mcpServers: { tapps-mcp: {} }` in subagent frontmatter, spawned subagents cannot call TappsMCP tools. This is the highest-priority fix in this epic.
3. **Model routing saves cost** — A `tapps-researcher` subagent running Haiku instead of inheriting Opus costs ~5-10x less per query. For projects that spawn many research agents, this is significant.
4. **Path-scoped rules reduce noise** — Quality reminders only activate when Python files are read, not during documentation editing, git operations, or conversation.
5. **Permission rules reduce friction** — Users who install TappsMCP shouldn't need to approve every tool call manually. Auto-approving `mcp__tapps-mcp__*` is safe because TappsMCP tools are read-only or file-scoped.

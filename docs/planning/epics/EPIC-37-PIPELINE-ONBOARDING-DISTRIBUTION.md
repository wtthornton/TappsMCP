# Epic 37: Pipeline Onboarding & Distribution

**Status:** Complete
**Priority:** P1 — High (plugin packaging enables one-click installation; interactive onboarding improves first-run experience)
**Estimated LOE:** ~2.5-3 weeks (1 developer)
**Dependencies:** Epic 33 (Platform Artifact Correctness), Epic 36 (Hook Expansion), Epic 6 (Distribution), Epic 8 (Pipeline Orchestration)
**Blocks:** None

---

## Goal

Transform TappsMCP's distribution and onboarding experience with three major improvements: (1) an interactive first-run wizard for `tapps_init` that uses MCP elicitation to guide new users through configuration choices, (2) a plugin packaging system that bundles TappsMCP's MCP server + skills + agents + hooks + rules into a Claude Code plugin for one-click marketplace installation, and (3) an upgrade rollback mechanism that creates backups before overwriting configuration files. These are informed by AI OS's zero-config business-setup wizard (its "killer feature") and AI OS Recommendation 8 (repackage as a Claude Code plugin).

## Motivation

**Current friction points:**
1. `tapps_init` generates everything from defaults — new users get no guidance on which quality preset, engagement level, or optional features to choose. AI OS's `business-setup` skill demonstrates that a conversational wizard transforms a generic template into a personalized workspace.
2. TappsMCP is installed per-project via `tapps_init` (writes files to `.claude/`). A Claude Code plugin would install once and apply to all projects, with marketplace distribution for discoverability. The 2026 plugin marketplace has 9,000+ plugins.
3. `tapps_upgrade` overwrites configuration files with no rollback. If an upgrade breaks something, the user must manually reconstruct their config.

## 2026 Best Practices Applied (verified against Claude Code docs 2026-02-28)

- **Claude Code Plugin System** — `.claude-plugin/plugin.json` manifest, namespaced skills (`tapps-mcp:skill-name`), bundled `.mcp.json` for MCP server config, `hooks/hooks.json` for hook definitions. Marketplace distribution via `claude.ai/settings/plugins/submit` or `platform.claude.com/plugins/submit`. Source: [code.claude.com/docs/en/plugins.md](https://code.claude.com/docs/en/plugins.md)
- **MCP Elicitation** — MCP sampling/elicitation enables interactive prompts during tool execution. TappsMCP already has `common/elicitation.py` infrastructure (provides `elicit_preset()` and `elicit_init_confirmation()`). Elicitation support depends on MCP client capabilities — graceful fallback to defaults when unsupported.
- **Plugin `.mcp.json`** — Plugins use **relative paths within the plugin directory structure** for referencing MCP servers. Note: `${CLAUDE_PLUGIN_ROOT}` is NOT documented in 2026 Claude Code docs. Use relative paths or investigate the actual plugin path resolution mechanism at implementation time.
- **Plugin namespacing** — Skills are namespaced as `plugin-name:skill-name` to prevent conflicts. E.g., `/tapps-mcp:score`.
- **Plugin components** — A plugin can include: skills (SKILL.md), agents (.md with frontmatter), hooks (hooks.json), MCP servers (.mcp.json), LSP servers (.lsp.json), default settings (settings.json with `agent` key).
- **Rollback safety** — Destructive operations should be reversible. Backup before overwrite is standard practice.

## Acceptance Criteria

- [ ] `tapps_init` presents interactive wizard when called with no explicit parameters and no existing config
- [ ] Wizard asks: quality preset, engagement level, agent team hooks, advanced skills, prompt hooks
- [ ] Wizard skipped when any parameter is explicitly provided (programmatic use preserved)
- [ ] `tapps-mcp build-plugin` CLI command generates a complete Claude Code plugin directory
- [ ] Plugin contains: `plugin.json`, skills/, agents/, hooks/hooks.json, .mcp.json, rules/
- [ ] Plugin `.mcp.json` references TappsMCP server with `${CLAUDE_PLUGIN_ROOT}`
- [ ] Plugin skills are namespaced (e.g., `tapps-mcp:score`)
- [ ] `tapps_upgrade` creates backup in `.tapps-mcp/backups/{timestamp}/` before overwriting
- [ ] `tapps-mcp rollback` CLI command restores from latest backup
- [ ] Rollback manifest tracks which files were changed
- [ ] All new code has unit tests
- [ ] Existing `tapps_init` behavior unchanged when parameters are provided (backward compatible)

---

## Stories

### 37.1 — Interactive First-Run Wizard

**Points:** 5

Add an interactive wizard to `tapps_init` that guides new users through configuration choices using MCP elicitation.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/common/elicitation.py` (existing — provides `elicit_preset()` and `elicit_init_confirmation()`, extend with wizard flow)

**Tasks:**
- Add wizard detection logic to `tapps_init`:
  - Wizard triggers when ALL of these conditions are true:
    1. No existing `.claude/settings.json` or `.tapps-mcp.yaml` in project
    2. No explicit parameters provided (all defaults)
    3. MCP context supports elicitation (check `ctx` capabilities)
  - If any condition is false, skip wizard and use current behavior
- Wizard flow (5 questions via MCP elicitation):
  1. **Quality preset**: "Which quality standard should TappsMCP enforce?"
     - Options: "Standard (70+ score, recommended for most projects)", "Strict (80+ score, for production codebases)", "Framework (75+ score, for library/framework development)"
     - Default: Standard
  2. **Engagement level**: "How actively should TappsMCP guide the coding agent?"
     - Options: "High (mandatory enforcement — blocks completion without validation)", "Medium (balanced — reminders and nudges)", "Low (optional guidance — minimal intervention)"
     - Default: Medium
  3. **Agent team hooks**: "Will you use Claude Code Agent Teams for parallel work?"
     - Options: "Yes (generate TeammateIdle and TaskCompleted hooks)", "No (skip team hooks)"
     - Default: No
  4. **Skill tier**: "Which TappsMCP skills should be installed?"
     - Options: "Core only (score, gate, validate, security — 4 skills)", "Full (all 7 skills including research, memory, review pipeline)"
     - Default: Full
  5. **Prompt hooks**: "Enable AI-powered quality judgment? (Uses Haiku, ~$0.001/check)"
     - Options: "Yes (intelligent file change detection via Haiku)", "No (pattern-based detection, free)"
     - Default: No
- Store wizard answers in `.tapps-mcp.yaml`
- Pass wizard answers as parameters to existing `tapps_init` logic
- If elicitation is not supported (older MCP clients), fall back to defaults with a message:
  "MCP elicitation not supported. Using defaults. Run tapps_set_engagement_level to customize."
- Write ~8 unit tests: wizard triggers correctly, skips when config exists, skips when params provided, each question maps to correct parameter, elicitation fallback, yaml persistence

**Definition of Done:** First-run wizard guides new users. Skips when not needed. Answers persist in YAML. Backward compatible.

---

### 37.2 — Plugin Package Builder

**Points:** 8

Build a `tapps-mcp build-plugin` CLI command that generates a complete Claude Code plugin directory structure.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/distribution/plugin_builder.py` (new)
- `packages/tapps-mcp/src/tapps_mcp/cli.py` (modify — add build-plugin command)

**Tasks:**
- Create `distribution/plugin_builder.py` with:
  - `PluginBuilder` class:
    - `__init__(output_dir: Path, engagement_level: str = "medium")`
    - `build() -> Path` — generates complete plugin directory, returns path
    - `_generate_manifest()` — creates `.claude-plugin/plugin.json`:
      ```json
      {
        "name": "tapps-mcp",
        "description": "Deterministic code quality tools for Python — scoring, security, gates, expert consultation, and more.",
        "version": "<from pyproject.toml>",
        "author": {
          "name": "TappsMCP"
        },
        "homepage": "https://github.com/...",
        "license": "MIT"
      }
      ```
    - `_generate_skills()` — copies skill templates to `skills/` directory, with namespaced names
    - `_generate_agents()` — copies subagent templates to `agents/` directory
    - `_generate_hooks()` — creates `hooks/hooks.json` from hook templates
    - `_generate_mcp_config()` — creates `.mcp.json`:
      ```json
      {
        "mcpServers": {
          "tapps-mcp": {
            "command": "tapps-mcp",
            "args": ["serve"],
            "env": {
              "TAPPS_MCP_PROJECT_ROOT": "."
            }
          }
        }
      }
      ```
      **Note:** `${CLAUDE_PLUGIN_ROOT}` is NOT documented in 2026 Claude Code plugin docs. Use the system-installed `tapps-mcp` command (expected on PATH via pip/uv install) or a relative `./bin/tapps-mcp` path. Investigate actual plugin path resolution at implementation time — the plugin system may provide a different mechanism for relative binary references.
    - `_generate_rules()` — creates `rules/` directory with path-scoped quality rules
    - `_generate_settings()` — creates `settings.json` with permission rules
  - Version read from `tapps_mcp/__init__.py` or `pyproject.toml`
- Plugin directory structure (verified against 2026 Claude Code plugin spec):
  ```
  tapps-mcp-plugin/
  +-- .claude-plugin/
  |   +-- plugin.json          # Required manifest
  +-- skills/
  |   +-- tapps-score/SKILL.md
  |   +-- tapps-gate/SKILL.md
  |   +-- tapps-validate/SKILL.md
  |   +-- tapps-research/SKILL.md
  |   +-- tapps-memory/SKILL.md
  |   +-- tapps-security/SKILL.md
  |   +-- tapps-review-pipeline/SKILL.md
  +-- agents/
  |   +-- tapps-researcher.md
  |   +-- tapps-reviewer.md
  |   +-- tapps-validator.md
  |   +-- tapps-review-fixer.md
  +-- hooks/
  |   +-- hooks.json
  +-- rules/
  |   +-- python-quality.md
  +-- .mcp.json                # MCP server config
  +-- settings.json            # Default settings with permissions
  ```
- Add `tapps-mcp build-plugin` CLI command via Click:
  - `--output-dir` — output directory (default: `./tapps-mcp-plugin/`)
  - `--engagement-level` — high/medium/low (default: medium)
  - `--include-binary` — copy TappsMCP binary into plugin (for offline use)
- Skills in plugin use namespaced names: `tapps-mcp:score`, `tapps-mcp:gate`, etc.
- Write ~12 unit tests: manifest generation, skill copying, hook JSON creation, MCP config, rule generation, CLI argument parsing, version extraction, directory structure validation

**Definition of Done:** `tapps-mcp build-plugin` generates a complete, valid Claude Code plugin. All artifacts conform to 2026 plugin spec.

---

### 37.3 — Upgrade Rollback Mechanism

**Points:** 5

Add backup and rollback capability to `tapps_upgrade` so configuration changes can be reversed.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/distribution/rollback.py` (new)
- `packages/tapps-mcp/src/tapps_mcp/cli.py` (modify — add rollback command)

**Tasks:**
- Create `distribution/rollback.py` with:
  - `BackupManager` class:
    - `create_backup(project_root: Path, files_to_backup: list[Path]) -> Path`:
      - Creates backup directory at `.tapps-mcp/backups/{YYYY-MM-DD-HHMMSS}/`
      - Copies each file (preserving relative path structure)
      - Writes `manifest.json` with: `timestamp`, `version` (TappsMCP version), `files` (list of relative paths), `reason` (e.g., "pre-upgrade backup")
      - Returns backup directory path
    - `list_backups(project_root: Path) -> list[BackupInfo]`:
      - Scans `.tapps-mcp/backups/` for manifest files
      - Returns sorted by timestamp (newest first)
    - `restore_backup(project_root: Path, backup_dir: Path) -> list[str]`:
      - Reads manifest.json
      - Copies each file from backup back to original location
      - Returns list of restored file paths
    - `cleanup_old_backups(project_root: Path, keep: int = 5)`:
      - Keep only the N most recent backups, delete older ones
  - `BackupInfo` Pydantic model: `timestamp`, `version`, `file_count`, `path`
- Modify `tapps_upgrade`:
  - Before overwriting any files, call `BackupManager.create_backup()` with the list of files that will change
  - After successful upgrade, log: "Backup created at .tapps-mcp/backups/{timestamp}/. Use 'tapps-mcp rollback' to restore."
  - Run `cleanup_old_backups(keep=5)` after successful upgrade
- Add `tapps-mcp rollback` CLI command:
  - No args: restore from latest backup
  - `--backup-id {timestamp}`: restore from specific backup
  - `--list`: list available backups
  - `--dry-run`: show what would be restored without doing it
- Write ~10 unit tests: backup creation, manifest writing, file restore, backup listing, old backup cleanup, CLI commands, dry-run mode

**Definition of Done:** Upgrades create backups. Rollback restores from backup. Old backups auto-cleaned. CLI works.

---

### 37.4 — Knowledge Cache Eviction

**Points:** 3

> **Thematic Note:** This story addresses cache management, not onboarding/distribution. It was placed here as a quality-of-life improvement that benefits the distribution story (cache size matters for plugin users). Consider moving to a dedicated "Cache & Performance" epic if the backlog is rebalanced.

Add size-based LRU eviction to the knowledge cache to prevent unbounded disk growth.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/knowledge/cache.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/config/settings.py` (modify — add `cache_max_mb` setting)

**Tasks:**
- Add `cache_max_mb: int = 100` to `TappsMCPSettings` (configurable max cache size in MB)
- Modify `KBCache`:
  - Add `_metadata_path` property pointing to `.tapps-mcp-cache/_metadata.json`
  - Track access timestamps per cache entry in metadata file
  - Add `_check_size()` method:
    - Calculate total cache directory size
    - If > `cache_max_mb`, evict LRU entries until under limit
    - Log evicted entries at DEBUG level
  - Call `_check_size()` after each `put()` operation
  - Update access timestamp on each `get()` operation
- Add size check to `tapps_session_start` (run cache eviction at session start)
- Write ~8 unit tests: eviction triggers at limit, LRU order correct, metadata tracking, config override, session start integration

**Definition of Done:** Cache has configurable size limit. LRU eviction prevents unbounded growth. Access timestamps tracked.

---

### 37.5 — Gate Failure Weighting

**Points:** 3

> **Thematic Note:** This story addresses gate evaluator improvements, not onboarding/distribution. It was placed here to improve the user experience for new adopters who see confusing gate failures. Consider moving to a dedicated "Quality Gate Enhancement" epic if the backlog is rebalanced.

Weight quality gate failure messages by category importance so security failures are highlighted over cosmetic issues.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/gates/evaluator.py` (modify)

**Current State (verified 2026-02-28):** The gate evaluator treats all categories equally — each has a configurable threshold, failures are collected, but they are not weighted or prioritized. Security is checked as a separate category but has no special "floor" enforcement.

**Tasks:**
- When a quality gate fails, order failing categories by scoring weight (from `ScoringWeights`):
  - Security (0.27) > Maintainability (0.24) > Complexity (0.18) > Test Coverage (0.13) > Performance (0.08) > Structure (0.05) > DevEx (0.05)
- Add `critical_categories` concept:
  - If `security` category score is below 50 (absolute floor), gate fails regardless of overall score
  - Include "CRITICAL: Security score below minimum threshold" in failure message
- Update gate failure response to include:
  - Categories sorted by scoring weight (highest first)
  - Each failing category with its weight, score, and threshold
  - "Fix these in order of priority (highest-weight categories first)"
- Write ~6 unit tests: ordering by weight, critical security floor, gate failure message format, overall pass but security fail

**Definition of Done:** Gate failures ordered by importance. Security has absolute floor. Failure messages guide priority fixes.

---

### 37.6 — Tests & Documentation

**Points:** 2

Integration tests across all new features and documentation updates.

**Source Files:**
- Various test files
- `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template*.md` (if not already updated)

**Tasks:**
- Integration test: wizard → init → verify artifacts → upgrade → verify backup → rollback → verify restore
- Integration test: build-plugin → verify directory structure → verify manifest → verify MCP config
- Edge case tests: wizard with partial config, upgrade with no changes, rollback with no backups
- Update AGENTS.md tool reference if new tools/actions were added
- Update README.md with plugin build instructions
- Write ~5 integration tests

**Definition of Done:** All integration paths tested. Documentation updated. End-to-end flows verified.

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Wizard question display | < 100ms | MCP elicitation round-trip |
| Plugin build (full) | < 5s | File generation + copying |
| Backup creation | < 500ms | File copying (typically < 20 files) |
| Rollback restoration | < 500ms | File copying from backup |
| Cache eviction check | < 200ms | Directory scan + size calculation |

## File Layout

```
packages/tapps-mcp/src/tapps_mcp/
    distribution/
        plugin_builder.py    # Plugin directory generation (new)
        rollback.py          # Backup and rollback manager (new)
```

Plugin output structure:
```
tapps-mcp-plugin/
    .claude-plugin/plugin.json
    skills/tapps-score/SKILL.md
    skills/tapps-gate/SKILL.md
    skills/tapps-validate/SKILL.md
    skills/tapps-research/SKILL.md
    skills/tapps-memory/SKILL.md
    skills/tapps-security/SKILL.md
    skills/tapps-review-pipeline/SKILL.md
    agents/tapps-researcher.md
    agents/tapps-reviewer.md
    agents/tapps-validator.md
    agents/tapps-review-fixer.md
    hooks/hooks.json
    rules/python-quality.md
    .mcp.json
    settings.json
```

## Key Dependencies

- Epic 33 (corrected skill/subagent/rule templates — plugin builder uses these)
- Epic 36 (expanded hook templates — plugin builder includes these)
- Epic 6 (distribution infrastructure — binary packaging)
- Epic 8 (pipeline infrastructure — init/upgrade)
- `common/elicitation.py` (existing — MCP sampling for wizard)

## Key Design Decisions

1. **Wizard is conditional** — Only triggers on true first-run with no config and no explicit params. Programmatic use is completely unchanged.
2. **Plugin complements, doesn't replace, tapps_init** — `tapps_init` remains for per-project customization (different presets per project). Plugins provide organization-wide defaults.
3. **Plugin MCP uses system-installed command** — The 2026 plugin docs do NOT document `${CLAUDE_PLUGIN_ROOT}`. Instead, the `.mcp.json` references `tapps-mcp` as a system command (installed via pip/uv). For self-contained plugins with bundled binaries, investigate the actual plugin path resolution mechanism at implementation time. Relative paths within the plugin directory may work.
4. **5 backup retention** — Keep the 5 most recent backups. This covers ~5 upgrade cycles, which is sufficient for rollback needs without consuming excessive disk space.
5. **Cache eviction at session start** — Running eviction during `tapps_session_start` is preferable to running during `put()` because it's a one-time cost per session, not per cache operation.
6. **Gate security floor at 50** — A file with < 50% security score has fundamental issues that shouldn't pass regardless of other category scores. This is conservative — most real security issues produce scores well above 50.

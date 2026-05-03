# Upgrading TappsMCP — Guide for Consuming Projects

When you **install or upgrade** TappsMCP in a project that uses it for quality checks, doc lookup, and experts, you may want to refresh pipeline templates and rules so the AI gets the latest workflow guidance.

---

## 0. Behavioral changes since v3.7.x

Upgrading to v3.8.x **enables a new opt-in PreToolUse hook by default at `medium` / `high` engagement**:

- **Linear cache-first read gate (TAP-1224)** — `tapps_upgrade` deploys two new scripts (`tapps-pre-linear-list.sh`, `tapps-post-linear-snapshot-get.sh`) and switches on `linear_enforce_cache_gate: warn` for `medium` / `high` engagement consumers. **Warn mode is non-blocking** — calls are allowed through but each violation lands in `.tapps-mcp/.cache-gate-violations.jsonl` for telemetry. Block mode (`linear_enforce_cache_gate: block` in `.tapps-mcp.yaml`) is opt-in once you've reviewed the warn-mode log.

To **stay on `off`** through the upgrade, set the flag in `.tapps-mcp.yaml` **before** running `tapps_upgrade`:

```yaml
linear_enforce_cache_gate: off
```

Emergency bypass at call time: `TAPPS_LINEAR_SKIP_CACHE_GATE=1 <command>` (logged to `.tapps-mcp/.bypass-log.jsonl`). Same envelope as the existing `TAPPS_LINEAR_SKIP_VALIDATE=1` for the TAP-981 write gate.

The **`linear-standards.md` rule** also gains a new `### Reads (TAP-1224)` enforcement subsection alongside the existing `### Writes (TAP-981)` block. The deployed copy is regenerated on `tapps_upgrade`. If you've hand-edited it, add `linear_standards_rule` to `upgrade_skip_files` in `.tapps-mcp.yaml` to preserve your edits.

---

## 1. Upgrade the package

```bash
pip install -U tapps-mcp
# or: uv tool install -U tapps-mcp
```

---

## 2. Run the upgrade command (recommended)

The easiest way to refresh all generated files:

```bash
tapps-mcp upgrade                           # auto-detect host, update everything
tapps-mcp upgrade --host claude-code        # target a specific host
tapps-mcp upgrade --dry-run                 # preview what would change (text summary)
tapps-mcp upgrade --dry-run --json          # preview as JSON (pipe to jq for scripting)
```

This updates AGENTS.md (smart merge), platform rules, the four `tapps-*` subagents, the `tapps-*` + `linear-issue` skills, `tapps-*` hook scripts, and `.claude/settings.json` permissions. **Files outside that managed set are preserved** — consumer-authored agents, skills, or hooks with other names are never touched. `settings.json` hook entries are merged by matcher, so hand-wired hooks stay.

### Reading the dry-run output

`tapps-mcp upgrade --dry-run` (or `tapps_upgrade(dry_run=true)` from MCP) returns a top-level `dry_run_summary` you can read first to decide whether to proceed:

```json
{
  "dry_run_summary": {
    "verdict": "safe-to-run",
    "message": "Upgrade is additive: 17 tapps-managed files would be written, 6 custom files preserved.",
    "managed_file_count": 17,
    "preserved_file_count": 6,
    "preserved_files": [
      "claude-code:agents/ralph.md",
      "claude-code:agents/ralph-architect.md",
      "claude-code:skills/ralph-quickfix"
    ],
    "skipped_components": [],
    "review_recommended_for": []
  }
}
```

- `verdict: "safe-to-run"` → only tapps-managed files change; consumer-custom files appear in `preserved_files`. Run live with confidence.
- `verdict: "review-recommended"` → the upgrade merges into a user-editable file (`CLAUDE.md` H1-section replace, or `settings.json` hook-matcher merge). Inspect diffs before running live. The specific components are listed in `review_recommended_for`.

Per-component details live under `components.platforms[].components.{agents,skills,hooks}` as dicts with `managed_files`/`managed_skills` (what would be written) and `preserved_files`/`preserved_skills` (what stays). Use these for a full audit; the top-level summary for a quick decision.

---

## 3. Or use the MCP tools from within a session

**Quick upgrade (new in v0.3.0):** Use the **`tapps_upgrade`** MCP tool to refresh all generated files without leaving your AI session:

```
tapps_upgrade(dry_run=true)   # preview changes
tapps_upgrade()               # apply updates
tapps_upgrade(force=true)     # overwrite even if up-to-date
```

**Fine-grained control:** Use the **`tapps_init`** MCP tool (via your AI assistant) with:

| Option | Purpose |
|--------|---------|
| `overwrite_agents_md=True` | Replace AGENTS.md with the latest template (new workflow, tool hints) |
| `overwrite_platform_rules=True` | Refresh platform rule files (CLAUDE.md, .cursor/rules) |
| `llm_engagement_level="high"` / `"medium"` / `"low"` | Use a specific engagement level for template language and checklist |
| `platform="cursor"` or `"claude"` | Which platform rules to generate |

To change engagement level only: use **`tapps_set_engagement_level(level)`** then `tapps_init(overwrite_agents_md=True)` to regenerate AGENTS.md and rules with the new level.

---

## 4. Refresh MCP host config (optional)

If the MCP server entry or startup command changed, run:

```bash
tapps-mcp init --force --host cursor        # for Cursor
tapps-mcp init --force --host claude-code   # for Claude Code
tapps-mcp init --force --host vscode        # for VS Code
```

---

## 5. Verify the upgrade

```bash
tapps-mcp doctor                  # diagnose configuration and connectivity
tapps-mcp init --check            # verify MCP config is correct
```

Doctor includes **Memory pipeline (effective config)** — a non-blocking summary of resolved `memory.*` and `memory_hooks.*` flags (expert auto-save, recurring quick_check memory, architectural supersede, impact enrichment, auto-recall/capture). Compare with [docs/MEMORY_REFERENCE.md](MEMORY_REFERENCE.md) if behavior feels noisy after an upgrade.

---

## 6. Re-run init for caches and TECH_STACK

A normal `tapps_init` run (without overwrite flags) will:

- Refresh TECH_STACK.md with current project profile
- Warm Context7 cache for detected libraries
- Warm expert RAG indices for relevant domains

---

## Summary

| What | How |
|------|-----|
| Upgrade the package | `pip install -U tapps-mcp` |
| Refresh everything (recommended) | `tapps-mcp upgrade` (CLI) or `tapps_upgrade()` (MCP tool) |
| Get latest AGENTS.md and workflow | `tapps_init(overwrite_agents_md=True)` |
| Get latest platform rules | `tapps_init(overwrite_platform_rules=True, platform="cursor")` or `platform="claude"` |
| Refresh MCP config | `tapps-mcp init --force` |
| Refresh caches and TECH_STACK | `tapps_init()` (default) |
| Verify upgrade | `tapps-mcp doctor` (includes memory pipeline summary) |
| Rollback if upgrade causes issues | `tapps-mcp rollback` (restores from automatic pre-upgrade backup) |
| List available backups | `tapps-mcp rollback --list` |

Backups are stored in `.tapps-mcp/backups/` with the 5 most recent kept automatically. Each backup includes a `manifest.json` listing all files that were overwritten.

See [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) for the full init and upgrade behavior.

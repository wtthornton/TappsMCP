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

## ADR-0016: NLT server rename (Build / Memory / Setup)

After upgrading to a release that includes [ADR-0016](adr/0016-needs-based-nlt-mcp-taxonomy.md):

1. Run `tapps-mcp upgrade --host auto --force` to refresh `.cursor/mcp.json` / `.mcp.json`.
2. Default **developer** bundle is **`nlt-build` + `nlt-memory` + `nlt-linear-issues`** (~18 eager tools). Use `--bundle minimal` on init/upgrade-fleet for build-only (~9 eager). Enable `nlt-setup` briefly for bootstrap/doctor.
3. Re-run `tapps-mcp init --host auto --force` or `tapps-mcp upgrade-fleet --bundle developer` so `.cursor/mcp.json` / `.mcp.json` picks up all three active servers (TAP-3925).
4. Update skill `allowed-tools` prefixes: `mcp__nlt-build__*`, `mcp__nlt-memory__*`, `mcp__nlt-setup__*`. Legacy `nlt-code-quality` / `nlt-platform-admin` profile aliases work for one release.
5. Session handoff / `tapps_session_notes` moved to **Memory** server — enable `nlt-memory` or use `tapps-mcp memory` CLI.

---

## ADR-0014: Brain-central doc RAG cutover

When enabling library docs via tapps-brain ([ADR-0014](adr/0014-brain-central-doc-rag-big-bang.md),
[ADR-0015](adr/0015-require-tapps-brain-docs-lookup-at-3240.md)):

1. Deploy tapps-brain **3.24.0+** with `docs_lookup` / `docs_warm` and `CONTEXT7_API_KEY` on the brain host.
2. Set `docs_via_brain: true` in `.tapps-mcp.yaml` (or `TAPPS_MCP_DOCS_VIA_BRAIN=1`).
3. Import legacy per-repo caches, then upgrade consumers:

   ```bash
   tapps-brain docs import-dir .tapps-mcp-cache          # per repo
   tapps-mcp upgrade-fleet --import-legacy-doc-cache --strip-context7-env --force
   tapps-mcp upgrade --force --host auto
   ```

4. Remove `TAPPS_MCP_CONTEXT7_API_KEY` from MCP env blocks and shell profiles.
5. Verify: `tapps-mcp doctor` (legacy doc cache + brain docs probe) and `tapps-mcp lookup-docs --library pytest --topic fixtures`.

Full **~30 minute maintenance window** steps:
[operations/brain-doc-rag-cutover-runbook.md](operations/brain-doc-rag-cutover-runbook.md).

---

## 1. Upgrade the package

TappsMCP is not published to PyPI — pull the latest checkout and reinstall:

```bash
cd <path-to-TappsMCP-checkout>
git pull
uv tool install --reinstall -e packages/tapps-mcp
uv tool install --reinstall -e packages/docs-mcp
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
      "claude-code:agents/custom-agent.md",
      "claude-code:agents/custom-architect.md",
      "claude-code:skills/custom-quickfix"
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

**Quick upgrade:** Use the **`tapps_upgrade`** MCP tool to refresh all generated files without leaving your AI session:

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
| Upgrade the package | `git pull && uv tool install --reinstall -e packages/tapps-mcp` (from the checkout) |
| Refresh everything (recommended) | `tapps-mcp upgrade` (CLI) or `tapps_upgrade()` (MCP tool) |
| Get latest AGENTS.md and workflow | `tapps_init(overwrite_agents_md=True)` |
| Get latest platform rules | `tapps_init(overwrite_platform_rules=True, platform="cursor")` or `platform="claude"` |
| Refresh MCP config | `tapps-mcp init --force` |
| Upgrade many repos at once | `tapps-mcp upgrade-fleet` or `./scripts/fleet-upgrade.sh` (see below) |

---

## 7. Fleet upgrade (multiple consumer repos)

When you maintain several TAPPS-bootstrapped projects (AgentForge, NLTlabsPE, ReportLab, etc.), use **fleet upgrade** instead of repeating the steps per repo.

### One-time setup

```bash
export TAPPS_FLEET_ROOTS=\
$HOME/code/AgentForge,\
$HOME/code/NLTlabsPE,\
$HOME/code/ReportLab,\
$HOME/code/tapps-mcp
```

Omit `TAPPS_FLEET_ROOTS` to scan `~/code` for any directory containing `.tapps-mcp.yaml`.

### Upgrade everything

From the tapps-mcp checkout:

```bash
# Preview
./scripts/fleet-upgrade.sh --dry-run

# Apply: reinstall global CLIs + upgrade scaffolding + migrate MCP to NLT
TAPPS_FLEET_BUNDLE=full ./scripts/fleet-upgrade.sh
```

Or directly:

```bash
tapps-mcp upgrade-fleet \
  --reinstall-clis \
  --tapps-checkout ~/code/tapps-mcp \
  --roots "$TAPPS_FLEET_ROOTS" \
  --bundle full \
  --uv-mode off
```

### What it does per project

1. **`tapps-mcp upgrade --force`** — refreshes AGENTS.md, hooks, agents, skills, rules; migrates legacy `tapps-mcp` + `docs-mcp` entries to NLT `nlt-*` servers when present.
2. **`tapps-mcp init --force --no-rules`** — writes the chosen NLT bundle into `.cursor/mcp.json` / `.mcp.json` / `.vscode/mcp.json` and Cursor wrapper scripts.
3. **`tapps-mcp doctor --quick`** — sanity check (non-blocking in the report).

### Bundle choices

| Bundle | Servers enabled |
|--------|-----------------|
| `developer` (default) | code-quality + platform-admin |
| `planning` | + linear-issues |
| `docs` | + project-docs |
| `release` | + release-ship |
| `full` | all five (power-user / maintainer repos) |

After fleet upgrade, **reload MCP** in each IDE session.

**Note:** `NewCompanyIdeas` lives at `~/NewCompanyIdeas` (not under `~/code`) — include it in `--roots` when upgrading.

**Operator secrets:** create `~/.tapps-operator.env` once per machine (see [OPERATOR-SECRETS.md](operations/OPERATOR-SECRETS.md)). Fleet `init` regenerates serve wrappers that source it; optional `.envrc` snippet in each consumer repo helps CLI `doctor` match GUI MCP.

---

| Refresh caches and TECH_STACK | `tapps_init()` (default) |
| Verify upgrade | `tapps-mcp doctor` (includes memory pipeline summary) |
| Rollback if upgrade causes issues | `tapps-mcp rollback` (restores from automatic pre-upgrade backup) |
| List available backups | `tapps-mcp rollback --list` |

Backups are stored in `.tapps-mcp/backups/` with the 5 most recent kept automatically. Each backup includes a `manifest.json` listing all files that were overwritten.

See [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) for the full init and upgrade behavior.

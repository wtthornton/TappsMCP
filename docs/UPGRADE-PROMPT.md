# Generic upgrade prompt — pull latest tapps-mcp into a consuming project

Open Claude Code (or Cursor) **inside the consuming project's repo** and paste the prompt below. It works whether or not the project already has the `tapps-upgrade` skill installed — the prompt is self-contained.

## When to use this

- A new tapps-mcp / docs-mcp version has shipped and you want this project to pick it up.
- `tapps_session_start` reports `diagnostics.install_drift.drift_detected: true`.
- `tapps doctor` warns that the global binary lags the source.

## What it does

1. Reinstalls the global `tapps-mcp` and `docsmcp` binaries from a source you specify (local checkout or git tag).
2. Pauses for an MCP-server restart (the running MCP servers still hold old code).
3. Verifies the new version is live via `tapps_session_start`.
4. Dry-runs `tapps-mcp upgrade` so you can review the scaffolding diff before it lands.
5. Applies the scaffolding refresh (timestamped backup under `.tapps-mcp/backups/`).
6. Verifies with `tapps-mcp doctor` + `tapps_checklist(task_type="upgrade")`.

## Source options

Pick one and substitute in the prompt below.

| Source | When | What to write |
|---|---|---|
| Local checkout | You have `tapps-mcp` cloned at `~/code/tapps-mcp` (or similar) and want bleeding-edge `master` | `--from-checkout ~/code/tapps-mcp` |
| Git tag | You want a specific released version | `--from-tag v3.12.0` (replace with current latest from <https://github.com/wtthornton/TappsMCP/releases>) |

## The prompt (copy from here)

```text
Upgrade this project's tapps-mcp + docs-mcp installs and refresh the scaffolding. Source: <FILL IN: --from-checkout /absolute/path OR --from-tag vX.Y.Z>

If a `tapps-upgrade` skill is already available in this project (check `.claude/skills/tapps-upgrade/`), invoke it with the same source argument and skip the rest of this prompt.

Otherwise run the steps yourself. Treat the standing authorization as: yes, reinstall both binaries; yes, refresh scaffolding; do NOT pause to re-confirm individual steps.

1. **Reinstall global CLIs.** Run both commands and verify both binaries show the same version with `uv tool list`.

   For `--from-checkout <path>`:
   - `uv tool install --reinstall --from <path>/packages/tapps-mcp tapps-mcp`
   - `uv tool install --reinstall --from <path>/packages/docs-mcp docs-mcp`

   For `--from-tag vX.Y.Z`:
   - `uv tool install --reinstall "git+https://github.com/wtthornton/tapps-mcp.git@vX.Y.Z#subdirectory=packages/tapps-mcp" tapps-mcp`
   - `uv tool install --reinstall "git+https://github.com/wtthornton/tapps-mcp.git@vX.Y.Z#subdirectory=packages/docs-mcp" docs-mcp`

2. **Restart MCP servers.** The running tapps-mcp / docs-mcp processes still hold the old code. Tell me to exit-and-reopen Claude Code (or run `/mcp` reconnect), then re-invoke this prompt. STOP here on the first invocation.

3. **Verify new version is live.** Call `mcp__tapps-mcp__tapps_session_start(force=true)`. Confirm `server.version` matches the target and `diagnostics.install_drift.drift_detected == false`. If drift persists, the server wasn't restarted — back to step 2.

4. **Dry-run the scaffolding refresh.** Run `tapps-mcp upgrade --dry-run`. Read the `dry_run_summary` block. Surface anything in `customized_canonical_sections` (those will be overwritten) and pause for me to confirm if any exist. If `verdict: safe-to-run` and no customizations are at risk, proceed without asking.

5. **Apply the upgrade.** Run `tapps-mcp upgrade`. It writes a timestamped backup under `.tapps-mcp/backups/<YYYY-MM-DD-HHMMSS>/`. Capture the backup path in your final report.

6. **Verify.** Run `tapps-mcp doctor` AND `mcp__tapps-mcp__tapps_checklist(task_type="upgrade")`. If either reports FAIL or WARN, surface it. Do not declare success on a failure.

7. **Report.** One paragraph: new versions, scaffolding file count, doctor result, checklist result, backup path. List any user-action follow-ups (e.g., "you customized `linear-standards.md`; review the diff and reapply if needed").

**Do NOT:**
- Publish to PyPI / npm — tapps-mcp is local-install only.
- Touch tapps-brain — separate Docker service with its own release flow.
- Add `tapps-brain` as a top-level `.mcp.json` entry — it's bridge-only via tapps-mcp's BrainBridge.
- Bump versions in the tapps-mcp dev repo itself — that's a separate workflow.

**Rollback (only if step 5 or 6 broke something):** `tapps-mcp rollback` restores from the most recent backup. Do NOT roll back "to be safe" after a clean run.
```

## After the upgrade

- If you have a Linear team, file any issues your project hits with the new version against the [TappsMCP Platform project](https://linear.app/tappscodingagents/project/tappsmcp-platform-1da25c8b5add).
- For breaking-change notices, see [CHANGELOG.md § Unreleased](../CHANGELOG.md) and the entries flagged "**Internal-breaking**" under each version section.
- For the per-version reference docs (behavioral changes, knob defaults, etc.), see [docs/UPGRADE_FOR_CONSUMERS.md](UPGRADE_FOR_CONSUMERS.md).

## Why this exists

`tapps-mcp` ships from a local checkout (no PyPI / npm distribution), so consuming projects need a deliberate refresh after a new release. The `tapps-upgrade` skill at `.claude/skills/tapps-upgrade/SKILL.md` does the same flow when invoked inside Claude Code, but this paste-friendly prompt covers the case where the consuming project hasn't yet picked up the skill (or where you'd rather drive the upgrade from a fresh session without skill context).

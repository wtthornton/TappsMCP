# Troubleshooting

## MCP tools unavailable after host restart

**Problem:** When the MCP host (Claude Code, Cursor, VS Code) restarts or reloads, the MCP server connection is lost. All `tapps_*` tools become unavailable for the rest of the session.

**Root cause:** This is a known limitation of the MCP protocol. The host starts MCP servers as child processes, and reconnection after a host restart is not currently supported within an active session.

### Recovery steps

| Host | Recovery |
|---|---|
| **Claude Code** | Start a new Claude Code session (`claude` in terminal). The MCP server will reconnect automatically. |
| **Cursor** | Reload the window (`Ctrl+Shift+P` > "Developer: Reload Window") or restart Cursor. |
| **VS Code** | Restart the extension host or reload the window. |

### CLI fallback commands

When the MCP server is unavailable, use these CLI equivalents directly in the terminal:

| MCP Tool | CLI Command |
|---|---|
| `tapps_memory` (list) | `tapps-mcp memory list [--tier TIER] [--scope SCOPE]` |
| `tapps_memory` (save) | `tapps-mcp memory save --key KEY --value VALUE [--tier TIER]` |
| `tapps_memory` (get) | `tapps-mcp memory get --key KEY` |
| `tapps_memory` (search) | `tapps-mcp memory search --query QUERY [--limit N]` |
| `tapps_memory` (delete) | `tapps-mcp memory delete --key KEY` |
| `tapps_memory` (import) | `tapps-mcp memory import-file --file PATH` |
| `tapps_memory` (export) | `tapps-mcp memory export-file --file PATH` |
| `tapps_lookup_docs` | `tapps-mcp lookup-docs --library LIB [--topic TOPIC] [--mode code\|info]` |
| `tapps_quick_check` | `tapps-mcp quick-check --file-path PATH [--preset standard\|strict\|framework]` |
| `tapps_validate_changed` | `tapps-mcp validate-changed [--file-paths a.py,b.py] [--quick\|--full]` |
| `tapps_doctor` | `tapps-mcp doctor [--quick]` |

All CLI commands use `TAPPS_MCP_PROJECT_ROOT` (or the current directory) for project context.

### YAML / template config changes (brand.yaml, templates)

**Problem:** `tapps_validate_changed` only scores code files (`.py`, polyglot sources). Edits to `brand.yaml`, template YAML, or other config are invisible to the batch gate.

**Recommended consumer pattern:** Use project checklist policy — not core batch validation:

```yaml
# .tapps-mcp/checklist-policy.yaml
extra_recommended:
  feature:
    - tapps_validate_config
```

When you change YAML brand/template manifests, call `tapps_validate_config(file_path='...', config_type='yaml_manifest')` after enabling `manifest_validation` in `.tapps-mcp.yaml`. Domain-specific quality (PDF layout, hyperlinks) belongs in consumer audit CLIs wired through `validate_changed.judges` (pytest/grep/shell) in `.tapps-mcp.yaml`, not generic code gates alone.

Use checklist `task_type=document` (or `.tapps-mcp/checklist-policy.yaml` extras) so agents run `tapps_validate_changed` with judges plus `tapps_validate_config` for manifest YAML.

### Verifying MCP server health

Run the doctor command to diagnose configuration and connectivity:

```bash
tapps-mcp doctor
```

Use `--quick` to skip tool version checks for faster results:

```bash
tapps-mcp doctor --quick
```

Doctor prints **Memory pipeline (effective config)** — a read-only summary of resolved `memory.*` and `memory_hooks.*` flags (expert auto-save, recurring quick_check memory, architectural supersede, impact enrichment, auto-recall/capture). If behavior feels noisy, set the relevant keys to `false` in `.tapps-mcp.yaml` (see [MEMORY_REFERENCE.md](MEMORY_REFERENCE.md)).

### Claude Code: project-only MCP (no `~/.claude.json`)

**Problem:** `tapps-mcp doctor` mentions Claude user config, or you only use project-scoped `.mcp.json`.

**Expected:** A valid **project** `.mcp.json` with a `tapps-mcp` entry is sufficient. User-level `~/.claude.json` is optional. Doctor reports this as OK when the project registers the server.

**Non-interactive init:** If `tapps-mcp init` skips merging an existing MCP entry (no TTY), pass `--force` or set `TAPPS_MCP_INIT_ASSUME_YES=1` to overwrite without prompts.

## Zombie MCP server processes

**Problem:** After multiple Claude Code sessions, running `ps aux | grep tapps-mcp` shows many old Python processes from previous sessions consuming memory.

**Root cause:** Claude Code spawns a new MCP server process per session but never terminates old ones. Over several sessions, these accumulate and become a resource leak.

**Solution:** The `.claude/hooks/tapps-session-start.sh` hook kills tapps-mcp and docsmcp processes older than 2 hours on session startup. Runs by default after `tapps_init`. The cleanup uses `ps -eo pid,etimes,cmd` and `awk` to find processes matching the `serve` command and terminates them with `kill`.

**Manual cleanup:** If you have accumulated processes, clean them up manually:

```bash
# Find old tapps-mcp processes
ps aux | grep "serve --profile nlt-"

# Kill all NLT MCP children before Reload Window (full-bundle dev repos)
pkill -f 'serve --profile nlt-' 2>/dev/null || true

# Kill a specific PID
kill -9 <pid>

# Kill all tapps-mcp processes (use with caution)
pkill -f "tapps-mcp serve"
pkill -f "docsmcp serve"
pkill -f "tapps-platform serve"
```

**Cursor sessionStart hook (v3.12.32+):** `.cursor/hooks/tapps-mcp-zombie-cleanup.sh` runs before memory auto-recall on every session start. It kills orphaned `serve --profile nlt-*` children left by prior Reload Window cycles so Cursor spawns a clean six-server fleet. `preCompact` only reaps duplicate PIDs per profile (never active singletons).

If hook cleanup is not running, check:
1. `.claude/hooks/tapps-session-start.sh` exists and is executable (`chmod +x`)
2. `.claude/settings.json` has a SessionStart hook entry pointing to it
3. On Windows, ensure PowerShell hooks exist instead (`.ps1` files)

---

## Common issues

### Too many automatic memory writes or hook injections

Shipped defaults turn **on** expert/research auto-save, recurring gate-failure memory, architectural supersede, impact-analysis memory context, and memory hook recall/capture. Disable selectively under `memory:` and `memory_hooks:` in `.tapps-mcp.yaml`, then restart the MCP server.

### Memory store not found

If `tapps-mcp memory list` returns no results, ensure you are running from the correct project directory or set `TAPPS_MCP_PROJECT_ROOT`:

```bash
export TAPPS_MCP_PROJECT_ROOT=/path/to/project
tapps-mcp memory list
```

### Documentation lookup fails

If `tapps-mcp lookup-docs` fails with a connection error, check:

1. The `CONTEXT7_API_KEY` environment variable is set (required for Context7 provider)
2. Network connectivity to the Context7 API
3. The cache at `{project_root}/.tapps-mcp-cache/` is accessible

Without an API key, only cached and llms.txt documentation is available.

## Cursor hooks on Windows

**Problem:** On Windows, when Cursor runs TappsMCP hooks, the `.sh` script files open in the editor instead of executing. The hook does not run; you see the script source (e.g. `tapps-before-mcp.sh`) in a new tab.

**Cause:** TappsMCP generates Bash (`.sh`) hooks when init/upgrade runs on a non-Windows environment (e.g. WSL, CI, or older behavior). On Windows, the default association for `.sh` is often "open in editor," and there is no system Bash unless you use Git Bash or WSL. So Cursor's hook "command" is treated as a file to open, not a script to run.

**Fix:** Run upgrade from **native Windows** (PowerShell or cmd) so TappsMCP detects `sys.platform == "win32"` and generates PowerShell (`.ps1`) hooks and updates `.cursor/hooks.json` to invoke them explicitly (e.g. `powershell -NoProfile -ExecutionPolicy Bypass -File .cursor/hooks/tapps-before-mcp.ps1`).

From the project root:

```powershell
tapps-mcp upgrade --host cursor
```

Or with uv:

```powershell
uv run tapps-mcp upgrade --host cursor
```

After that, `.cursor/hooks/` will contain `tapps-before-mcp.ps1` and `tapps-after-edit.ps1`, and `hooks.json` will reference them with the `powershell -File ...` form. Hooks will then run instead of opening in the editor.

**Doctor:** If you run `tapps-mcp doctor` on Windows and your hooks are still configured as `.sh`, the Hooks check will fail with a message telling you to run `tapps-mcp upgrade --host cursor`.

**Workaround (if you cannot run upgrade):** Disable hooks by removing or clearing the `hooks` entries in `.cursor/hooks.json`, or add Bash to PATH (e.g. Git Bash) and change the command to `bash .cursor/hooks/tapps-before-mcp.sh` (and similarly for the other hook).

## Cursor-only projects

**Upgrade preserves third-party hooks:** Since v3.12.20, `tapps-mcp upgrade` merges Tapps-owned entries into `.cursor/hooks.json` without removing other valid keys (e.g. `preToolUse` / `postToolUse` from continuous-learning-v2). Back up `.cursor/hooks.json` before major upgrades anyway; rollback restores it from `.tapps-mcp/backups/<timestamp>/`.

**Init check:** For Cursor-only repos, `tapps-mcp init --check --host auto` validates only hosts that already have MCP config (e.g. `.cursor/mcp.json`). You do not need Claude Code or VS Code configs on the machine. Prefer `tapps-mcp upgrade --host cursor` for Cursor-only scaffolding refresh.

## NLT MCP servers and tool visibility

**Problem:** Expected tools (`tapps_memory`, `docs_*`, `tapps_init`) missing from the tool list.

**Cause:** ADR-0016 splits tools across NLT servers. Only enabled servers expose their tool subset. Memory tools require `nlt-memory`; doc tools require `nlt-project-docs`; setup tools require `nlt-setup`.

**Fix:**

1. Open `.cursor/mcp.json` and enable the bundle you need (default: `nlt-build`, `nlt-memory`, `nlt-linear-issues`).
2. Reload Cursor (`Developer: Reload Window`).
3. Run `tapps-mcp doctor --quick` — check NLT bundle and tool-budget rows.

See [ADR-0016](adr/0016-needs-based-nlt-mcp-taxonomy.md) and [tutorial: NLT session modes](tutorials/04-nlt-mcp-session-modes.md).

## Six NLT servers errored in Cursor (full bundle)

**Problem:** After `Developer: Reload Window`, several NLT servers show **errored** or **Not connected** in Settings → MCP — commonly `nlt-setup`, `nlt-project-docs`, `nlt-release-ship`, and sometimes `nlt-linear-issues` / `nlt-build`. CLI smoke tests of `.cursor/bin/nlt-*-serve.sh` still succeed.

**Cause:** Cursor spawns all enabled stdio servers in parallel on reload. With **multiple Cursor windows** on one machine, each window owns its own six-server fleet — but older cleanup logic assumed **one global winner per profile** and killed live servers in other windows (duplicate reap, 45s stale reap, blanket `.venv` kill). Reload/compaction in window A could break MCP in windows B–E.

**Fix (copy/paste recovery):**

```bash
# 1. Kill only true orphans (parent dead) — safe across windows
ps -eo pid=,ppid=,cmd= | while read -r pid ppid rest; do
  case "$rest" in *serve*--profile*nlt-*|*tapps-mcp*serve*|*docsmcp*serve*)
    [ "$ppid" = "1" ] || ! kill -0 "$ppid" 2>/dev/null && echo "$pid"
  ;; esac
done | xargs -r kill 2>/dev/null || true

# 2. Cursor: Developer → Reload Window — wait 30–60s for cold starts

# 3. Settings → MCP — toggle OFF → ON any server still red

# 4. Per-server smoke test (one tool each)
#    nlt-build: tapps_session_start
#    nlt-memory: tapps_memory(action="health")
#    nlt-setup: tapps_doctor(quick=true)
#    nlt-linear-issues: tapps_linear_count
#    nlt-project-docs: docs_session_start
#    nlt-release-ship: tapps_release_update(version="…")
```

**Multi-window policy (2–5 Cursor windows):**

| Approach | Servers per box | When |
|----------|-----------------|------|
| **Orphan-only cleanup** (v3.12.36+ hooks) | 6 × N windows | Required — never profile-global `pkill` |
| **`developer` bundle** | 3 × N windows | Daily coding across many windows/repos |
| **`full` bundle** | 6 × N windows | Maintainer / power-user; expect ~30 processes with 5 windows |
| **Host HTTP fleet** (future) | 6 total shared | Best for full bundle + many windows — see below |

**Prevention:** Run `tapps-mcp upgrade --host cursor` so hooks use orphan-only reap (not duplicate/stale per profile). Avoid `pkill -f 'serve --profile nlt-'` during normal use — that kills every window's fleet.

**Host-level shared fleet (recommended for multi-window full bundle):** Run six long-lived HTTP processes once and point every window at Streamable HTTP URLs — **six processes total**, no per-window stdio rotation storms. See [ADR-0024](adr/0024-shared-http-mcp-fleet.md).

```bash
# Once per machine
tapps-mcp fleet start
# optional persistence:
tapps-mcp fleet install-systemd
systemctl --user enable --now tapps-mcp-fleet

# Per consumer repo (or set mcp_transport: http in .tapps-mcp.yaml)
tapps-mcp init --host cursor --mcp-transport http --force --bundle full
# Then Reload Window once
```

Ports: `8760` (nlt-build) … `8765` (nlt-release-ship). Config: `~/.tapps-mcp/fleet.env` (`TAPPS_FLEET_CODE_ROOT`, default `~/code`).

**Legacy note:** stdio wrappers remain the default when `mcp_transport` is unset.

**After editing `packages/tapps-mcp` or `packages/docs-mcp` (dev monorepo):**

```bash
tapps-mcp deploy-local
tapps-mcp init --host cursor --force --allow-package-init --no-uv --bundle full
# Then Reload Window / refresh MCP
```

Use `--skip-gate` only in emergencies (deploy waits for pytest quiescence by default). See [ADR-0023](adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md) (current; supersedes [ADR-0019](adr/0019-blue-green-dev-monorepo-mcp-deploy.md)).

## Cursor agent transcripts and loop metrics {#cursor-vs-claude-transcript-parsing}

**Problem:** Stop-hook telemetry (`loop-metrics.jsonl`) shows gate skips or missing pipeline calls despite agent behavior looking correct.

**Cause:** Cursor wraps MCP calls as `CallMcpTool` with nested JSON; older parsers only matched bare tool names. Cursor transcript paths differ from Claude Code.

**Fix:** Ensure tapps-mcp ≥ 3.12.28 (TAP-4017 unwraps `CallMcpTool`). Run `tapps_doctor(quick=True)` and inspect loop-metrics / completion-gate sections. Retest checklist: [docs/operations/DOGFOOD-RETEST.md](operations/DOGFOOD-RETEST.md). See [TAP-4016](https://linear.app/tappscodingagents/issue/TAP-4016) and child stories in Linear.

**Dev repo note:** `.cursor/bin/nlt-*-serve.sh` always probe `~/.tapps-mcp/current/bin/{tapps-mcp,tapps-platform,docsmcp}` at runtime and fall back to the `~/.local/bin` global shims when no blue/green release is present ([ADR-0023](adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md)). **Do not** point wrappers at `.venv` or `uv run`. Note: Claude Code `.mcp.json` launches the `~/.local/bin` shim directly and does **not** probe `current` — bring that global to the target version and reload to upgrade Claude Code. After source edits:

```bash
tapps-mcp deploy-local
# then reload MCP in Cursor
```

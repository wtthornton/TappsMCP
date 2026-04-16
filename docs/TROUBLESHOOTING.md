# Troubleshooting

## MCP tools unavailable after host restart

**Problem:** When the MCP host (Claude Code, Cursor, VS Code) restarts or reloads, the MCP server connection is lost. All `tapps_*` tools become unavailable for the rest of the session.

**Root cause:** This is a known limitation of the MCP protocol. MCP servers are started as child processes by the host, and reconnection after a host restart is not currently supported within an active session.

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
| `tapps_research` | `tapps-mcp research --question "..." [--domain DOMAIN] [--library LIB]` |
| `tapps_consult_expert` | `tapps-mcp consult-expert --question "..." [--domain DOMAIN]` |
| `tapps_validate_changed` | `tapps-mcp validate-changed [--quick\|--full]` |
| `tapps_doctor` | `tapps-mcp doctor [--quick]` |

All CLI commands use `TAPPS_MCP_PROJECT_ROOT` (or the current directory) for project context.

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

**Solution:** The `.claude/hooks/tapps-session-start.sh` hook automatically kills tapps-mcp and docsmcp processes older than 2 hours on session startup. This is enabled by default when you run `tapps_init`. The cleanup uses `ps -eo pid,etimes,cmd` and `awk` to find processes matching the `serve` command and terminates them with `kill`.

**Manual cleanup:** If you have accumulated processes, clean them up manually:

```bash
# Find old tapps-mcp processes
ps aux | grep "tapps-mcp serve"

# Kill a specific PID
kill -9 <pid>

# Kill all tapps-mcp processes (use with caution)
pkill -f "tapps-mcp serve"
pkill -f "docsmcp serve"
```

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

### Expert consultation returns low confidence

Low confidence results indicate the question may not match the expert's knowledge base well. Try:

1. Use `--domain` to explicitly route to the correct expert domain
2. Rephrase the question with domain-specific terminology
3. Supplement with `tapps-mcp lookup-docs` for library-specific documentation

## Cursor hooks on Windows

**Problem:** On Windows, when Cursor runs TappsMCP hooks, the `.sh` script files open in the editor instead of executing. The hook does not run; you see the script source (e.g. `tapps-before-mcp.sh`) in a new tab.

**Cause:** TappsMCP generates Bash (`.sh`) hooks when init/upgrade runs on a non-Windows environment (e.g. WSL, CI, or older behavior). On Windows, the default association for `.sh` is often “open in editor,” and there is no system Bash unless you use Git Bash or WSL. So Cursor’s hook “command” is treated as a file to open, not a script to run.

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

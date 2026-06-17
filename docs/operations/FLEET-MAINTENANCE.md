# Fleet maintenance — multi-repo TAPPS upgrade and audit

Runbook for upgrading **tapps-mcp**, **AgentForge**, **NLTlabsPE**, and **NewCompanyIdeas** together on one machine (Cursor + Claude Code). Use this when you want all six NLT MCP servers visible in each workspace plus a usage audit before reload.

See also [UPGRADE_FOR_CONSUMERS.md](../UPGRADE_FOR_CONSUMERS.md) §7 for the generic fleet-upgrade API.

---

## Maintainer fleet (this machine)

| Project | Path | Brain project id | Notes |
|---------|------|------------------|-------|
| tapps-mcp | `~/code/tapps-mcp` | `tapps-mcp` | Dev repo — `mcp_bundle: full` is normal |
| AgentForge | `~/code/AgentForge` | `agentforge` | `upgrade_skip_files` on AGENTS/CLAUDE (stamp stays `slim-local`); `mcp_bundle: full` |
| NLTlabsPE | `~/code/NLTlabsPE` | `nlt-engine` | Consumer repo; `mcp_bundle: full` |
| NewCompanyIdeas | `~/NewCompanyIdeas` | `nlt-ideas-scout` | Extra **`agentforge`** MCP server preserved on upgrade |

```bash
export TAPPS_FLEET_ROOTS=\
$HOME/code/tapps-mcp,\
$HOME/code/AgentForge,\
$HOME/code/NLTlabsPE,\
$HOME/NewCompanyIdeas
```

`NewCompanyIdeas` is **not** under `~/code` — always pass explicit `--roots` (or `TAPPS_FLEET_ROOTS`) when upgrading it.

---

## Six NLT MCP servers

| Server | Profile | Purpose |
|--------|---------|---------|
| `nlt-build` | `nlt-build` | Score, gate, security, validate, impact |
| `nlt-memory` | `nlt-memory` | Brain memory (search/save/health) |
| `nlt-linear-issues` | `nlt-linear-issues` | Linear snapshot + issue tools |
| `nlt-project-docs` | `nlt-project-docs` | DocsMCP (drift, generate, validate) |
| `nlt-release-ship` | `nlt-release-ship` | Release notes / ship gate |
| `nlt-setup` | `nlt-setup` | Init, upgrade, doctor |

**Bundles**

| Bundle | Enabled in `.cursor/mcp.json` | When |
|--------|-------------------------------|------|
| `full` (default) | All 6 | Default deployment ([ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)); doctor NLT **PASS** when `mcp_bundle=full` is resolved |
| `developer` | 3 — build, memory, linear-issues | Opt-down for token-tight sessions; doctor NLT **PASS** |

The default deployment enables all six servers ([ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)). Set `mcp_bundle: developer` (or `minimal`) in `.tapps-mcp.yaml`, or run `TAPPS_FLEET_BUNDLE=developer ./scripts/fleet-upgrade.sh`, to opt a repo or the maintainer fleet down to a smaller surface.

Custom non-NLT entries (e.g. NewCompanyIdeas `agentforge`) are **preserved** during `init` / fleet upgrade.

---

## Upgrade + audit (copy/paste)

From the tapps-mcp checkout after `git pull`:

```bash
cd ~/code/tapps-mcp
export TAPPS_FLEET_ROOTS="$HOME/code/tapps-mcp,$HOME/code/AgentForge,$HOME/NewCompanyIdeas"

# 1. Preview
TAPPS_FLEET_BUNDLE=full ./scripts/fleet-upgrade.sh --dry-run

# 2. Apply (reinstalls global tapps-mcp + docsmcp, upgrades scaffolding, writes MCP config)
TAPPS_FLEET_BUNDLE=full ./scripts/fleet-upgrade.sh

# 3. Usage audit (24h default; JSON to stdout)
uv run tapps-mcp audit-fleet --roots "$TAPPS_FLEET_ROOTS"

# 4. Per-repo doctor
for d in $HOME/code/tapps-mcp $HOME/code/AgentForge $HOME/NewCompanyIdeas; do
  echo "=== $(basename "$d") ==="
  (cd "$d" && uv run tapps-mcp doctor --quick) | rg 'FAIL|NLT partial|MCP client config|AGENTS.md|CLAUDE.md|Results:'
done
```

**Cursor:** reload MCP after fleet upgrade (`Developer: Reload Window` or Settings → MCP refresh). Open **each repo as its own workspace** — `.cursor/mcp.json` is project-scoped.

**Operator secrets:** `~/.tapps-operator.env` (see [OPERATOR-SECRETS.md](OPERATOR-SECRETS.md)).

---

## Global CLI policy ([ADR-0020](../adr/0020-global-uv-tool-default-blue-green-opt-in.md) → [ADR-0023](../adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md))

Two install stories coexist; pick by **whether the machine has the tapps-mcp checkout**:

- **Dev-monorepo machine (this one):** the global `~/.local/bin/{tapps-mcp,docsmcp}` is the **editable** install from the checkout — `uv tool install -e --reinstall packages/tapps-mcp` (and `packages/docs-mcp`). Re-run after a version bump so the global metadata matches the source (the upgrade **drift guard** blocks scaffolding upgrades until the global == the running server version). Blue/green (`~/.tapps-mcp/current`) is the **immutable** copy used by the Cursor wrappers.
- **Remote consumer machine (no checkout):** pin the global to a **release tag**:

  ```bash
  uv tool install --reinstall "tapps-mcp @ git+https://github.com/wtthornton/TappsMCP@v3.12.43#subdirectory=packages/tapps-mcp"
  uv tool install --reinstall "docs-mcp @ git+https://github.com/wtthornton/TappsMCP@v3.12.43#subdirectory=packages/docs-mcp"
  ```

**Fleet refresh defaults to blue/green ([ADR-0023](../adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md)):** `upgrade-fleet --reinstall-clis` runs `deploy-local` (build immutable release → flip `~/.tapps-mcp/current` → regenerate consumer Cursor wrappers). It does **not** mutate the live `~/.local` venv. In-place reinstall is the deprecated hazard (it can kill *other* open Cursor windows machine-wide); it requires explicit `--force-inplace-cli-reinstall` and a full MCP stop.

| Host | MCP launch | Picks up blue/green flips? |
|------|------------|---------------------------|
| **Cursor** (any repo) | `.cursor/bin/nlt-*-serve.sh` — probes `~/.tapps-mcp/current/bin/<tool>`, falls back to `~/.local/bin` ([ADR-0023](../adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md)) | **Yes** — on MCP reload |
| **Claude Code** (any repo) | `.mcp.json` → `~/.local/bin/tapps-mcp` **directly** (no `current` probe) | **No** — the `~/.local` global must itself be at the target version; reinstall it (dev: `-e` from checkout; remote: tagged) and reload |

> **Claude Code gap:** because `.mcp.json` launches the raw `~/.local/bin` shim, a `deploy-local` flip alone never reaches Claude Code — only Cursor wrappers probe `current`. To upgrade Claude Code you must bring the `~/.local` global to the target version (the drift guard enforces this) and reload. Tracked for a generator fix so Claude `.mcp.json` also probes `current`.

`tapps-mcp doctor` warns when globals were installed from a local path (`Global CLI install source`) — expected on the dev-monorepo machine. The default deployment is `full` (all six servers, [ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)); set `mcp_bundle: developer` in `.tapps-mcp.yaml` (build + memory + linear-issues) for token-tight sessions.

---

## Expected doctor outcomes (2026-06-16, v3.12.43)

| Project | MCP | Doctor notes |
|---------|-----|--------------|
| tapps-mcp | 6 NLT (full) | PASS |
| AgentForge | 6 NLT | Intentional full-bundle WARN; AGENTS/CLAUDE stamp stays **`slim-local`** (`upgrade_skip_files`) |
| NLTlabsPE | 6 NLT | Same WARN; stamp at 3.12.43 |
| NewCompanyIdeas | 6 NLT + agentforge | Same WARN; stamp at 3.12.43 |

Fleet upgrade exit code may be non-zero when doctor reports the intentional full-bundle WARN — upgrade and MCP init still succeed.

---

## AgentForge version stamps (manual)

AgentForge pins `AGENTS.md` and `CLAUDE.md` in `.tapps-mcp.yaml` `upgrade_skip_files` to keep its slimmed deployment-policy callouts. The stamp intentionally reads `slim-local`, **not** a version number, and `tapps-mcp upgrade` leaves it untouched:

```markdown
<!-- tapps-claude-version: slim-local (upgrade_skip_files) -->
```

---

## Last fleet run

| Field | Value |
|-------|-------|
| Date | 2026-06-16 |
| Bundle | `full` |
| CLI version | tapps-mcp / docsmcp 3.12.43 (tagged v3.12.43; global `-e` from checkout; blue/green `current` = `3.12.43-4082bec`) |
| Brain | 3.24.0 @ `http://localhost:8080` |
| Projects | 4/4 upgrade + MCP init OK (tapps-mcp, AgentForge, NLTlabsPE, NewCompanyIdeas) |

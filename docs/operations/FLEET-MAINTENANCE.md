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

`NewCompanyIdeas` is **not** under `~/code` — always pass explicit `--roots` (or `TAPPS_FLEET_ROOTS`) when upgrading it. For the HTTP fleet, list it in `~/.tapps-mcp/fleet.env` as:

```bash
TAPPS_FLEET_EXTRA_ROOTS=$HOME/NewCompanyIdeas
```

Absolute `X-Tapps-Project-Root` headers already identify any repo; `TAPPS_FLEET_EXTRA_ROOTS` documents extras for audit/scan (TAP-5159).

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

The default deployment enables all six servers ([ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)). Opt a single repo down with `tapps-mcp mcp-bundle set developer` (writes yaml + host MCP configs; then reload MCP), set `mcp_bundle: developer` in `.tapps-mcp.yaml`, or run `TAPPS_FLEET_BUNDLE=developer ./scripts/fleet-upgrade.sh` for the whole fleet.

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
| **Claude Code** (stdio) | `.claude/bin/nlt-*-serve.sh` — same `current` probe as Cursor (TAP-5155) | **Yes** — on MCP reload after `init`/`upgrade` regenerates wrappers |
| **Claude Code / Cursor** (HTTP) | `streamableHttp` / `http` URLs → shared fleet on 8760–8765 | **Yes** — fleet restart after `deploy-local` |

> **Resolved (TAP-5155):** Claude Code stdio configs now use `.claude/bin/nlt-*-serve.sh` wrappers with the same `~/.tapps-mcp/current` probe as Cursor. Re-run `tapps-mcp init --host claude-code --force` (or fleet upgrade) once to regenerate; HTTP transport was already shared-fleet and unchanged.

`tapps-mcp doctor` warns when globals were installed from a local path (`Global CLI install source`) — expected on the dev-monorepo machine. The default deployment is `full` (all six servers, [ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md)); opt down with `tapps-mcp mcp-bundle set developer` (build + memory + linear-issues) for token-tight sessions. Doctor reports **eager (Claude)** vs **listed (Cursor)** on the NLT row.

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
| Date | 2026-07-30 |
| Bundle | `full` |
| CLI version | tapps-mcp / docsmcp **3.12.53** (global `-e` from checkout; blue/green `current` = `3.12.53-943e313c`) |
| Brain | 3.27.0 @ `http://localhost:8080` |
| Projects | 5/5 upgrade + MCP init OK (tapps-mcp, AgentForge, NLTlabsPE, NewCompanyIdeas, ReportLab). Doctor exit non-zero on intentional budget WARNs (CLAUDE.md / skill inventory ceilings) — not upgrade regressions. Binary version mismatch cleared after editable `uv tool install -e --reinstall`. |
| Gate rollup (7d, local JSONL) | completion_gate_violations=311; cache_gate_violations=800; loop_metrics_rows=5353 |
| Call-graph GC | Empty `.cursor-mcp-session-*` markers pruned across 5 projects; doctor no longer reports pending GC on tapps-mcp |
| Notes | One `http_client_close_failed` / Event loop closed at fleet restart (11:08Z) during deploy-local cutover — expected; pre-deploy hits remain in rotated logs. Reload Cursor stdio MCP if a window still pins an old release dir. Consumer repos may have uncommitted scaffolding diffs from this upgrade. |

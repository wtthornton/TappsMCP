# Fleet maintenance — multi-repo TAPPS upgrade and audit

Runbook for upgrading **tapps-mcp**, **AgentForge**, and **NewCompanyIdeas** together on one machine (Cursor primary). Use this when you want all six NLT MCP servers visible in each workspace plus a usage audit before reload.

See also [UPGRADE_FOR_CONSUMERS.md](../UPGRADE_FOR_CONSUMERS.md) §7 for the generic fleet-upgrade API.

---

## Maintainer fleet (this machine)

| Project | Path | Brain project id | Notes |
|---------|------|------------------|-------|
| tapps-mcp | `~/code/tapps-mcp` | `tapps-mcp` | Dev repo — `--bundle full` is normal |
| AgentForge | `~/code/AgentForge` | `agentforge` | `AGENTS.md` / `CLAUDE.md` in `upgrade_skip_files` — bump version stamps manually |
| NewCompanyIdeas | `~/NewCompanyIdeas` | `nlt-ideas-scout` | Extra **`agentforge`** MCP server preserved on upgrade |

```bash
export TAPPS_FLEET_ROOTS=\
$HOME/code/tapps-mcp,\
$HOME/code/AgentForge,\
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
| `developer` (default) | 3 — build, memory, linear-issues | Daily coding; doctor NLT **PASS** |
| `full` | All 6 | Maintainer fleet upgrade / power-user; doctor NLT **WARN** if >3 enabled |

The **tapps-mcp dev repo** uses `mcp_bundle: developer` in `.tapps-mcp.yaml` for stable Cursor MCP. Run `TAPPS_FLEET_BUNDLE=full ./scripts/fleet-upgrade.sh` when you need all six servers across the maintainer fleet.

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

## Expected doctor outcomes (2026-06-15, v3.12.29)

| Project | MCP (Cursor) | Doctor notes |
|---------|--------------|--------------|
| tapps-mcp | 3 NLT (developer) | PASS: build + memory + linear-issues |
| AgentForge | 6 NLT | Same WARN; AGENTS/CLAUDE stamps **3.12.28** until manually bumped (`upgrade_skip_files`) |
| NewCompanyIdeas | 6 NLT + agentforge | Same WARN; stamps at 3.12.29 |

Fleet upgrade exit code may be non-zero when doctor reports the intentional full-bundle WARN — upgrade and MCP init still succeed.

---

## AgentForge version stamps (manual)

AgentForge pins `AGENTS.md` and `CLAUDE.md` in `.tapps-mcp.yaml` `upgrade_skip_files` to keep deployment-policy callouts. After each fleet upgrade, optionally update:

```markdown
<!-- tapps-agents-version: 3.12.29 -->
<!-- tapps-claude-version: 3.12.29 -->
```

---

## Last fleet run

| Field | Value |
|-------|-------|
| Date | 2026-06-15 |
| Bundle | `full` |
| CLI version | tapps-mcp / docsmcp 3.12.29 |
| Brain | 3.24.0 @ `http://localhost:8080` |
| Projects | 3/3 upgrade + MCP init OK |

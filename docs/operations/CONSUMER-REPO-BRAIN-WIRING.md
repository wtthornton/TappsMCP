# Consumer repo: verify tapps-mcp ↔ tapps-brain wiring

Operator and agent checklist for wiring a **new LLM coding repo** to the shared
tapps-brain memory service via tapps-mcp (bridge-only — agents never call
tapps-brain directly).

For host-level brain deployment, see [TAPPS-BRAIN-LOCAL-SETUP.md](TAPPS-BRAIN-LOCAL-SETUP.md).
For runtime troubleshooting, see [MEMORY_REFERENCE.md § brain-health-diagnostics](../MEMORY_REFERENCE.md#brain-health-diagnostics).

---

## Architecture (non-negotiable)

- Consumer repo MCP config lists **tapps-mcp only** — NOT `tapps-brain` as a
  parallel MCP server in `.mcp.json` / `.cursor/mcp.json`.
- Memory flows: agent → `tapps-mcp memory` CLI → tapps-mcp BrainBridge → tapps-brain HTTP
  (`http://127.0.0.1:8080` or host URL). The `tapps_memory` MCP tool was removed (TAP-1994).
- Brain credentials live on the **tapps-mcp env block**, not in agent hands.
- Skill to use: `tapps-memory` (NOT `tapps-brain`).

`tapps_init` scaffolds HTTP bridge env by default. In-process mode
(`TAPPS_BRAIN_DATABASE_URL`) still exists for single-host setups — see
[ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md) and
[TAPPS-BRAIN-LOCAL-SETUP.md](TAPPS-BRAIN-LOCAL-SETUP.md). This guide targets
**shared-brain / multi-repo** HTTP wiring.

---

## Prerequisites (host-level, once per machine)

1. tapps-brain HTTP stack is running and healthy:

   ```bash
   curl -fsS http://127.0.0.1:8080/healthz | jq '{ok, brain_version, db_ok}'
   ```

   - `brain_version` must be **≥ 3.24.0** (floor per
     [ADR-0013](../adr/0013-pin-tapps-brain-version-floor-at-3240.md),
     `packages/tapps-core/pyproject.toml`, and `_BRAIN_VERSION_FLOOR` in
     `brain_bridge.py`).
   - The hard floor is enforced at bridge startup, in
     `tapps_session_start() → brain_bridge_health.details.brain_version`, and
     by `tapps-mcp doctor` (`tapps-brain version floor` check). The separate
     `tapps-brain version delta` check only warns when the running brain is far
     *ahead* of the pin.

2. You have the data-plane bearer token from the brain deployment
   (`TAPPS_BRAIN_AUTH_TOKEN` in tapps-brain `docker/.env`, or a per-project
   client token from `tapps-brain token create` — either works if it reaches
   `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` at MCP server startup).

---

## Per-repo setup checklist

### A. Bootstrap tapps-mcp (if not done)

From the consumer repo root:

1. `tapps_init` (or `tapps-mcp upgrade --host auto --force` if MCP unavailable).
   MCP config is written by default (`mcp_config=True`); pass `mcp_config=False`
   to scaffold pipeline files only.
2. Confirm generated files: `AGENTS.md`, `.tapps-mcp.yaml`, `.mcp.json` or
   `.cursor/mcp.json`, hooks, `tapps-memory` skill.
3. **Regression check:** `.mcp.json` must NOT contain a `tapps-brain` HTTP server
   entry. `tapps-mcp doctor` fails on this; `tapps_init` and `tapps_upgrade`
   strip stray entries automatically (TAP-1888).

### B. Register this repo on the brain (one-time per project)

**Project slug** must match what tapps-mcp sends as `X-Project-Id`.

By default tapps-mcp derives the slug from `project_root.name` via
`_slugify_project_root` (lowercase; non-alphanumeric → `-`; generic names like
`tmp`, `code`, `src`, `workspace` are rejected — set an explicit slug instead).

Examples:

| Directory name | Derived slug |
|----------------|--------------|
| `my-cool-app` | `my-cool-app` |
| `MyApp` | `myapp` |
| `foo.bar` | `foo-bar` |
| `tmp` | *(empty — set explicitly)* |

**Source of truth:** `tapps_session_start() → memory_status.brain_project_id`.
For non-trivial directory names, set `memory.brain_project_id` in
`.tapps-mcp.yaml` (section D) *before* registering on the brain.

```bash
docker exec tapps-brain-http tapps-brain project register <project_id> \
  --profile /usr/local/lib/python3.13/site-packages/tapps_brain/profiles/repo-brain.yaml \
  --notes "Consumer: <repo-name> via tapps-mcp"
docker exec tapps-brain-http tapps-brain project list | grep <project_id>
```

Cross-check against tapps-brain's own register docs if your deployment uses a
different CLI shape (`tapps-brain project register --name X --slug X`).

### C. Consumer repo secrets (gitignored)

Create `.env` (`chmod 600`, add to `.gitignore` **before** first commit):

```bash
# Shared name used by .mcp.json ${TAPPS_BRAIN_AUTH_TOKEN} substitution
TAPPS_BRAIN_AUTH_TOKEN=<same token as brain container>

# Client env vars tapps-mcp reads (required for CLI doctor + shell workflows)
TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://127.0.0.1:8080
TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN=<same token>
TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID=<project_id>
```

Enable direnv (`echo 'dotenv' > .envrc && direnv allow .`) so MCP subprocesses
and terminal `tapps-mcp doctor` inherit the token.

### Brain auth token resolution (shared precedence)

tapps-mcp resolves the brain bearer token in **one order** for MCP subprocesses,
CLI (`tapps-mcp doctor`, `memory save/get`), and `tapps_session_start` probes.
Literal `${VAR}` placeholders in config count as **missing** (unexpanded).

| Priority | Source | Notes |
|----------|--------|-------|
| 1 | `memory.brain_auth_token` in `.tapps-mcp.yaml` | Highest; use for repo-local override |
| 2 | `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` | MCP env block + shell export; primary CLI name |
| 3 | `TAPPS_BRAIN_AUTH_TOKEN` | Shared name in `.env`; mapped to (2) by Cursor wrapper and MCP `${...}` substitution |

**Cursor (TAP-3255):** `tapps-mcp init/upgrade --host cursor` writes
`.cursor/bin/tapps-mcp-serve.sh`, which sources project `.env` and maps
`TAPPS_BRAIN_AUTH_TOKEN` → `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` before
`exec tapps-mcp serve`. This avoids GUI-launched Cursor failing when
`${TAPPS_BRAIN_AUTH_TOKEN}` in `mcp.json` does not expand.

**Hints on auth failure:** `tapps_session_start` and `tapps doctor` suggest
setting `TAPPS_BRAIN_AUTH_TOKEN` in `.env` *or* exporting
`TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` — both are valid; precedence above decides
which value wins.

Minimal `.envrc` (loads `.env` above):

```bash
dotenv
```

**GUI-launched IDEs** (Cursor/VS Code from desktop dock) do not source
`~/.bashrc` or direnv automatically. If `${TAPPS_BRAIN_AUTH_TOKEN}` expands
empty in MCP config, use `~/.config/environment.d/` (Linux) or `launchctl
setenv` (macOS) — see [TAPPS-BRAIN-LOCAL-SETUP.md § GUI-launched IDE](TAPPS-BRAIN-LOCAL-SETUP.md#vscode--gui-launched-ide-the-gui-launch-gotcha).

### D. `.tapps-mcp.yaml` memory block

Ensure (create or merge — do not wipe user customizations):

```yaml
memory:
  brain_http_url: http://127.0.0.1:8080   # or remote brain URL
  brain_project_id: <project_id>          # MUST match brain registration slug
  # brain_auth_token: optional if TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN is set
```

Optional offline mode only: `memory.tolerate_brain_auth_failure: true` (quality
pipeline works; memory degrades — not for production brain setups).

### E. `.mcp.json` tapps-mcp env block (generated by `tapps_init`; verify on upgrade)

The tapps-mcp server entry must include:

```json
"env": {
  "TAPPS_MCP_PROJECT_ROOT": "<host-specific>",
  "TAPPS_MCP_MEMORY_BRAIN_HTTP_URL": "http://127.0.0.1:8080",
  "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN": "${TAPPS_BRAIN_AUTH_TOKEN}",
  "TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID": "<project_id>",
  "TAPPS_BRAIN_PROFILE": "full"
}
```

**`TAPPS_MCP_PROJECT_ROOT` is host-specific:** Claude Code uses `"."` (launch
CWD == project root); Cursor and VS Code get the resolved absolute path.
Do not blindly overwrite on upgrade.

Common mistake: setting only `TAPPS_BRAIN_AUTH_TOKEN` in the shell without
`TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` — MCP substitution handles the mapping
when the host expands `${...}`, but CLI `tapps-mcp doctor` reads
`TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` directly.

`TAPPS_BRAIN_PROFILE=full` is required for the full `tapps_memory` facade (42
actions including hive, KG, feedback). Do not downgrade to `coder` unless
intentionally narrowing scope ([ADR-0012](../adr/0012-brain-capability-profile-per-consumer-role.md)).

### F. CLI from shell (memory save/get, session-end)

MCP subprocesses inherit brain auth from the tapps-mcp **env block** in
`.mcp.json` / `.cursor/mcp.json`. Shell CLI commands do **not** — they read
environment variables at invocation time.

**Required for HTTP brain from a terminal** (same values as section C):

| Variable | Purpose |
|----------|---------|
| `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` | Brain HTTP endpoint |
| `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` | Bearer token (401 without it) |
| `TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID` | Registered project slug |

`TAPPS_BRAIN_AUTH_TOKEN` alone is **not** enough for CLI unless you also export
`TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` (doctor accepts either name; CLI bridge
reads the `TAPPS_MCP_*` names first).

```bash
cd <consumer-repo>
direnv reload 2>/dev/null || true
uv run tapps-mcp memory save --key wiring-smoke --tier context --value "CLI smoke"
uv run tapps-mcp memory get --key wiring-smoke
uv run tapps-mcp session-end   # best-effort; exits 0 on degrade
```

If `memory save/get` returns 401, export `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`
in the shell (section C) and re-run `tapps-mcp doctor --quick`.

### G. Verification (all must pass)

#### 1. CLI doctor

```bash
cd <consumer-repo> && direnv reload 2>/dev/null; tapps-mcp doctor
```

Expect PASS on (among others):

| Check | Meaning |
|-------|---------|
| `Brain MCP entry (bridge-only)` | No direct `tapps-brain` MCP server |
| `tapps-brain HTTP auth` | Bearer token + project id present; profile probe ok |
| `tapps-brain health` | MCP `initialize` to `/mcp/` succeeds |
| `tapps-brain capability profile` | `full` profile exposes bridge tools |
| `tapps-brain version floor` | Running brain ≥ `3.24.0` |

Doctor also reads `memory.brain_http_url` from `.tapps-mcp.yaml` when
`TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` is unset in the shell, and accepts
`TAPPS_BRAIN_AUTH_TOKEN` for CLI direnv workflows (same value as
`TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`).

#### 2. Session probe

Call `tapps_session_start()` and inspect `data.brain_bridge_health`:

- `enabled: true`, `ok: true`
- `dsn_reachable: true`, `native_health_ok: true`
- `errors: []` (if `brain_auth_failed`, fix token propagation — restart MCP host)
- `details.brain_version` ≥ `3.24.0`

#### 3. Round-trip memory

```bash
uv run tapps-mcp memory save --key "wiring-smoke-<project_id>" \
  --tier context --value "Brain bridge smoke test"
uv run tapps-mcp memory search --query "wiring smoke"
```

Second call must return the saved entry.

Optional HTTP smoke (from tapps-brain repo, same token): `make brain-smoke-live`
against the live stack.

### H. Document in repo (minimal)

`tapps_init` already populates `AGENTS.md` with `tapps_memory` guidance. If you
add a project-specific block to `CLAUDE.md` or `.cursor/rules/`, keep it short:

- Use `uv run tapps-mcp memory` for cross-session project knowledge — not direct brain MCP tools.
- `project_id = <project_id>`.
- Link: [MEMORY_REFERENCE.md § brain-health-diagnostics](../MEMORY_REFERENCE.md#brain-health-diagnostics).

---

## Failure remediation quick-reference

| Symptom | Fix |
|---------|-----|
| `brain_auth_failed` | `.env` token + direnv or `environment.d`; restart Cursor/Claude; check `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` in MCP env |
| CLI `memory save/get` 401 | Export `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` in shell (not just MCP `${TAPPS_BRAIN_AUTH_TOKEN}`); `direnv reload`; see § F |
| `brain_project_id_missing` | Set in `.tapps-mcp.yaml` or `TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID` |
| `403` / `out_of_profile` | Raise `TAPPS_BRAIN_PROFILE` to `full` (or `suggested_profile` from error) |
| version below floor | Upgrade brain image; confirm `brain_bridge_health.details.brain_version` ≥ `3.24.0` |
| project not registered | Run `tapps-brain project register <slug>` on the brain container |
| duplicate MCP servers | Remove direct `tapps-brain` block from `.mcp.json`; run `tapps_upgrade` |

---

## High-traffic projects: Linear cache-gate block mode (TAP-3577)

For repos with heavy `list_issues` usage (e.g. backlog triage bots), keep
`linear_enforce_cache_gate: block` in `.tapps-mcp.yaml` so raw
`mcp__plugin_linear_linear__list_issues` calls fail unless a matching
`tapps_linear_snapshot_get` sentinel exists (<300s). Route agents through the
`linear-read` skill.

```yaml
# .tapps-mcp.yaml excerpt — high-traffic consumer
linear_enforce_cache_gate: block
```

After changing the mode, run `tapps-mcp upgrade --force` to rebake hook scripts.
`tapps-mcp doctor` reports 24h cache-gate violations and recommends `block`
when warn-mode misses exceed 20/day.

---

## Deliverable (agent report template)

Post a short report:

- `project_id` used
- `brain_version` from `/healthz` or `brain_bridge_health.details`
- doctor pass/fail summary
- `brain_bridge_health` from `tapps_session_start`
- memory round-trip result
- any files changed (`.tapps-mcp.yaml`, `.envrc`, `.mcp.json` merge fixes)

Do **not** commit `.env`. Commit only safe config changes if the user asks.

---

## Shorter version (quick audit)

Audit tapps-mcp brain wiring in this repo:

1. No `tapps-brain` entry in `.mcp.json` / `.cursor/mcp.json` (bridge-only).
2. `.tapps-mcp.yaml` has `memory.brain_http_url` + `memory.brain_project_id`.
3. `.mcp.json` tapps-mcp env has `TAPPS_MCP_MEMORY_BRAIN_*` vars +
   `TAPPS_BRAIN_PROFILE=full` (verify host-specific `TAPPS_MCP_PROJECT_ROOT`).
4. `.env` has `TAPPS_BRAIN_AUTH_TOKEN` **and** `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`;
   direnv loads them (or `environment.d` for GUI-launched IDE).
5. Brain project registered: slug matches `tapps_session_start() →
   memory_status.brain_project_id` (usually slugified dirname; set explicitly
   when generic).
6. Run `tapps-mcp doctor` — brain checks PASS.
7. `tapps_session_start()` → `brain_bridge_health.ok == true`;
   `details.brain_version` ≥ `3.24.0`.
8. `tapps_memory` save + search round-trip succeeds.

Report failures with exact remediation from
[MEMORY_REFERENCE.md § brain-health-diagnostics](../MEMORY_REFERENCE.md#brain-health-diagnostics).

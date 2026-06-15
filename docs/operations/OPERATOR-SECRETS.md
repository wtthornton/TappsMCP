# Operator secrets (one file, all repos)

TappsMCP operator secrets are **machine-wide** — the same Context7 API key and
brain bearer token work for every consumer repo. Per-repo MCP config only
**references** them via `${TAPPS_MCP_CONTEXT7_API_KEY}` and
`${TAPPS_BRAIN_AUTH_TOKEN}`; it does not need unique values per project.

What **is** per-repo: `memory.brain_project_id` / `TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID`
(memory namespace) and project-specific keys such as `AGENTFORGE_API_KEY`.

---

## The GUI-launch problem

Terminal shells load `~/.bashrc` and export secrets. **Cursor/VS Code launched from
the desktop dock** do not — MCP subprocesses started via `.cursor/mcp.json` inherit
an empty environment unless you wire secrets another way.

Symptoms:

- `tapps_lookup_docs` → Context7 **401** on first MCP call (CLI works)
- `tapps_session_start` → `brain_auth_failed` while shell `tapps-mcp doctor` looks fine

---

## Recommended: `~/.tapps-operator.env`

Create a single gitignored file on the workstation:

```bash
cp docs/operations/tapps-operator.env.example ~/.tapps-operator.env
chmod 600 ~/.tapps-operator.env
# Edit and paste your Context7 key + brain bearer token (same values as tapps-brain docker/.env)
```

**Variables (shared across all repos):**

| Variable | Purpose |
|----------|---------|
| `TAPPS_MCP_CONTEXT7_API_KEY` | Live library docs via Context7 (`tapps_lookup_docs`) |
| `TAPPS_BRAIN_AUTH_TOKEN` | Bearer token for tapps-brain HTTP (memory, hive) |
| `TAPPS_MCP_MEMORY_BRAIN_HTTP_URL` | Brain URL (default `http://localhost:8080`) |

Optional alias: `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` (same value as `TAPPS_BRAIN_AUTH_TOKEN`).

**Per-repo `.env`** keeps **project-owned** secrets only (e.g. `AGENTFORGE_API_KEY`,
`REDDIT_CLIENT_ID`). Do not duplicate operator secrets unless you prefer a
self-contained repo checkout.

---

## How secrets reach MCP subprocesses

`tapps-mcp init/upgrade --host cursor` writes `.cursor/bin/nlt-*-serve.sh` wrappers
that:

1. `source ~/.tapps-operator.env` (operator-wide)
2. `source .env` (project-specific; overrides operator)
3. Map `TAPPS_BRAIN_AUTH_TOKEN` → `TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN` when needed
4. Map `CONTEXT7_API_KEY` → `TAPPS_MCP_CONTEXT7_API_KEY` when needed
5. `exec tapps-mcp serve …`

Reload MCP in Cursor after creating or editing `~/.tapps-operator.env`.

---

## Alternative: Linux `environment.d`

For GUI apps without per-repo `.envrc`, you can set literals once in
`~/.config/environment.d/tapps-operator.conf` and **log out/in**. See
[TAPPS-BRAIN-LOCAL-SETUP.md § GUI-launched IDE](TAPPS-BRAIN-LOCAL-SETUP.md#vscode--gui-launched-ide-the-gui-launch-gotcha).

`environment.d` does not support shell expansion — use literal values.

---

## Brain-central docs (ADR-0014)

When `docs_via_brain: true` and brain runs Context7 centrally, consumers can
**remove** `TAPPS_MCP_CONTEXT7_API_KEY` from MCP env after fleet cutover. See
[brain-doc-rag-cutover-runbook.md](brain-doc-rag-cutover-runbook.md).

---

## Verify

```bash
tapps-mcp doctor --quick
# Expect: mcp_operator_secrets PASS

cd /path/to/consumer-repo
tapps-mcp doctor --quick
```

---

## Related

- [CONSUMER-REPO-BRAIN-WIRING.md](CONSUMER-REPO-BRAIN-WIRING.md) — per-repo brain project id + registration
- [TAPPS-BRAIN-LOCAL-SETUP.md](TAPPS-BRAIN-LOCAL-SETUP.md) — brain deployment + GUI env
- [tapps-operator.env.example](tapps-operator.env.example) — copy template

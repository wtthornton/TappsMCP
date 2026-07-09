# Tutorial: Wire tapps-brain into a Claude Code session

**Time:** ~20 minutes (10 of it is the brain HTTP service warming up the first time). **Outcome:** A Claude Code session with cross-session memory backed by tapps-brain — you save a fact in one session and recall it in the next.

This walkthrough is for projects that want the optional shared-memory layer. tapps-mcp works without tapps-brain; this tutorial shows the additional wiring.

## Prerequisites

- Docker installed and running (`docker --version` works).
- TappsMCP installed and a `.mcp.json` already pointing at it (run [tutorial 02](02-quality-pipeline-walkthrough.md) first if you haven't bootstrapped).
- Claude Code on the latest version.

## Step 1 — Start the tapps-brain service

```bash
git clone https://github.com/wtthornton/tapps-brain.git ~/code/tapps-brain
cd ~/code/tapps-brain
docker compose up -d
```

The compose file brings up Postgres + the brain HTTP service on `localhost:8080`.

**Verify:**

```bash
curl -fsS http://localhost:8080/health
```

Should return JSON with `status: "ok"`. If it doesn't, give it ~30 seconds — the first start has to run migrations.

## Step 2 — Confirm tapps-mcp imports tapps-brain

tapps-mcp uses the in-process `AgentBrain` adapter (see [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md)). The `tapps-brain` Python package is declared as a dependency of `tapps-core` and installed by `uv sync --all-packages` against the local tapps-brain checkout — there is no PyPI distribution ([ADR-0003](../adr/0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md)).

```bash
uv run python -c "from tapps_brain import AgentBrain; print('import ok')"
```

Should print `import ok`. If it raises `ImportError`, the package isn't installed — clone the tapps-brain repo next to tapps-mcp and run `uv sync --all-packages` from the tapps-mcp checkout.

## Step 3 — Set the auth token

tapps-brain runs with auth on by default. Pull the token from the container env:

```bash
docker compose -f ~/code/tapps-brain/docker-compose.yaml exec brain env | grep TAPPS_BRAIN_AUTH_TOKEN
```

Copy the value. Then add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export TAPPS_BRAIN_AUTH_TOKEN="<paste-here>"
```

Reload your shell. Without this, `tapps_session_start` returns `code: brain_auth_failed` instead of silently degrading. (For offline workflows, set `memory.tolerate_brain_auth_failure: true` in `.tapps-mcp.yaml` instead.)

## Step 4 — Verify wiring with `tapps doctor`

```bash
uv run tapps-mcp doctor
```

Look for:
- `BrainBridge connection: ok` — the in-process client can reach the brain.
- `Hive status: enabled` — federation across projects is live.
- No lines marked `[FAIL]`.

If the doctor flags `brain_auth_failed`, your token didn't propagate to the MCP server's environment. Restart your terminal and Claude Code so the new `TAPPS_BRAIN_AUTH_TOKEN` reaches the spawned MCP subprocess.

## Step 5 — Save a memory

From the project root (CLI — works in every session):

```bash
uv run tapps-mcp memory save \
  --key tutorial-fact \
  --tier context \
  --value "The brain test value is 42."
```

The JSON output should include `success: true` and an `expires_at` timestamp 14 days out (default for the `context` tier).

Alternatively, enable **`nlt-memory`** in MCP config and use the slim `tapps_memory` MCP facade (see [tutorial 06](06-first-memory-session.md)). The tool is **not** on `nlt-build`; prefer `uv run tapps-mcp memory` CLI for full brain actions.

## Step 6 — Recall it from a new session

```bash
uv run tapps-mcp memory search --query "brain test value"
```

You should see the entry from Step 5 in the results. Cross-session persistence is working.

## Step 7 — Inspect the storage directly

```bash
docker compose -f ~/code/tapps-brain/docker-compose.yaml exec postgres \
  psql -U brain -d brain -c "select tier, scope, title from entries order by created_at desc limit 5;"
```

Your `Tutorial fact` entry should appear at the top. This confirms the entry round-tripped through the Postgres-backed brain rather than living in process-local state.

## Verification summary

You've confirmed:

- [x] tapps-brain HTTP service responds on `:8080/health`.
- [x] `AgentBrain` imports cleanly into tapps-mcp's process.
- [x] `TAPPS_BRAIN_AUTH_TOKEN` flows from your shell to the spawned MCP subprocess.
- [x] `tapps doctor` reports brain connection ok.
- [x] A saved memory in session A is recallable in session B.
- [x] The entry is visible in Postgres directly.

## What you learned

tapps-brain is **storage behind BrainBridge**, not a separate MCP server you configure. Use `uv run tapps-mcp memory …` or enable **`nlt-memory`** for MCP-exposed recall/save/handoff; tapps-mcp routes through `BrainBridge` to tapps-brain (in-process per [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md), or HTTP when `memory.brain_http_url` is set). **Do not** add a direct `tapps-brain` entry to `.mcp.json` / `.cursor/mcp.json` — `tapps_init` and `tapps_upgrade` strip stray entries (bridge-only, TAP-1888).

The four pieces that have to line up: brain HTTP service running (or in-process DSN), `tapps-brain` Python package importable, auth token in the MCP subprocess env, and `.mcp.json` listing **tapps-mcp only**. Miss any one and `tapps doctor` calls it out. Running brain must be **≥ 3.24.0** ([ADR-0013](../adr/0013-pin-tapps-brain-version-floor-at-3240.md)).

## Going further

- [docs/operations/CONSUMER-REPO-BRAIN-WIRING.md](../operations/CONSUMER-REPO-BRAIN-WIRING.md) — per-repo wiring checklist (bootstrap, registration, verification).
- [docs/MEMORY_REFERENCE.md](../MEMORY_REFERENCE.md) — full memory reference (44 actions, tier and scope rules, federation).
- [docs/operations/TAPPS-BRAIN-LOCAL-SETUP.md](../operations/TAPPS-BRAIN-LOCAL-SETUP.md) — production-grade setup, multi-project federation, operational notes.

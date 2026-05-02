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

tapps-mcp uses the in-process `AgentBrain` adapter (see [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md)), which is shipped by the `tapps-brain` PyPI package as a transitive dependency of `tapps-core`.

```bash
uv run python -c "from tapps_brain import AgentBrain; print('import ok')"
```

Should print `import ok`. If it raises `ImportError`, the package isn't installed — run `uv sync --all-packages` from the tapps-mcp checkout.

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

## Step 5 — Save a memory from the agent

Open Claude Code in any project and ask it to call:

```
tapps_memory(action="save", title="Tutorial fact", content="The brain test value is 42.", tier="context", scope="project")
```

The response should include `success: true`, an entry id, and an `expires_at` timestamp 14 days out (the default for the `context` tier).

## Step 6 — Recall it from a new session

Quit Claude Code, reopen it on the same project, and ask:

```
tapps_memory(action="search", query="brain test value")
```

You should see the entry from Step 5 in `data.results`. Cross-session persistence is working.

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

tapps-brain is **opt-in storage**, not a separate MCP server you talk to. tapps-mcp loads `AgentBrain` in-process and routes the `tapps_memory` MCP tool through `BrainBridge` to it (see [ADR-0001](../adr/0001-in-process-agentbrain-via-brainbridge.md) for why). Your agents only ever see `tapps_memory(...)` as a tool call — the brain is the storage backing that tool, not a parallel API.

The four pieces that have to line up: brain HTTP service running, `tapps-brain` Python package importable, `TAPPS_BRAIN_AUTH_TOKEN` set in the MCP subprocess env, and `.mcp.json` pointing at tapps-mcp. Miss any one and `tapps doctor` calls it out.

## Going further

- [docs/MEMORY_REFERENCE.md](../MEMORY_REFERENCE.md) — full memory reference (33 actions, tier and scope rules, federation).
- [docs/operations/TAPPS-BRAIN-LOCAL-SETUP.md](../operations/TAPPS-BRAIN-LOCAL-SETUP.md) — production-grade setup, multi-project federation, operational notes.

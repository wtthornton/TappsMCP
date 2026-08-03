# Hand-back prompt: move `agentforge-mcp` off per-session `uvx`

**Repo:** `AgentForge` (NOT tapps-mcp — filed from tapps-mcp per repo-boundaries rule)
**Observed:** 2026-08-03 on the primary dev host
**Impact:** 18 accumulated processes; `uv cache prune` is permanently blocked (24 GB cache unreclaimable)

---

## Problem

`AgentForge/.mcp.json` launches the MCP server through `uvx` as a **stdio** server:

```json
"agentforge": {
  "type": "stdio",
  "command": "uvx",
  "args": ["--from", "/home/wtthornton/code/AgentForge/clients/agentforge-mcp", "agentforge-mcp"]
}
```

Every editor session that opens a repo with this entry spawns a **new** `uv` process, and
that process holds `~/.cache/uv/.lock` open for its entire lifetime.

Measured on 2026-08-03:

1. **18** live `uvx --from .../agentforge-mcp` processes
2. Oldest age **2d 22h** (spawned 2026-07-31)
3. All 18 hold `~/.cache/uv/.lock` (confirmed via `fuser -v` and `/proc/*/fd`)
4. Exactly **1:1** with the 18 live Claude Code extension processes — one per open session

## Consequence

`uv cache prune` cannot run:

```
Cache is currently in-use, waiting for other uv processes to finish (use `--force` to override)
error: Timeout (300s) when waiting for lock on `/home/wtthornton/.cache/uv`
```

The uv cache is **24 GB** and cannot be reclaimed while any session is open. Because
sessions accumulate faster than they are closed, the practical window for pruning is
never. Disk is at 86% (131 GB free of 937 GB).

**These are not zombies.** Every process has a live parent and is serving an open
session — killing them would break those sessions. The accumulation is structural, not a
leak.

## Requested change

Pick one of the following, in descending order of preference.

### Option A — shared HTTP fleet (what tapps-mcp did)

Run one long-lived server and point every session at it over HTTP, instead of spawning one
stdio process per session. tapps-mcp runs six servers this way under a single systemd unit:

```ini
# ~/.config/systemd/user/tapps-mcp-fleet.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/home/wtthornton/.tapps-mcp/current/bin/tapps-mcp fleet start
ExecStop=/home/wtthornton/.tapps-mcp/current/bin/tapps-mcp fleet stop
```

with a companion `.timer` polling every 60s to restart if down, and configs referencing
`{"type": "http", "url": "http://127.0.0.1:<port>/mcp"}`.

Result on the tapps-mcp side: **6 processes total** regardless of session count, 695 MB
resident, no uv process in the picture at all, and one upgrade surface for every client
(Claude Code, Cursor, VS Code) simultaneously.

### Option B — `uv tool install` once, invoke the installed entry point

If stdio is required, install the tool once rather than resolving per launch:

```bash
uv tool install --from /home/wtthornton/code/AgentForge/clients/agentforge-mcp agentforge-mcp
```

```json
"agentforge": {
  "type": "stdio",
  "command": "/home/wtthornton/.local/bin/agentforge-mcp"
}
```

The launched process is then a plain Python process that never touches the uv cache lock.
Cost: an explicit reinstall step on each AgentForge change.

### Option C — status quo, documented

If per-session `uvx` is deliberate, document that `uv cache prune` requires closing all
editor sessions first, and schedule the prune (e.g. a boot-time unit before any editor
starts). This is the weakest option — it manages the symptom.

## Verification after the change

```bash
# Should drop to 0 (Option A) or to plain non-uv processes (Option B):
pgrep -fc 'uvx --from.*agentforge-mcp'

# Should now complete instead of timing out:
uv cache prune
```

## Note on scope

The tapps-mcp side of this host is already clean: six systemd-managed HTTP servers,
no per-session process growth. This issue is isolated to `agentforge-mcp` and is the sole
remaining blocker on reclaiming the 24 GB uv cache.

## Related

- [BRAIN-sentence-transformers-optional.md](BRAIN-sentence-transformers-optional.md) — the other out-of-lane
  dependency issue found in the same audit (~4.5 GB of unused CUDA wheels via tapps-brain)

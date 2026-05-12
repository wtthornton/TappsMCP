# 1. In-process AgentBrain via BrainBridge

Date: 2026-05-02

## Status

accepted

## Context

tapps-mcp depends on tapps-brain (the shared memory service backed by Postgres in Docker, exposed at `localhost:8080`). Two integration shapes were available: (a) call tapps-brain over HTTP via `TappsBrainClient`, the same way an external client would; or (b) load tapps-brain in-process via `AgentBrain` and route reads/writes through a thin `BrainBridge` adapter inside tapps-mcp. The HTTP path adds network hops, retry/timeout handling, lifespan-startup races, and a hard runtime dependency on the brain HTTP service being up before tapps-mcp can serve the first MCP tool call. The in-process path avoids those costs but binds tapps-mcp to tapps-brain at the Python-import level.

## Decision

tapps-mcp uses **in-process AgentBrain via `BrainBridge`** for all memory operations. The `tapps_memory` MCP tool, the auto-recall/auto-capture hooks, and the `tapps_core.memory.*` re-export shims all delegate to `BrainBridge`, which calls `AgentBrain` directly in the same Python process. The HTTP `TappsBrainClient` path is **not** used from tapps-mcp; it remains in tapps-brain only as the surface for future remote brain-as-a-service consumers. The version floor on tapps-brain is still bumped (see ADR-0002) so that any future migration to remote brain-as-a-service inherits a working client.

## Consequences

**Positive:** No network round-trip on every memory call; no lifespan-startup race; tapps-mcp serves tool calls instantly regardless of brain HTTP service state. Imports use `try/except ImportError` so tapps-mcp degrades gracefully when tapps-brain isn't installed (e.g. in non-standard installs).

**Negative:** Two `tapps-mcp` processes (one per Claude Code session) each load their own `AgentBrain` and Postgres connection pool — there is no cross-process memory sharing inside the Python layer; cross-process consistency comes from Postgres itself.

**Neutral:** A future remote brain-as-a-service migration must swap `BrainBridge` for `TappsBrainClient` at one seam — the rest of the codebase is unaffected because the `tapps_core.memory.*` modules are re-export shims.

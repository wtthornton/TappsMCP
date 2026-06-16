# 19. Blue/green dev-monorepo MCP deploy

Date: 2026-06-16

## Status

accepted

## Context

The tapps-mcp dev monorepo shares one machine-global MCP CLI install across many concurrent agents and Cursor windows. Deploys used `uv tool install --reinstall`, which mutates `~/.local/share/uv/tools/tapps-mcp` in place. Running MCP servers keep inode-pinned file handles but Python lazy imports read swapped files after reinstall — version mismatch, import errors, and fleet-wide Cursor **error** states. The same repo constantly runs pytest against its workspace `.venv`; deploys during test churn compounded handshake timeouts.

Consumer repos pin globals to release tags and are unaffected by this ADR.

## Decision

Dev-monorepo deploys use **blue/green** layout under `~/.tapps-mcp/`:

- Immutable release venvs: `~/.tapps-mcp/releases/<version>-<shortsha>/`
- Atomic flip: `~/.tapps-mcp/current` symlink via `Path.replace`
- Deploy lock: `flock` on `~/.tapps-mcp/.deploy.lock`
- Quiescence gate: refuse flip while pytest runs against the checkout
- Wrappers prefer `~/.tapps-mcp/current/bin/*` at runtime when present

CLI: `tapps-mcp deploy-local`. Fleet: `upgrade-fleet --reinstall-clis` calls the same path. Doctor adds `check_blue_green_deploy`.

Running servers stay pinned to their release dir until MCP reload; only new launches pick up `current`.

## Consequences

**Positive:** Zero-downtime deploy for live agents; no in-place mutation of the shared install; deploy serializes and waits for test quiescence.

**Negative:** First deploy builds a full venv (~minutes); disk under `~/.tapps-mcp/releases/`; operators must reload MCP after deploy for new code in new processes. Legacy `uv tool install --reinstall` remains for consumer tag pins and one-time bootstrap of the global CLI that hosts `deploy-local`.

**Operational note:** Do not use in-place `--reinstall` on the dev monorepo while agents are live. Use `deploy-local` then reload MCP.

## Alternatives

- **Deploy gate only (no blue/green):** Serializes timing but still mutates live install — rejected.
- **Keep in-place reinstall:** Simple but recurring outages — rejected.

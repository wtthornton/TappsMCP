# Consuming the TappsMCP HTTP fleet from AgentForge (TAP-6062)

How an AgentForge project registers one TappsMCP fleet endpoint as a
project-scoped MCP server, authenticates with a vault-held credential, and gets
a deliberately small tool surface.

Audience: the operator who runs the fleet and the person wiring an AgentForge
project. For fleet architecture see [ADR-0024](../adr/0024-shared-http-mcp-fleet.md);
for day-2 operations see [FLEET-MAINTENANCE.md](FLEET-MAINTENANCE.md).

## What is on offer

Exactly one server: **`nlt-build`** on port 8760, reached with a *runtime*
bearer token. That token buys four tools and nothing else:

| Tool | What it needs |
|---|---|
| `tapps_lookup_docs` | network only — works with no workspace |
| `tapps_research` | network only — works with no workspace |
| `tapps_security_scan` | a project root; refuses without one |
| `tapps_dependency_scan` | a project root; refuses without one |

The allowlist is enforced **server-side, per request**, on both `tools/list` and
`tools/call`. The list an agent sees and the calls it can make are the same set;
naming a tool the agent was not offered returns an error, not a result. The
other five fleet servers (`nlt-memory`, `nlt-setup`, `nlt-linear-issues`,
`nlt-project-docs`, `nlt-release-ship`) reject the runtime token outright with
`401` — they are not part of this surface at all.

## Operator side: enable auth, then open the bind

Two environment variables, both read from `~/.tapps-mcp/fleet.env` (or the
process environment):

```bash
# ~/.tapps-mcp/fleet.env
TAPPS_FLEET_AUTH_TOKEN=<operator credential, all six servers>
TAPPS_FLEET_RUNTIME_TOKEN=<agent-runtime credential, nlt-build only>
```

Generate them with something you would not mind reading in a log line only
once:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Auth is **off** while both are unset. That is the unchanged local default: a
loopback-only fleet with no token, exactly as before TAP-6062. Setting either
variable turns auth on for every fleet server, and an unauthenticated request
then gets `401`.

Only after a token exists may the fleet leave loopback:

```bash
TAPPS_FLEET_HOST=0.0.0.0     # or a specific interface address
```

This ordering is enforced in code, not in this document. `tapps-mcp fleet start`
refuses the whole start, and each server's own `run_server` refuses before
`uvicorn.run`, when the bind host is non-loopback and no token is configured:

```
Refusing to start: HTTP fleet bind host '0.0.0.0' is not loopback and bearer
auth is disabled. Set TAPPS_FLEET_AUTH_TOKEN (and optionally
TAPPS_FLEET_RUNTIME_TOKEN for agent-runtime callers) before exposing the fleet
off 127.0.0.1, or bind to 127.0.0.1.
```

A hostname the guard cannot resolve offline is treated as non-loopback. Unknown
refuses; it never skips.

> The fleet speaks plain HTTP. Off-loopback exposure belongs behind a TLS
> terminator or a private overlay network — the bearer token authenticates the
> caller, it does not encrypt the hop.

## Presenting the credential

Two accepted header shapes, same token:

```http
Authorization: Bearer <token>
```
```http
X-Tapps-Fleet-Token: <token>
```

The second exists for AgentForge. Its publish-time validator
(`backend/projects/mcp_entry_validate.py`) requires every `headers` value to be
*entirely* a `${...}` template — a `"Bearer ${vault:...}"` value is rejected as
an inline secret because of the literal `Bearer ` prefix. `X-Tapps-Fleet-Token`
carries the bare token, so the vault reference stands alone.

## AgentForge project entry

Publish one project-scoped MCP entry. The credential is a vault reference
scoped to the project slug; the workspace path is a template the runtime
expands.

```json
{
  "name": "nlt-build",
  "type": "http",
  "url": "http://127.0.0.1:8760/mcp",
  "headers": {
    "X-Tapps-Fleet-Token": "${vault:tapps_fleet_runtime_token@project:<slug>}",
    "X-Tapps-Project-Root": "${AF_PROJECT_ROOT}"
  },
  "tool_allowlist": [
    "tapps_lookup_docs",
    "tapps_research",
    "tapps_security_scan",
    "tapps_dependency_scan"
  ],
  "read_only": true
}
```

What the validator checks, and how this entry satisfies it:

1. `type` is `"http"` and `url` is non-empty — HTTP entries are validated on
   `url`, not `command`.
2. Every `env` / `headers` value matches `^(\$\{[^}]+\})+$` in full. Both header
   values above are a single template each.
3. Any `vault:` interior is shaped `${vault:<key>@project:<slug>}`, with the
   scope equal to `project:<slug>` for the project being published. Substitute
   the real slug; a mismatched scope is rejected with a `vault_ref` error.
4. An inline `name` must equal the path name.

`tool_allowlist` is a least-privilege declaration on AgentForge's side. It is
belt-and-braces: TappsMCP enforces the same four names server-side regardless
of what the registry says, so a drifted or omitted allowlist cannot widen the
surface.

Store the secret first, under the same project scope:

```
vault key: tapps_fleet_runtime_token
vault scope: project:<slug>
value: <the TAPPS_FLEET_RUNTIME_TOKEN value>
```

## Workspace-free mode

`X-Tapps-Project-Root` is optional. Its absence on an HTTP request is a
first-class state — *workspace-free* — distinct from a stdio server that legitimately
falls back to its own working directory.

- `tapps_lookup_docs` and `tapps_research` run normally. They need the network,
  not a repository.
- `tapps_security_scan` and `tapps_dependency_scan` are refused before their
  handler runs, with a structured error:

```json
{
  "success": false,
  "error": {
    "code": "workspace_required",
    "message": "tapps_security_scan needs a project root and this request has none: the X-Tapps-Project-Root header was absent. Refusing rather than scanning the fleet server's own working directory.",
    "category": "user_input",
    "retryable": false,
    "missing": "X-Tapps-Project-Root",
    "workspace_mode": "workspace-free",
    "remediation": "Send the X-Tapps-Project-Root header with an absolute path to the repository to scan, or pass an explicit project_root argument. Docs and research tools work without one; scanners do not."
  }
}
```

That is deliberate. The alternatives are both worse than an error: scanning the
fleet process's own directory reports on the wrong repository, and returning an
empty result reads to an agent as "no vulnerabilities found". The set of tools
that need a tree is one declaration (`WORKSPACE_REQUIRED_TOOLS`) checked in the
same request guard that enforces the allowlist, so a future scanner cannot ship
without it.

The path in the header must be one the *fleet host* can read — it is resolved by
the fleet process, not by the agent runtime. Keep consumer repositories under
`TAPPS_FLEET_CODE_ROOT` (or list them in `TAPPS_FLEET_EXTRA_ROOTS`) so operator
audit tooling knows about them.

## Verifying the wiring

```bash
# 1. Unauthenticated -> 401 once a token is configured
curl -si http://127.0.0.1:8760/mcp -X POST \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -1

# 2. Runtime token -> four tools
curl -s http://127.0.0.1:8760/mcp -X POST \
  -H "X-Tapps-Fleet-Token: $TAPPS_FLEET_RUNTIME_TOKEN" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 3. Runtime token on another fleet server -> 401
curl -si http://127.0.0.1:8761/mcp -X POST \
  -H "X-Tapps-Fleet-Token: $TAPPS_FLEET_RUNTIME_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -1
```

## Rotating the credential

1. Set the new value in `~/.tapps-mcp/fleet.env`.
2. `tapps-mcp fleet start --force` (or `systemctl --user restart tapps-mcp-fleet.service`).
3. Update the vault secret under `project:<slug>` and re-publish the project entry.

There is no dual-token grace window: the old value stops working as soon as the
fleet restarts, so rotate the vault secret in the same maintenance step.

## Why this is not TAP-299

TAP-299 proposed registering **tapps-brain** as its own MCP entry for agents,
and was cancelled: tapps-brain is bridge-only, and a parallel MCP entry would
have created a second action surface that bypasses `BrainBridge`'s profile
enforcement, tier rules, supersede semantics, and content-safety gating. The
objection was to *shipping a second server that routes around the gateway*.

This is the opposite shape. No new server is published; the consumer is an HTTP
client of the `nlt-build` endpoint the operator already runs, and every call
still traverses tapps-mcp's own gates. The bearer token and the four-tool
allowlist narrow that existing surface rather than widening it, so the
cancellation reason does not apply — it is the principle being applied.

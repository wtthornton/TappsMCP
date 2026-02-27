# Epic 25: IDE Marketplace Integration

**Status:** Proposed
**Priority:** P3 - Nice to have (depends on adoption trajectory)
**Estimated LOE:** ~4-6 weeks (1 developer)
**Dependencies:** Epic 6 (Distribution), Epic 24 (HTTP Transport - helpful for managed server)
**Blocks:** None

---

## Goal

Package TappsMCP as installable extensions for VS Code Marketplace and JetBrains Marketplace, providing one-click install with automatic MCP server management, configuration UI, and inline quality feedback.

## Why This Epic Exists

Currently, installing TappsMCP requires:

1. Installing via pip/pipx/uv (`pip install tapps-mcp`)
2. Manually editing MCP configuration files (`.mcp.json`, `.claude/settings.json`, `.cursor/settings.json`)
3. Understanding MCP server configuration (transport, project root, arguments)
4. Running `tapps-mcp init` to bootstrap project files

This multi-step process limits adoption. IDE marketplace extensions solve this by:

1. **Discoverability** - Users find TappsMCP by searching "code quality" in their IDE's marketplace
2. **One-click install** - Extension handles Python/uv installation, MCP config, and server lifecycle
3. **Configuration UI** - Settings panel instead of YAML files
4. **Inline feedback** - Quality scores and issues shown in the editor, not just MCP tool responses

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Users don't discover TappsMCP | Marketplace search surfaces it alongside popular quality tools |
| MCP configuration errors | Extension auto-configures the MCP server correctly |
| Server not running when needed | Extension manages server lifecycle (start/stop/restart) |
| Quality feedback hidden in tool responses | Inline decorations show scores in the editor gutter |

## Architecture Notes

### Extension structure

Both VS Code and JetBrains extensions would be thin wrappers around the TappsMCP server:

```
vscode-tapps-mcp/
  package.json        <- VS Code extension manifest
  src/
    extension.ts      <- activation, server lifecycle
    server-manager.ts <- install/start/stop TappsMCP process
    config-provider.ts <- settings UI <-> .tapps-mcp.yaml
    mcp-client.ts     <- optional: direct MCP client for inline features
    diagnostics.ts    <- optional: show lint issues as VS Code diagnostics
  resources/
    icon.png

jetbrains-tapps-mcp/
  plugin.xml          <- JetBrains plugin descriptor
  src/main/kotlin/
    TappsMCPPlugin.kt
    ServerManager.kt
    SettingsConfigurable.kt
```

### Server management approach

The extensions would NOT embed TappsMCP. Instead they:

1. Check if `tapps-mcp` is installed (pip/pipx/uv)
2. If not, offer to install it (via pipx or uv tool install)
3. Manage the server process lifecycle (start on IDE open, stop on close)
4. Write MCP configuration to the appropriate location for the IDE's MCP client
5. Optionally use HTTP transport for richer integration

### VS Code extension API considerations

- **MCP support in VS Code** - As of early 2026, VS Code Copilot supports MCP servers via `.vscode/mcp.json`. The extension can auto-generate this file.
- **Language Server Protocol** - TappsMCP is NOT an LSP server, but the extension could translate scoring results into VS Code diagnostics for inline display.
- **Settings sync** - VS Code settings sync would propagate TappsMCP configuration across machines.

## Stories

### Story 25.1: VS Code Extension - Server Management

Create a VS Code extension that manages the TappsMCP server lifecycle: detect installation, offer to install, start/stop server, and auto-configure MCP settings.

- Extension activation on workspace open
- Detect `tapps-mcp` binary (pip, pipx, uv, or PyInstaller exe)
- Install prompt if not found (via pipx or uv tool install)
- Start server on activation, stop on deactivation
- Auto-generate `.vscode/mcp.json` with correct configuration
- Status bar indicator showing server state

### Story 25.2: VS Code Extension - Settings UI

Add a VS Code settings panel for TappsMCP configuration, mapping UI controls to `.tapps-mcp.yaml` settings.

- VS Code `contributes.configuration` for quality preset, engagement level, scoring weights
- Settings changes update `.tapps-mcp.yaml` in the project root
- "Initialize Project" command that runs `tapps_init` equivalent
- "Run Quality Check" command that triggers `tapps_validate_changed`

### Story 25.3: JetBrains Plugin - Server Management

Create a JetBrains IDE plugin (IntelliJ, PyCharm, WebStorm) that manages the TappsMCP server lifecycle with equivalent functionality to the VS Code extension.

- Plugin activation on project open
- Detect and install TappsMCP
- Start/stop server tied to project lifecycle
- Auto-configure MCP settings for JetBrains MCP support
- Tool window showing server status and recent scores

### Story 25.4: Extension Settings and Configuration Sync

Implement bidirectional sync between IDE extension settings and `.tapps-mcp.yaml`, ensuring changes in either location are reflected.

- File watcher on `.tapps-mcp.yaml` to update IDE settings
- IDE settings changes write to `.tapps-mcp.yaml`
- Handle conflicts (IDE setting wins, with notification)
- Support workspace-level and user-level settings

### Story 25.5: Marketplace Publishing Pipeline

Set up automated build and publishing for both marketplaces, integrated with the existing GitHub Actions CI.

- VS Code: `vsce` packaging and marketplace publishing
- JetBrains: Gradle build and marketplace publishing
- Versioning aligned with TappsMCP PyPI releases
- GitHub Actions workflow for automated publishing on release
- Marketplace metadata: description, screenshots, changelog

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Maintenance burden of IDE-specific wrappers | High | Keep extensions thin; all logic in TappsMCP server |
| IDE MCP support is rapidly evolving | High | Target stable APIs only; avoid deprecated extension points |
| Python dependency management from IDE extensions | Medium | Support pipx/uv tool install for isolated installs |
| JetBrains MCP support may lag VS Code | Medium | Start with VS Code; JetBrains as follow-up |
| Extension review process delays publishing | Low | Submit early; iterate on feedback |
| Two separate codebases (TypeScript + Kotlin) | Medium | VS Code first; evaluate JetBrains demand before investing |

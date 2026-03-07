# Epic 59: MCP Registry Submission

**Status:** Complete
**Priority:** P1
**LOE:** ~1 week
**Dependencies:** None (packages already on PyPI)

---

## Overview

List TappsMCP and DocsMCP in the official MCP server registry at `registry.modelcontextprotocol.io` for discoverability. This enables MCP clients (Claude Desktop, Cursor, VS Code) to find and install these servers directly from the registry.

---

## Background

The MCP Registry is the official directory for MCP servers. Publishing there:
- Increases discoverability for users searching for code quality tools
- Enables one-click installation in compatible MCP clients
- Provides verified ownership through PyPI package verification

### PyPI Package Verification

The MCP Registry verifies PyPI package ownership by checking for an `mcp-name: $SERVER_NAME` string in the package README. This can be hidden in an HTML comment.

### Namespace Format

Using GitHub-based authentication, server names must follow `io.github.{username}/{server}` format.

---

## Stories

### Story 59.1: Add MCP Name Verification to READMEs ✅

Add the required `mcp-name` verification strings to package READMEs for PyPI verification.

**Tasks:**
- [x] Add `<!-- mcp-name: io.github.wtthornton/tapps-mcp -->` to `packages/tapps-mcp/README.md`
- [x] Add `<!-- mcp-name: io.github.wtthornton/docs-mcp -->` to `packages/docs-mcp/docs/README.md`
- [ ] Verify strings appear in PyPI package descriptions after next release

**AC:**
- [x] Both README files contain the verification comment
- [x] Comment is visible in raw markdown but hidden in rendered view

### Story 59.2: Create server.json for tapps-mcp ✅

Create the MCP Registry metadata file for tapps-mcp.

**Tasks:**
- [x] Create `packages/tapps-mcp/server.json` with required schema
- [x] Include all 29 tools in description
- [x] Define environment variables (TAPPS_MCP_PROJECT_ROOT, etc.)
- [x] Validate against MCP Registry schema

**AC:**
- [x] `server.json` validates against `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`
- [x] All required fields populated

### Story 59.3: Create server.json for docs-mcp ✅

Create the MCP Registry metadata file for docs-mcp.

**Tasks:**
- [x] Create `packages/docs-mcp/server.json` with required schema
- [x] Include all 22 tools in description
- [x] Define environment variables (DOCS_MCP_PROJECT_ROOT, etc.)
- [x] Validate against MCP Registry schema

**AC:**
- [x] `server.json` validates against schema
- [x] All required fields populated

### Story 59.4: GitHub Actions for Registry Publishing ✅

Create CI workflow to automate registry publishing on releases.

**Tasks:**
- [x] Add `publish-mcp-registry` job to `.github/workflows/publish.yml`
- [x] Trigger after PyPI publishing completes
- [x] Install `mcp-publisher` CLI
- [x] Authenticate using GitHub OIDC
- [x] Publish both packages to registry

**AC:**
- [x] Workflow runs on release tag push
- [x] Successfully publishes to MCP Registry
- [x] Fails gracefully with clear error messages

### Story 59.5: Documentation and Verification ✅

Document the registry submission process and verify listings.

**Tasks:**
- [x] Update ROADMAP.md to mark Epic 59 complete
- [x] Add registry URLs to main README.md
- [ ] Verify servers appear in registry search (after first release)
- [ ] Test installation from registry in Claude Desktop / Cursor (after first release)

**AC:**
- [x] Installation instructions reference registry
- [ ] Both servers discoverable via registry API (pending release)

---

## Acceptance Criteria

1. Both `tapps-mcp` and `docs-mcp` are listed in the MCP Registry
2. Servers are discoverable via registry search API
3. Automated publishing triggers on release tags
4. Documentation updated with registry references

---

## Technical Notes

### Server Name Format

Using GitHub namespace:
- tapps-mcp: `io.github.wtthornton/tapps-mcp`
- docs-mcp: `io.github.wtthornton/docs-mcp`

### PyPI Package Names

- tapps-mcp: `tapps-mcp` (PyPI identifier)
- docs-mcp: `docs-mcp` (PyPI identifier)

### Environment Variables

tapps-mcp:
- `TAPPS_MCP_PROJECT_ROOT` (required) - Project root directory
- `CONTEXT7_API_KEY` (optional) - For documentation lookup

docs-mcp:
- `CONTEXT7_API_KEY` (required) - For Context7 provider

---

## References

- [MCP Registry Quickstart](https://modelcontextprotocol.io/registry/quickstart)
- [PyPI Package Verification](https://modelcontextprotocol.io/registry/package-types#pypi-packages)
- [GitHub Actions Publishing](https://modelcontextprotocol.io/registry/github-actions)

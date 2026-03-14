# MCP Companion Server Ecosystem

## Overview

MCP servers are most effective when composed into curated configurations that
combine complementary capabilities. Each server is registered individually as a
direct stdio entry (e.g., `tapps-mcp`, `docs-mcp`) in MCP client configs.

This guide covers companion server selection, profile composition patterns,
the Context7 dual-role architecture, and enterprise catalog curation.

## Companion Server Selection Criteria

When selecting companion servers for an MCP profile, evaluate along four axes:

1. **Workflow coverage** -- Does the companion fill a gap in the primary server's capabilities?
2. **Data flow** -- Does the companion produce outputs the primary server consumes (or vice versa)?
3. **Redundancy** -- Does the companion overlap with the primary server? (avoid tool bloat)
4. **Trust** -- Is the companion from a verified source (signed images, known maintainer)?

### Anti-pattern: Tool Overload

Adding too many servers to a profile creates "tool soup" -- the LLM sees hundreds
of tools and struggles to pick the right one. Aim for **3-5 servers per profile**
with distinct, non-overlapping capabilities.

## Recommended Companions for Code Quality

### TappsMCP + DocsMCP Core

| Server | Tools | Why |
|--------|-------|-----|
| **TappsMCP** | 28 | Code quality: scoring, gates, security, experts, memory |
| **DocsMCP** | 18 | Documentation: extraction, generation, validation, drift |

These two are the foundation. TappsMCP handles code quality; DocsMCP handles
documentation quality. Together they cover the full quality lifecycle.

### Tier 1: Essential Companions

| Server | Docker Catalog | Complementary Value |
|--------|---------------|---------------------|
| **Context7** | `mcp/context7` | Real-time library documentation lookup. Ensures agents use current APIs, not stale training data. |
| **GitHub** | `mcp/github` | PR/issue/discussion management. Agents can create PRs with quality reports, manage issues, run checks. |

### Tier 2: Recommended Companions

| Server | Docker Catalog | Complementary Value |
|--------|---------------|---------------------|
| **Filesystem** | `mcp/filesystem` | Secure sandboxed file access. Complements TappsMCP's path-validated scoring with general file operations. |
| **Sequential Thinking** | `mcp/sequentialthinking` | Structured reasoning. Breaks complex decisions into steps before calling `tapps_consult_expert`. |

### Tier 3: Situational Companions

| Server | Docker Catalog | When to Include |
|--------|---------------|-----------------|
| **Playwright** | `mcp/playwright` | Web app projects needing browser-based testing or link validation |
| **Postgres/SQLite** | `mcp/postgres` | Database-heavy projects needing schema analysis |
| **E2B** | community | Projects needing sandboxed code execution for testing |

## Profile Composition Patterns

### Tiered Profiles

Offer users three tiers matching their workflow complexity:

```
tapps-minimal:
  - tapps-mcp                    # Code quality only (28 tools)
  Total: 28 tools

tapps-standard:
  - tapps-mcp                    # Code quality (28 tools)
  - docs-mcp                     # Documentation (18 tools)
  - context7                     # Library docs (3 tools)
  Total: 49 tools

tapps-full:
  - tapps-mcp                    # Code quality (28 tools)
  - docs-mcp                     # Documentation (18 tools)
  - context7                     # Library docs (3 tools)
  - github                       # PR/issue management (~15 tools)
  - filesystem                   # File operations (~5 tools)
  Total: ~69 tools
```

### Example Configuration

```json
{
  "mcpServers": {
    "tapps-mcp": {
      "type": "stdio",
      "command": "tapps-mcp",
      "args": ["serve"],
      "env": { "TAPPS_MCP_PROJECT_ROOT": "." }
    },
    "docs-mcp": {
      "type": "stdio",
      "command": "docsmcp",
      "args": ["serve"],
      "env": { "DOCS_MCP_PROJECT_ROOT": "." }
    }
  }
}
```

## Context7: Dual-Role Architecture

Context7 plays two distinct roles in the TappsMCP ecosystem:

### Role 1: Library API (Inside TappsMCP)

TappsMCP uses Context7 as a **library API** via `CONTEXT7_API_KEY`:

```
tapps_lookup_docs("react", "hooks")
  → Context7 API → cached docs → formatted response

tapps_research("How to use React useEffect?")
  → Expert consultation + Context7 API → combined answer
```

This is the **internal** usage -- Context7 feeds TappsMCP's toolchain directly.
Configured via environment variable, no separate MCP server needed.

### Role 2: MCP Server (Companion)

The **Context7 MCP server** (`mcp/context7`) is a separate, standalone server
that gives the AI client **direct** access to library documentation:

```
User: "Look up the latest FastAPI middleware docs"
  → AI client calls Context7 MCP directly (not via TappsMCP)
  → Returns current docs
```

This is the **external** usage -- the client calls Context7 for ad-hoc queries
that don't need TappsMCP's quality pipeline.

### Why Include Both

| Scenario | Which Context7 | Why |
|----------|---------------|-----|
| `tapps_lookup_docs("react")` | API (internal) | Integrated into scoring/expert workflow |
| "Show me React 19 migration guide" | MCP (companion) | Direct client query, no quality context needed |
| `tapps_research("best caching pattern for FastAPI")` | API (internal) | Expert + docs combined response |
| "What changed in Pydantic v2.10?" | MCP (companion) | Ad-hoc lookup, not quality-related |

**Recommendation**: Always include Context7 MCP in companion profiles AND keep
the API integration. They serve different use cases with zero overlap.

## Enterprise Catalog Curation

Organizations can build private catalogs that bundle approved servers:

### Custom Catalog Structure

```yaml
# company-catalog.yaml
servers:
  tapps-mcp:
    name: tapps-mcp
    description: "Code quality (28 tools)"
    image: company-registry.azurecr.io/mcp/tapps-mcp:1.0.0
    transport: stdio
  docs-mcp:
    name: docs-mcp
    description: "Documentation (18 tools)"
    image: company-registry.azurecr.io/mcp/docs-mcp:1.0.0
    transport: stdio
  context7:
    name: context7
    description: "Library documentation"
    image: mcp/context7:latest  # use official catalog image
    transport: stdio
```

### Benefits of Custom Catalogs

- **Version pinning**: Lock to specific image tags, not `latest`
- **Approval workflow**: Only pre-approved servers in the catalog
- **Private registry**: Host images in your own ACR/ECR/GHCR
- **Mix sources**: Combine official catalog images with internal servers
- **Audit trail**: Track which teams use which server versions

### Lifecycle Integration

`tapps_init` detects the catalog source and generates appropriate configs:

```yaml
# .tapps-mcp.yaml
docker:
  enabled: true
  transport: docker
  profile: tapps-standard
  catalog: company-registry.azurecr.io/catalogs/approved:latest
  companions: [context7, github]
```

`tapps_doctor` validates that all servers in the profile are available and
that the catalog is reachable:

```
Docker checks:
  [PASS] Docker daemon: 27.4.1
  [PASS] MCP Toolkit: docker-mcp v0.3.2
  [PASS] tapps-mcp image: company-registry/mcp/tapps-mcp:1.0.0
  [PASS] docs-mcp image: company-registry/mcp/docs-mcp:1.0.0
  [PASS] context7: mcp/context7:latest
  [WARN] github: Not in profile (recommended)
  [PASS] Gateway: 49 tools via tapps-standard
```

## Best Practices

1. **Start with tapps-standard** -- covers 90% of developer needs
2. **Add companions incrementally** -- use `docker mcp profile server add`
3. **Pin versions in enterprise** -- use semver tags, not `latest`
4. **Share profiles via OCI** -- `docker mcp profile push` for team consistency
5. **Configure secrets locally** -- never embed API keys in profiles or catalogs
6. **Monitor tool count** -- stay under 80 tools per profile to avoid LLM confusion
7. **Test profiles end-to-end** -- verify gateway routes to all servers after changes
8. **Use `tapps_doctor`** -- validates the full stack including companions

## Anti-Patterns

- **Including every available MCP server** -- tool overload degrades LLM performance
- **Sharing profiles with embedded secrets** -- security risk; use Docker Desktop secret management
- **Using `latest` tag in enterprise** -- unpredictable updates; pin to semver
- **Mixing Docker and non-Docker servers** -- confusing config; pick one transport per project
- **Skipping Context7 companion** -- lose ad-hoc doc queries outside TappsMCP pipeline
- **Not running `tapps_doctor`** -- Docker config drift goes undetected

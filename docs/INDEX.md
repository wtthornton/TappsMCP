# TappsMCP Documentation Index

## Getting Started

| Document | Description |
|---|---|
| [README](../README.md) | Project overview, installation, tools reference |
| [Onboarding Guide](ONBOARDING.md) | Setup for consumers and developers |
| [Contributing Guide](../CONTRIBUTING.md) | Code standards, testing, PR workflow |
| [Migration Guide](MIGRATION_FROM_TAPPS_AGENTS.md) | Migrating from TappsCodingAgents |

## API Reference

| Document | Description |
|---|---|
| [tapps-core API](api/tapps-core-api.md) | Shared infrastructure library (config, security, scoring, experts, memory) |
| [tapps-mcp Core Tools](api/tapps-mcp-core-tools.md) | Server info, security scan, docs lookup, config validation, experts |
| [tapps-mcp Scoring Tools](api/tapps-mcp-scoring_tools.md) | `tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check` |
| [tapps-mcp Pipeline Tools](api/tapps-mcp-pipeline_tools.md) | `tapps_validate_changed`, `tapps_session_start`, `tapps_init`, `tapps_upgrade` |
| [tapps-mcp Metrics Tools](api/tapps-mcp-metrics_tools.md) | `tapps_dashboard`, `tapps_stats`, `tapps_feedback`, `tapps_research` |
| [tapps-mcp Memory Tools](api/tapps-mcp-memory_tools.md) | `tapps_memory` (11 actions) |
| [tapps-mcp Analysis Tools](api/tapps-mcp-analysis_tools.md) | Session notes, impact analysis, reports, dead code, dependencies |
| [tapps-mcp Expert Tools](api/tapps-mcp-expert_tools.md) | `tapps_manage_experts` (5 actions) |
| [docs-mcp API](api/docs-mcp-api.md) | Documentation MCP server (19 tools) |

## Architecture

| Document | Description |
|---|---|
| [Module Map](MODULE_MAP.md) | Full module hierarchy across all packages |
| [Architecture: Cache & RAG](ARCHITECTURE_CACHE_AND_RAG.md) | Caching and RAG subsystem design |
| [MCP Composition](MCP_COMPOSITION.md) | How TappsMCP and DocsMCP compose |
| [Composition Guide](COMPOSITION_GUIDE.md) | Using the combined platform server |
| [CTX Pattern Reference](CTX_PATTERN_REFERENCE.md) | MCP context progress notification patterns |

## Diagrams

| Diagram | Description |
|---|---|
| [tapps-core Dependencies](diagrams/tapps-core-dependency.md) | Dependency graph for tapps-core |
| [tapps-core Module Map](diagrams/tapps-core-module_map.md) | Module structure diagram |
| [tapps-mcp Dependencies](diagrams/tapps-mcp-dependency.md) | Dependency graph for tapps-mcp |
| [tapps-mcp Module Map](diagrams/tapps-mcp-module_map.md) | Module structure diagram |
| [docs-mcp Dependencies](diagrams/docs-mcp-dependency.md) | Dependency graph for docs-mcp |
| [docs-mcp Module Map](diagrams/docs-mcp-module_map.md) | Module structure diagram |
| [Class Hierarchy](diagrams/class-hierarchy.md) | Project-wide class hierarchy |

## Operations

| Document | Description |
|---|---|
| [Setup & Usage](TAPPS_MCP_SETUP_AND_USE.md) | Detailed setup instructions |
| [Docker Deployment](DOCKER_DEPLOYMENT.md) | Docker MCP Toolkit deployment |
| [MCP Client Timeouts](MCP_CLIENT_TIMEOUTS.md) | Timeout configuration for MCP clients |
| [Upgrade for Consumers](UPGRADE_FOR_CONSUMERS.md) | Upgrading TappsMCP in consuming projects |
| [Init & Upgrade Features](INIT_AND_UPGRADE_FEATURE_LIST.md) | Complete feature list for init/upgrade |
| [Claude Full Access Setup](CLAUDE_FULL_ACCESS_SETUP.md) | Claude Code integration setup |
| [CI Integration](ci-integration.md) | CI/CD pipeline integration |
| [Validate Changed Loop](TAPPS_VALIDATE_CHANGED_LOOP_AND_TIMING.md) | Validation timing details |

# TappsMCP Diagrams

Auto-generated from source by `docs-mcp`. All diagrams render natively on GitHub.

To regenerate: see [Regeneration](#regeneration) at the bottom.

| File | Type | Generator |
|---|---|---|
| [01-c4-context.md](01-c4-context.md) | C4 System Context | `docs_generate_diagram(diagram_type="c4_context")` |
| [02-c4-container.md](02-c4-container.md) | C4 Container | `docs_generate_diagram(diagram_type="c4_container")` |
| [03-module-map.md](03-module-map.md) | Module map (top-level) | `docs_generate_diagram(diagram_type="module_map")` |
| [04-pattern-card.md](04-pattern-card.md) | Architectural archetype | `docs_generate_diagram(diagram_type="pattern_card")` |
| [05-c4-component-tapps-mcp.md](05-c4-component-tapps-mcp.md) | C4 Component (tapps-mcp) | `docs_generate_diagram(diagram_type="c4_component", scope="packages/tapps-mcp/src/tapps_mcp")` |
| [06-c4-component-docs-mcp.md](06-c4-component-docs-mcp.md) | C4 Component (docs-mcp) | `docs_generate_diagram(diagram_type="c4_component", scope="packages/docs-mcp/src/docs_mcp")` |
| [07-er-output-schemas.md](07-er-output-schemas.md) | ER diagram (output schemas) | `docs_generate_diagram(diagram_type="er_diagram", scope=".../common/output_schemas.py")` |
| [08-sequence-quality-pipeline.md](08-sequence-quality-pipeline.md) | Quality pipeline sequence | `docs_generate_diagram(diagram_type="sequence", flow_spec=...)` |
| [interactive.html](interactive.html) | Pan/zoom HTML | `docs_generate_interactive_diagrams(...)` |

## At a glance

### System context

```mermaid
C4Context
    title System Context — TappsMCP

    Person(User, "AI Agent", "Claude Code / Cursor / VS Code Copilot")
    Person(Dev, "Developer", "Editing code, asking the agent for help")

    System(tapps_mcp, "TappsMCP", "Deterministic code quality MCP server (32 tools)")
    System_Ext(docs_mcp, "DocsMCP", "Documentation MCP server (38 tools)")
    System_Ext(brain, "tapps-brain", "Postgres-backed cross-session memory service")
    System_Ext(ctx7, "Context7", "Live library docs API")

    Rel(User, tapps_mcp, "Scores files, runs gates, looks up docs")
    Rel(User, docs_mcp, "Generates / validates docs")
    Rel(Dev, User, "Prompts")
    Rel(tapps_mcp, brain, "Memory read/write (HTTP)")
    Rel(tapps_mcp, ctx7, "Library docs lookup")
    Rel(docs_mcp, brain, "Architecture insights")
```

### Container view

```mermaid
C4Container
    title Container diagram — tapps-mcp monorepo

    Person(Agent, "AI Agent", "MCP client")

    System_Boundary(monorepo, "tapps-mcp monorepo") {
        Container(tapps_mcp, "tapps-mcp", "Python / FastMCP", "32 tools — scoring, gates, security, lookup, memory")
        Container(docs_mcp, "docs-mcp", "Python / FastMCP", "38 tools — generation + validation")
        Container(tapps_core, "tapps-core", "Python library", "Shared infra: config, security, logging, knowledge, metrics, adaptive")
    }

    System_Ext(brain, "tapps-brain", "Dockerized Postgres @ :8080")
    System_Ext(ctx7, "Context7", "External docs API")

    Rel(Agent, tapps_mcp, "stdio MCP")
    Rel(Agent, docs_mcp, "stdio MCP")
    Rel(tapps_mcp, tapps_core, "imports")
    Rel(docs_mcp, tapps_core, "imports")
    Rel(tapps_mcp, brain, "BrainBridge HTTP")
    Rel(docs_mcp, brain, "BrainBridge HTTP")
    Rel(tapps_core, ctx7, "knowledge.context7_client")
```

## Quality pipeline flow

```mermaid
sequenceDiagram
    title TAPPS Quality Pipeline

    actor Agent
    participant SS as tapps_session_start
    participant LD as tapps_lookup_docs
    participant QC as tapps_quick_check
    participant VC as tapps_validate_changed
    participant CL as tapps_checklist
    participant M as tapps_memory

    Agent->>SS: bootstrap context (first call)
    SS-->>Agent: server info + memory status + cache health
    Agent->>LD: library docs (Context7-backed)
    LD-->>Agent: current API surface
    Note over Agent: Edit Python file
    Agent->>QC: after every edit
    QC-->>Agent: score + gate + basic security
    Agent->>VC: before declaring complete
    VC-->>Agent: per-file pass/fail
    Agent->>CL: final verification
    CL-->>Agent: missing-required hints
    Agent->>M: save architectural / pattern learnings
    M-->>Agent: persisted (cross-session)
```

## Regeneration

```bash
# Full report (HTML, embedded SVGs)
docs_generate_architecture(output_path="docs/ARCHITECTURE.html", motion="subtle")

# Interactive (Mermaid.js with pan/zoom)
docs_generate_interactive_diagrams(
    diagram_types="dependency,module_map,c4_component,c4_container,c4_context,er_diagram",
    output_path="docs/diagrams/interactive.html",
    motion="subtle",
)

# Standalone diagrams — see the per-file headers for the exact call.
```

Pin diagram regeneration to: every minor version bump, every refactor of `server*.py`, every package add/remove.

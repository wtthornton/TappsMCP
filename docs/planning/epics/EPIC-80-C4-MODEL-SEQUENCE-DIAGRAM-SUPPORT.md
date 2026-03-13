# Epic 80: C4 Model & Sequence Diagram Support

<!-- docsmcp:start:metadata -->
**Status:** Complete (all stories including 80.4 Sequence Diagrams)
**Priority:** P1 - High
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 6 (Diagram Generation)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that DocsMCP produces architecture diagrams that match the 2026 industry standard -- the C4 model -- and sequence diagrams that visualize request flows and workflow orchestration. Without these two diagram types, DocsMCP cannot compete with documentation produced by teams using Structurizr, PlantUML, or manual diagramming tools.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP generates C4 model diagrams (System Context, Container, Component, Code) and sequence diagrams in both Mermaid and PlantUML formats, closing the two most critical diagram gaps identified in the 2026 documentation best practices audit.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The C4 model is the industry standard for architecture visualization in 2026, adopted by enterprise and startup teams alike. Sequence diagrams are essential for documenting request flows, API interactions, and workflow orchestration. Without these, DocsMCP cannot produce documentation that matches Stripe/Vercel/Cloudflare quality standards. TheStudio's architecture docs use numbered Internal Flow sections that are essentially text sequence diagrams -- proving demand exists.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] C4 System Context diagrams generated from project scan data showing external actors and system boundaries
- [ ] C4 Container diagrams generated from module map showing high-level tech building blocks
- [ ] C4 Component diagrams generated from dependency analysis showing internal components per container
- [ ] Sequence diagrams generated from call graph analysis or user-provided flow definitions
- [ ] All new diagram types available in both Mermaid and PlantUML formats
- [ ] docs_generate_diagram accepts diagram_type values c4_context, c4_container, c4_component, and sequence
- [ ] Existing 4 diagram types (dependency, class_hierarchy, module_map, er_diagram) unchanged
- [ ] Unit tests cover all new diagram types with node_count and edge_count validation
- [ ] DiagramGenerator.VALID_TYPES updated to include new types

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [80.1](EPIC-80/story-80.1-c4-system-context-diagram-generator.md) -- C4 System Context Diagram Generator

**Points:** 5

Add c4_context diagram type that generates a top-level view showing the system as a central box with external actors and neighboring systems around it.

**Tasks:**
- [ ] Add c4_context to DiagramGenerator.VALID_TYPES
- [ ] Implement _generate_c4_context_mermaid() using Mermaid C4 syntax
- [ ] Implement _generate_c4_context_plantuml() using PlantUML C4 macros
- [ ] Extract external system boundaries from project scan
- [ ] Add tests for c4_context with both formats

**Definition of Done:** C4 System Context Diagram Generator is implemented, tests pass, and documentation is updated.

---

### [80.2](EPIC-80/story-80.2-c4-container-diagram-generator.md) -- C4 Container Diagram Generator

**Points:** 5

Add c4_container diagram type showing high-level technology building blocks. Map Python packages to containers, detect infrastructure from docker-compose/config.

**Tasks:**
- [ ] Implement _generate_c4_container_mermaid()
- [ ] Implement _generate_c4_container_plantuml()
- [ ] Detect containers from docker-compose.yml and package structure
- [ ] Map inter-container relationships from import graphs
- [ ] Add tests with multi-package project fixtures

**Definition of Done:** C4 Container Diagram Generator is implemented, tests pass, and documentation is updated.

---

### [80.3](EPIC-80/story-80.3-c4-component-diagram-generator.md) -- C4 Component Diagram Generator

**Points:** 5

Add c4_component diagram type showing internal components within a selected container using existing module_map and dependency analyzers.

**Tasks:**
- [ ] Implement _generate_c4_component_mermaid()
- [ ] Implement _generate_c4_component_plantuml()
- [ ] Accept container_name parameter to scope to a specific package
- [ ] Reuse existing ModuleMap and ImportGraph analyzers
- [ ] Add tests with scoped and unscoped component diagrams

**Definition of Done:** C4 Component Diagram Generator is implemented, tests pass, and documentation is updated.

---

### [80.4](EPIC-80/story-80.4-sequence-diagram-generator.md) -- Sequence Diagram Generator

**Points:** 8

Add sequence diagram type for visualizing request flows and API call chains. Support auto-generated from call graphs and user-provided flow definitions via JSON spec.

**Tasks:**
- [ ] Implement _generate_sequence_mermaid()
- [ ] Implement _generate_sequence_plantuml()
- [ ] Add auto-detection mode from entry points and call chains
- [ ] Add manual mode accepting flow_spec JSON parameter
- [ ] Support activation bars, notes, alt/loop/opt blocks
- [ ] Handle async flows with different arrow styles
- [ ] Add tests for both auto and manual modes

**Definition of Done:** Sequence Diagram Generator is implemented, tests pass, and documentation is updated.

---

### [80.5](EPIC-80/story-80.5-integration-and-documentation.md) -- Integration and Documentation

**Points:** 3

Wire new diagram types into docs_generate_diagram MCP tool, update AGENTS.md templates, add documentation.

**Tasks:**
- [ ] Update docs_generate_diagram tool handler
- [ ] Update AGENTS.md template with C4 and sequence references
- [ ] Update docs/README.md with examples
- [ ] Add integration tests
- [ ] Update VALID_TYPES constant and error messages

**Definition of Done:** Integration and Documentation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Mermaid has native C4 support via C4Context/C4Container/C4Component blocks (added in Mermaid v10)
- PlantUML C4 support requires the C4-PlantUML stdlib macros (`!include C4_Context.puml`)
- Sequence diagrams are natively supported by both Mermaid and PlantUML with mature syntax
- Auto-generated sequence diagrams should limit call depth to 2-3 to avoid explosion
- The existing DiagramGenerator follows a clean dispatch pattern making new types straightforward
- `_MAX_DEPENDENCY_NODES` and similar constants need C4-specific equivalents

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Structurizr DSL output format (separate epic)
- Interactive/clickable diagram rendering (Epic 81)
- C4 Code-level diagrams (too granular for auto-generation)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Diagram types | 4 | 8 | DiagramGenerator.VALID_TYPES count |
| C4 adoption | 0% | 50% | projects using C4 diagrams in 90 days |
| Sequence usage | 0 | 30 | monthly sequence diagram generations |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 80.1: C4 System Context Diagram Generator
2. Story 80.2: C4 Container Diagram Generator
3. Story 80.3: C4 Component Diagram Generator
4. Story 80.4: Sequence Diagram Generator
5. Story 80.5: Integration and Documentation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Auto-generated sequence diagrams from call graphs may produce noisy results | Medium | Medium | Depth limits (2-3 levels) and entry-point scoping |
| C4 container detection from docker-compose is heuristic | High | Medium | Fallback to package-level containers; manual hints via parameter |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/generators/diagrams.py` | 80.1-80.4 | Add C4 and sequence generation methods |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | 80.5 | Update tool handler for new types |
| `packages/docs-mcp/src/docs_mcp/analyzers/dependency.py` | 80.3 | Extend for component extraction |
| `packages/docs-mcp/src/docs_mcp/analyzers/module_map.py` | 80.2 | Extend for container detection |

<!-- docsmcp:end:files-affected -->

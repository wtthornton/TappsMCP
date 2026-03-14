# Epic 81: D2 Diagram Format & Interactive HTML Diagrams

<!-- docsmcp:start:metadata -->
**Status:** Complete (all stories: 81.1 D2 existing types, 81.2 D2 C4+sequence, 81.3 Interactive HTML, 81.4 D2 themes)
**Priority:** P1 - High
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 6, Epic 80

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that DocsMCP's diagram output matches the aesthetic and interactive standards of 2026's best documentation sites. D2 produces superior layouts for complex architectures, and interactive HTML diagrams eliminate the friction of static images that cannot be explored.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP supports D2 as a third diagram output format alongside Mermaid and PlantUML, and the docs_generate_architecture HTML report embeds interactive clickable/zoomable diagrams via Mermaid.js instead of static SVGs.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

D2 produces significantly better layout and aesthetics than Mermaid for complex architecture diagrams using the TALA layout engine. In 2026, D2 is the fastest-growing docs-as-code diagram tool. Meanwhile, interactive diagrams (click to zoom, pan, expand) are the 2026 standard seen on Stripe and Vercel. Adding both transforms DocsMCP from functional to best-in-class.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] D2 format added to DiagramGenerator.VALID_FORMATS
- [x] All 8 diagram types generate valid D2 output
- [x] docs_generate_diagram accepts format=d2
- [x] D2 output uses idiomatic syntax with shapes/connections/containers
- [x] docs_generate_architecture embeds Mermaid.js for interactive rendering
- [x] Interactive diagrams support click-to-zoom and pan
- [x] Architecture report includes diagram toggle controls
- [x] Unit tests validate D2 output for all types
- [x] D2 includes theme support (default and sketch modes)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [81.1](EPIC-81/story-81.1-d2-output-format-existing-types.md) -- D2 Output Format for Existing Diagram Types

**Points:** 8

Add D2 as a third output format for existing 4 diagram types using D2 shape, connection, container, and label primitives.

**Tasks:**
- [x] Add d2 to DiagramGenerator.VALID_FORMATS
- [x] Implement _generate_dependency_d2()
- [x] Implement _generate_class_hierarchy_d2()
- [x] Implement _generate_module_map_d2() with containers
- [x] Implement _generate_er_diagram_d2() with sql_table shapes
- [x] Add D2 theme support (default, sketch, terminal)
- [x] Add tests for all 4 types in D2 format

**Definition of Done:** D2 Output Format for Existing Diagram Types is implemented, tests pass, and documentation is updated.

---

### [81.2](EPIC-81/story-81.2-d2-output-c4-sequence.md) -- D2 Output for C4 and Sequence Diagrams

**Points:** 5

Extend D2 support to C4 and sequence diagram types from Epic 80.

**Tasks:**
- [x] Implement C4 context/container/component in D2
- [x] Implement sequence diagrams in D2
- [x] Add tests for all new types in D2 format

**Definition of Done:** D2 Output for C4 and Sequence Diagrams is implemented, tests pass, and documentation is updated.

---

### [81.3](EPIC-81/story-81.3-interactive-mermaidjs-architecture.md) -- Interactive Mermaid.js in Architecture Reports

**Points:** 8

Replace static SVGs in docs_generate_architecture HTML with interactive Mermaid.js rendering with pan/zoom controls.

**Tasks:**
- [x] Embed Mermaid.js in architecture HTML template
- [x] Replace static SVGs with mermaid code blocks
- [x] Add pan/zoom wrapper using SVG panZoom library
- [x] Add diagram toggle controls (show/hide per section)
- [x] Add diagram table of contents with anchor links
- [x] Ensure self-contained HTML (all JS/CSS inlined)
- [x] Add print-friendly CSS for static rendering
- [x] Add tests for interactive HTML output

**Definition of Done:** Interactive Mermaid.js in Architecture Reports is implemented, tests pass, and documentation is updated.

---

### [81.4](EPIC-81/story-81.4-d2-theme-style-system.md) -- D2 Theme and Style System

**Points:** 3

Configurable theming for D2 output including color schemes, sketch mode, and terminal mode.

**Tasks:**
- [x] Add theme parameter to DiagramGenerator.generate()
- [x] Implement D2 theme blocks (vars, style) for each theme
- [x] Support sketch mode via D2's `sketch: true` directive
- [x] Add theme parameter to docs_generate_diagram MCP tool
- [x] Add tests for themed output

**Definition of Done:** D2 Theme and Style System is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- D2 syntax is cleaner than Mermaid for complex diagrams -- uses shape declarations and arrow connections with labels
- D2 supports nested containers natively which maps perfectly to C4 model boundaries
- Mermaid.js ESM bundle can be inlined (~800KB) or loaded via CDN for smaller files
- SVG panZoom is a lightweight library (~15KB) that can be inlined for zero-dependency interactive diagrams
- DocsMCP generates D2 source text only -- users render with `d2` CLI or online tools
- The `architecture.py` generator already produces self-contained HTML -- extending it with JS is architecturally clean

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- D2 rendering/compilation (DocsMCP generates source text only)
- Excalidraw or tldraw format output
- Real-time collaborative diagram editing

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Diagram formats | 2 | 3 | DiagramGenerator.VALID_FORMATS count |
| Interactive reports | 0% | 100% | architecture reports with Mermaid.js |
| D2 adoption | 0% | 30% | projects choosing D2 over Mermaid |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 81.1: D2 Output Format for Existing Diagram Types
2. Story 81.2: D2 Output for C4 and Sequence Diagrams
3. Story 81.3: Interactive Mermaid.js in Architecture Reports
4. Story 81.4: D2 Theme and Style System

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| D2 syntax evolves faster than Mermaid | Medium | Medium | Pin to stable syntax subset; version-lock D2 features used |
| Inlining Mermaid.js increases HTML file size (~800KB) | Medium | Medium | Lazy loading + optional CDN mode parameter |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/generators/diagrams.py` | 81.1, 81.2, 81.4 | Add D2 format methods and theme system |
| `packages/docs-mcp/src/docs_mcp/generators/architecture.py` | 81.3 | Embed Mermaid.js interactive rendering |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | 81.1, 81.4 | Update tool handler for d2 format and theme param |

<!-- docsmcp:end:files-affected -->

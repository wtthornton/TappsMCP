# Epic 85: Purpose/Intent Architecture Templates & Doc Index Generation

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2 - Medium
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 8 (ADR and Guides), Epic 80 (C4 Diagrams)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that any project can bootstrap a TheStudio-quality architecture documentation suite with a single tool call -- interconnected, numbered, consistently structured documents that create a navigable documentation web maintained via smart merge.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP adds a Purpose/Intent architecture document template (inspired by TheStudio's pattern), a numbered documentation index generator, and a structured architecture document series generator -- enabling projects to create interconnected, navigable architecture documentation suites with consistent structure.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

TheStudio's architecture documentation uses a Purpose/Intent/Flow/Diagram template across 25+ numbered files that creates a navigable documentation web. This pattern scored A in content organization in the 2026 audit. No documentation tool auto-generates this kind of structured architecture series. Adding this to DocsMCP enables any project to bootstrap a TheStudio-quality architecture documentation suite with a single tool call, then maintain it with smart merge.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] New `docs_generate_architecture_doc` tool creates single architecture documents following Purpose/Intent template
- [ ] Template sections: Purpose, Intent, Plane Placement, Key Inputs/Outputs, Internal Flow, Diagram, Admin/API Integration
- [ ] New `docs_generate_doc_index` tool creates a numbered reading-order index with cross-references
- [ ] Index auto-detects document ordering from filenames or explicit sequence
- [ ] `docs_generate_architecture_doc` supports `auto_populate` to enrich from code analysis
- [ ] Smart merge markers on all sections for regeneration without losing human edits
- [ ] Numbered file naming convention support (`00-overview.md` through `NN-topic.md`)
- [ ] Cross-reference validation integrated into `docs_check_links`
- [ ] Unit tests cover template generation and index building

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [85.1](EPIC-85/story-85.1-purpose-intent-architecture-doc.md) -- Purpose/Intent Architecture Document Generator

**Points:** 8

New `docs_generate_architecture_doc` tool creating individual architecture documents following the Purpose/Intent/Flow/Diagram template. Each document describes one component or subsystem with consistent structure.

**Tasks:**
- [ ] Create `generators/architecture_doc.py` with `ArchitectureDocGenerator` class
- [ ] Implement template with sections: Purpose, Intent, Plane Placement, Key Inputs/Outputs, Internal Flow, Diagram placeholder, Integration Points
- [ ] Support `auto_populate` from module_map and dependency analysis
- [ ] Support `component_name` parameter to scope to a specific module/package
- [ ] Generate Internal Flow as numbered steps from call graph analysis
- [ ] Add diagram placeholder with inline Mermaid sequence diagram
- [ ] Add smart merge markers on all sections
- [ ] Register `docs_generate_architecture_doc` in `server_gen_tools.py`
- [ ] Add tests for single-component and multi-component docs

**Definition of Done:** Purpose/Intent Architecture Document Generator is implemented, tests pass, and documentation is updated.

---

### [85.2](EPIC-85/story-85.2-documentation-index-generator.md) -- Documentation Index Generator

**Points:** 5

New `docs_generate_doc_index` tool creating a master index document with numbered reading order, cross-references, and navigation links.

**Tasks:**
- [ ] Create `generators/doc_index.py` with `DocIndexGenerator` class
- [ ] Auto-detect document ordering from filename numbering (`00-`, `01-`, etc.)
- [ ] Support explicit ordering via JSON sequence parameter
- [ ] Generate index with: title, one-line description, cross-references per doc
- [ ] Include documentation map diagram (Mermaid graph of doc relationships)
- [ ] Support flat and grouped index styles
- [ ] Register `docs_generate_doc_index` in `server_gen_tools.py`
- [ ] Add tests for auto-detect and explicit ordering

**Definition of Done:** Documentation Index Generator is implemented, tests pass, and documentation is updated.

---

### [85.3](EPIC-85/story-85.3-architecture-series-bootstrap.md) -- Architecture Series Bootstrap

**Points:** 5

New `docs_generate_architecture_series` tool that analyzes a project and generates a complete numbered architecture document set with index, similar to TheStudio's 00-26 series.

**Tasks:**
- [ ] Create `generators/architecture_series.py` with `ArchitectureSeriesGenerator` class
- [ ] Analyze project to identify key components (packages, services, APIs, data stores)
- [ ] Generate numbered doc set: `00-overview`, `01-N` per component, standards block, extensions
- [ ] Generate master index linking all documents
- [ ] Support custom numbering groups (core `00-09`, domain `10-19`, standards `20-29`)
- [ ] Add cross-references between related documents
- [ ] Add tests for series generation with varying project sizes

**Definition of Done:** Architecture Series Bootstrap is implemented, tests pass, and documentation is updated.

---

### [85.4](EPIC-85/story-85.4-cross-reference-validation.md) -- Cross-Reference Validation

**Points:** 3

Extend `docs_check_links` to validate cross-references between architecture documents (e.g., `See 08-agent-roles.md` patterns).

**Tasks:**
- [ ] Add cross-reference pattern detection (`See filename.md`, `filename.md` references)
- [ ] Validate referenced files exist
- [ ] Report broken cross-references in link check results
- [ ] Add tests for cross-reference validation

**Definition of Done:** Cross-Reference Validation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- TheStudio's template has 7 sections but not all apply to every component -- generate applicable sections based on component type
- Numbered file naming uses zero-padded prefixes (`00-` through `99-`) for sort stability
- Cross-references use filename-only format (no relative paths) for portability
- Internal Flow generation reuses sequence diagram logic from Epic 80
- Smart merge markers enable regeneration without losing human edits to Intent/Purpose sections
- "Plane Placement" section is optional -- only generated when project defines agent/platform separation

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Wiki engine or static site generation
- Persona document generation (separate concern)
- Real-time document synchronization

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Architecture doc adoption | 0 | 10 | projects using purpose/intent template |
| Series generation | 0 | 5 | architecture series bootstrapped |
| Cross-ref accuracy | N/A | 95% | validated cross-references |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 85.1: Purpose/Intent Architecture Document Generator
2. Story 85.2: Documentation Index Generator
3. Story 85.3: Architecture Series Bootstrap
4. Story 85.4: Cross-Reference Validation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Auto-generated docs miss domain-specific components | High | Low | Manual override + `auto_populate` enrichment from code analysis |
| Large projects generate too many documents | Medium | Medium | Component count limits + configurable grouping |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/generators/architecture_doc.py` | 85.1 | New file: ArchitectureDocGenerator |
| `packages/docs-mcp/src/docs_mcp/generators/doc_index.py` | 85.2 | New file: DocIndexGenerator |
| `packages/docs-mcp/src/docs_mcp/generators/architecture_series.py` | 85.3 | New file: ArchitectureSeriesGenerator |
| `packages/docs-mcp/src/docs_mcp/validators/link_checker.py` | 85.4 | Extend cross-reference detection |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | 85.1-85.3 | Register 3 new tools |

<!-- docsmcp:end:files-affected -->

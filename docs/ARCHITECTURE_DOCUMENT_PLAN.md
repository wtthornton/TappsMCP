# Architecture Document Enhancement Plan

> **Goal:** Transform the generated Architecture Report into a professional, developer-focused document that explains business intent, design rationale, and architectural defenses—targeting humans, not agents.

**Reference:** [TappMCP Style Guide](STYLE_GUIDE.md) | [HomeIQ Style Guide](../HomeIQ/docs/STYLE_GUIDE.md)  
**Current generator:** `packages/docs-mcp/src/docs_mcp/generators/architecture.py`

---

## 1. Vision

The Architecture Report must serve **developers and architects** who need to:

- **Understand why** the system is built this way
- **See how** components fit together and interact
- **Justify decisions** (backup defenses) when proposing changes or reviewing designs
- **Navigate** a data-rich, visually clear document quickly

**Not for:** LLMs or agents consuming structured data. Use MCP tools, API docs, or JSON exports for that.

---

## 2. Style Guide Compliance

### 2.1 Apply TappMCP Style Guide

| Task | Source | Action |
|------|--------|--------|
| Import `docs/STYLE_GUIDE.md` tokens | New TappMCP style guide | Replace hardcoded values in `architecture.py` `_CSS` with variables from style guide |
| Color palette | STYLE_GUIDE § Color System | Ensure diagram palette, status colors, and CSS variables match |
| Typography | STYLE_GUIDE § Typography | Use `.hero-title`, `.section-title`, `.stat-label`, `.metric-value` conventions |
| Spacing & radius | STYLE_GUIDE § Spacing | Use `--radius-*`, section padding values |
| Components | STYLE_GUIDE § Components | Purpose blocks, stat cards, diagram containers per spec |

### 2.2 Light Theme Option

- Add `prefers-color-scheme: light` override or optional `?theme=light` query param
- Use light-theme tokens from HomeIQ (adapted): `--bg-primary: #f8f9fc`, `--accent-primary: #0d9488`

---

## 3. Business & Intent for All Features

### 3.1 Document-Level Intent

Add an explicit **"Document Purpose"** block after the hero:

- Who this is for (developers, architects, technical leads)
- What questions it answers (architecture, dependencies, API surface)
- How to use it (TOC, sections, print)

### 3.2 Per-Section Business Intent

Each major section must include a **"Why this matters"** / **"Business intent"** paragraph:

| Section | Intent |
|---------|--------|
| **Executive Summary** | Quick overview for stakeholders; key metrics for risk assessment |
| **Architecture Diagram** | Visual anchoring—understand boundaries before diving in |
| **Data Flow Pipeline** | Understand runtime behavior and processing order |
| **Component Deep-Dive** | Rationale for each package; why it exists, what problem it solves |
| **Dependency Flow** | Coupling analysis, change impact, refactoring safety |
| **Public API Surface** | Contract for consumers; breaking-change awareness |
| **Technology Stack** | Setup, supply-chain risk, upgrade planning |
| **Architecture Health** | Maturity signals, hotspots, technical debt visibility |

### 3.3 Per-Feature / Per-Package Intent

For each **package/component**:

- **Business purpose:** What problem does this package solve?
- **Design rationale:** Why is it structured this way?
- **Backup defense:** What architectural principle or constraint justifies this design? (e.g., "Single Responsibility", "Dependency Inversion", "Minimal coupling to external tools")

**Source:** `__init__.py` or top-level module docstrings; fallback to README or `pyproject.toml` description.

**Generator change:** Extend `_generate_component_value()` (and `_node_to_package_info`) to:
- Prefer `docstring` from package/module
- Append a structured "Design rationale" line when available
- Add "Key responsibilities" bullets from docstrings

---

## 4. How, Why, and Backup Defenses

### 4.1 "How" Content

- **Flow diagrams:** Show processing order, data paths
- **Dependency graph:** Show import relationships with arrow direction
- **Sequence snippets:** Optional Mermaid or text-based sequence for critical flows (e.g., "MCP request → tool dispatch → scorer → response")

### 4.2 "Why" Content

- **Decisions block:** Add optional section "Architectural Decisions" linking to ADRs or summarizing key choices (e.g., "Why MCP? Deterministic tools, no LLM in tool chain")
- **Trade-offs:** For large packages, note trade-offs (e.g., "tapps_mcp is large; trade-off: single deployable vs. finer modularity")

### 4.3 "Backup Defenses"

- **Principles applied:** List principles used (e.g., "All file I/O through PathValidator", "No LLM calls in tool chain")
- **Constraints:** Security sandbox, path validation, checker allowlists
- **Risks & mitigations:** For hotspots (e.g., "tapps_mcp has 29 modules → mitigation: clear module boundaries, checklist for refactors")

**Implementation:** New section "Architectural Principles & Constraints" populated from:
- Config or convention (e.g., `.tappsmcp-architecture.yaml`)
- Heuristics (e.g., "PathValidator usage" if security module present)
- Static text template for common patterns

---

## 5. Professional Full HTML: Data, Graphs, Detail

### 5.1 New Sections to Add

| Section | Content |
|---------|---------|
| **Table of Contents** | Sticky/collapsible nav; links to all section IDs; omit empty |
| **Document Purpose** | Audience, use cases, how to read |
| **Key Metrics Dashboard** | Expand stats: packages, modules, classes, APIs, deps; add trend if git history available |
| **Architecture Diagram** | (existing; ensure SVG is rich) |
| **Data Flow Pipeline** | (fix empty case; add fallback layout) |
| **Component Deep-Dive** | (existing; enrich with business intent) |
| **Dependency Flow** | (fix monorepo; show edges or "none detected" message) |
| **Public API Surface** | (existing; optionally group by package) |
| **Technology Stack** | (fix workspace metadata; show runtime + dev deps) |
| **Architectural Principles** | New; principles, constraints, risks |
| **Architecture Health** | (existing; clarify labels) |
| **Appendix: Module Index** | Optional; sortable table of modules with paths, LOC if available |
| **Appendix: Glossary** | Terms: package, module, API surface, coupling, etc. |
| **Footer** | Generation timestamp, DocsMCP version, Back to top |

### 5.2 Data Enrichment

| Data Point | Source | Notes |
|------------|--------|------|
| Project description | `pyproject.toml` (root + workspace) | Use for Purpose & Intent |
| Package descriptions | `packages/*/pyproject.toml`, `__init__.py` | Component business intent |
| Dependencies | Aggregate from workspace packages | Tech stack section |
| Import edges | ImportGraphBuilder (monorepo fix) | Dependency flow |
| Layer grouping | Improve heuristic + fallback | Data flow diagram |
| ADR links | `docs/decisions/` or config | Architectural decisions |
| LOC / complexity | Optional: radon, pygount | Appendix metrics |

### 5.3 Graph Improvements

| Graph | Enhancement |
|-------|-------------|
| Architecture overview | Add package count badges; ensure responsive SVG |
| Data flow | Fallback when 1 layer: horizontal package flow |
| Dependency flow | Show edges; "No edges" message when empty |
| Architecture health | Add simple bar/indicator for modularity, coupling |
| Optional | Package size (module count) bar chart; dependency treemap |

### 5.4 Accessibility

- Skip link
- ARIA landmarks
- SVG `<title>`, `<desc>`, `<figcaption>`
- Light theme support

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Style & Structure)

| # | Task | Effort | Owner |
|---|------|--------|-------|
| 1 | Refactor `_CSS` to use TappMCP style guide variables | S | Generator |
| 2 | Add skip link, TOC, back-to-top | S | Generator |
| 3 | Add Document Purpose block | S | Generator |

### Phase 2: Content Completeness

| # | Task | Effort | Owner |
|---|------|--------|-------|
| 4 | Use metadata `description` for Purpose & Intent | S | Metadata + Generator |
| 5 | Fix Data Flow: layer heuristic + single-layer fallback | M | Generator |
| 6 | Fix Dependency Flow: monorepo `_path_to_package` | M | Analyzer + Generator |
| 7 | Aggregate dependencies from workspace packages | M | Metadata |

### Phase 3: Business & Intent

| # | Task | Effort | Owner |
|---|------|--------|-------|
| 8 | Per-section "Why this matters" paragraphs | M | Generator |
| 9 | Per-package business intent from docstrings | M | Generator |
| 10 | "Architectural Principles & Constraints" section | M | Generator + optional config |

### Phase 4: Professional Polish

| # | Task | Effort | Owner |
|---|------|--------|-------|
| 11 | SVG accessibility (title, figcaption) | S | Generator |
| 12 | Light theme option | S | Generator |
| 13 | Appendix: Module index (optional) | M | Generator |
| 14 | Stat label clarifications (Public APIs, External Deps) | S | Generator |

### Phase 5: Optional Enhancements

| # | Task | Effort | Owner |
|---|------|--------|-------|
| 15 | ADR integration | M | Config + Generator |
| 16 | LOC / complexity metrics | L | New analyzer |
| 17 | Bar chart for package sizes | M | Generator (inline SVG or Chart.js) |

---

## 7. File Changes Summary

| File | Changes |
|------|---------|
| `docs/STYLE_GUIDE.md` | **Created** — TappMCP style guide |
| `docs/ARCHITECTURE_DOCUMENT_PLAN.md` | **Created** — this plan |
| `packages/docs-mcp/src/docs_mcp/generators/architecture.py` | Major: sections, style, intent, diagrams |
| `packages/docs-mcp/src/docs_mcp/generators/metadata.py` | Workspace aggregation, description from root |
| `packages/docs-mcp/src/docs_mcp/analyzers/dependency.py` | Monorepo path handling |
| `packages/docs-mcp/src/docs_mcp/analyzers/module_map.py` | Package docstring extraction |

---

## 8. Success Criteria

- [ ] Document follows TappMCP style guide
- [ ] Every section has explicit business intent
- [ ] Every component has purpose + rationale where docstrings exist
- [ ] No empty sections without explanation
- [ ] TOC, skip link, back-to-top
- [ ] SVGs accessible
- [ ] Data flow and dependency flow populated (or explicitly "none detected")
- [ ] Tech stack populated from workspace
- [ ] Print-friendly
- [ ] Reader can answer: "Why is this designed this way?" and "What are the constraints?"

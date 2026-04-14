# Epic 100: Architecture Pattern Recognition & Poster Diagrams

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Priority:** P1 - High
**Estimated LOE:** ~7-9 weeks (1 developer) — revised after stub audit

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that consumers of docs-mcp get at-a-glance, publication-quality architecture visuals that name the pattern their codebase follows — not just raw import graphs. The current output is accurate but dense; the goal is to make architecture diagrams feel like the Amigoscode pattern poster: one page, one insight, zero scrolling.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Extend docs-mcp's diagram and architecture generators to classify a project into a known architectural archetype (layered, hexagonal, monolith, microservice, event-driven, pipeline) and render compact, semantic-colored "poster" diagrams alongside the existing deep reports.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today `docs_generate_architecture` emits a long HTML scroll and `docs_generate_diagram` produces renderer-specific code with ad-hoc coloring and no legend. Users asked for output closer to reference infographics: labeled pattern, semantic colors (presentation/business/data/infra), legend, and a single-page overview. Naming the shape is more valuable than drawing every edge.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] docs-mcp exposes a pattern classifier that returns one of six archetypes with confidence
- [ ] Each archetype renders its **canonical topology** (layered = stacked bands, event-driven = bus + publishers/subscribers, hexagonal = domain ring, microservice = isolated service boxes, monolith = single container, pipeline = LR stages)
- [ ] Each topology animates data flow using CSS `@keyframes` / SVG `<animateMotion>` with no JS runtime dependency
- [ ] `pattern_comparison` diagram type renders all six archetypes in a 2×3 animated grid
- [x] Semantic role-based color palette applied consistently across all diagram types
- [x] All SVG and Mermaid output includes a legend block
- [ ] Architecture HTML hero surfaces detected archetype name, confidence badge, and animated single-panel topology
- [ ] `prefers-reduced-motion` disables all animations
- [ ] Small projects (< 15 packages) get the poster variant by default
- [ ] Existing diagram/architecture tests continue to pass with zero regressions

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 100.1 -- Architecture pattern classifier

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement architecture pattern classifier
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Architecture pattern classifier is implemented, tests pass, and documentation is updated.

---

### 100.2 -- Semantic role palette across diagram renderers

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement semantic role palette across diagram renderers
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Semantic role palette across diagram renderers is implemented, tests pass, and documentation is updated.

---

### 100.3 -- Poster / pattern_card diagram type

**Points:** 5

> ⚠️ **Stub shipped** — `_render_pattern_card_mermaid` was implemented but outputs a generic
> linear chain (`header → p0 → p1 → p2`) with no pattern topology. A LAYERED project and a
> MICROSERVICE project produce identical shapes — just different node labels. Stories 100.8–100.11
> replace this with correct topology rendering and animation.

**Tasks:**
- [x] Implement poster / pattern_card diagram type
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Poster / pattern_card diagram type is implemented, tests pass, and documentation is updated.

---

### 100.4 -- Legend blocks for SVG and Mermaid output

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement legend blocks for svg and mermaid output
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Legend blocks for SVG and Mermaid output is implemented, tests pass, and documentation is updated.

---

### 100.5 -- Hero-section archetype label in architecture HTML

**Points:** 2

> ⚠️ **Stub shipped** — `_render_hero` in `architecture.py` was never wired to `PatternClassifier`.
> It still renders only project name + "Architecture Report". No archetype label, no badge, no
> confidence score. Story 100.11 completes this properly.

**Tasks:**
- [x] Implement hero-section archetype label in architecture html
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Hero-section archetype label in architecture HTML is implemented, tests pass, and documentation is updated.

---

### 100.6 -- Auto-select poster variant for small projects

**Points:** 2 | **Status:** ✅ Done

When `diagram_type="dependency"` and `output_format` is `"mermaid"` or `"html"`, projects with
fewer than `_POSTER_AUTO_THRESHOLD = 15` top-level packages are silently redirected to the
`pattern_card` poster, which is more readable at that scale.

**Tasks:**
- [x] Implement auto-select poster variant for small projects
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Auto-select poster variant for small projects is implemented, tests pass, and documentation is updated.

---

### 100.7 -- ADR cross-link from detected pattern

**Points:** 3 | **Status:** ✅ Done

`_find_adr_for_archetype(project_root, archetype)` searches `docs/adr/`, `docs/decisions/`,
`adr/`, and `.docs/adr/` for a Markdown file mentioning the detected archetype keyword.
When found, the relative path is included as `adr_link` in `DiagramResult`, as a
`%% ADR:` comment in Mermaid output, and as a `<p class="adr-link">` note in HTML output.

**Tasks:**
- [x] Implement adr cross-link from detected pattern
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** ADR cross-link from detected pattern is implemented, tests pass, and documentation is updated.

---

### 100.8 -- ArchPatternPosterGenerator: per-archetype topology SVG

**Points:** 8

Build `generators/pattern_poster.py` — a new `ArchPatternPosterGenerator` class that renders each
of the six archetypes using its **correct canonical topology shape**, not a generic node chain.
Each archetype gets its own SVG layout method:

| Archetype | Topology |
|---|---|
| `layered` | Full-width horizontal bands stacked top-to-bottom, packages assigned to bands by semantic role |
| `event_driven` | Central `EventBus` node, publishers column on left connected to bus, subscribers column on right |
| `hexagonal` | Domain hexagon in center, adapter/port nodes arranged as an outer ring |
| `microservice` | Each service as its own isolated `subgraph`-style box with a DB cylinder beneath |
| `monolith` | Single large container box with all module nodes packed inside |
| `pipeline` | Left-to-right stages (LR flow) with labelled arrow connectors |

Output format is self-contained HTML with inline SVG (same model as `docs_generate_architecture`).
Mermaid is kept as a static fallback for README embedding — it does not need topology awareness.

**Tasks:**
- [ ] Create `generators/pattern_poster.py` with `ArchPatternPosterGenerator`
- [ ] Implement `_render_layered`, `_render_event_driven`, `_render_hexagonal`, `_render_microservice`, `_render_monolith`, `_render_pipeline` SVG layout methods
- [ ] Wire archetype dispatch: `PatternClassifier.classify()` → correct layout method
- [ ] Assign project packages to topology slots by semantic role (reuse `_classify_role`)
- [ ] Write unit tests for each layout method (snapshot + node-count assertions)
- [ ] Update documentation

**Definition of Done:** `docs_generate_diagram(type="pattern_card", output_format="html")` produces
an HTML file where each archetype is rendered with its correct structural topology, not a linear
chain. Snapshot tests confirm distinct shapes per archetype. Mermaid fallback unchanged.

---

### 100.9 -- CSS @keyframes data-flow animations for all six archetypes

**Points:** 8

Add animated data-flow overlays to each topology SVG produced by `ArchPatternPosterGenerator`.
Animations show canonical data movement for that pattern — they must loop, be smooth, and be
meaningful (not decorative noise):

| Archetype | Animation |
|---|---|
| `layered` | Dot packets flowing downward through band boundaries, one per second |
| `event_driven` | Event pulse travelling from publisher → bus → subscriber with fade |
| `hexagonal` | Request arcs entering adapters, crossing to domain core, exiting through other adapters |
| `microservice` | Animated HTTP arrows bouncing between service boxes with latency labels |
| `monolith` | Internal call pulse rippling outward from a random module node |
| `pipeline` | Token sliding left-to-right through stages, pausing at each stage briefly |

Implementation uses CSS `@keyframes` + SVG `<animateMotion>` or `<animate>` — no JS runtime
dependency. Animations must respect `prefers-reduced-motion` with a `@media` override that
disables motion.

**Tasks:**
- [ ] Design `@keyframes` and `<animateMotion>` path for each archetype's data-flow
- [ ] Add `prefers-reduced-motion` media query override (static fallback)
- [ ] Ensure animations loop cleanly with no visual jump at loop boundary
- [ ] Write visual regression tests (rendered SVG element presence; timing attributes)
- [ ] Update documentation

**Definition of Done:** All six archetype panels animate data flow. Motion is disabled when
`prefers-reduced-motion: reduce` is set. No JS required at runtime.

---

### 100.10 -- Multi-pattern comparison grid (`pattern_comparison` diagram type)

**Points:** 5

Add a new `diagram_type="pattern_comparison"` that renders all six archetypes simultaneously in a
**2×3 grid** — the actual Amigoscode poster shape. This is the "comparison" view; `pattern_card`
remains the single-detected-archetype view.

Layout spec:
- Dark background (`#0a0a0f`)
- Bold title banner: **SOFTWARE ARCHITECTURAL PATTERNS** in white at the top
- 2 columns × 3 rows of equal-size panels, each panel = one archetype from story 100.8/100.9
- Each panel: archetype name as header, animated topology SVG below
- Responsive: panels reflow to 1-column on narrow viewports
- Output: self-contained HTML file (linked from README, not inline)

The detected archetype for the current project is highlighted with a colored border/badge.

**Tasks:**
- [ ] Add `"pattern_comparison"` to `DiagramGenerator.VALID_TYPES`
- [ ] Implement `_generate_pattern_comparison` handler
- [ ] Render 2×3 grid using flex/grid CSS layout with dark background
- [ ] Highlight detected archetype panel
- [ ] Add `docs_generate_diagram(type="pattern_comparison")` integration test
- [ ] Update AGENTS.md and README tool table
- [ ] Write unit tests

**Definition of Done:** `docs_generate_diagram(type="pattern_comparison")` writes a self-contained
HTML file with all six animated archetype panels in a 2×3 grid. Detected archetype is highlighted.

---

### 100.11 -- Wire animated poster into architecture HTML hero (complete 100.5)

**Points:** 3

Replace the stub `_render_hero` in `architecture.py` with a real implementation that:
1. Calls `PatternClassifier().classify(project_root, ...)` using the already-built `module_map` and `dep_graph` (no extra analysis cost)
2. Renders a `<span class="arch-badge">LAYERED · 87%</span>` pill in the hero section, styled with the semantic role color for the archetype's primary layer
3. Embeds the single-panel animated SVG for the detected archetype (from story 100.8/100.9) directly below the project title — replacing the static "Architecture Report" label
4. Falls back gracefully (no badge, no animation) when classification confidence < 0.5

**Tasks:**
- [ ] Add `PatternClassifier` call inside `ArchitectureGenerator.generate()`, passing existing `module_map` and `dep_graph`
- [ ] Pass `archetype_result` into `_render_hero`
- [ ] Render arch-badge pill with correct color and confidence percentage
- [ ] Embed single-panel animated SVG from `ArchPatternPosterGenerator` in hero
- [ ] Add fallback for low-confidence classification
- [ ] Write unit tests for badge rendering and fallback path
- [ ] Update documentation

**Definition of Done:** `docs_generate_architecture` HTML hero shows the detected archetype name,
confidence %, semantic color badge, and an animated topology SVG for the detected pattern. Low
confidence (< 0.5) renders no badge. Existing tests pass.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Classifier already ships (story 100.1) — stories 100.8–100.11 consume its output, they don't change it
- `ArchPatternPosterGenerator` lives in `generators/pattern_poster.py`; `DiagramGenerator` dispatches to it for `type="pattern_card"` with `output_format="html"`
- Mermaid `pattern_card` stays as a static README fallback — do not animate it (Mermaid can't)
- SVG animation: prefer `<animateMotion>` + `<mpath>` for path-following dots; `<animate>` for opacity/color pulses
- Animation paths must be embedded as `<path>` elements in `<defs>` and referenced by `xlink:href` for reuse
- `prefers-reduced-motion: reduce` override is non-negotiable — add it as a test assertion
- Poster SVG budget: < 50 nodes per panel; < 1 screen height per panel
- `pattern_comparison` grid: each panel is a fixed 280×200px SVG cell inside a CSS grid
- Architecture hero: call `PatternClassifier` once and pass result down — do not run analysis twice
- Reuse `_classify_role` and `_ROLE_COLORS` from `diagrams.py` (do not copy)

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Not replacing existing detailed diagrams
- Not adding a GUI editor
- Not auto-generating ADRs (only linking)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Time-to-understand new codebase reduced by 40% in internal eval | - | - | - |
| Poster diagram fits in a README without scrolling for projects up to 15 packages | - | - | - |
| 80%+ classifier accuracy on internal reference projects | - | - | - |
| Zero regressions in existing diagram tests | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| docs-mcp maintainers | - | - |
| TappsMCP consumers | - | - |
| Documentation reviewers | - | - |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- packages/docs-mcp/src/docs_mcp/generators/diagrams.py
- packages/docs-mcp/src/docs_mcp/generators/architecture.py
- https://blog.amigoscode.com/p/software-architectural-patterns-you

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 100.1: Architecture pattern classifier ✅
2. Story 100.2: Semantic role palette across diagram renderers ✅
3. Story 100.3: Poster / pattern_card diagram type ✅ (stub — superseded by 100.8)
4. Story 100.4: Legend blocks for SVG and Mermaid output ✅
5. Story 100.5: Hero-section archetype label in architecture HTML ✅ (stub — superseded by 100.11)
6. Story 100.8: ArchPatternPosterGenerator — per-archetype topology SVG
7. Story 100.9: CSS @keyframes data-flow animations for all six archetypes
8. Story 100.10: Multi-pattern comparison grid (pattern_comparison diagram type)
9. Story 100.11: Wire animated poster into architecture HTML hero (complete 100.5)
10. Story 100.6: Auto-select poster variant for small projects
11. Story 100.7: ADR cross-link from detected pattern

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Classifier heuristics may mislabel hybrid architectures | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| SVG hand-rolling adds maintenance burden vs. delegating to mermaid | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Palette opinions may conflict with consumer brand styles | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->

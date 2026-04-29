# Motion in docs-mcp graphs

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Estimated LOE:** ~1 week (1 developer) across 3 stories

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that generated diagrams visually convey direction-of-flow the way modern infographics do — animated dots/dashes traveling along edges — instead of forcing readers to mentally trace static arrows. Today's docs-mcp output (Mermaid in the interactive HTML viewer, hand-built SVG in the architecture report and pattern_poster) is fully static, which makes dependency, pipeline, and sequence diagrams less legible than equivalent reference graphics from LinkedIn-style backend-architecture roadmaps.</purpose_and_intent>
<parameter name="goal">Add an opt-in motion layer to docs-mcp diagram output, delivered in three phases: (1) CSS marching-ants on Mermaid edges in the interactive HTML viewer, (2) native SVG animateMotion on hand-built dependency-flow / pipeline / layered panels in the architecture report and pattern_poster, (3) optional JS particle layer for high-fidelity motion. Ship as a per-tool `motion` argument with safe defaults: `subtle` for the interactive viewer, `off` for the printable architecture report. Honor `prefers-reduced-motion` everywhere; keep determinism (no randomness in animation params).

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Describe how **Motion in docs-mcp graphs** will change the system. What measurable outcome proves this epic is complete?

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Static diagrams under-communicate flow. The interactive HTML viewer already supports 7 Mermaid diagram types but renders them as still images; the architecture report's dependency-flow SVG and pattern_poster's pipeline/layered panels emit hand-built `<line>` edges with no motion cue. A small CSS / SVG addition matches the visual idiom users see in modern reference docs at near-zero runtime cost, while preserving print/PDF output and accessibility.</motivation>
<parameter name="acceptance_criteria">A `motion` argument is exposed on docs_generate_interactive_diagrams (default `subtle`) and docs_generate_architecture (default `off`) with values `off` / `subtle` / `particles`, All animation is gated by `@media (prefers-reduced-motion: no-preference)` and disabled inside `@media print`, Motion is applied only on flow-direction-meaningful diagram types (dependency / module_map / sequence / c4_container; pipeline / layered / dependency-flow panels) and never on relationship-only types (class_hierarchy / er_diagram / c4_context / hexagonal / monolith), Animation parameters are fixed constants — no Date.now() / Math.random() seeds — so output remains deterministic, Unit tests assert presence/absence of animation markup per motion value and per diagram type, All three phases land as separate stories so phase 1 can ship independently of phase 2 and 3

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Define verifiable criteria for **Motion in docs-mcp graphs**...
- [ ] All stories completed and passing tests
- [ ] Documentation updated

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 0.1 -- Phase 1 — CSS marching-ants on Mermaid edges in interactive HTML viewer

**Points:** 2

Add motion arg to docs_generate_interactive_diagrams and emit conditional CSS that animates stroke-dashoffset on Mermaid edge paths.

**Tasks:**
- [ ] Implement phase 1 — css marching-ants on mermaid edges in interactive html viewer
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Phase 1 — CSS marching-ants on Mermaid edges in interactive HTML viewer is implemented, tests pass, and documentation is updated.

---

### 0.2 -- Phase 2 — SVG animateMotion on hand-built dependency / pipeline / layered SVG panels

**Points:** 3

Convert hand-built line edges to path id=... and append circle with animateMotion+mpath on the flow-meaningful panels in architecture.py and pattern_poster.py.

**Tasks:**
- [ ] Implement phase 2 — svg animatemotion on hand-built dependency / pipeline / layered svg panels
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Phase 2 — SVG animateMotion on hand-built dependency / pipeline / layered SVG panels is implemented, tests pass, and documentation is updated.

---

### 0.3 -- Phase 3 — Opt-in JS particle layer for motion=particles

**Points:** 5

Post-Mermaid render walks svg .edgePath path, calls getTotalLength()/getPointAtLength() on a requestAnimationFrame loop to spawn N=3 particles per edge.

**Tasks:**
- [ ] Implement phase 3 — opt-in js particle layer for motion=particles
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Phase 3 — Opt-in JS particle layer for motion=particles is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Motion in docs-mcp graphs**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Animating relationship-only diagram types (class_hierarchy
- er_diagram
- c4_context
- hexagonal pattern
- monolith pattern)
- Adding animation to PlantUML or D2 PNG exports (rasterized — no motion possible)
- Changing the default behavior of the printable architecture report (must stay still by default for PDF use)
- Introducing non-deterministic animation seeds (would break TappsMCP's deterministic-tools rule)
- Adding a third-party animation library — all motion must be plain CSS / SVG / vanilla JS</non_goals>
<parameter name="priority">P3 - Normal

<!-- docsmcp:end:non-goals -->

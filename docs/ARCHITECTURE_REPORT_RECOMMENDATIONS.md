# Architecture Report (docs_generate_architecture) — Evaluation & Recommendations

**Evaluated:** `docs/ARCHITECTURE.html` generated for TappMCP  
**Date:** 2026-03-09

---

## Executive Summary

The `docs_generate_architecture` tool produces a polished, self-contained HTML report with embedded SVG diagrams, HomeIQ design system styling, and strong visual hierarchy. The evaluation identifies gaps in content completeness, accessibility, and generator logic that should be addressed to improve usability and accuracy.

---

## 1. Content Completeness

### 1.1 Generic Purpose Statement
**Current:** "Purpose & Intent" shows "A software project."  
**Cause:** Project description from `pyproject.toml` / metadata not used when subtitle is empty.  
**Recommendation:** Ensure metadata extractor pulls the project `description` from root `pyproject.toml` (and workspace `pyproject.toml`) and uses it as the default purpose text. Fallback to "A software project." only when no description exists.

### 1.2 Empty Data Flow Pipeline Section
**Current:** Section header and intro exist, but the diagram container is empty.  
**Cause:** `_group_into_layers` heuristic groups packages by keywords (config, server, cli, etc.). For TappMCP, all three packages (docs_mcp, tapps_core, tapps_mcp) match "Core Logic" only, so `len(layers) == 1` and `_build_flow_pipeline_svg` returns empty.  
**Recommendation:** 
- Add fallback: when all packages land in one layer, split into logical groups (e.g., by dependency direction: leaf packages first, then dependents).
- Alternatively, when `len(layers) < 2`, show a simplified horizontal flow of packages instead of omitting the diagram.

### 1.3 Missing Dependency Flow Section
**Current:** Dependency Flow section is absent.  
**Cause:** `dep_edges` is empty (edge_count: 0). `ImportGraphBuilder` may not map cross-package imports correctly in a `packages/*/src/*` monorepo layout.  
**Recommendation:**
- Audit `ImportGraphBuilder` and `_path_to_package` for monorepo paths like `packages/docs-mcp/src/docs_mcp/...`.
- Improve package-name extraction from paths that include `docs_mcp`, `tapps_core`, `tapps_mcp`.
- When edges are empty, optionally show a "No cross-package dependencies detected" message with a note that the analyzer may need monorepo-aware path handling.

### 1.4 Missing Technology Stack Section
**Current:** Technology Stack section is absent.  
**Cause:** `metadata.dependencies` and `metadata.dev_dependencies` are empty. The metadata extractor likely reads a single `pyproject.toml`; in a uv workspace, dependencies live in `packages/*/pyproject.toml`.  
**Recommendation:** Extend metadata extraction to aggregate dependencies from workspace member packages (e.g., `packages/tapps-mcp`, `packages/docs-mcp`, `packages/tapps-core`) and merge runtime vs. dev dependency lists.

---

## 2. Accessibility

### 2.1 Skip Link
**Recommendation:** Add a "Skip to main content" link at the top for keyboard/screen-reader users.

### 2.2 ARIA Landmarks
**Current:** Sections use `<section>` but lack `role` and `aria-label`.  
**Recommendation:** Add `role="region"` and `aria-labelledby` (or `aria-label`) to each section for clearer landmark navigation.

### 2.3 SVG Accessibility
**Current:** SVGs have no `<title>` or `<desc>` for screen readers.  
**Recommendation:** Wrap each diagram SVG in a `<figure>` with `<figcaption>` and add `<title>` inside the SVG:
```html
<figure role="figure" aria-labelledby="arch-diagram-caption">
  <svg><title id="arch-diagram-title">High-level architecture diagram showing docs_mcp, tapps_core, tapps_mcp</title>...</svg>
  <figcaption id="arch-diagram-caption">High-level architecture overview</figcaption>
</figure>
```

### 2.4 Color Contrast
**Current:** Design uses dark theme with teal/gold accents.  
**Recommendation:** Verify WCAG AA contrast for `--text-secondary`, `--text-muted`, and accent colors on dark backgrounds. Consider a `prefers-color-scheme: light` media query for users who prefer light mode.

---

## 3. Navigation & Structure

### 3.1 Table of Contents
**Current:** Long report with no TOC.  
**Recommendation:** Add a sticky or collapsible table of contents after the hero, linking to section IDs (executive-summary, architecture-diagram, data-flow, component-details, api-surface, tech-stack, health-insights). Omit empty sections from the TOC.

### 3.2 Back-to-Top
**Recommendation:** Add a "Back to top" link or button in the footer for long reports.

---

## 4. Accuracy & Clarification

### 4.1 "Public APIs" Stat
**Current:** Shows 2221 (from `module_map.public_api_count`).  
**Interpretation:** Likely total public functions/methods, not just classes.  
**Recommendation:** Clarify the label: e.g., "Public APIs (functions + methods)" or split into "Public Functions" and "Public Classes" if both are available.

### 4.2 "External Deps"
**Current:** Shows 3657.  
**Interpretation:** Likely total external import statements (transitive), not direct `pyproject.toml` dependencies.  
**Recommendation:** Clarify: "External Import Count" or "Unique External Imports". Consider adding a separate "Direct Dependencies" stat from metadata.

### 4.3 API Density
**Current:** "96.2% API Density" — computed as `cls_count / mod_count * 100`.  
**Interpretation:** Classes per module, expressed as a percentage.  
**Recommendation:** Rename to "Class Coverage" or "Classes per Module (avg)" to avoid confusion with "API completeness."

### 4.4 Component Descriptions
**Current:** Boilerplate text ("This component adds value by encapsulating domain-specific logic...") appended to every component.  
**Recommendation:** Use package/module docstrings from `__init__.py` or top-level docstrings more prominently. Omit or shorten the generic closing sentence when a specific description exists.

---

## 5. Offline & Performance

### 5.1 Google Fonts
**Current:** Fonts loaded from `fonts.googleapis.com` and `fonts.gstatic.com`.  
**Recommendation:** 
- Add `font-display: swap` (if not already) to reduce layout shift.
- Consider optional embedded font subset for fully offline use (e.g., via `@font-face` with base64 or local files in a "standalone" mode).

### 5.2 Reduce Layout Shift
**Recommendation:** Reserve space for diagrams (min-height) or use `aspect-ratio` so content doesn't jump when SVG loads.

---

## 6. Print & Export

### 6.1 Print Styles
**Current:** Print media query switches to white background and black text.  
**Recommendation:** 
- Ensure diagrams (SVG) print with sufficient contrast.
- Add page-break hints before major sections to avoid awkward cuts.
- Include report generation timestamp and project name in a print-only header/footer.

---

## 7. Generator Code Improvements

| Area | Recommendation |
|------|----------------|
| **Metadata** | Aggregate dependencies from all workspace `pyproject.toml` files. |
| **Layer heuristic** | Extend `_group_into_layers` keywords to recognize `mcp`, `docs` (documentation layer), `core` (infrastructure). Add fallback for single-layer case. |
| **Import graph** | Validate `_path_to_package` against monorepo paths; add tests for `packages/*/src/<pkg>/*` layout. |
| **Empty sections** | When a section has no content (e.g., Data Flow, Dependency Flow, Tech Stack), either omit it or show a brief "No data" message with guidance. |
| **Purpose** | Pass `metadata.description` as default `proj_subtitle` in `_render_executive_summary`. |

---

## 8. Priority Matrix

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | Fix empty Data Flow diagram (layer heuristic) | Medium | High |
| P0 | Use project description for Purpose | Low | High |
| P1 | Dependency flow for monorepos | Medium | High |
| P1 | Tech stack from workspace packages | Medium | Medium |
| P2 | Table of contents | Low | Medium |
| P2 | SVG accessibility (title/figcaption) | Low | Medium |
| P3 | Stat label clarifications | Low | Low |
| P3 | Print improvements | Low | Low |

---

## Conclusion

The architecture report is visually strong and well-structured. Addressing content completeness (purpose, Data Flow, Dependency Flow, Tech Stack), accessibility (ARIA, SVG titles), and metadata extraction for monorepos will significantly improve its usefulness. The recommended priority order focuses on high-impact, moderate-effort fixes first.

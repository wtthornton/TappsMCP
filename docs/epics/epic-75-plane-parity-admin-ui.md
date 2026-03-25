# Epic 75: Plane-Parity Admin UI — Interactive Richness & Polish

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 4 (Admin UI Core), Epic 53 (Admin UI Canonical Compliance), Epic 52 (Frontend UI Modernization)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that TheStudio's admin interface evolves from an operational monitoring dashboard into an interactive work-management experience on par with modern tools like Plane.so. The current UI has strong structural bones (dark sidebar, card layout, accessibility) but lacks the interactive richness — detail panels, kanban views, command palette, proper icons, dark mode — that makes a tool feel production-grade and delightful to use daily.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Close the visual and interactive gap between TheStudio's admin UI and Plane.so by adding a sliding detail panel, SVG icon system, kanban/board views, command palette, and dark mode — transforming the admin from a read-only dashboard into an interactive work management surface.

**Tech Stack:** TappMCP

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The admin UI was designed to mirror Plane's clean, modern aesthetic. While the structural foundation is solid (dark sidebar, semantic badges, accessible markup, HTMX-driven updates), user-facing interactivity lags behind. Users cannot click into detail views, drag work items, search via keyboard, or toggle dark mode. These gaps make the UI feel like a monitoring tool rather than the command center it was meant to be. Closing this gap is critical for daily usability and for demonstrating TheStudio as a credible platform product.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Clicking any row/card in repos or workflows opens a right-side sliding detail panel with full item details
- [ ] All navigation and UI icons use SVG (Heroicons/Lucide) instead of Unicode symbols
- [ ] Workflows page has a toggleable kanban board view with drag-and-drop column reordering
- [ ] Ctrl+K opens a command palette with fuzzy search across pages and actions and repos
- [ ] Dark mode toggle works across all pages with consistent theming using CSS custom properties
- [ ] All new components pass WCAG 2.2 AA accessibility checks
- [ ] HTMX integration preserved — no full-page reloads introduced
- [ ] Existing Playwright test suite continues to pass

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 75.1 -- SVG Icon System — Replace Unicode with Heroicons

**Points:** 3

Replace all Unicode symbol icons (▶ ★ ⚙ ☠ etc.) in sidebar nav and throughout templates with inline SVG Heroicons. Create a reusable Jinja2 icon macro.

(5 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create icon macro in components/icon.html with SVG sprite references', 'file_path': 'src/admin/templates/components/icon.html'}
- [ ] {'description': 'Replace all Unicode nav icons in base.html sidebar with SVG icons', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Replace Unicode icons in dashboard cards and badges', 'file_path': 'src/admin/templates/partials/dashboard_content.html'}
- [ ] {'description': 'Update status_badge.html to use SVG icons where appropriate', 'file_path': 'src/admin/templates/components/status_badge.html'}
- ... and 1 more

**Definition of Done:** SVG Icon System — Replace Unicode with Heroicons is implemented, tests pass, and documentation is updated.

---

### 75.2 -- Right-Side Sliding Detail Panel Infrastructure

**Points:** 5

Build a reusable sliding panel component that opens from the right edge when a row or card is clicked. Panel should support dynamic content loading via HTMX, keyboard dismiss (Escape), click-outside dismiss, and smooth CSS transitions.

(6 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create detail_panel.html component with slide-in/out CSS transitions', 'file_path': 'src/admin/templates/components/detail_panel.html'}
- [ ] {'description': 'Add panel trigger JS and HTMX integration to base.html', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Create panel API endpoint pattern in admin routes', 'file_path': 'src/admin/routes.py'}
- [ ] {'description': 'Add keyboard handling (Escape to close, Tab trap within panel)', 'file_path': 'src/admin/templates/base.html'}
- ... and 1 more

**Definition of Done:** Right-Side Sliding Detail Panel Infrastructure is implemented, tests pass, and documentation is updated.

---

### 75.3 -- Repo Detail Panel — Click-to-Inspect Repos

**Points:** 3

Wire the repos table rows to open the sliding detail panel showing full repo information: config, recent activity, queue status, trust tier history, and quick actions.

(4 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create repo detail partial template', 'file_path': 'src/admin/templates/partials/repo_detail.html'}
- [ ] {'description': 'Add HTMX endpoint for repo detail content', 'file_path': 'src/admin/routes.py'}
- [ ] {'description': 'Wire repos table rows with hx-get triggers to open panel', 'file_path': 'src/admin/templates/repos.html'}
- [ ] {'description': 'Style repo detail content with proper sections and badges', 'file_path': 'src/admin/templates/partials/repo_detail.html'}

**Definition of Done:** Repo Detail Panel — Click-to-Inspect Repos is implemented, tests pass, and documentation is updated.

---

### 75.4 -- Workflow Detail Panel — Click-to-Inspect Workflows

**Points:** 3

Wire workflow table rows and kanban cards to open the sliding detail panel showing workflow execution details: status timeline, step outputs, logs, retry actions.

(4 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create workflow detail partial template', 'file_path': 'src/admin/templates/partials/workflow_detail.html'}
- [ ] {'description': 'Add HTMX endpoint for workflow detail content', 'file_path': 'src/admin/routes.py'}
- [ ] {'description': 'Wire workflow rows with hx-get triggers', 'file_path': 'src/admin/templates/workflows.html'}
- [ ] {'description': 'Add status timeline visualization in detail view', 'file_path': 'src/admin/templates/partials/workflow_detail.html'}

**Definition of Done:** Workflow Detail Panel — Click-to-Inspect Workflows is implemented, tests pass, and documentation is updated.

---

### 75.5 -- Kanban Board View for Workflows

**Points:** 5

Add a toggleable kanban board view to the workflows page. Columns represent workflow states (Queued, Running, Completed, Failed). Cards show workflow summary. Support drag-and-drop reordering within columns using a lightweight JS library (SortableJS).

(5 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create kanban board partial template with column layout', 'file_path': 'src/admin/templates/partials/workflows_kanban.html'}
- [ ] {'description': 'Add view toggle (list/kanban) to workflows page header', 'file_path': 'src/admin/templates/workflows.html'}
- [ ] {'description': 'Integrate SortableJS for drag-and-drop card movement', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Create HTMX endpoint for kanban data shape', 'file_path': 'src/admin/routes.py'}
- ... and 2 more

**Definition of Done:** Kanban Board View for Workflows is implemented, tests pass, and documentation is updated.

---

### 75.6 -- Command Palette (Ctrl+K)

**Points:** 5

Implement a global command palette modal activated by Ctrl+K (or Cmd+K on Mac). Supports fuzzy search across navigation pages, repos, workflows, and common actions. Built with vanilla JS and HTMX for search results.

(6 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create command palette modal component', 'file_path': 'src/admin/templates/components/command_palette.html'}
- [ ] {'description': 'Add global keyboard listener for Ctrl+K in base.html', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Implement fuzzy search logic (client-side for nav, HTMX for entities)', 'file_path': 'src/admin/templates/components/command_palette.html'}
- [ ] {'description': 'Create search API endpoint returning repos, workflows, pages', 'file_path': 'src/admin/routes.py'}
- ... and 2 more

**Definition of Done:** Command Palette (Ctrl+K) is implemented, tests pass, and documentation is updated.

---

### 75.7 -- Dark Mode with CSS Custom Properties

**Points:** 5

Implement dark mode using CSS custom properties (design tokens from the style guide). Add a toggle in the header that persists preference to localStorage. Ensure all pages, components, badges, and panels render correctly in both modes.

(6 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Define CSS custom property token system in base.html style block', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Create dark mode toggle button in header', 'file_path': 'src/admin/templates/base.html'}
- [ ] {'description': 'Convert all Tailwind color classes to use CSS custom properties', 'file_path': 'src/admin/templates/'}
- [ ] {'description': 'Update sidebar colors for dark mode variant', 'file_path': 'src/admin/templates/base.html'}
- ... and 3 more

**Definition of Done:** Dark Mode with CSS Custom Properties is implemented, tests pass, and documentation is updated.

---

### 75.8 -- Accessibility Audit & Fixes for New Components

**Points:** 2

Run WCAG 2.2 AA audit on all new components (detail panel, command palette, kanban board, dark mode). Fix any contrast, focus, or ARIA issues. Ensure keyboard-only navigation works end-to-end.

(5 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Audit detail panel for focus trap, ARIA dialog, keyboard dismiss', 'file_path': 'src/admin/templates/components/detail_panel.html'}
- [ ] {'description': 'Audit command palette for combobox pattern compliance', 'file_path': 'src/admin/templates/components/command_palette.html'}
- [ ] {'description': 'Audit kanban board for drag-drop keyboard alternatives', 'file_path': 'src/admin/templates/partials/workflows_kanban.html'}
- [ ] {'description': 'Check dark mode contrast ratios meet 4.5:1 minimum', 'file_path': 'src/admin/templates/base.html'}
- ... and 1 more

**Definition of Done:** Accessibility Audit & Fixes for New Components is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Use HTMX for all dynamic content loading — no React/Vue/framework dependencies
- Heroicons (MIT licensed) provides consistent icon set matching Tailwind ecosystem
- SortableJS is lightweight (~10KB) and framework-agnostic for drag-and-drop
- CSS custom properties enable runtime theme switching without Tailwind rebuild
- Command palette follows WAI-ARIA combobox pattern for accessibility
- Detail panel follows WAI-ARIA dialog pattern with focus trap
- All new components must work with existing HTMX polling/refresh patterns

**Project Structure:** 13 packages, 53 modules, 237 public APIs

### Expert Recommendations

- **Security Expert** (63%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (64%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Full Plane.so feature parity (issues tracking or project management features)
- Mobile-first responsive redesign (read-only mobile support already exists)
- Real-time WebSocket updates (HTMX polling is sufficient for current scale)
- Inline editing of records (this epic is about viewing and navigation richness)
- Custom theming beyond light/dark (no user-configurable color palettes)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `src/admin/templates/base.html` | *(not found)* | - | - |
| `src/admin/templates/dashboard.html` | *(not found)* | - | - |
| `src/admin/templates/partials/dashboard_content.html` | *(not found)* | - | - |
| `src/admin/templates/components/status_badge.html` | *(not found)* | - | - |
| `src/admin/templates/components/empty_state.html` | *(not found)* | - | - |
| `src/admin/templates/repos.html` | *(not found)* | - | - |
| `src/admin/templates/workflows.html` | *(not found)* | - | - |
| `src/admin/routes.py` | *(not found)* | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All Unicode icons replaced with SVGs — zero Unicode symbols in navigation | 0 | 0 | Template audit |
| Detail panel opens in under 200ms for any row click | 200ms | 150ms | Browser DevTools |
| Command palette search returns results in under 100ms | 100ms | 80ms | Network tab |
| Dark mode toggle works on all 15+ admin pages without contrast violations | 100% | 100% | axe-core audit |
| Existing Playwright test suite passes with zero regressions | 0 failures | 0 failures | CI |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| Owner | Solo Developer | Implementation and review |
| Meridian | VP of Success | Epic review and approval |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- Epic 4 (Admin UI Core)
- Epic 52 (Frontend UI Modernization Master Plan)
- Epic 53 (Admin UI Canonical Compliance)
- docs/design/07-THESTUDIO-UI-UX-STYLE-GUIDE.md

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 75.1: SVG Icon System — Replace Unicode with Heroicons
2. Story 75.2: Right-Side Sliding Detail Panel Infrastructure
3. Story 75.3: Repo Detail Panel — Click-to-Inspect Repos
4. Story 75.4: Workflow Detail Panel — Click-to-Inspect Workflows
5. Story 75.5: Kanban Board View for Workflows
6. Story 75.6: Command Palette (Ctrl+K)
7. Story 75.7: Dark Mode with CSS Custom Properties
8. Story 75.8: Accessibility Audit & Fixes for New Components

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Dark mode conversion may break existing Tailwind color assumptions across 15+ templates | Medium | Low | Warning: Mitigation required - no automated recommendation available |
| SortableJS drag-and-drop may conflict with HTMX swap behavior | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Command palette search API could add latency if not properly indexed | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Detail panel may interfere with existing page-level HTMX polling | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->

# Epic 58: Playwright Test Infrastructure & Visual Snapshot Framework

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P0 - Critical
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** Epic 12 (original Playwright test rig)
**Blocks:** Epic 59, Epic 60, Epic 61, Epic 62, Epic 63, Epic 64, Epic 65, Epic 66, Epic 67, Epic 68, Epic 69, Epic 70, Epic 71, Epic 72, Epic 73, Epic 74

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that all subsequent per-page Playwright test epics (59-74) share a common, battle-tested foundation for style-guide compliance checks, API endpoint verification, interactive element testing, accessibility auditing, and Playwright visual snapshot baselines — eliminating duplication and ensuring consistent quality gates across every Admin UI page.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Build shared Playwright test infrastructure: reusable fixtures for style-guide color/typography/spacing assertions, API response verification helpers, interactive element test utilities, WCAG 2.2 AA accessibility checks, and a visual snapshot baseline framework that captures and compares page screenshots.

**Tech Stack:** TappMCP

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The existing Playwright test rig validates page intent and rendering quality but lacks style-guide compliance checks, API verification, interactive element testing, accessibility auditing, and visual regression baselines. Every page epic (59-74) will depend on these shared utilities.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Style-guide color assertion helper validates semantic token colors (status/success/warning/error/info/neutral) against docs/design/07-THESTUDIO-UI-UX-STYLE-GUIDE.md Section 5
- [ ] Typography assertion helper validates font family (Inter/JetBrains Mono) and size scale per Section 6
- [ ] Spacing assertion helper validates 4px base unit grid per Section 7
- [ ] Component recipe validators for cards/tables/badges/buttons/forms per Section 9
- [ ] API endpoint verification helper: call endpoint and assert status + JSON schema
- [ ] Interactive element tester: click buttons and verify response/state change/HTMX swap
- [ ] WCAG 2.2 AA accessibility checker: contrast ratios and focus indicators and ARIA roles and keyboard navigation
- [ ] Visual snapshot framework: capture full-page screenshot and compare against baseline with configurable threshold
- [ ] Snapshot storage in tests/playwright/snapshots/ with platform-aware naming
- [ ] All helpers are importable from tests/playwright/lib/ and documented with docstrings
- [ ] CI-compatible: snapshots auto-update on first run and fail on diff above threshold

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 58.1 -- Style Guide Color & Token Assertion Library

**Points:** 5

Build assertion helpers that extract computed CSS colors from page elements and validate them against the style guide token definitions (Section 4-5). Covers status colors, trust tier colors, role colors, and interactive colors for both light and dark themes.

(7 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create tests/playwright/lib/style_assertions.py with color extraction via page.evaluate()'}
- [ ] {'description': 'Implement assert_status_colors() validating green/yellow/red/blue/gray badge backgrounds'}
- [ ] {'description': 'Implement assert_trust_tier_colors() for EXECUTE/SUGGEST/OBSERVE badges'}
- [ ] {'description': 'Implement assert_button_colors() for primary/secondary/destructive/ghost variants'}
- ... and 3 more

**Definition of Done:** Style Guide Color & Token Assertion Library is implemented, tests pass, and documentation is updated.

---

### 58.2 -- Typography & Spacing Assertion Library

**Points:** 3

Build helpers that verify font family, font size, font weight, line height, letter spacing, and spacing values against the style guide type scale (Section 6) and spacing system (Section 7).

(5 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Implement assert_typography() checking font-family, font-size, font-weight, line-height'}
- [ ] {'description': 'Implement assert_heading_scale() for h1-h3 and label/body/caption/KPI roles'}
- [ ] {'description': 'Implement assert_spacing() validating padding and gap values against 4px grid'}
- [ ] {'description': 'Implement assert_density_mode() for compact/comfortable/spacious'}
- ... and 1 more

**Definition of Done:** Typography & Spacing Assertion Library is implemented, tests pass, and documentation is updated.

---

### 58.3 -- Component Recipe Validators

**Points:** 5

Build validators for each component recipe in Section 9: cards, tables, badges, buttons, form inputs, alerts, empty states, error states. Each validator checks structure, classes, ARIA attributes, and visual properties.

(8 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Implement validate_card() checking bg, border, radius, padding'}
- [ ] {'description': 'Implement validate_table() checking header bg, scope attributes, row hover, dividers'}
- [ ] {'description': 'Implement validate_badge() checking size, font-weight, color pairing'}
- [ ] {'description': 'Implement validate_button() checking variant classes, min touch target, focus ring'}
- ... and 4 more

**Definition of Done:** Component Recipe Validators is implemented, tests pass, and documentation is updated.

---

### 58.4 -- API Endpoint Verification Helper

**Points:** 3

Build a helper that calls API endpoints via Playwright request context (sharing auth cookies/headers with the browser session), asserts HTTP status codes, validates JSON response structure, and reports failures with endpoint context.

(6 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create tests/playwright/lib/api_helpers.py'}
- [ ] {'description': 'Implement assert_api_endpoint() with method, path, expected_status, json_schema params'}
- [ ] {'description': 'Implement assert_api_returns_data() for list endpoints (non-empty or valid empty)'}
- [ ] {'description': 'Implement assert_api_fields() to check required fields in JSON response'}
- ... and 2 more

**Definition of Done:** API Endpoint Verification Helper is implemented, tests pass, and documentation is updated.

---

### 58.5 -- Interactive Element Test Utilities

**Points:** 3

Build utilities for testing buttons, form submissions, HTMX swaps, tab navigation, dropdowns, and modals. Each utility clicks/interacts and asserts the expected outcome (DOM change, network request, visible feedback).

(7 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create tests/playwright/lib/interaction_helpers.py'}
- [ ] {'description': 'Implement click_and_assert_response() for buttons triggering HTMX or page nav'}
- [ ] {'description': 'Implement fill_and_submit_form() with field map and expected result assertion'}
- [ ] {'description': 'Implement switch_tab_and_assert() for HTMX tab navigation'}
- ... and 3 more

**Definition of Done:** Interactive Element Test Utilities is implemented, tests pass, and documentation is updated.

---

### 58.6 -- WCAG 2.2 AA Accessibility Checker

**Points:** 5

Build accessibility assertion helpers covering contrast ratios, focus indicators, ARIA roles, keyboard navigation, semantic HTML, touch targets, and screen reader support per style guide Section 11.

(8 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create tests/playwright/lib/accessibility_helpers.py'}
- [ ] {'description': 'Implement assert_focus_visible() checking 2px solid ring on Tab navigation'}
- [ ] {'description': 'Implement assert_keyboard_navigation() tabbing through all interactive elements'}
- [ ] {'description': 'Implement assert_aria_roles() checking landmarks, labels, live regions'}
- ... and 5 more

**Definition of Done:** WCAG 2.2 AA Accessibility Checker is implemented, tests pass, and documentation is updated.

---

### 58.7 -- Visual Snapshot Baseline Framework

**Points:** 5

Build a Playwright visual snapshot system that captures full-page and element-level screenshots, stores baselines in tests/playwright/snapshots/, compares with configurable pixel-diff threshold, and supports CI auto-update mode.

(8 acceptance criteria)

**Tasks:**
- [ ] {'description': 'Create tests/playwright/lib/snapshot_helpers.py'}
- [ ] {'description': 'Implement capture_page_snapshot() with full-page screenshot and consistent viewport'}
- [ ] {'description': 'Implement capture_element_snapshot() for component-level screenshots'}
- [ ] {'description': 'Implement compare_snapshot() using Playwright built-in toHaveScreenshot or pixelmatch'}
- ... and 5 more

**Definition of Done:** Visual Snapshot Baseline Framework is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- All helpers must work with pytest-playwright (not @playwright/test)
- Style guide reference: docs/design/07-THESTUDIO-UI-UX-STYLE-GUIDE.md
- Color extraction uses page.evaluate() to get getComputedStyle() values
- axe-core integration via inline script injection for accessibility checks
- Snapshots use Playwright expect(page).to_have_screenshot() with maxDiffPixelRatio
- Visual snapshots require consistent viewport (1280x720) and font rendering
- All helpers importable from tests/playwright/lib/__init__.py

**Project Structure:** 48 packages, 789 modules, 3076 public APIs

### Expert Recommendations

- **Security Expert** (69%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (65%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Testing React SPA Dashboard (separate epic scope)
- Implementing fixes for style guide violations (test-only epic)
- Dark theme testing beyond token validation (full dark mode is separate)
- Performance/load testing
- Mobile responsive testing beyond basic viewport checks

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `tests/playwright/conftest.py` | *(not found)* | - | - |
| `tests/playwright/test_all_pages.py` | *(not found)* | - | - |
| `tests/playwright/test_rendering_quality.py` | *(not found)* | - | - |
| `tests/playwright/test_htmx_interactions.py` | *(not found)* | - | - |
| `tests/playwright/test_url_docs.py` | *(not found)* | - | - |
| `tests/playwright/test_smoke.py` | *(not found)* | - | - |
| `docs/design/07-THESTUDIO-UI-UX-STYLE-GUIDE.md` | *(not found)* | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 11 acceptance criteria met | 0/11 | 11/11 | Checklist review |
| All 7 stories completed | 0/7 | 7/7 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 58.1: Style Guide Color & Token Assertion Library
2. Story 58.2: Typography & Spacing Assertion Library
3. Story 58.3: Component Recipe Validators
4. Story 58.4: API Endpoint Verification Helper
5. Story 58.5: Interactive Element Test Utilities
6. Story 58.6: WCAG 2.2 AA Accessibility Checker
7. Story 58.7: Visual Snapshot Baseline Framework

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| No risks identified | - | - | Consider adding risks during planning |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->

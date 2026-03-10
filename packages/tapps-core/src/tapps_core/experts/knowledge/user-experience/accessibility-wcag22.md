# Accessibility & WCAG 2.2

## Overview

Web accessibility ensures that people with disabilities can perceive, understand, navigate, and interact with websites and applications. WCAG 2.2 (published October 2023, enforced 2025+) adds new success criteria focused on cognitive accessibility, mobile interactions, and authentication. Building accessible interfaces is both a legal requirement and a competitive advantage.

## WCAG 2.2 Conformance Levels

| Level | Meaning | Minimum for |
|-------|---------|-------------|
| **A** | Essential — site is basically usable | Internal tools |
| **AA** | Standard — site works well for most users | Public websites, apps (legal standard) |
| **AAA** | Enhanced — best possible accessibility | Specialized/government sites |

**Target AA conformance as the baseline for all projects.**

## New in WCAG 2.2

### 2.4.11 Focus Not Obscured (Minimum) — AA

Focused elements must not be entirely hidden by other content (sticky headers, modals, chat widgets).

```css
/* Ensure focused items scroll into view above sticky elements */
:focus {
  scroll-margin-top: 80px; /* Height of sticky header */
  scroll-margin-bottom: 60px; /* Height of sticky footer */
}

/* Avoid overlapping focus with fixed elements */
.sticky-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}
```

### 2.4.12 Focus Not Obscured (Enhanced) — AAA

No part of the focused element is hidden by author-created content.

### 2.4.13 Focus Appearance — AAA

Focus indicator must meet minimum size and contrast requirements.

```css
/* High-visibility focus indicator */
:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
  border-radius: 2px;
}

/* Ensure contrast ratio of at least 3:1 against adjacent colors */
:root {
  --color-focus: #2563eb; /* Blue with good contrast on white and light grays */
}
```

### 2.5.7 Dragging Movements — AA

Any action performed by dragging must have a non-drag alternative.

```html
<!-- Sortable list: drag to reorder + button alternative -->
<li draggable="true">
  <span>Item 1</span>
  <button aria-label="Move Item 1 up">↑</button>
  <button aria-label="Move Item 1 down">↓</button>
</li>
```

### 2.5.8 Target Size (Minimum) — AA

Interactive targets must be at least 24×24 CSS pixels, or have sufficient spacing.

```css
/* Minimum target sizes */
button, a, input, select, textarea {
  min-height: 24px;
  min-width: 24px;
}

/* Recommended: 44×44 for touch targets */
.touch-target {
  min-height: 44px;
  min-width: 44px;
  padding: 10px;
}

/* Spacing exception: inline links in text are exempt */
```

### 3.2.6 Consistent Help — A

Help mechanisms (contact info, chat, FAQ) must appear in the same relative order across pages.

### 3.3.7 Redundant Entry — A

Don't ask users to re-enter information they've already provided in the same process.

```html
<!-- Bad: asking for address again on confirmation page -->
<!-- Good: pre-fill from previous step -->
<input
  type="text"
  name="shipping-city"
  value="Portland"
  autocomplete="shipping address-level2"
/>
```

### 3.3.8 Accessible Authentication (Minimum) — AA

No cognitive function test (CAPTCHAs, memorizing passwords) unless an alternative is provided.

Acceptable alternatives:
- Passkeys / WebAuthn / biometrics
- Password managers (autocomplete="current-password")
- Magic links / email codes
- OAuth / social login
- Copy-paste allowed in password fields

```html
<!-- Allow password managers -->
<input
  type="password"
  autocomplete="current-password"
  id="password"
/>

<!-- Never disable paste on password fields -->
```

## ARIA Patterns

### When to Use ARIA

1. **First rule of ARIA**: Don't use ARIA if native HTML works
2. Use ARIA when native elements can't express the semantics
3. All interactive ARIA elements must be keyboard operable

```html
<!-- Bad: div with ARIA -->
<div role="button" tabindex="0" aria-label="Submit">Submit</div>

<!-- Good: native button -->
<button type="submit">Submit</button>
```

### Common ARIA Patterns

#### Dialog / Modal

```html
<dialog id="confirm-dialog" aria-labelledby="dialog-title">
  <h2 id="dialog-title">Confirm Deletion</h2>
  <p>This action cannot be undone.</p>
  <div class="dialog-actions">
    <button onclick="this.closest('dialog').close()">Cancel</button>
    <button onclick="confirmDelete()">Delete</button>
  </div>
</dialog>
```

```javascript
// Use the native dialog API
const dialog = document.getElementById('confirm-dialog');
dialog.showModal(); // Traps focus, adds backdrop, handles Escape
```

#### Tabs

```html
<div role="tablist" aria-label="Product details">
  <button role="tab" id="tab-desc" aria-selected="true" aria-controls="panel-desc">
    Description
  </button>
  <button role="tab" id="tab-specs" aria-selected="false" aria-controls="panel-specs" tabindex="-1">
    Specifications
  </button>
  <button role="tab" id="tab-reviews" aria-selected="false" aria-controls="panel-reviews" tabindex="-1">
    Reviews
  </button>
</div>

<div role="tabpanel" id="panel-desc" aria-labelledby="tab-desc">
  <!-- Description content -->
</div>
<div role="tabpanel" id="panel-specs" aria-labelledby="tab-specs" hidden>
  <!-- Specs content -->
</div>
```

Keyboard: Arrow keys move between tabs, Tab moves to panel content.

#### Combobox / Autocomplete

```html
<label for="city-input">City</label>
<div role="combobox" aria-expanded="true" aria-haspopup="listbox" aria-owns="city-list">
  <input
    id="city-input"
    type="text"
    aria-autocomplete="list"
    aria-controls="city-list"
    aria-activedescendant="city-portland"
  />
</div>
<ul role="listbox" id="city-list">
  <li role="option" id="city-portland" aria-selected="true">Portland</li>
  <li role="option" id="city-seattle">Seattle</li>
  <li role="option" id="city-vancouver">Vancouver</li>
</ul>
```

#### Live Regions

```html
<!-- Polite: announced after current speech -->
<div aria-live="polite" aria-atomic="true">
  3 results found
</div>

<!-- Assertive: interrupts current speech (use sparingly) -->
<div role="alert">
  Your session will expire in 2 minutes.
</div>

<!-- Status: implicit polite live region -->
<div role="status">
  File uploaded successfully.
</div>
```

## Focus Management

### Focus Trapping in Modals

```javascript
function trapFocus(modal) {
  const focusable = modal.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  modal.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  first.focus();
}
```

### Focus Restoration

```javascript
// Save focus before opening modal
const previousFocus = document.activeElement;

// Open modal...
openModal();

// On close, restore focus
function closeModal() {
  modal.hidden = true;
  previousFocus?.focus();
}
```

### Skip Links

```html
<a href="#main-content" class="skip-link">
  Skip to main content
</a>

<nav><!-- navigation --></nav>

<main id="main-content" tabindex="-1">
  <!-- page content -->
</main>
```

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  padding: 8px;
  z-index: 1000;
}
.skip-link:focus {
  top: 0;
}
```

## Color and Contrast

### Contrast Requirements

| Element | AA Minimum | AAA Minimum |
|---------|-----------|-------------|
| Normal text | 4.5:1 | 7:1 |
| Large text (18pt+ or 14pt bold) | 3:1 | 4.5:1 |
| UI components & graphics | 3:1 | N/A |
| Focus indicators | 3:1 | N/A |

### Don't Rely on Color Alone

```html
<!-- Bad: only color indicates error -->
<input class="border-red" />

<!-- Good: color + icon + text -->
<input class="border-red" aria-invalid="true" aria-describedby="email-error" />
<p id="email-error" class="error">
  <svg aria-hidden="true"><!-- error icon --></svg>
  Please enter a valid email address.
</p>
```

## Semantic HTML

### Document Structure

```html
<header>
  <nav aria-label="Main navigation">...</nav>
</header>

<main>
  <h1>Page Title</h1>

  <section aria-labelledby="features-heading">
    <h2 id="features-heading">Features</h2>
    <article>...</article>
  </section>

  <aside aria-label="Related content">...</aside>
</main>

<footer>
  <nav aria-label="Footer navigation">...</nav>
</footer>
```

### Heading Hierarchy

- One `<h1>` per page
- Don't skip levels (h1 → h3)
- Use headings for structure, not styling
- Screen reader users navigate by headings — they must make sense out of context

## Testing Accessibility

### Automated Tools

- **axe-core** — Most comprehensive rule engine (used by Deque, browser extensions)
- **Lighthouse** — Built into Chrome DevTools
- **Pa11y** — CLI and CI integration
- **jest-axe** — Jest matcher for automated tests
- **Playwright** — `@axe-core/playwright` for E2E a11y testing

```typescript
// Playwright + axe example
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('homepage has no a11y violations', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

### Manual Testing Checklist

- [ ] Navigate entire page with keyboard only (Tab, Shift+Tab, Enter, Escape, Arrow keys)
- [ ] Test with screen reader (NVDA on Windows, VoiceOver on Mac)
- [ ] Zoom to 200% — no content loss or overlap
- [ ] Check with Windows High Contrast Mode
- [ ] Test with prefers-reduced-motion enabled
- [ ] Verify all images have meaningful alt text (or alt="" for decorative)
- [ ] Check that form errors are announced to screen readers
- [ ] Confirm focus is visible on all interactive elements

## Common Mistakes

### Missing alt Text

```html
<!-- Informative image: describe the content -->
<img src="chart.png" alt="Sales increased 40% from Q1 to Q3 2025" />

<!-- Decorative image: empty alt -->
<img src="decorative-border.png" alt="" />

<!-- Icon button: label the action, not the icon -->
<button aria-label="Close dialog">
  <svg aria-hidden="true"><!-- X icon --></svg>
</button>
```

### Removing Focus Outlines

```css
/* NEVER do this */
*:focus { outline: none; }

/* Instead, customize focus-visible */
:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}

/* Remove outline only for mouse clicks */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Auto-playing Media

- Never auto-play audio or video with sound
- If auto-playing muted video, provide pause/stop controls
- Respect `prefers-reduced-motion` for auto-playing animations

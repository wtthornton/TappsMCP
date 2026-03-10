# Modern CSS (2025-2026)

## Overview

CSS has undergone a renaissance. Container queries, the :has() selector, view transitions, scroll-driven animations, subgrid, CSS nesting, and @scope have transformed what's possible without JavaScript. This guide covers production-ready CSS features that every frontend developer should use in 2026.

## Container Queries

### The Problem Container Queries Solve

Media queries respond to viewport size. Container queries respond to a component's container size — enabling truly portable, responsive components.

```css
/* Define a containment context */
.card-wrapper {
  container-type: inline-size;
  container-name: card;
}

/* Style based on container width, not viewport */
@container card (min-width: 400px) {
  .card {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 1rem;
  }
}

@container card (max-width: 399px) {
  .card {
    display: flex;
    flex-direction: column;
  }
}
```

### Container Query Units

Size-relative units based on the query container:

| Unit | Relative To |
|------|-------------|
| `cqw` | 1% of container width |
| `cqh` | 1% of container height |
| `cqi` | 1% of container inline size |
| `cqb` | 1% of container block size |
| `cqmin` | Smaller of cqi/cqb |
| `cqmax` | Larger of cqi/cqb |

```css
.card-title {
  font-size: clamp(1rem, 3cqi, 1.5rem);
}
```

### Style Queries

Query computed style values of a container:

```css
.card-wrapper {
  container-type: normal; /* No size containment needed */
}

@container style(--theme: dark) {
  .card {
    background: #1a1a2e;
    color: #e0e0e0;
  }
}
```

## The :has() Selector

The "parent selector" CSS never had — select elements based on their descendants or siblings.

```css
/* Card with an image gets different layout */
.card:has(img) {
  grid-template-rows: 200px 1fr;
}

/* Card without an image gets more padding */
.card:not(:has(img)) {
  padding: 2rem;
}

/* Form group with invalid input gets error styling */
.form-group:has(:invalid) {
  border-color: var(--color-error);
}

/* Label for required fields */
label:has(+ input:required)::after {
  content: ' *';
  color: var(--color-error);
}

/* Sidebar present — adjust main content */
body:has(.sidebar) .main-content {
  margin-left: 280px;
}

/* Navigation with dropdown open */
nav:has(.dropdown[open]) {
  z-index: 100;
}
```

## CSS Nesting

Native nesting without preprocessors:

```css
.card {
  padding: 1rem;
  border-radius: 0.5rem;

  & .title {
    font-size: 1.25rem;
    font-weight: 600;
  }

  & .body {
    margin-top: 0.75rem;
    color: var(--color-text-secondary);
  }

  &:hover {
    box-shadow: var(--shadow-md);
  }

  &:has(.badge) {
    padding-top: 2rem;
  }

  @media (min-width: 768px) {
    padding: 1.5rem;
  }
}
```

## View Transitions API

Smooth animated transitions between DOM states or page navigations.

### Same-Document Transitions

```javascript
// Wrap DOM updates in a view transition
document.startViewTransition(() => {
  // Update the DOM
  updateSortOrder();
});
```

```css
/* Customize the transition */
::view-transition-old(root) {
  animation: fade-out 200ms ease-out;
}

::view-transition-new(root) {
  animation: fade-in 200ms ease-in;
}

/* Name specific elements for independent transitions */
.hero-image {
  view-transition-name: hero;
}

/* Animate named elements independently */
::view-transition-old(hero) {
  animation: scale-down 300ms ease-out;
}
::view-transition-new(hero) {
  animation: scale-up 300ms ease-in;
}
```

### Cross-Document Transitions (MPA)

```css
/* Enable for same-origin navigations */
@view-transition {
  navigation: auto;
}

/* Assign transition names to elements */
.product-image {
  view-transition-name: product;
}

.page-title {
  view-transition-name: title;
}
```

## Scroll-Driven Animations

Animate based on scroll position without JavaScript.

```css
/* Animation tied to scroll progress */
.progress-bar {
  animation: grow-width linear;
  animation-timeline: scroll();
}

@keyframes grow-width {
  from { width: 0%; }
  to { width: 100%; }
}

/* Element enters viewport — reveal animation */
.reveal {
  animation: fade-slide-up linear both;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}

@keyframes fade-slide-up {
  from {
    opacity: 0;
    transform: translateY(2rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Parallax effect */
.parallax-bg {
  animation: parallax linear;
  animation-timeline: scroll();
}

@keyframes parallax {
  from { transform: translateY(0); }
  to { transform: translateY(-30%); }
}
```

## Subgrid

Child elements align to parent grid tracks:

```css
.page-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 1rem;
}

.card {
  grid-column: span 4;
  display: grid;
  grid-template-rows: subgrid; /* Inherit parent's row tracks */
  grid-row: span 3;
}

/* All card titles, bodies, and footers align across cards */
.card-title { grid-row: 1; }
.card-body  { grid-row: 2; }
.card-footer { grid-row: 3; }
```

## @scope

Scope styles to a DOM subtree without BEM or CSS Modules:

```css
@scope (.card) to (.card-footer) {
  /* Styles apply inside .card but not inside .card-footer */
  p {
    color: var(--color-text);
    line-height: 1.6;
  }

  a {
    color: var(--color-primary);
    text-decoration: underline;
  }
}
```

## @layer

Control cascade precedence explicitly:

```css
/* Define layer order */
@layer reset, base, components, utilities;

@layer reset {
  * { margin: 0; box-sizing: border-box; }
}

@layer base {
  body { font-family: var(--font-sans); }
  h1 { font-size: 2rem; }
}

@layer components {
  .button { padding: 0.5rem 1rem; border-radius: 0.25rem; }
}

@layer utilities {
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
}
```

## Modern Layout Patterns

### Fluid Typography

```css
/* clamp() for responsive font sizes without media queries */
h1 { font-size: clamp(1.75rem, 1rem + 2vw, 3rem); }
h2 { font-size: clamp(1.25rem, 0.8rem + 1.5vw, 2rem); }
body { font-size: clamp(1rem, 0.9rem + 0.3vw, 1.125rem); }
```

### Intrinsic Sizing

```css
/* Content-aware sizing */
.tag {
  width: fit-content;
  padding: 0.25rem 0.75rem;
}

.sidebar {
  width: min(300px, 100%);
}

.main {
  width: min(65ch, 100% - 2rem);
  margin-inline: auto;
}
```

### Holy Grail with Grid

```css
body {
  display: grid;
  grid-template:
    "header  header  header"  auto
    "sidebar main    aside"   1fr
    "footer  footer  footer"  auto
    / minmax(200px, 1fr) minmax(0, 3fr) minmax(200px, 1fr);
  min-height: 100dvh;
}
```

## Dynamic Viewport Units

```css
/* dvh accounts for mobile browser chrome */
.hero {
  min-height: 100dvh; /* Dynamic viewport height */
}

/* svh = smallest viewport, lvh = largest viewport */
.modal-overlay {
  height: 100svh; /* Never overflows even with browser chrome */
}
```

## Color Functions

```css
/* oklch — perceptually uniform, wide gamut */
:root {
  --primary: oklch(60% 0.15 250);
  --primary-light: oklch(80% 0.1 250);
  --primary-dark: oklch(40% 0.15 250);
}

/* color-mix for derived colors */
.hover-bg {
  background: color-mix(in oklch, var(--primary) 80%, white);
}

/* Relative color syntax */
.muted {
  color: oklch(from var(--primary) l c h / 50%);
}
```

## Best Practices

### Use CSS Before JavaScript

Many patterns that previously required JS are now CSS-only:
- Scroll-driven animations replace Intersection Observer
- :has() replaces parent-state JavaScript
- Container queries replace ResizeObserver
- View transitions replace FLIP animations
- @starting-style replaces JS entry animations

### Progressive Enhancement

```css
/* Feature detection with @supports */
@supports (container-type: inline-size) {
  .widget { container-type: inline-size; }
}

@supports not (view-transition-name: none) {
  /* Fallback for browsers without view transitions */
  .card { transition: opacity 0.2s; }
}
```

## Common Mistakes

### Overusing z-index

- Problem: z-index battles and magic numbers
- Fix: Use stacking context layers and CSS custom properties

```css
:root {
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-modal: 300;
  --z-toast: 400;
}
```

### Not Using Logical Properties

```css
/* Physical (avoid) */
margin-left: 1rem;
padding-right: 0.5rem;
border-top: 1px solid;

/* Logical (prefer — supports RTL) */
margin-inline-start: 1rem;
padding-inline-end: 0.5rem;
border-block-start: 1px solid;
```

### Ignoring prefers-reduced-motion

Always provide reduced motion alternatives for animations. See motion-animation.md for details.

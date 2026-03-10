# Responsive & Mobile Design

## Overview

Mobile accounts for over 60% of web traffic. Responsive design is not about shrinking desktop layouts — it's about designing fluid, adaptive interfaces that work naturally across devices. In 2026, container queries, fluid typography, and progressive web app (PWA) capabilities have redefined responsive design.

## Mobile-First Approach

### Why Mobile-First

- Forces prioritization of content and features
- Mobile constraints produce cleaner, faster interfaces
- Easier to add complexity than remove it
- Matches CSS cascade (base styles → media query enhancements)

```css
/* Mobile-first: base styles for smallest screens */
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

/* Tablet */
@media (min-width: 768px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Large desktop */
@media (min-width: 1280px) {
  .grid {
    grid-template-columns: repeat(4, 1fr);
    max-width: 1280px;
    margin-inline: auto;
  }
}
```

## Breakpoints

### Modern Breakpoint Strategy

Don't target devices — target content breakpoints where the layout breaks.

| Token | Width | Target |
|-------|-------|--------|
| `sm` | 640px | Large phones (landscape) |
| `md` | 768px | Tablets |
| `lg` | 1024px | Small laptops |
| `xl` | 1280px | Desktops |
| `2xl` | 1536px | Large screens |

```css
/* Use container queries instead of viewport breakpoints where possible */
.card-container {
  container-type: inline-size;
}

@container (min-width: 400px) {
  .card { grid-template-columns: 150px 1fr; }
}
```

### Content-Based Breakpoints

```css
/* Instead of device breakpoints, break when content needs it */
.article {
  width: min(65ch, 100% - 2rem);
  margin-inline: auto;
}

/* Sidebar disappears when there isn't room for it */
.layout {
  display: grid;
  grid-template-columns: 1fr;
}

@media (min-width: 60rem) {
  .layout {
    grid-template-columns: 1fr minmax(250px, 300px);
  }
}
```

## Touch Targets

### Minimum Sizes

```css
/* WCAG 2.2: 24×24px minimum (2.5.8 Target Size) */
/* Recommended: 44×44px for primary touch targets */

button, a, [role="button"] {
  min-height: 44px;
  min-width: 44px;
}

/* Small inline controls: ensure spacing */
.icon-button {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* Touch target spacing */
.action-list button + button {
  margin-left: 8px; /* Prevent accidental taps */
}
```

### Touch-Friendly Patterns

```css
/* Larger checkboxes and radios on touch devices */
@media (pointer: coarse) {
  input[type="checkbox"],
  input[type="radio"] {
    width: 24px;
    height: 24px;
  }

  /* Increase link padding */
  nav a {
    padding: 12px 16px;
  }
}

/* Hover-only styles for non-touch devices */
@media (hover: hover) {
  .card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
}
```

## Responsive Navigation

### Mobile Navigation Patterns

#### Hamburger Menu (Standard)

```html
<nav aria-label="Main navigation">
  <button
    aria-expanded="false"
    aria-controls="nav-menu"
    aria-label="Open navigation menu"
    class="nav-toggle"
  >
    <span class="hamburger-icon" aria-hidden="true"></span>
  </button>

  <ul id="nav-menu" class="nav-menu" hidden>
    <li><a href="/" aria-current="page">Home</a></li>
    <li><a href="/products">Products</a></li>
    <li><a href="/about">About</a></li>
    <li><a href="/contact">Contact</a></li>
  </ul>
</nav>
```

#### Bottom Navigation (Mobile Apps, PWA)

```css
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-around;
  background: var(--color-bg);
  border-top: 1px solid var(--color-border);
  padding: 8px 0;
  padding-bottom: env(safe-area-inset-bottom); /* iPhone notch */
  z-index: var(--z-sticky);
}

.bottom-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 0.75rem;
  min-width: 64px;
  padding: 4px;
}
```

Limit to 3-5 items. More than 5 → use "More" tab with overflow menu.

### Responsive Navigation Switch

```css
/* Desktop: horizontal navigation */
.nav-menu {
  display: flex;
  gap: 1rem;
  list-style: none;
}

.nav-toggle {
  display: none;
}

/* Mobile: hidden behind toggle */
@media (max-width: 767px) {
  .nav-toggle {
    display: block;
  }

  .nav-menu {
    position: fixed;
    inset: 0;
    flex-direction: column;
    background: var(--color-bg);
    padding: 2rem;
    transform: translateX(-100%);
    transition: transform 300ms var(--ease-out);
  }

  .nav-menu:not([hidden]) {
    transform: translateX(0);
  }
}
```

## Responsive Images

```html
<!-- Art direction: different crops for different screens -->
<picture>
  <source media="(min-width: 1024px)" srcset="hero-wide.webp" />
  <source media="(min-width: 640px)" srcset="hero-medium.webp" />
  <img src="hero-mobile.webp" alt="Product hero" width="640" height="480" />
</picture>

<!-- Resolution switching: same image, different sizes -->
<img
  srcset="product-400.webp 400w, product-800.webp 800w, product-1200.webp 1200w"
  sizes="(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
  src="product-800.webp"
  alt="Product photo"
  loading="lazy"
/>
```

## Responsive Typography

```css
/* Fluid type scale — no breakpoints needed */
:root {
  --text-xs: clamp(0.75rem, 0.7rem + 0.2vw, 0.875rem);
  --text-sm: clamp(0.875rem, 0.8rem + 0.25vw, 1rem);
  --text-base: clamp(1rem, 0.9rem + 0.3vw, 1.125rem);
  --text-lg: clamp(1.125rem, 1rem + 0.4vw, 1.25rem);
  --text-xl: clamp(1.25rem, 1rem + 0.8vw, 1.5rem);
  --text-2xl: clamp(1.5rem, 1rem + 1.5vw, 2rem);
  --text-3xl: clamp(1.75rem, 1rem + 2vw, 3rem);
}
```

## Responsive Tables

Tables are notoriously difficult on mobile. Options:

### Horizontal Scroll

```css
.table-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

/* Scroll shadow indicators */
.table-wrapper {
  background:
    linear-gradient(to right, var(--color-bg) 30%, transparent),
    linear-gradient(to left, var(--color-bg) 30%, transparent),
    linear-gradient(to right, rgba(0,0,0,.1), transparent),
    linear-gradient(to left, rgba(0,0,0,.1), transparent);
  background-position: left, right, left, right;
  background-repeat: no-repeat;
  background-size: 40px 100%, 40px 100%, 20px 100%, 20px 100%;
  background-attachment: local, local, scroll, scroll;
}
```

### Stacked Cards (Mobile)

```css
/* Table becomes stacked cards on mobile */
@media (max-width: 640px) {
  table, thead, tbody, tr, th, td {
    display: block;
  }

  thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
  }

  td {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--color-border);
  }

  td::before {
    content: attr(data-label);
    font-weight: 600;
    margin-right: 1rem;
  }

  tr {
    margin-bottom: 1rem;
    border: 1px solid var(--color-border);
    border-radius: 8px;
  }
}
```

## Safe Areas (Notch, Dynamic Island)

```css
/* Account for device-specific safe areas */
.app-container {
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}

/* Fixed bottom elements */
.bottom-bar {
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
}
```

## Progressive Web Apps (PWA)

### Web App Manifest

```json
{
  "name": "My Application",
  "short_name": "MyApp",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#2563eb",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icon-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

### PWA UX Considerations

- **Offline support**: Show cached content with "offline" indicator
- **Install prompt**: Show only after user has engaged (2+ visits)
- **Update notification**: "New version available. Refresh to update."
- **Native feel**: Remove browser chrome, use standalone display mode
- **Splash screen**: Background color + icon from manifest during load

## Viewport Meta

```html
<!-- Standard viewport (always include) -->
<meta name="viewport" content="width=device-width, initial-scale=1" />

<!-- Prevent zoom on iOS when focusing inputs (if needed, but NOT recommended) -->
<!-- Users should always be able to zoom -->
```

**Never use `user-scalable=no` or `maximum-scale=1`** — this is an accessibility violation (WCAG 1.4.4 Resize Text).

## Common Mistakes

### Desktop-First Design

- Problem: Design for desktop, then try to squeeze into mobile
- Fix: Design mobile-first, then enhance for larger screens

### Fixed Widths

- Problem: Elements with `width: 500px` break on small screens
- Fix: Use `max-width`, `min()`, percentage, or fluid units

### Hover-Dependent Interactions

- Problem: Tooltips, dropdown menus, previews that only work with hover
- Fix: Provide tap/click alternatives; use `@media (hover: hover)` for hover enhancements

### Tiny Touch Targets

- Problem: Links and buttons smaller than 44×44px on mobile
- Fix: Ensure all interactive elements meet minimum touch target sizes

### Ignoring Landscape Orientation

- Problem: Layout breaks in landscape on phones
- Fix: Test both orientations; don't lock orientation unless there's a strong reason

### Not Testing on Real Devices

- Problem: Only testing in browser DevTools responsive mode
- Fix: Test on actual phones/tablets — touch behavior, performance, and rendering differ

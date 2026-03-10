# Motion & Animation Design

## Overview

Motion in UI communicates relationships, provides feedback, guides attention, and creates a sense of continuity. In 2026, CSS-native animations (View Transitions API, scroll-driven animations) have largely replaced JavaScript animation libraries for common patterns. This guide covers when, why, and how to use motion effectively.

## Motion Principles

### Purpose-Driven Motion

Every animation must serve a purpose:

| Purpose | Example |
|---------|---------|
| **Feedback** | Button press ripple, toggle state change |
| **Orientation** | Page transition showing navigation direction |
| **Continuity** | Shared element transition between list and detail |
| **Attention** | Notification badge pulse, error shake |
| **Hierarchy** | Staggered list entrance showing item order |
| **Delight** | Subtle hover effects, success celebrations |

### Motion Should Not

- Delay the user from completing their task
- Distract from primary content
- Cause motion sickness or discomfort
- Play when the user hasn't interacted
- Be the only indicator of state change (combine with color, icon, text)

## Duration & Easing

### Duration Guidelines

| Interaction Type | Duration | Example |
|-----------------|----------|---------|
| Micro-interaction | 100-200ms | Button hover, toggle, tooltip |
| Small transition | 200-300ms | Dropdown open, tab switch |
| Medium transition | 300-500ms | Modal open/close, page section |
| Large transition | 500-800ms | Full-page transition, complex layout |
| Enter animation | 200-400ms | Element appearing on screen |
| Exit animation | 150-250ms | Element disappearing (exits should be faster) |

### Easing Functions

```css
:root {
  /* Standard easings */
  --ease-in: cubic-bezier(0.4, 0, 1, 0.2);      /* Acceleration */
  --ease-out: cubic-bezier(0, 0, 0.2, 1);         /* Deceleration */
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);    /* Both */

  /* Spring-like easings (more natural) */
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-bounce: cubic-bezier(0.34, 1.8, 0.64, 1);

  /* Modern CSS spring() — experimental */
  /* transition: transform spring(1 100 10 0); */
}
```

**When to use each:**
- **ease-out**: Elements entering the screen (decelerating to rest)
- **ease-in**: Elements leaving the screen (accelerating away)
- **ease-in-out**: Elements moving on screen (position changes)
- **linear**: Progress bars, scroll-linked animations
- **spring**: Playful interactions, bouncy buttons, card flips

## Common Animation Patterns

### Enter / Exit

```css
/* Fade in */
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Slide up and fade in */
@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(1rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Scale in (for modals, popovers) */
@keyframes scale-in {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Usage with @starting-style for enter animations */
.popover {
  opacity: 1;
  transform: scale(1);
  transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out);

  @starting-style {
    opacity: 0;
    transform: scale(0.95);
  }
}

/* Exit: transition to hidden */
.popover[hidden] {
  opacity: 0;
  transform: scale(0.95);
  transition: opacity 150ms var(--ease-in), transform 150ms var(--ease-in);
  display: none;
  transition-behavior: allow-discrete;
}
```

### Staggered Entrance

```css
/* Stagger list items */
.list-item {
  animation: slide-up 300ms var(--ease-out) backwards;
}

.list-item:nth-child(1) { animation-delay: 0ms; }
.list-item:nth-child(2) { animation-delay: 50ms; }
.list-item:nth-child(3) { animation-delay: 100ms; }
.list-item:nth-child(4) { animation-delay: 150ms; }

/* Or use custom properties for dynamic stagger */
.list-item {
  animation: slide-up 300ms var(--ease-out) backwards;
  animation-delay: calc(var(--index) * 50ms);
}
```

```tsx
// Set index via style prop
{items.map((item, i) => (
  <div key={item.id} className="list-item" style={{ '--index': i }}>
    {item.name}
  </div>
))}
```

### Loading Indicators

```css
/* Pulsing dot loader */
.loader {
  display: flex;
  gap: 0.25rem;
}

.loader-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse 1s ease-in-out infinite;
}

.loader-dot:nth-child(2) { animation-delay: 150ms; }
.loader-dot:nth-child(3) { animation-delay: 300ms; }

@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

/* Spinning loader */
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
```

### Micro-Interactions

```css
/* Button press effect */
button {
  transition: transform 100ms var(--ease-out), box-shadow 100ms var(--ease-out);
}

button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

button:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* Toggle switch */
.toggle-track {
  transition: background-color 200ms var(--ease-in-out);
}

.toggle-thumb {
  transition: transform 200ms var(--ease-spring);
}

.toggle[aria-checked="true"] .toggle-thumb {
  transform: translateX(20px);
}

/* Checkbox check animation */
.checkbox-icon {
  stroke-dasharray: 20;
  stroke-dashoffset: 20;
  transition: stroke-dashoffset 200ms var(--ease-out);
}

.checkbox:checked + .checkbox-icon {
  stroke-dashoffset: 0;
}
```

### Skeleton Shimmer

```css
/* See performance-ux.md for full skeleton implementation */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    hsl(0 0% 90%) 25%,
    hsl(0 0% 95%) 50%,
    hsl(0 0% 90%) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
```

## Reduced Motion

### Respecting User Preferences

**This is non-negotiable.** Always provide reduced motion alternatives.

```css
/* Default: full animations */
.card {
  transition: transform 300ms var(--ease-out), opacity 300ms var(--ease-out);
}

/* Reduced motion: instant or minimal transitions */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Or selectively reduce (preferred approach) */
@media (prefers-reduced-motion: reduce) {
  .card {
    /* Keep opacity fade (not motion-triggering) */
    transition: opacity 200ms;
    /* Remove transform (motion-triggering) */
    transform: none;
  }

  .hero-animation {
    animation: none;
  }
}
```

### What to Reduce vs. Remove

| Keep (non-triggering) | Remove (motion-triggering) |
|----------------------|---------------------------|
| Opacity fades | Sliding / translating |
| Color transitions | Scaling / zooming |
| Border changes | Rotating / spinning |
| Background changes | Parallax effects |
| | Bouncing / shaking |

## View Transitions API

See modern-css.md for implementation details. Key motion guidance:

```css
/* Shared element transitions */
::view-transition-old(card) {
  animation: fade-out 200ms var(--ease-in);
}

::view-transition-new(card) {
  animation: fade-in 200ms var(--ease-out);
}

/* Respect reduced motion for view transitions too */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*) {
    animation-duration: 0ms;
  }
}
```

## Animation Performance

### GPU-Accelerated Properties

Only animate these properties for smooth 60fps:
- `transform` (translate, scale, rotate)
- `opacity`
- `filter`
- `clip-path`

**Never animate:** `width`, `height`, `top`, `left`, `margin`, `padding`, `border-width`, `font-size`

```css
/* Bad: triggers layout */
.card:hover {
  width: 110%;
  padding: 2rem;
}

/* Good: GPU-accelerated */
.card:hover {
  transform: scale(1.05);
}
```

### will-change

```css
/* Only use for elements that will definitely animate */
.modal {
  will-change: transform, opacity;
}

/* Remove after animation completes to free GPU memory */
.modal.closed {
  will-change: auto;
}
```

## Common Mistakes

### Animating Layout Properties

- Problem: Animating `width`, `height`, `margin` causes jank (triggers layout recalculation)
- Fix: Use `transform: scale()` or `clip-path` instead

### Too Many Simultaneous Animations

- Problem: Everything animates at once, creating visual chaos
- Fix: Stagger animations, limit to 2-3 concurrent animations

### Animation Without Purpose

- Problem: Elements bounce, spin, and slide for no functional reason
- Fix: Every animation must communicate something (state change, hierarchy, direction)

### Forgetting Reduced Motion

- Problem: Users with vestibular disorders experience discomfort
- Fix: Always implement `prefers-reduced-motion` — test with it enabled

### Too Slow or Too Fast

- Problem: Animations feel sluggish (>500ms for simple interactions) or abrupt (<100ms)
- Fix: Follow duration guidelines above; exits faster than entrances

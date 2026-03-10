# Dark Mode & Theming

## Overview

Dark mode is no longer optional — it's expected. A well-implemented theme system uses design tokens, respects OS preferences, avoids common contrast pitfalls, and transitions smoothly between themes. This guide covers robust theming architecture for modern web applications.

## Theme Architecture

### CSS Custom Properties (Design Tokens)

```css
/* Light theme (default) */
:root {
  /* Surfaces */
  --color-bg: #ffffff;
  --color-bg-secondary: #f8fafc;
  --color-bg-tertiary: #f1f5f9;
  --color-bg-elevated: #ffffff;

  /* Text */
  --color-text: #0f172a;
  --color-text-secondary: #475569;
  --color-text-tertiary: #94a3b8;
  --color-text-inverse: #ffffff;

  /* Borders */
  --color-border: #e2e8f0;
  --color-border-strong: #cbd5e1;

  /* Brand */
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-primary-text: #ffffff;

  /* Semantic */
  --color-success: #16a34a;
  --color-warning: #d97706;
  --color-error: #dc2626;
  --color-info: #2563eb;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);

  /* Focus */
  --color-focus: #2563eb;
  --color-focus-ring: rgba(37, 99, 235, 0.4);
}

/* Dark theme */
[data-theme="dark"] {
  --color-bg: #0f172a;
  --color-bg-secondary: #1e293b;
  --color-bg-tertiary: #334155;
  --color-bg-elevated: #1e293b;

  --color-text: #f1f5f9;
  --color-text-secondary: #94a3b8;
  --color-text-tertiary: #64748b;
  --color-text-inverse: #0f172a;

  --color-border: #334155;
  --color-border-strong: #475569;

  --color-primary: #60a5fa;
  --color-primary-hover: #93bbfd;
  --color-primary-text: #0f172a;

  --color-success: #4ade80;
  --color-warning: #fbbf24;
  --color-error: #f87171;
  --color-info: #60a5fa;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);

  --color-focus: #60a5fa;
  --color-focus-ring: rgba(96, 165, 250, 0.4);
}
```

### Using Tokens in Components

```css
/* Components reference tokens, never raw colors */
.card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  color: var(--color-text);
}

.card-subtitle {
  color: var(--color-text-secondary);
}

button.primary {
  background: var(--color-primary);
  color: var(--color-primary-text);
}

button.primary:hover {
  background: var(--color-primary-hover);
}

button.primary:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}
```

## OS Preference Detection

### CSS Media Query

```css
/* Automatic dark mode from OS preference */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* Dark theme tokens */
    --color-bg: #0f172a;
    --color-text: #f1f5f9;
    /* ... */
  }
}
```

### JavaScript Detection

```javascript
// Detect OS preference
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');

// Listen for changes
prefersDark.addEventListener('change', (e) => {
  if (!getUserThemePreference()) {
    // Only auto-switch if user hasn't manually chosen
    applyTheme(e.matches ? 'dark' : 'light');
  }
});
```

## Theme Switching

### Three-State Toggle (Light / Dark / System)

```tsx
function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'system';
  });

  function applyTheme(newTheme) {
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);

    if (newTheme === 'system') {
      document.documentElement.removeAttribute('data-theme');
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    } else {
      document.documentElement.setAttribute('data-theme', newTheme);
    }
  }

  return (
    <div role="radiogroup" aria-label="Theme preference">
      <button role="radio" aria-checked={theme === 'light'} onClick={() => applyTheme('light')}>
        ☀️ Light
      </button>
      <button role="radio" aria-checked={theme === 'dark'} onClick={() => applyTheme('dark')}>
        🌙 Dark
      </button>
      <button role="radio" aria-checked={theme === 'system'} onClick={() => applyTheme('system')}>
        💻 System
      </button>
    </div>
  );
}
```

### Preventing Flash of Wrong Theme

```html
<!-- In <head>, before any CSS loads -->
<script>
  (function() {
    const theme = localStorage.getItem('theme');
    if (theme === 'dark' || (theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  })();
</script>
```

### Smooth Theme Transition

```css
/* Transition theme changes */
[data-theme] {
  transition: background-color 200ms ease, color 200ms ease;
}

/* Disable transitions during theme switch for snappy feel */
[data-theme-transitioning] * {
  transition: none !important;
}
```

```javascript
function applyTheme(theme) {
  // Disable transitions during switch
  document.documentElement.setAttribute('data-theme-transitioning', '');
  document.documentElement.setAttribute('data-theme', theme);

  // Re-enable transitions after paint
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.documentElement.removeAttribute('data-theme-transitioning');
    });
  });
}
```

## Dark Mode Design Guidelines

### Color Adjustments

**Don't just invert.** Dark mode requires deliberate color choices:

1. **Reduce saturation** — Saturated colors on dark backgrounds cause vibration
2. **Adjust primary colors** — Lighter tints for dark backgrounds (blue-500 → blue-400)
3. **Soften whites** — Pure white (#fff) on dark backgrounds is harsh; use off-white (#f1f5f9)
4. **Increase shadow opacity** — Shadows need more opacity on dark surfaces
5. **Reduce surface contrast steps** — Fewer distinct gray levels needed

### Elevation in Dark Mode

In dark mode, elevation is shown by surface lightness, not shadows:

```css
[data-theme="dark"] {
  /* Higher elevation = lighter surface */
  --color-bg: #0f172a;           /* Base: 0dp */
  --color-bg-elevated-1: #1e293b; /* Card: 1dp */
  --color-bg-elevated-2: #283548; /* Dialog: 2dp */
  --color-bg-elevated-3: #334155; /* Popover: 3dp */
}
```

### Images and Media

```css
/* Reduce image brightness in dark mode */
[data-theme="dark"] img:not([data-theme-aware]) {
  filter: brightness(0.9);
}

/* Invert diagrams and illustrations that are black-on-white */
[data-theme="dark"] img[data-invertible] {
  filter: invert(1) hue-rotate(180deg);
}

/* SVG icons should use currentColor */
.icon {
  color: var(--color-text);
  fill: currentColor;
}
```

### Code Blocks

```css
/* Separate syntax highlighting themes */
[data-theme="light"] .code-block {
  --code-bg: #f8fafc;
  --code-keyword: #7c3aed;
  --code-string: #16a34a;
  --code-comment: #94a3b8;
}

[data-theme="dark"] .code-block {
  --code-bg: #1e293b;
  --code-keyword: #c084fc;
  --code-string: #4ade80;
  --code-comment: #64748b;
}
```

## Advanced Theming

### Multiple Brand Themes

```css
/* Theme = color scheme × brand */
[data-brand="product-a"][data-theme="light"] {
  --color-primary: #2563eb;
  --color-bg: #ffffff;
}

[data-brand="product-a"][data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-bg: #0f172a;
}

[data-brand="product-b"][data-theme="light"] {
  --color-primary: #7c3aed;
  --color-bg: #faf5ff;
}

[data-brand="product-b"][data-theme="dark"] {
  --color-primary: #a78bfa;
  --color-bg: #1a0a2e;
}
```

### High Contrast Mode

```css
/* Support Windows High Contrast Mode */
@media (forced-colors: active) {
  .button {
    border: 2px solid ButtonText;
    /* forced-colors overrides most custom styling */
  }

  .icon {
    /* Ensure icons are visible */
    forced-color-adjust: auto;
  }
}

/* Custom high contrast option */
[data-contrast="high"] {
  --color-text: #000000;
  --color-bg: #ffffff;
  --color-border: #000000;
  --color-text-secondary: #333333;
}
```

## Contrast Testing

### Tools

- **WebAIM Contrast Checker** — Manual checking
- **Chrome DevTools** — Built-in contrast ratio in color picker
- **Figma plugins** — Stark, A11y Color Contrast Checker
- **axe-core** — Automated contrast scanning

### Minimum Ratios

| Element | Against | Minimum Ratio |
|---------|---------|---------------|
| Body text | Background | 4.5:1 (AA) |
| Large text (18pt+) | Background | 3:1 (AA) |
| Interactive borders | Background | 3:1 (AA) |
| Focus rings | Adjacent | 3:1 (AA) |
| Placeholder text | Input background | 4.5:1 (AA) |

## Common Mistakes

### Inverting Colors

- Problem: Simply invert all colors — produces jarring, inconsistent results
- Fix: Design dark mode intentionally with reduced saturation and adjusted tints

### Pure Black Backgrounds

- Problem: #000000 background with white text is harsh and fatiguing
- Fix: Use dark gray (#0f172a, #18181b) for a softer dark mode

### Forgetting Component States

- Problem: Hover, active, disabled states only designed for light mode
- Fix: Test all interactive states in both themes

### Hard-Coded Colors in Components

- Problem: `color: #333` instead of `var(--color-text)` — won't adapt to themes
- Fix: Every color reference uses a design token custom property

### No System Preference Option

- Problem: Only light/dark toggle — forces manual switching
- Fix: Three-state toggle: Light / Dark / System (auto)

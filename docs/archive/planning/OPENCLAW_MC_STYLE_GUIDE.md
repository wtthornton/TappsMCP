# OpenClaw Mission Control — Design System Style Guide

> Version 1.0.0 | March 2026
> Applies to: Mission Control Dashboard (`:3777`)
> Companion to: [OPENCLAW_MISSION_CONTROL_PRD.md](OPENCLAW_MISSION_CONTROL_PRD.md)

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Brand Identity](#brand-identity)
3. [Color System](#color-system)
4. [Typography](#typography)
5. [Spacing & Layout](#spacing--layout)
6. [Border Radius](#border-radius)
7. [Elevation & Shadows](#elevation--shadows)
8. [Motion & Animation](#motion--animation)
9. [Iconography](#iconography)
10. [Components](#components)
11. [Layout Patterns](#layout-patterns)
12. [Data Visualization](#data-visualization)
13. [Accessibility](#accessibility)
14. [Theme Modes](#theme-modes)
15. [Implementation Constraints](#implementation-constraints)

---

## Design Philosophy

Mission Control is a **data-dense operational dashboard** for AI agent monitoring. Every design choice serves legibility, information density, and fast scanning.

| Principle | Rule |
|---|---|
| **Dark-first** | Operators run dashboards for hours; dark mode reduces eye strain and suits ambient/wall-mounted displays |
| **Data-dense** | Maximize information per viewport pixel. Compact spacing, small type, no decorative whitespace |
| **Zero-dependency** | No external CDN calls, no icon font CDN, no Google Fonts. Everything bundled or system-stack |
| **No build step** | Pure CSS — no Sass, PostCSS, or Tailwind. CSS custom properties for theming |
| **Status-first** | Color communicates status before anything else. Green = healthy, amber = warning, red = critical |
| **Industrial, not pretty** | Inspired by flight control systems and server monitoring dashboards (Grafana, Datadog), not consumer apps |

---

## Brand Identity

| Property | Value |
|---|---|
| **Product name** | Mission Control |
| **Tagline** | Air traffic control for your AI workforce |
| **Primary accent** | Cobalt blue `#58a6ff` |
| **Secondary accent** | Amber `#d29922` |
| **Logo concept** | Stylized radar/orbit glyph or lobster claw + satellite dish |
| **Design lineage** | GitHub dark theme palette + Grafana data density |

---

## Color System

### Dark Theme (Default)

#### Core Palette

| Token | CSS Variable | Value | Usage |
|---|---|---|---|
| Background Primary | `--bg-primary` | `#0d1117` | Page background |
| Background Secondary | `--bg-secondary` | `#161b22` | Card backgrounds |
| Background Tertiary | `--bg-tertiary` | `#21262d` | Elevated surfaces, sidebar |
| Background Inset | `--bg-inset` | `#010409` | Code blocks, inset panels |
| Border Default | `--border-default` | `#30363d` | Card borders, dividers |
| Border Muted | `--border-muted` | `#21262d` | Subtle separators |

#### Text Colors

| Token | CSS Variable | Value | Usage |
|---|---|---|---|
| Text Primary | `--text-primary` | `#f0f6fc` | Headings, primary content |
| Text Secondary | `--text-secondary` | `#8b949e` | Descriptions, labels |
| Text Tertiary | `--text-tertiary` | `#6e7681` | Placeholders, timestamps |
| Text Link | `--text-link` | `#58a6ff` | Hyperlinks, clickable text |

#### Accent Colors

| Token | CSS Variable | Value | Usage |
|---|---|---|---|
| Accent Blue | `--accent-blue` | `#58a6ff` | Primary actions, active nav, links |
| Accent Blue Muted | `--accent-blue-muted` | `rgba(56, 139, 253, 0.15)` | Active item background |
| Accent Amber | `--accent-amber` | `#d29922` | Secondary highlight, gold metrics |
| Accent Amber Muted | `--accent-amber-muted` | `rgba(210, 153, 34, 0.15)` | Warning background tint |

#### Status Colors

| Status | Color | Muted BG | Text | Indicator |
|---|---|---|---|---|
| Healthy / Active | `--status-green` `#3fb950` | `rgba(63, 185, 80, 0.12)` | `#3fb950` | Filled circle |
| Warning / Idle | `--status-amber` `#d29922` | `rgba(210, 153, 34, 0.12)` | `#d29922` | Half circle |
| Error / Critical | `--status-red` `#f85149` | `rgba(248, 81, 73, 0.12)` | `#f85149` | Filled triangle |
| Info / Neutral | `--status-blue` `#58a6ff` | `rgba(56, 139, 253, 0.12)` | `#58a6ff` | Filled diamond |
| Offline / Disabled | `--status-gray` `#484f58` | `rgba(72, 79, 88, 0.12)` | `#6e7681` | Empty circle |

#### Interactive State Tokens

| Token | CSS Variable | Value | Usage |
|---|---|---|---|
| Hover Background | `--hover-bg` | `rgba(177, 186, 196, 0.08)` | Row hover, button hover |
| Active Background | `--active-bg` | `rgba(177, 186, 196, 0.12)` | Pressed state |
| Focus Ring | `--focus-ring` | `rgba(56, 139, 253, 0.5)` | Focus-visible outline |
| Selected Background | `--selected-bg` | `rgba(56, 139, 253, 0.15)` | Active nav item, selected row |

### Light Theme (Optional)

Light theme is secondary — most operators prefer dark. Provide as opt-in.

| Token | Light Value | Notes |
|---|---|---|
| `--bg-primary` | `#ffffff` | White base |
| `--bg-secondary` | `#f6f8fa` | Light gray cards |
| `--bg-tertiary` | `#eaeef2` | Elevated surfaces |
| `--border-default` | `#d0d7de` | Visible borders |
| `--text-primary` | `#1f2328` | Near-black text |
| `--text-secondary` | `#656d76` | Gray descriptions |
| `--accent-blue` | `#0969da` | Darker blue for contrast |
| `--status-green` | `#1a7f37` | Darker green for contrast |
| `--status-red` | `#cf222e` | Darker red for contrast |

### Semantic Aliases

```css
--color-brand:    var(--accent-blue);
--color-danger:   var(--status-red);
--color-caution:  var(--status-amber);
--color-positive: var(--status-green);
--color-neutral:  var(--text-tertiary);
```

---

## Typography

### Font Stack

No external font loading. System fonts only for body; bundled JetBrains Mono for metrics.

| Role | Font Family | CSS Variable | Stack |
|---|---|---|---|
| **Body** (UI text) | System sans-serif | `--font-sans` | `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif` |
| **Mono** (metrics, code) | JetBrains Mono | `--font-mono` | `"JetBrains Mono", "SF Mono", "Cascadia Code", ui-monospace, monospace` |

JetBrains Mono is bundled as a WOFF2 variable font file (~95KB) in `fonts/`. No CDN.

### Size Scale

Base size: **14px** (`0.875rem`). Optimized for data density.

| Token | Size | Pixels | Usage |
|---|---|---|---|
| `--text-2xs` | `0.625rem` | 10px | Tiny timestamps, badge counts |
| `--text-xs` | `0.6875rem` | 11px | Small labels, table headers |
| `--text-sm` | `0.75rem` | 12px | Secondary text, descriptions |
| `--text-base` | `0.875rem` | **14px** | Body text, form inputs |
| `--text-lg` | `1rem` | 16px | Card titles, section headers |
| `--text-xl` | `1.25rem` | 20px | Page titles, h2 |
| `--text-2xl` | `1.5rem` | 24px | Dashboard hero metrics |
| `--text-3xl` | `2rem` | 32px | Large metric displays (cost totals) |

### Weight Scale

| Token | Weight | Usage |
|---|---|---|
| `--font-normal` | 400 | Body text, descriptions |
| `--font-medium` | 500 | Labels, nav items, table headers |
| `--font-semibold` | 600 | Card titles, section headers |
| `--font-bold` | 700 | Page titles, hero metrics |

### Line Height Scale

| Token | Value | Usage |
|---|---|---|
| `--leading-none` | 1 | Metric display numbers |
| `--leading-tight` | 1.25 | Headings, compact labels |
| `--leading-normal` | 1.5 | Body text, descriptions |
| `--leading-relaxed` | 1.625 | Readable paragraphs (docs, tooltips) |

### Typography Patterns

```css
/* Page title */
.mc-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

/* Card title */
.mc-card-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

/* Metric value (big number) */
.mc-metric {
  font-family: var(--font-mono);
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  font-variant-numeric: tabular-nums;
  line-height: var(--leading-none);
  letter-spacing: -0.02em;
}

/* Label (uppercase) */
.mc-label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Monospace (code, IDs, timestamps) */
.mc-mono {
  font-family: var(--font-mono);
  font-size: 0.9em;
  font-variant-numeric: tabular-nums;
}
```

### Font Features

```css
body {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

/* Metric numbers: tabular figures for aligned columns */
.mc-metric, .mc-mono, td.number {
  font-variant-numeric: tabular-nums;
}
```

---

## Spacing & Layout

### Base Unit: 4px

| Token | Value | Pixels | Usage |
|---|---|---|---|
| `--space-0` | `0` | 0 | Reset |
| `--space-1` | `0.25rem` | 4px | Tight inline spacing |
| `--space-2` | `0.5rem` | 8px | Badge padding, icon gaps |
| `--space-3` | `0.75rem` | 12px | Card internal padding (compact) |
| `--space-4` | `1rem` | 16px | Standard card padding |
| `--space-5` | `1.25rem` | 20px | Section gaps |
| `--space-6` | `1.5rem` | 24px | Large section padding |
| `--space-8` | `2rem` | 32px | Page margins |
| `--space-10` | `2.5rem` | 40px | Hero spacing |

### Gap Scale

| Token | Value | Usage |
|---|---|---|
| `--gap-tight` | `0.5rem` (8px) | Grid items in dense panels |
| `--gap-normal` | `0.75rem` (12px) | Standard card grid |
| `--gap-loose` | `1rem` (16px) | Section-level spacing |

---

## Border Radius

Tight radii — this is an operational dashboard, not a consumer app.

| Token | Value | Pixels | Usage |
|---|---|---|---|
| `--radius-none` | `0` | 0 | Table cells, inset panels |
| `--radius-sm` | `0.1875rem` | 3px | Badges, small buttons |
| `--radius-md` | `0.375rem` | 6px | Cards, inputs, dropdowns |
| `--radius-lg` | `0.5rem` | 8px | Modals, popovers |
| `--radius-full` | `9999px` | Pill | Status dots, pill badges |

---

## Elevation & Shadows

### 3-Tier System

No backdrop blur. Blur is expensive, fragile on older GPUs, and adds no value for data-dense dashboards.

| Tier | Class | Background | Shadow |
|---|---|---|---|
| **Surface** | `.mc-surface` | `var(--bg-secondary)` | `0 1px 0 var(--border-default)` |
| **Raised** | `.mc-raised` | `var(--bg-secondary)` | `0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)` |
| **Floating** | `.mc-floating` | `var(--bg-tertiary)` | `0 3px 12px rgba(0,0,0,0.28), 0 0 1px rgba(0,0,0,0.3)` |

### Card Style

```css
.mc-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

/* Status-left-border card */
.mc-card[data-status="healthy"] { border-left: 3px solid var(--status-green); }
.mc-card[data-status="warning"] { border-left: 3px solid var(--status-amber); }
.mc-card[data-status="error"]   { border-left: 3px solid var(--status-red); }
```

---

## Motion & Animation

Minimal animation. Operators stare at this dashboard for hours — nothing should distract.

### Timing

| Token | Duration | Usage |
|---|---|---|
| `--motion-fast` | `100ms` | Hover states, focus rings |
| `--motion-normal` | `200ms` | Panel transitions, collapses |
| `--motion-slow` | `350ms` | Page-level transitions |

### Easing

| Token | Curve | Usage |
|---|---|---|
| `--ease-default` | `cubic-bezier(0.4, 0, 0.2, 1)` | General transitions |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Elements exiting |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Elements entering |

### Allowed Animations

| Animation | Duration | Usage |
|---|---|---|
| `fadeIn` | 200ms | New content appearing |
| `slideDown` | 200ms | Expanding panels / accordions |
| `countUp` | 300ms | Metric value updates (opacity + subtle scale) |
| `pulse` | 2s infinite | Active alert indicator (opacity 0.6 → 1 → 0.6) |

### Disallowed

- No bounces, spring physics, or playful motion
- No skeleton shimmer (show real data or a simple spinner)
- No parallax, float, or wiggle effects
- No entry animations on page load (instant render)

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Iconography

### Source

No icon font library. Use inline SVG for the ~30 icons needed:

| Category | Icons Needed |
|---|---|
| Navigation | Dashboard, Sessions, Cron, Topics, Router, Governance, Config, Settings |
| Status | Circle (fill/empty/half), Triangle (alert), Checkmark, Cross |
| Actions | Play, Pause, Stop, Refresh, Edit, Delete, Expand, Collapse |
| System | CPU, Memory, Disk, Network, Clock, Dollar, Key |

### Specifications

| Property | Value |
|---|---|
| Size (nav) | 16x16px |
| Size (inline) | 14x14px |
| Size (hero) | 24x24px |
| Stroke width | 1.5px |
| Color | `currentColor` (inherits text color) |
| Style | Outlined, consistent weight, rounded caps |

SVG icons are embedded directly in HTML or stored in a single `icons.js` module exporting template literal strings. No sprite sheet, no icon font.

---

## Components

### Buttons

| Variant | Background | Text | Border |
|---|---|---|---|
| **Primary** | `var(--accent-blue)` | `#ffffff` | none |
| **Secondary** | transparent | `var(--text-secondary)` | `1px solid var(--border-default)` |
| **Danger** | `var(--status-red)` | `#ffffff` | none |
| **Ghost** | transparent | `var(--text-secondary)` | none |

```css
.mc-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  line-height: 20px;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-default);
}
.mc-btn:active { transform: scale(0.98); }
.mc-btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

### Status Badge

```css
.mc-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--text-2xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.mc-badge--green  { background: rgba(63,185,80,0.12);  color: var(--status-green); }
.mc-badge--amber  { background: rgba(210,153,34,0.12); color: var(--status-amber); }
.mc-badge--red    { background: rgba(248,81,73,0.12);  color: var(--status-red); }
.mc-badge--blue   { background: rgba(56,139,253,0.12); color: var(--status-blue); }
.mc-badge--gray   { background: rgba(72,79,88,0.12);   color: var(--text-tertiary); }
```

### Status Dot

```css
.mc-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  display: inline-block;
}
.mc-dot--green  { background: var(--status-green); }
.mc-dot--amber  { background: var(--status-amber); }
.mc-dot--red    { background: var(--status-red); animation: pulse 2s infinite; }
.mc-dot--gray   { background: var(--status-gray); }
```

### Gauge / Progress Bar

For LLM Fuel Gauges and quota visualization:

```css
.mc-gauge {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.mc-gauge__fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--motion-normal) var(--ease-default);
}
/* Color thresholds */
.mc-gauge__fill[data-level="normal"]  { background: var(--status-green); }
.mc-gauge__fill[data-level="warning"] { background: var(--status-amber); }
.mc-gauge__fill[data-level="danger"]  { background: var(--status-red); }
```

### Table / Data Grid

Primary data display component. Sessions, cron jobs, audit trails.

```css
.mc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.mc-table th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-default);
}
.mc-table td {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-muted);
  color: var(--text-primary);
  vertical-align: middle;
}
.mc-table tr:hover td {
  background: var(--hover-bg);
}
/* Numeric columns right-aligned with mono font */
.mc-table td.number {
  text-align: right;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
```

### Alert Banner

Top-of-page alerts for critical conditions (loop detected, gateway offline, budget exceeded):

```css
.mc-alert {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  border-bottom: 1px solid;
}
.mc-alert--red    { background: rgba(248,81,73,0.08);  border-color: rgba(248,81,73,0.3);  color: var(--status-red); }
.mc-alert--amber  { background: rgba(210,153,34,0.08); border-color: rgba(210,153,34,0.3); color: var(--status-amber); }
.mc-alert--blue   { background: rgba(56,139,253,0.08); border-color: rgba(56,139,253,0.3); color: var(--status-blue); }
```

### Modal / Dialog

```css
.mc-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 50;
}
.mc-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  max-width: 480px;
  width: 90vw;
  z-index: 51;
}
```

### Input / Form Controls

```css
.mc-input {
  width: 100%;
  padding: 6px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-base);
  line-height: 20px;
  transition: border-color var(--motion-fast) var(--ease-default);
}
.mc-input:focus {
  border-color: var(--accent-blue);
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.mc-input::placeholder { color: var(--text-tertiary); }
```

### Toggle Switch

For cron enable/disable, feature flags:

```css
.mc-toggle {
  width: 36px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition: background var(--motion-fast);
  position: relative;
}
.mc-toggle[aria-checked="true"] {
  background: var(--status-green);
  border-color: transparent;
}
.mc-toggle::after {
  content: '';
  width: 14px;
  height: 14px;
  border-radius: var(--radius-full);
  background: #ffffff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform var(--motion-fast);
}
.mc-toggle[aria-checked="true"]::after { transform: translateX(16px); }
```

---

## Layout Patterns

### Page Structure

```
┌─────────────────────────────────────────────────────────────┐
│ Alert Banner (conditional — loop detected, budget exceeded)  │
├────────┬────────────────────────────────────────────────────┤
│        │  ┌──────────────────────────────────────────────┐  │
│ Sidebar│  │ Page Header   [Actions]                      │  │
│  48px  │  ├──────────────────────────────────────────────┤  │
│  wide  │  │                                              │  │
│  icons │  │             Main Content                     │  │
│  only  │  │          (cards, tables, charts)             │  │
│        │  │                                              │  │
│ ┌────┐ │  │                                              │  │
│ │ D  │ │  │                                              │  │
│ │ S  │ │  │                                              │  │
│ │ C  │ │  │                                              │  │
│ │ T  │ │  │                                              │  │
│ │ R  │ │  │                                              │  │
│ │ G  │ │  │                                              │  │
│ │ M  │ │  │                                              │  │
│ │ ⚙ │ │  │                                              │  │
│ └────┘ │  │                                              │  │
│        │  └──────────────────────────────────────────────┘  │
├────────┴────────────────────────────────────────────────────┤
│ Status Bar: Gateway status │ Uptime │ Version │ Connections  │
└─────────────────────────────────────────────────────────────┘
```

### Sidebar (Icon Rail)

- Fixed 48px-wide icon-only sidebar on desktop
- Active item: `--selected-bg` background + `--accent-blue` icon color
- Hover: `--hover-bg` background
- Tooltip on hover showing page name (pure CSS `::after`)
- Mobile: collapses to a bottom tab bar (5 priority items)

### Dashboard Grid

```css
.mc-grid {
  display: grid;
  gap: var(--gap-normal);
}
/* Summary cards row */
.mc-grid--summary {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
/* Main content + sidebar */
.mc-grid--page {
  grid-template-columns: 1fr;
}
@media (min-width: 1024px) {
  .mc-grid--page { grid-template-columns: 1fr 320px; }
}
```

### Responsive Breakpoints

| Breakpoint | Width | Layout Change |
|---|---|---|
| `sm` | 640px | 2-column summary cards |
| `md` | 768px | Sidebar visible (icon rail) |
| `lg` | 1024px | Side panel visible (details/inspector) |
| `xl` | 1280px | Full dashboard layout, wider tables |

### Scrollbar Styling

```css
* {
  scrollbar-color: #484f58 transparent;
  scrollbar-width: thin;
}
::-webkit-scrollbar       { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #484f58; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #6e7681; }
```

---

## Data Visualization

### Charts

All charts rendered as **inline SVG** — no charting library (D3, Chart.js). Keep bundle at zero external dependencies.

| Chart Type | Use Case | Implementation |
|---|---|---|
| **Sparkline** | Cost trends in summary cards | SVG `<polyline>` |
| **Bar chart** | Model usage distribution | SVG `<rect>` elements |
| **Gauge arc** | Quota percentage | SVG `<circle>` with `stroke-dashoffset` |
| **Timeline** | Cron schedule visualization | SVG `<rect>` on a time axis |
| **Tree** | Subagent hierarchy | Nested `<div>` with CSS connectors or SVG `<line>` |

### Chart Colors

Use status colors for data meaning. For categorical data (model types), use a muted 5-color palette:

| Index | Color | Usage |
|---|---|---|
| 0 | `#58a6ff` (blue) | Primary model / highest usage |
| 1 | `#3fb950` (green) | Secondary / local models |
| 2 | `#d29922` (amber) | Tertiary |
| 3 | `#bc8cff` (purple) | Quaternary |
| 4 | `#f0883e` (orange) | Quinary |

### Number Formatting

| Type | Format | Example |
|---|---|---|
| Token counts | Compact notation | `12.4k`, `1.2M` |
| Cost (USD) | 2 decimal places | `$3.47`, `$127.50` |
| Percentages | Integer or 1 decimal | `67%`, `99.5%` |
| Durations | Human-readable | `2m ago`, `3h 22m`, `14d` |
| Timestamps | Relative + absolute tooltip | `2m ago` / `2026-03-02 14:30:22 UTC` |

---

## Accessibility

### WCAG 2.2 AA Compliance

| Requirement | Target | Implementation |
|---|---|---|
| Text contrast | 4.5:1 minimum | All text tokens verified against `--bg-primary` and `--bg-secondary` |
| Large text contrast | 3:1 minimum | Headings, metrics |
| UI component contrast | 3:1 minimum | Borders, icons against backgrounds |
| Target size | 24x24 CSS px minimum | All clickable elements (buttons, nav, toggles) |
| Focus indicator | Visible, sufficient area | `--focus-ring` outline on `:focus-visible` |

### Contrast Verification (Dark Theme)

| Pair | Ratio | Passes |
|---|---|---|
| `--text-primary` (#f0f6fc) on `--bg-primary` (#0d1117) | 15.3:1 | AA + AAA |
| `--text-secondary` (#8b949e) on `--bg-primary` (#0d1117) | 5.0:1 | AA |
| `--text-secondary` (#8b949e) on `--bg-secondary` (#161b22) | 4.5:1 | AA |
| `--status-green` (#3fb950) on `--bg-primary` (#0d1117) | 7.9:1 | AA + AAA |
| `--status-red` (#f85149) on `--bg-primary` (#0d1117) | 5.6:1 | AA |
| `--status-amber` (#d29922) on `--bg-primary` (#0d1117) | 7.2:1 | AA + AAA |
| `--accent-blue` (#58a6ff) on `--bg-primary` (#0d1117) | 6.5:1 | AA + AAA |

### Focus-Visible System

```css
:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
:focus:not(:focus-visible) { outline: none; }
```

### Color-Independent Status

Status is **never** communicated by color alone:

| Status | Color | Shape | Text |
|---|---|---|---|
| Healthy | Green dot | Filled circle | "Active" / "Healthy" |
| Warning | Amber dot | Half circle or triangle | "Idle" / "Warning" |
| Error | Red dot (pulsing) | Filled triangle | "Error" / "Critical" |
| Offline | Gray dot | Empty circle | "Offline" / "Disconnected" |

### Keyboard Navigation

- All interactive elements reachable via Tab
- Sidebar nav: arrow keys for item navigation
- Tables: row focus with Enter to expand
- Modals: focus trap, Escape to close
- Shortcuts: `?` for help overlay listing all shortcuts

### Screen Reader Support

- `<nav>` landmark for sidebar
- `aria-label` on all icon-only buttons
- `role="status"` on live-updating metrics (with `aria-live="polite"`)
- `role="alert"` on alert banners (with `aria-live="assertive"`)
- `<table>` with proper `<thead>`, `<tbody>`, `scope` attributes

---

## Theme Modes

### 2 Modes

| Mode | Activation | Description |
|---|---|---|
| **Dark** (default) | No class / `:root` | Deep blue-black backgrounds, high-contrast text |
| **Light** | `[data-theme="light"]` on `<html>` | White backgrounds, darker accents for contrast |

### Switching

Theme preference stored in `localStorage`. Applied before first paint via inline `<script>` in `<head>` to prevent flash:

```html
<script>
  const t = localStorage.getItem('mc-theme');
  if (t === 'light') document.documentElement.dataset.theme = 'light';
</script>
```

### CSS Custom Properties Swap

All color tokens are defined in `:root` (dark) and `[data-theme="light"]` (light). Components reference only CSS variables — no hardcoded colors anywhere.

---

## Implementation Constraints

### Zero-Dependency Rule

| Allowed | Not Allowed |
|---|---|
| Vanilla JS (ES2022+), ES Modules | React, Vue, Angular, Svelte, or any framework |
| CSS custom properties, `@media`, `@layer` | Sass, PostCSS, Less, Tailwind, or any CSS preprocessor |
| Inline SVG for icons and charts | Icon font CDNs (Font Awesome, Material Icons) |
| Bundled WOFF2 for JetBrains Mono | Google Fonts, external font CDNs |
| `<template>` elements for HTML cloning | JSX, template engines (Handlebars, EJS) |
| Native `fetch`, `WebSocket`, `EventSource` | Axios, Socket.IO, or HTTP client libraries |

### File Size Budget

| Asset | Target | Max |
|---|---|---|
| HTML (index.html) | < 5 KB | 10 KB |
| CSS (style.css) | < 15 KB | 25 KB |
| JS (all modules) | < 100 KB | 200 KB |
| Font (JetBrains Mono WOFF2) | ~95 KB | 120 KB |
| Icons (SVG inlined or module) | < 5 KB | 10 KB |
| **Total bundle** | **< 220 KB** | **365 KB** |

### Browser Support

| Browser | Version |
|---|---|
| Chrome / Edge | Last 2 versions |
| Firefox | Last 2 versions |
| Safari | Last 2 versions |

ES modules, CSS custom properties, `:has()`, `container queries`, and `scrollbar-color` are all supported in these targets.

---

*Source of truth: This document. No separate `designSystem.ts` or stale config files. CSS variables in `style.css` are canonical.*

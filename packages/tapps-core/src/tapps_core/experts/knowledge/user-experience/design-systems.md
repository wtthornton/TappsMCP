# Design Systems & Component Libraries

## Overview

A design system is a collection of reusable components, design tokens, guidelines, and tooling that enables teams to build consistent, accessible, and scalable user interfaces. In 2026, design systems bridge design tools (Figma, Penpot) and code (React, Vue, Web Components) through tokens and automated pipelines.

## Design Tokens

### What Are Design Tokens

Design tokens are the atomic values of a design system — colors, spacing, typography, shadows, borders, motion — stored in a platform-agnostic format and transformed into platform-specific outputs.

```json
{
  "color": {
    "primary": {
      "50": { "$value": "#eff6ff", "$type": "color" },
      "500": { "$value": "#3b82f6", "$type": "color" },
      "900": { "$value": "#1e3a5f", "$type": "color" }
    }
  },
  "spacing": {
    "xs": { "$value": "4px", "$type": "dimension" },
    "sm": { "$value": "8px", "$type": "dimension" },
    "md": { "$value": "16px", "$type": "dimension" },
    "lg": { "$value": "24px", "$type": "dimension" },
    "xl": { "$value": "32px", "$type": "dimension" }
  },
  "font": {
    "family": {
      "sans": { "$value": "Inter, system-ui, sans-serif", "$type": "fontFamily" },
      "mono": { "$value": "JetBrains Mono, monospace", "$type": "fontFamily" }
    },
    "size": {
      "sm": { "$value": "0.875rem", "$type": "dimension" },
      "base": { "$value": "1rem", "$type": "dimension" },
      "lg": { "$value": "1.125rem", "$type": "dimension" },
      "xl": { "$value": "1.25rem", "$type": "dimension" }
    }
  }
}
```

### Token Naming Conventions

Use a three-tier naming structure:

1. **Global tokens** — Raw values: `color-blue-500`, `spacing-16`
2. **Alias tokens** — Semantic mapping: `color-primary`, `spacing-md`
3. **Component tokens** — Scoped to components: `button-bg-primary`, `card-padding`

```css
/* Global tokens */
--color-blue-500: #3b82f6;
--spacing-16: 1rem;

/* Alias tokens (reference globals) */
--color-primary: var(--color-blue-500);
--spacing-md: var(--spacing-16);

/* Component tokens (reference aliases) */
--button-bg: var(--color-primary);
--button-padding: var(--spacing-md);
```

### Token Tooling

- **Style Dictionary** — Transform tokens to CSS, iOS, Android, Flutter
- **Tokens Studio (Figma plugin)** — Sync tokens between Figma and code
- **Design Tokens W3C spec (DTCG)** — Standardized JSON format ($value, $type)
- **Cobalt UI** — Token pipeline with W3C DTCG support

## Component Architecture

### Compound Component Pattern

Build complex components from composable primitives:

```tsx
// Compound component API
<Select>
  <Select.Trigger>
    <Select.Value placeholder="Choose..." />
  </Select.Trigger>
  <Select.Content>
    <Select.Item value="opt1">Option 1</Select.Item>
    <Select.Item value="opt2">Option 2</Select.Item>
  </Select.Content>
</Select>
```

Benefits:
- Flexible composition without prop drilling
- Each sub-component manages its own concerns
- Easy to extend without breaking API

### Headless Components

Separate behavior from presentation:

```tsx
// Headless component provides logic, consumer provides UI
function useToggle(initial = false) {
  const [on, setOn] = useState(initial);
  const toggle = useCallback(() => setOn(v => !v), []);
  return { on, toggle, setOn };
}

// Usage — consumer controls all styling
function CustomSwitch() {
  const { on, toggle } = useToggle();
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={toggle}
      className={on ? 'bg-blue-600' : 'bg-gray-300'}
    >
      {on ? 'On' : 'Off'}
    </button>
  );
}
```

Leading headless libraries (2026):
- **Radix UI** — Primitives with full a11y
- **React Aria (Adobe)** — ARIA-compliant hooks
- **Headless UI (Tailwind)** — Minimal, composable
- **Ark UI** — Framework-agnostic (React, Vue, Solid)

### Variant Pattern

Use variant APIs for component flexibility:

```tsx
// Using class-variance-authority (cva)
import { cva } from 'class-variance-authority';

const button = cva('rounded font-medium transition-colors', {
  variants: {
    intent: {
      primary: 'bg-blue-600 text-white hover:bg-blue-700',
      secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200',
      danger: 'bg-red-600 text-white hover:bg-red-700',
    },
    size: {
      sm: 'text-sm px-3 py-1.5',
      md: 'text-base px-4 py-2',
      lg: 'text-lg px-6 py-3',
    },
  },
  defaultVariants: {
    intent: 'primary',
    size: 'md',
  },
});
```

## Component Documentation

### What to Document

Every component needs:

1. **Purpose** — What problem this component solves
2. **API reference** — All props with types, defaults, descriptions
3. **Usage examples** — Common patterns and edge cases
4. **Accessibility** — ARIA roles, keyboard interactions, screen reader behavior
5. **Do/Don't** — Visual examples of correct and incorrect usage
6. **Design specs** — Token usage, spacing, responsive behavior

### Storybook Best Practices

```tsx
// Component story with controls and documentation
export default {
  title: 'Components/Button',
  component: Button,
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'danger'],
      description: 'Visual style variant',
    },
    size: {
      control: 'radio',
      options: ['sm', 'md', 'lg'],
    },
    disabled: { control: 'boolean' },
  },
};

// Interactive playground
export const Playground = {
  args: {
    children: 'Click me',
    variant: 'primary',
    size: 'md',
  },
};

// Documented variants
export const AllVariants = () => (
  <div className="flex gap-4">
    <Button variant="primary">Primary</Button>
    <Button variant="secondary">Secondary</Button>
    <Button variant="danger">Danger</Button>
  </div>
);
```

## Design-to-Code Workflow

### Figma Integration

Modern design-to-code pipeline:

1. **Design in Figma** using token-backed styles and auto-layout
2. **Export tokens** via Tokens Studio plugin → JSON
3. **Transform tokens** via Style Dictionary → CSS custom properties
4. **Generate components** using Figma code generation or manual build
5. **Validate** — Visual regression tests (Chromatic, Percy)

### Component Checklist

Before shipping a component:

- [ ] Renders correctly across all variants and sizes
- [ ] Keyboard navigable (Tab, Enter, Escape, Arrow keys as appropriate)
- [ ] Screen reader tested (announces role, state, label)
- [ ] Supports `ref` forwarding
- [ ] Responsive across breakpoints
- [ ] Supports dark/light themes via tokens
- [ ] Has loading/disabled/error states
- [ ] Visual regression snapshot captured
- [ ] Bundle size measured and acceptable
- [ ] Documentation and stories complete

## Popular Design Systems (2026)

| System | Framework | Approach | Strengths |
|--------|-----------|----------|-----------|
| shadcn/ui | React | Copy-paste, Tailwind | Full control, no dependency |
| Radix UI | React | Headless primitives | Best accessibility |
| Material UI (MUI) | React | Styled, themed | Comprehensive, mature |
| Chakra UI | React | Styled props | DX, composable |
| Ant Design | React | Enterprise | Data-heavy UIs |
| Mantine | React | Hooks + components | Batteries included |
| Vuetify | Vue | Material Design | Vue ecosystem standard |
| PrimeVue | Vue | Enterprise | Rich component set |
| Shoelace | Web Components | Framework-agnostic | Works everywhere |

### shadcn/ui Pattern (2026 Dominant)

The copy-paste model has become dominant because:
- Components live in your codebase, not node_modules
- Full customization without fighting library internals
- Built on Radix primitives (accessibility guaranteed)
- Tailwind CSS for styling (token-aligned)
- No version upgrade burden

```bash
# Add a component to your project
npx shadcn@latest add button dialog toast
```

## Lessons From Industry Leaders

### Stripe — Documentation as Product

Stripe's design system treats documentation as a first-class product:
- Interactive code examples that run in-browser
- Copy-paste snippets for every component and API pattern
- Error messages that explain what went wrong AND how to fix it
- Onboarding flow gets users to first success in minutes
- Takeaway: your component docs should be as polished as your components

### Shopify Polaris — Content Guidelines

Polaris includes UX writing standards alongside component specs:
- Tone and voice guidelines for every component type
- Do/Don't examples with visual comparisons
- Merchant-focused patterns (product management, order flows)
- Takeaway: design systems should include content design, not just visual design

### IBM Carbon — Accessibility First

Carbon proves enterprise-grade accessibility is achievable:
- WCAG 2.2 AA compliant across every component
- Extensive data visualization accessibility (patterns, not just color)
- Framework-agnostic (React, Angular, Vue, Web Components)
- 1:1 parity between Figma kit and code components
- Takeaway: accessibility should be built into the system, not added per-component

### Linear — Opinionated Defaults

Linear's design system philosophy: reduce decisions, not options:
- Strong defaults that work for 90% of cases
- Keyboard-first — every action has a shortcut
- Command palette (Cmd+K) as the primary power-user navigation
- Takeaway: opinionated defaults reduce cognitive load; escape hatches serve power users

## Common Mistakes

### Over-Engineering the System

- Building components nobody needs yet
- Creating too many variants before validating usage
- Designing for hypothetical future requirements
- Fix: Start with 5-10 core components, expand based on actual usage

### Token Sprawl

- Too many similar tokens (gray-50 through gray-950 when only 5 are used)
- Inconsistent naming across platforms
- Fix: Audit token usage quarterly, remove unused tokens

### Ignoring Accessibility in Components

- Building custom components without ARIA attributes
- Not testing keyboard navigation
- Fix: Use headless primitives (Radix, React Aria) as foundation

### No Versioning Strategy

- Breaking changes without migration paths
- Fix: Semantic versioning, changelogs, codemods for breaking changes

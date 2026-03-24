# Dual-surface operational UI (admin HTMX + SPA)

## Purpose

Many B2B / internal products ship **two coordinated frontends**: a **server-rendered admin or operations console** (often with HTMX or light JS) and a **separate product SPA** (often React + utility CSS). Consultations on layout, theming, or components must **not conflate the two shells** unless an explicit unification program exists.

This note encodes patterns aligned with mature **dual-surface** style guides (including TheStudio-style admin + pipeline splits).

## Surface A — Admin / operations console

- **Typical stack:** server-rendered templates + partial refresh (e.g. HTMX).
- **Common shell:** **dark sidebar rail** + **light content canvas** (white header, white cards on gray page background).
- **Theme policy:** if there is **no** user-facing dark-mode toggle, do **not** treat full dark-mode parity as a default acceptance criterion for that surface; plan it as a dedicated follow-up with tokens, contrast audit, and migration.
- **Layout cues (Tailwind-style examples, not mandatory literals):** page `bg-gray-50 text-gray-900`, sidebar `w-56 bg-gray-900 text-gray-100`, main header `bg-white border-b border-gray-200`, cards `bg-white rounded-lg border border-gray-200`, section titles `text-sm font-semibold text-gray-500 uppercase tracking-wide`.

## Surface B — Pipeline / product SPA

- **Typical stack:** SPA (e.g. React) + Tailwind or design tokens.
- **Common shell:** **dark-first** operational canvas (distinct from the admin shell).
- **Rule:** visual systems may differ, but **semantics and state UX** must stay aligned with Surface A (see below).

## Cross-surface invariants (mandatory)

Apply on **both** surfaces:

1. **Status semantics:** the same color means the same state everywhere (success / warning / error / in-progress / neutral).
2. **Explicit states:** every async or data-backed view defines **loading**, **empty**, and **error** (copy + layout stability; avoid layout jump).
3. **Accessibility:** keyboard reachability, visible focus, semantic tables/lists; **do not rely on color alone** — keep text labels (`OK`, `FAILED`, `STUCK`, etc.) on badges and KPIs where color reinforces meaning.
4. **Recency / refresh:** when using partial refresh (e.g. HTMX polling), show **in-flight refresh** affordance and **last updated** time in the chrome users scan first (often header).

## Anti-patterns

- Copying the **SPA dark shell** onto the **admin console** (or vice versa) without an explicit design decision.
- **Color-only** KPI or status communication (numeric hue without label).
- Silent failure: swapping partial HTML with no loading or error path.

## When answering design questions

- Ask which **surface** the user is changing before prescribing classes or components.
- Prefer **incremental alignment** (semantics, states, a11y) over **forced visual unification** across surfaces.

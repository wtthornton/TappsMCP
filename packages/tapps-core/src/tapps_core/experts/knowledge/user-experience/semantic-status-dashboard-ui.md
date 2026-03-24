# Semantic color, badges, and operational dashboards

## Purpose

Operational dashboards (fleet health, workflows, repos, metrics) need **fast scanning** and **shared meaning** across pages. This document summarizes **semantic color**, **badge**, and **table** patterns suitable for Tailwind-style admin UIs and cross-surface SPAs.

## Status and severity (production-style mapping)

Use **consistent** background + text pairs for pills and KPI numerals:

| Meaning | Example utility pairing (illustrative) |
|--------|----------------------------------------|
| Success / OK / healthy | `bg-green-100 text-green-800`; KPI numeral `text-green-600` |
| Warning / degraded / stuck | `bg-yellow-100 text-yellow-800`; KPI `text-yellow-600` |
| Error / failed / unhealthy | `bg-red-100 text-red-800`; KPI `text-red-600` |
| In progress / running / info | `bg-blue-100 text-blue-800`; links `text-blue-600` |
| Neutral / unknown | `bg-gray-100 text-gray-700` |

**Rule:** if a metric uses color, repeat the **category word** under or beside the number (`Running`, `Stuck`, `Failed`) so color is not the only cue.

## Trust tier mapping (automation / agent products)

| Tier | Suggested accent |
|------|------------------|
| EXECUTE | purple tint |
| SUGGEST | blue tint |
| OBSERVE | gray tint |

Keep tier badges **short** (`OBS` / `SUGG` / `EXEC`) only if a **legend or tooltip** exists; otherwise prefer readable words for clarity.

## Role mapping (admin consoles)

| Role | Example |
|------|---------|
| ADMIN | red-tint badge |
| OPERATOR | yellow-tint badge |
| Other / default | blue-tint badge |

## Tables (operational density)

- Container: white card + `overflow-hidden`.
- Header row: `bg-gray-50`, header text `text-xs text-gray-500 uppercase`.
- Body: `divide-y divide-gray-100`, row hover `hover:bg-gray-50`.
- **Numeric columns right-aligned.**
- Header **tooltips** (short definitions): support **keyboard focus** (`:focus-visible`) in addition to hover so operators using keyboards get the same hints.

## Buttons and links (admin chrome)

- **Primary:** blue fill `bg-blue-600 text-white hover:bg-blue-700`.
- **Secondary:** gray fill `bg-gray-600 text-white hover:bg-gray-700`.
- **Destructive:** red text or red button treatment.
- **Resource links:** blue text, underline on hover.

## Dashboard visualization guardrails (2025–2026)

- **Overview first:** top of page surfaces the 3–4 critical KPIs before detail tables.
- **Fast encodings:** prefer position / bar / line over pie or heavy gauge-first layouts for **operational** decisions.
- **Limit palette cardinality:** ~5–6 distinguishable categories before grouping.
- **No low-contrast text on chart fills;** add non-color cues (labels, icons, separators).

## Empty and error copy

- **Empty:** plain language what is missing + **next action** (link or primary CTA to the screen where data is configured).
- **Error:** red-tint panel `bg-red-50 border-red-200 text-red-800`; **warning** yellow-tint; **success/info** green-tint where appropriate.

## Deferred by default

Unless explicitly in scope: AR/VR UI standards, radial/gauge-heavy operational dashboards as the default, unbounded no-code layout editors that break shared semantics.

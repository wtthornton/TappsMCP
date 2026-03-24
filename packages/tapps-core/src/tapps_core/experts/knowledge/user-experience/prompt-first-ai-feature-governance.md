# Prompt-first AI UI governance (2026)

## Purpose

AI-assisted features in operational and admin products must avoid **hidden autonomy** and **magic output**. This note defines a **required interaction contract** for new AI UI (chat, copilots, workflow assistants). It generalizes patterns from **AI-first UX standards** used in modern internal platforms.

## Required sequence (non-negotiable for compliant flows)

Every new AI-assisted flow should implement:

1. **Intent capture** — user instruction (freeform and/or structured fields).
2. **Intent preview** — system restates scope, constraints, and assumptions **before** side effects.
3. **Execution mode** — user picks or confirms mode: `draft`, `suggest`, or `execute` (only when policy allows execute).
4. **Evidence-backed output** — results expose **sources**, citations, or trace affordances where applicable.
5. **Human decision point** — approve, edit, retry, or reject; no irreversible action without confirmation.

If a design skips steps 2–5, treat it as **non-compliant** with prompt-first governance until remediated.

## Prompt object fields (UI + API alignment)

Structured prompts should round-trip these concepts (expose in UI or infer with **editable** defaults):

- `goal` — desired outcome  
- `context` — repo, task, environment, user role  
- `constraints` — policies, budgets, forbidden actions  
- `success_criteria` — what “good” looks like  
- `mode` — `draft` | `suggest` | `execute`

## Agentic controls (high-impact actions)

For actions that mutate state, publish, bill, or affect compliance:

- **Intent preview** — planned action + impacted surface.  
- **Autonomy dial** — visible current mode; change only when allowed.  
- **Rationale on demand** — short summary default; depth behind disclosure.  
- **Action audit + undo** — what changed; reverse when feasible.  
- **Escalation path** — handoff to manual flow when confidence is low.

## Trust and safety signals

Surface on AI output and recommendations:

- Qualitative **confidence** (even coarse buckets).  
- **Provenance** / evidence link or summary.  
- **Last updated** timestamp.  
- **Ownership cue** — e.g. user is responsible for the final action.  
- **Labeling** — AI-generated or AI-transformed content marked **subtly and consistently** in-context.

Never present AI output as guaranteed fact without verification affordances.

## Appropriate friction

For destructive, publish, or compliance-affecting operations:

- Explicit confirmation  
- Short **risk summary**  
- Final acknowledgment before irreversible steps  

## In-product guidance (onboarding, tours, tooltips)

When adding wizards, tours, tooltips, or spotlights:

- Pick the **right mechanism** (wizard vs panel vs tooltip vs tour vs spotlight).  
- **One primary guidance layer** active at a time; always provide dismiss + replay.  
- Do not block emergency controls; skip targets gracefully if DOM is empty or forbidden.  
- Keep tours **short** (≈5–7 steps), spotlights **minimal** (≈1–3 highlights).  
- **Keyboard:** full keyboard use, `Escape` closes when safe, focus trap/restore for modals/tours.

## Anti-patterns

- Hidden autonomous actions without preview.  
- Anthropomorphic copy that overstates understanding (“I know”, “I feel”).  
- Color-only status communication.  
- “Magic” output without source, rationale, or correction path.  
- Replacing existing workflow controls with **opaque AI-only** controls.

## Cross-domain consultation

- **API / payload design** for prompt objects → also involve `api-design-integration`.  
- **Accessibility** of AI widgets and guidance layers → also involve `accessibility`.

"""Platform ``tapps-wayfind`` skill — body + companion files.

Shipped as a multi-file skill (SKILL.md smart-merged via
``skill_managed_block``; companion references refreshed wholesale). Kept in its
own module so ``platform_skills.py`` stays navigable.

Wayfind charts foggy multi-session work as a **decision map** on Linear (SoT),
then works one decision ticket per session until the route is clear. Harness
loops for *clear* multi-step work stay with ``orchestration-prompt`` — wayfind
is the fog gate upstream of that.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# SKILL.md body (managed block — smart-merged on upgrade)
# ---------------------------------------------------------------------------

WAYFIND_SKILL_FRONTMATTER = """\
---
name: tapps-wayfind
user-invocable: true
disable-model-invocation: true
description: >-
  Chart foggy multi-session work as a Linear decision map, then resolve one
  decision ticket per session until the route to the destination is clear. Use
  when the path is still foggy, the user invokes /tapps-wayfind, or
  orchestration-prompt refuses to invent a Goal because decisions are missing.
argument-hint: "[chart <idea> | work <map-id> [ticket-id]]"
---
"""

# NOTE: host-agnostic prose (no tool grants) so Claude and Cursor share one body.
WAYFIND_SKILL_BODY = (
    WAYFIND_SKILL_FRONTMATTER
    + r"""
# tapps-wayfind

A loose idea arrived — too big for one agent session, and wrapped in **fog**: the
way from here to the **destination** isn't visible yet. Wayfinding finds that way
as a **shared decision map** on Linear, then resolves **decision tickets**
(questions whose answer is a decision, not build slices) one at a time until the
route is clear.

You produce **decisions and map updates**, not the destination deliverable.
When the route is clear, hand off to `/orchestration-prompt` (or implementable
stories via `linear-issue`). Do **not** invent a harness Goal while fog remains.

## Plan, don't do

Default: each ticket resolves a decision; the map is done when nothing is left to
decide before someone builds. The pull to just ship code usually means you've
reached the edge of the map — hand off. An effort may override this in **Notes**
(carry limited execution into the map); absent that, produce decisions, not
deliverables.

## Refer by name

Every map and ticket is a Linear issue with a **title**. In narration and in the
map's Decisions-so-far, refer by **name** (title wrapping its URL) — never bare
ids alone. Ids ride inside the name.

## Linear is SoT; brain is resume/rationale

| Concern | Where |
|---------|--------|
| Map, tickets, status, assignee, blocking, frontier | **Linear** (always) |
| Cross-session resume notes, decision rationale extras | **brain** (`tapps-mcp memory`) optional |

Never store ticket status or frontier in brain. See `references/linear-ops.md`.

## The map

One Linear parent issue (label or title convention `wayfinder:map`) — the
canonical artifact. Tickets are **children** of that map. The map is an
**index**, not a store: it gists closed decisions and links the ticket that holds
detail. Open tickets are **not** listed in the body — query children.

Map body shape: `assets/map-template.md`. Ticket types: `references/ticket-types.md`.

## Fog of war

Don't chart what you can't yet see. **Not yet specified** holds in-scope fog too
dim to ticket. **Out of scope** is past the destination — never graduates.

- **Ticket when** the question is already sharp (even if blocked).
- **Not yet specified when** you can't phrase it that sharply yet.

## Invocation

Two modes. **Never resolve more than one non-research ticket per session.**

### Chart the map

User invokes with a loose idea (`/tapps-wayfind chart …`).

1. **Name the destination** — what reaching the end looks like (spec, locked
   decision, or in-place change). Settles scope first.
2. **Map the frontier breadth-first** — surface open decisions and first
   takeable steps. **If no fog** (journey fits one session, route already clear):
   stop; ask how to proceed — no map needed; prefer `/orchestration-prompt` or a
   normal story.
3. **Create the map** on Linear (parent): Destination + Notes filled,
   Decisions-so-far empty, fog in Not yet specified. Use `linear-issue` (never
   raw `save_issue`).
4. **Create tickets you can specify now** as children (Question body; type from
   `references/ticket-types.md`), then **wire blocking** in a second pass.
5. **Research only:** for each `research` ticket, spawn research subagents in
   parallel; capture findings with a context pointer on the ticket.
6. Stop — charting hand-resolves nothing.

### Work through the map

User invokes with a map id (`/tapps-wayfind work TAP-#### [ticket]`).

1. Load the **map** body (low-res), not every ticket.
2. Choose the ticket (user-named, else first frontier: open + unblocked +
   unclaimed). **Claim** by assigning yourself before work.
3. Resolve — zoom related/closed tickets on demand; follow Notes skills.
4. Record: resolution comment + close ticket + append one gist line to map
   Decisions-so-far. Optionally save rationale to brain keyed to the ticket id.
5. Graduate newly sharp fog into tickets (create-then-wire); clear graduated
   patches from Not yet specified. Rule mis-scoped tickets **out of scope**
   (close + one Out-of-scope line) rather than resolving them on the route.

When no open children remain and Not yet specified is empty, the map is done —
point the user at `/orchestration-prompt` or implementable stories.

## Guardrails

- One non-research ticket per session.
- Linear writes only via `linear-issue`; multi-issue reads via `linear-read`.
- Decision tickets use a **Question** body — do not invent fake Acceptance
  Criteria or file anchors to pass validators (until `issue_kind=decision`
  lands, keep bodies honest and note the kind in the title/labels).
- Do not start `/orchestration-prompt` while fog remains on this map.
- Refer by name; keep Decisions-so-far as an index, not a paste dump.
"""
)

# ---------------------------------------------------------------------------
# Companion files (refreshed wholesale on upgrade)
# ---------------------------------------------------------------------------

_MAP_TEMPLATE = r"""# Wayfind map template

Paste into the Linear parent issue body when charting. Open tickets are **not**
listed here — they are open children found by query.

```markdown
## Destination

<what reaching the end of this map looks like — one or two lines>

## Notes

<domain; skills every session should consult; standing preferences>

## Decisions so far

<!-- one line per closed ticket: name-link + one-line gist -->

- [<closed ticket title>](url) — <gist of the answer>

## Not yet specified

<!-- in-scope fog too dim to ticket yet; graduates as the frontier advances -->

## Out of scope

<!-- past the destination; never graduates -->
```

### Child ticket body

```markdown
## Question

<the decision or investigation this ticket resolves — one session sized>
```

Optional below the Question (keep short): context links, blockers already
expressed as Linear relations, asset pointers.
"""

_TICKET_TYPES = r"""# Wayfind ticket types

Every ticket is **HITL** (human in the loop) or **AFK** (agent alone). HITL only
resolves through live human exchange — never stand in for the human's side.

| Type | Mode | When | Resolution |
|------|------|------|------------|
| **research** | AFK | Facts outside the working tree (docs, APIs, KB) | Research subagent; findings + context pointer on the ticket |
| **prototype** | HITL | "How should it look/behave?" needs a cheap artifact to react to | Link the prototype as an asset; decision recorded on close |
| **grilling** | HITL | Default — conversation to lock a preference or tradeoff | Human answers; agent records the decision |
| **task** | HITL or AFK | Manual work that *unblocks a decision* (access, signup, data move) — not the destination deliverable | Done when the blocking work is done; answer records resulting facts |

Label convention (Linear labels or title prefix): `wayfinder:research`,
`wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`. Map parent:
`wayfinder:map`.

**Research exception:** multiple research tickets may run in parallel in one
charting or work session. All other types: **one ticket per session**.
"""

_LINEAR_OPS = r"""# Wayfind Linear operations

Linear is the system of record for maps, tickets, claims, and blocking.

## Create / update

- **Writes:** always the `linear-issue` skill (docs-mcp generate → validate →
  save). Never call plugin `save_issue` directly.
- **Map parent:** create as a parent issue (or epic child story that owns the
  map). Title names the destination effort; body from `assets/map-template.md`.
- **Tickets:** children of the map. Body starts with `## Question`. Prefer
  labels `wayfinder:*` when the workspace has them.
- **Claim:** assign the ticket to the driving agent/user **before** work.
  Open + unassigned = unclaimed.
- **Blocking:** use Linear's native blocking/related relations so the frontier
  is visible in the UI. Wire edges in a **second pass** after create (ids needed).
- **Resolve:** comment with the answer → close → append gist to map
  Decisions-so-far (edit map via `linear-issue` update).

## Read

- **Multi-issue / frontier queries:** `linear-read` skill only (cache-first;
  never raw `list_issues` without `tapps_linear_snapshot_get`).
- **Single issue:** `get_issue(id=...)` is fine.
- **Frontier:** open children of the map that are unblocked and unclaimed.

## Brain (optional)

- Save resume/rationale with a key tied to the ticket id after resolve.
- Do **not** mirror status, assignee, or frontier into brain — Linear wins.
"""

WAYFIND_COMPANION_FILES: dict[str, str] = {
    "assets/map-template.md": _MAP_TEMPLATE,
    "references/ticket-types.md": _TICKET_TYPES,
    "references/linear-ops.md": _LINEAR_OPS,
}

__all__ = [
    "WAYFIND_COMPANION_FILES",
    "WAYFIND_SKILL_BODY",
]

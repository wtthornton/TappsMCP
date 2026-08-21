"""Platform ``orchestration-prompt`` skill — body + companion files.

Shipped as a multi-file skill (SKILL.md smart-merged via
``skill_managed_block``; companion reference/template refreshed wholesale;
``learnings.md`` created-once and never overwritten). Kept in its own module so
``platform_skills.py`` stays navigable.

The body is the *generic platform core* of loop/harness engineering. Consumer
specifics (fleet manifest path, observed-failure examples, run-as lines) live in
each project's preserved region below the managed block — never here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# SKILL.md body (managed block — smart-merged on upgrade)
# ---------------------------------------------------------------------------

ORCHESTRATION_PROMPT_SKILL_FRONTMATTER = """\
---
name: orchestration-prompt
user-invocable: true
model: claude-sonnet-4-6
description: >-
  Generate a ready-to-run orchestration PROMPT: a verifiable Goal, a bounded loop,
  and an independent creator-verifier pass. Refuses foggy Goals — redirects to
  /tapps-wayfind. Use whenever the user wants to orchestrate multi-step, multi-repo,
  autonomous, or recurring work — "create a prompt to…", "orchestrate…", "make a
  goal for…", "work the backlog", "loop until X" — even if they don't say
  "orchestrate".
argument-hint: "[free-form objective]"
---
"""

# NOTE: the body below is deliberately host-agnostic prose (no tool grants), so
# the same text serves both the Claude and Cursor skill hosts.
ORCHESTRATION_PROMPT_SKILL_BODY = (
    ORCHESTRATION_PROMPT_SKILL_FRONTMATTER
    + r"""
# orchestration-prompt

You produce **prompts, not actions**. The output is a self-contained orchestration
prompt (a markdown file under `prompts/`) that the user — or a Routine, or a `/goal`
run — executes later. You write the *loop*; you do not run it.

## Why this exists

The leverage is in the loop's shape — goal, termination, verification, model tier
per step — not in phrasing. A well-shaped harness lets a cheaper model match a
frontier one on verification-friendly work. Every prompt rests on seven load-bearing
parts; miss one and the loop never terminates, terminates without finishing, trusts
self-report, invents a Goal under fog, or can't be cold-started.

## The method

### 0. Wayfind fog preflight (before inventing a Goal)

**Do not invent a Goal while the route is still foggy.** This skill emits execute
loops for *clear* work; decision maps belong to `/tapps-wayfind`.

**Foggy (refuse):** a destination with no locked route; an open `wayfinder:map` with
open children or non-empty **Not yet specified**; the user cannot state Done-when
without guessing an undecided tradeoff.
**Clear (proceed):** remaining work is implementable (build / verify / fix), not
"what should we do?"

**On fog:** stop drafting, point at `/tapps-wayfind chart <idea>` or
`/tapps-wayfind work <map-id>`, and do not fill the template with a fake Goal.

**Resume:** when a map exists, open Context with
`uv run tapps-mcp memory search --query "wayfind <map-id>"` and prefer
`memory_group=wayfind` hits. Linear stays SoT for ticket status; fold named
decisions into Context, never invent missing ones.

### Decide-vs-execute chunk taxonomy

**Decide / map / research-to-decide** chunks are fog — they belong on
`/tapps-wayfind`, never on a `/goal` or a Workflow. **Execute / verify / fix /
research-to-execute** chunks are this skill's. Full table:
`references/claude-feature-map.md`.

### 1. Pin the Goal to a *verifiable, demonstrable* done-condition

A `/goal` evaluator judges only what Claude *surfaced in its output* — it does not
run commands or read files. So anchor the condition to **ground truth, not
narration**: name the deterministic artifact that proves it (exit code, test-count
line, diff, pasted query result), so a confident-but-wrong model cannot score itself
green by asserting success.

- Good: "All five repos paste a `pytest` summary line showing 0 failures."
- Good: "Zero open P1 issues — paste the final query result."
- Weak: "The code is better" / "tests pass" (nothing in the transcript proves it).

**Then pressure-test *reachability*.** A condition can be demonstrable yet
unsatisfiable without the system misbehaving. Separate **validate** goals ("prove X
works" — a correct *negative* IS success) from **optimize** goals ("drive the metric
to 100"). A validation Done-when must accept a verified-correct negative, or the loop
burns its budget chasing a result correct behavior will never produce.

### 2. Decompose if the goal is large — contract before features when behavior changes

Break it into **sequential sub-goals, each with its own narrow verifiable
condition**. The loop advances one sub-goal at a time; each is a checkpoint a fresh
context can resume from.

**When the objective changes software behavior** (feature, bugfix with observable
effect, migration), insert a **validation contract** *before* any execution
sub-goal — the Factory Missions ordering that stops post-hoc tests from ratifying
whatever the implementer already built:

1. Write a finite checklist of **behavioral assertions** with stable IDs
   (`VAL-…`). Each assertion is testable without reading the implementation
   (user-visible outcome, API response, CLI exit+stdout, smoke script).
2. Map every execution sub-goal to the assertion IDs it **fulfills**. Coverage
   must be complete: no orphan assertions, no duplicate claims.
3. Anchor **Done-when** to contract coverage (every ID verified by an independent
   verifier), not to "executor says the feature is done."

Skip the contract section only for pure research/triage/docs prompts where there
is no behavioral product surface. Fog preflight (method §0) already ran — if you
are writing a Goal, the route is clear.

### 3. Map each chunk to a plane, a mechanism, and a model tier

The highest-value step — most ad-hoc prompts pick the wrong mechanism *and* pay
frontier-model rates for mechanical work. Two planes (full catalog in
`references/claude-feature-map.md`):

- **Coordination plane** — research, audit, triage, synthesis, dispatch,
  **verification**. Fan-out is good. Tools: **subagents** (3–5 parallel), the
  **Workflow tool** (budget-capped, resumable fan-out).
- **Execution plane** — editing code. **One repo at a time, sequentially.** Tools:
  per-repo PR, **Routines** / `claude -p`+cron for recurring runs. Never fan
  parallel agents across coupled code — the documented worst fit.

Give every chunk a **model tier**, not just a mechanism — run the harness cheap,
spend the strong model only where judgement is load-bearing (independent verify is
always frontier tier). Selector table: `references/claude-feature-map.md`.

**Preflight the mechanism before you commit a chunk to it.** A mechanism that is
listed is not a mechanism that works: a granted tool with no targets, a degraded
index, an unreachable MCP server all fail *silently* and the loop degrades into a
confident wrong answer. Sub-goal 0 must prove each one executes once for real.

**Commit to the mechanism — don't hedge.** "You *may* dispatch subagents" forces the
runner to re-decide and usually defaults to the weakest option. Name exactly one
mechanism + tier per chunk. For **multi-stage parallel work** (N items × ≥2 steps)
emit a companion Workflow script (`.claude/workflows/<slug>.js`) using
`pipeline()`/`parallel()` with a result **schema**, a **`budget`** cap, and per-stage
`model`/`effort`. A **single coupled item** (N=1) is a `/goal` drive, not a Workflow
— say so in the prompt so the runner doesn't default to one.

### 4. Write the loop with termination + guardrails

Shape every loop as **state → decide → execute → verify → record → (repeat or
stop)**, with a **diagnose-don't-repeat** branch on any failed verify. Open **state**
with a brain recall of prior attempts; close each iteration by **recording** the
outcome (incl. what failed and why). Give the loop an explicit exit, then bake in the
guardrails below.

**Context hygiene in every iteration.** A long loop rots its own context by
re-reading the same files. Instruct the loop to prune stale reads, prefer a targeted
grep/snippet over a full re-Read, and carry forward a compact state summary rather
than raw transcripts — so iteration N isn't paying for iteration 1's tokens.

### 5. Add an independent verification pass (creator ≠ verifier)

Self-verification is the weakest link — the implementer has cost bias, a fresh
context does not. A separate adversarial verifier is the single largest quality gain.

- After Execute, spawn a **verifier subagent** (frontier tier, *fresh* context)
  prompted to **refute** the proof: re-run the deterministic check rather than trust
  the executor's narration. Default to "not done" on any doubt.
- The verifier **grades the artifact, not the run.** "Node completed" / "tool
  returned" is not evidence; re-run the deterministic check and read the output.
- The verifier **reports gaps; it does not implement fixes** — the loop scopes a
  narrow fix sub-goal for a fresh executor.
- The verifier's verdict — not the executor's claim — advances the loop.

Two-layer verification, N-verifier majority, and perspective-diverse lenses:
`references/cold-start-and-verify.md`.

### 6. Make it cold-start runnable (the drop-in test)

The point is a prompt a **brand-new session** can run with zero hand-holding.

- **Wayfind resume first.** Cold-start State opens with a brain search for
  `memory_group=wayfind` / `wayfind:*` keyed to the map or destination (method §0).
  Prefer those hits over inventing Context; Linear is still SoT for open tickets.
- **Self-bootstrap launch line.** `/goal "<condition>"` carries only the *condition*
  into a fresh session — not the prompt body. So every emitted prompt needs a
  top-of-file **"How to run (cold start)"** block with one paste-able line that
  **reads the file in full first, then enters the loop**.
- **Self-healing preconditions.** Anything the loop needs (a runtime up, a
  scorer/tool built, a branch, auth reachable) is a **Sub-goal 0** the loop
  *establishes itself* — never a "set this up first" note the user must action.
- **Capability + harness preflight.** Sub-goal 0 proves the loop can actually do
  its job before it spends: every granted tool executes once for real, every
  hook-gated call has its unlock step, every MCP standing nudge is explicitly
  adopted or overridden, and a live target passes deploy-freshness + `/health`.
  Checklists: `references/cold-start-and-verify.md`.

## Guardrails every emitted prompt must carry

- **Verifiable termination** — the Goal condition *and* a hard cap (max iterations
  or a token budget) so a stuck loop stops instead of burning quota.
- **Independent verification** — the sub-goal's proof is confirmed by a verifier that
  did not produce the work (method §5), against ground truth.
- **Caps must not fire on *correct* behavior** — for every required-fail cap, ask "is
  there a legitimate correct run where this still fires?" Separate *broken* from
  *correct-empty* (the gate rightly held everything) or a correct negative scores red.
- **No fan-out of coupled coding** — parallel agents editing related code cascade
  errors; keep code edits sequential, per repo.
- **Context hygiene** — prune stale reads each iteration; targeted grep over full
  re-Read (method §4).
- **Autonomy, not checkpoints** — act on every reversible in-scope step; for an
  outward/irreversible step produce a reversible precursor (draft PR, staged diff)
  and keep going.
- **Fog gate** — never invent a Goal while decide work remains; redirect to
  `/tapps-wayfind` (method §0).
- **Scope** — name the exact repos/paths; reads can be fleet-wide, writes go through
  the owning repo's channel.
- **Budget** — every loop carries *both* an iteration cap and a token budget; set a
  Workflow `budget` to a token ceiling (≈ the autonomy cost gate) so it self-aborts.
- **Memory** — recall at the start, record the outcome (incl. failures) at each
  checkpoint, so learning survives the session.
- **Harness compatibility** — every tool call the loop makes that is gated by a
  project hook has its unlock/refresh step in the prompt, and every MCP standing
  nudge is explicitly adopted or overridden (method §6).

## Autonomy contract (every emitted prompt carries this)

Run like an operator, not an intern. Decide and act on every reversible, in-scope
step — never insert "should I proceed?" checkpoints. For an irreversible/outward step,
produce the *reversible precursor* (draft PR, staged diff, written proposal) and
continue; the human reviews async. A draft PR is not a stop.

Hard-stop and ask **once** (batched, with a recommendation) only when: the step is
irreversible/outward with no reversible precursor (merge to main, force-push, delete
un-recreatable data, external message, cross-project write); **or** the projected
cost of the next step exceeds the configured ceiling (default ≈ $20; honor any higher
pre-authorization); **or** a genuinely ambiguous decision where a wrong guess is
expensive and unrecoverable. Enforce the cost gate mechanically via the Workflow
`budget` so the run aborts itself instead of asking.

## Failure handling (diagnose, don't repeat)

On a failed verify, do **not** re-run the same action. Diagnose first: read the
actual error, inspect state/files, recall prior failures from the brain, research the
cause. Form a specific hypothesis, apply a fix, retry with *something changed*. Bound
it: max **3 distinct strategies** per sub-goal, then escalate once (more capable
model / different approach), then **stop and surface a concise diagnosis**. Repeating
the same action on the same error is forbidden.

## Expected-fail fix loop (Missions-inspired)

Independent verification **almost never passes on the first attempt** for non-trivial
work. Treat that as the design, not a crisis:

1. **Record a structured handoff** before fixing: what completed, what is undone,
   commands run + exit codes, issues found, whether procedures were followed.
2. **Scope a narrow fix sub-goal** targeting the verifier's actionable gaps — do not
   reopen the whole feature or weaken the validation contract to go green.
3. **Re-execute → re-verify** (fresh verifier context again).
4. **Attempt cap (default 3 validation rounds per sub-goal)** — override explicitly
   in the emitted prompt when needed. After the cap: escalate once, then stop with
   a diagnosis. If the *contract* itself is wrong, stop and ask the human — do not
   silently rewrite Done-when to match the broken implementation.

Infinite fix spirals and "green by suppression" are forbidden.

## Engineering discipline (emit in every prompt's guardrails)

Produce *solutions*, not band-aids: root-cause not workarounds; **no
green-by-suppression** (never skip/disable a check to pass); **right-sized** (the
simplest thing that fully solves it); durable over expedient; match repo conventions;
no silent scope creep.

## Output

1. **Fog preflight (method §0).** If foggy, refuse and point at `/tapps-wayfind` —
   do not emit a prompt. If clear, recall `memory_group=wayfind` resume when present.
2. Read the workspace manifest (e.g. `fleet.md`) for the repos / Linear projects /
   brain ids involved, if the project has one.
3. Fill `assets/prompt-template.md` — keep only the sections the task needs. Always
   keep **Prerequisites / Wayfind gate**, the **"How to run (cold start)"** block, a
   **Sub-goal 0** for self-healing preconditions, the **Verify** step wired to an
   independent verifier, and — when changing software behavior — a **Validation
   contract** filled *before* execution sub-goals plus an **expected-fail fix loop**
   with attempt cap.
4. If any chunk is multi-stage parallel work, also write the companion
   `.claude/workflows/<slug>.js` (schema + `budget` + per-stage `model`/`effort`) and
   point Run-as at it. A single coupled item (N=1) is a `/goal` drive, not a Workflow.
5. Save the prompt to `prompts/<short-slug>.md`.
6. **Completeness self-check** — walk the **Guardrails** list above and confirm the
   emitted prompt satisfies every line; then run the **cold-start test** (a fresh
   session with nothing loaded can run it). Fix anything weak before saving.
7. Tell the user exactly how to run it — the `/goal` line, the `/loop` cadence, the
   Routine schedule, or "invoke the Workflow tool `<script>`" — and from which
   session.

## Learn as you go (measured evolution)

Before drafting, read `learnings.md` (project-scoped) and fold in relevant lessons.
When a generation teaches a better pattern — or the user edits your output before
running it — append a one-line lesson. Keep lessons **project-scoped**; never bleed
them across repos. Treat this as a *measured* loop, not a scratchpad: the harness
improves by observing its own runs. When a golden set (`evals/evals.json`) and a
gated improvement loop (`SELF_IMPROVEMENT.md`) exist, promote a template change only
when it shows measured lift against the evals — don't hand-tune blind.
"""
)

# ---------------------------------------------------------------------------
# Companion files (refreshed wholesale on upgrade — canonical platform docs)
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = r"""# <Objective title>

> Generated by the `orchestration-prompt` skill. Keep only the sections this task
> needs. Run from the orchestrator session unless noted.

## Prerequisites / Wayfind gate
<Fill BEFORE Objective. Refuse to invent a Goal if any fog remains.>

- **Route clear?** <yes / no — open `wayfinder:map` children? Not yet specified empty?>
- **If no:** stop — run `/tapps-wayfind chart <idea>` or `/tapps-wayfind work <map-id>`;
  do not continue this prompt until decide tickets are closed.
- **Wayfind resume (cold start):** `uv run tapps-mcp memory search --query "wayfind <map-id or destination>"` — prefer `memory_group=wayfind` / keys `wayfind:*`; fold named decisions into Context. Linear is SoT for status/frontier.
- **Chunk mix:** decide chunks → wayfind; execute / verify / fix → this loop (see skill decide-vs-execute taxonomy).

## How to run (cold start — paste into a NEW session)
<`/goal "<condition>"` alone does NOT load this file's body, so the launch line must
read the file first, then loop. Run Prerequisites / Wayfind gate recall before Loop.>

- **Goal loop (recommended):** `Read prompts/<slug>.md in full, run Prerequisites / Wayfind gate (incl. wayfind resume recall), then execute it as a goal loop — run the Loop section repeatedly until Done-when holds, printing the score line every iteration. Establish your own preconditions per Sub-goal 0; do not stop unless an Autonomy hard-stop fires.`
- **Durable / recurring:** save as a Routine (one item per run) so it survives the terminal.

## Objective
<one sentence — the outcome, not the steps. Only fill if Prerequisites say route is clear.>

## Done-when (Goal condition — ground-truth, not narration)
<a single condition Claude's own output can demonstrate. Name the deterministic
artifact that proves it — exit code, test-count line, diff, pasted query result.
For software behavior: every validation-contract ID below is verified by an
independent verifier (paste evidence per ID).>

## Validation contract (before execution — software behavior only)
<Skip for pure research/triage/docs. Write assertions BEFORE execution sub-goals.>

| ID | Behavioral assertion | Fulfilled by sub-goal | Evidence tool |
|----|----------------------|-----------------------|---------------|
| VAL-… | <user-visible / API / CLI outcome> | <sub-goal #> | <pytest / smoke / tapps_validate_changed / …> |

Coverage rule: every ID claimed exactly once; Done-when requires all IDs green.

## Sub-goals  (sequential; each a checkpoint)
0. **Establish preconditions (self-healing — the loop sets these up, NOT the user).** <runtime up, scorer/tool built, auth reachable, branch ready; wayfind resume already recalled in Prerequisites>
   - **Deploy freshness (live/deployed target only):** merged ≠ live. If baked image, compare latest merged commit to build time; rebuild/redeploy (preserve overlays) if `main` is newer. Stale image = required-fail cap.
   - **Smoke + health gate (after any deploy, before the real run):** `/health` is `ok|degraded` and one cheap end-to-end call succeeds.
   - **Harness compatibility:** <PreToolUse gates + MCP standing nudges the loop's tool calls will hit → bake unlock/refresh steps here; adopt-or-override each nudge in Guardrails>
   - proof: <preconditions verified; for live targets — image no older than latest merged commit + a 200/non-error smoke pasted>
1. **(Software behavior) Finalize validation contract** — proof: contract table above complete + coverage check pasted
2. <narrow, verifiable execution> — fulfills: <VAL-…> — proof: <ground-truth artifact>
3. <…>

## Plane map  (mechanism + model tier per chunk)
| Step | Plane | Mechanism | Model tier | Notes |
|------|-------|-----------|-----------|-------|
| <audit/research> | coordination | Workflow / 3–5 subagents | cheap/low-effort | fan-out OK (read-only); research-to-*decide* stays on wayfind |
| <code change> | execution | dispatch to <repo> via PR | cheap unless hard | **serial writes** — one repo at a time |
| <verify proof> | coordination | **verifier subagent (fresh context)** | **frontier/high-effort** | creator ≠ verifier; refutes proof |
| <fix after fail> | execution | fresh worker on scoped fix sub-goal | cheap unless hard | expected-fail loop; do not reopen whole feature |
| <recurring check> | execution | Routine / `claude -p`+cron | cheap | human-gated |

## Loop
- **State:** <read first — wayfind resume (`memory_group=wayfind`), status, brain recall of prior attempts, Linear, last handoff>
- **Decide:** <how to pick the next *execute* action / sub-goal — never invent decide work; if fog reappears → stop and `/tapps-wayfind`>
- **Execute:** <the action, on the committed mechanism + tier>
- **Verify (independent):** spawn a fresh-context verifier (frontier tier) to *refute* the sub-goal's proof — re-run scrutiny + behavioral checks against the validation contract; don't trust the executor's claim. The verifier's verdict advances the loop.
- **On fail (expected-fail fix loop):** record structured handoff → scope narrow fix sub-goal → re-execute → re-verify; ≤**3** validation rounds per sub-goal (override: N=…), then escalate once, then stop with a diagnosis. Never weaken the contract to go green.
- **Record (structured handoff):** completed · undone · commands+exit codes · issues · procedures followed? · failure-and-why → brain
- **Context hygiene:** prune stale reads; carry a compact state summary, not raw transcripts.
- **Repeat or stop:** loop until **Done-when** holds; caps: <N iterations> AND <token budget>

## Guardrails
- Termination: <goal condition>; caps: <N iterations> AND <token budget>.
- Wayfind fog gate: no Goal invent while decide tickets / Not yet specified remain.
- Validation contract before features when changing behavior; coverage complete.
- Independent verification (creator ≠ verifier); ground-truth proof; expected-fail fix loop with attempt cap.
- No fan-out of coupled coding — sequential per-repo edits (serial writes, parallel reads OK).
- Context hygiene — targeted grep over full re-Read.
- Scope: repos in play = <list>; reads fleet-wide, writes via owner.
- Memory: recall wayfind resume + prior attempts at start; record structured handoff (incl. failures) at each checkpoint.
- Harness compatibility: <gated tool calls → unlock/refresh steps; MCP standing nudges → adopted or overridden>.
- Discipline: root-cause not workarounds; no green-by-suppression; right-sized; durable; match conventions; no scope creep.

## Autonomy
- Act on every reversible, in-scope step — no "should I proceed?" checkpoints.
- Irreversible/outward step → produce the reversible precursor (draft PR / staged diff / proposal) and continue; human reviews async.
- Hard-stop once (batched, with a recommendation) only for: irreversible/outward with no precursor · projected next-step cost > ceiling · unsafe-to-guess ambiguity · **validation contract itself is wrong** · **fog returned (open decide work)**.

## Failure handling
- On failed verify: diagnose (error + state + brain recall) → hypothesis → fix → retry *differently*.
- ≤3 distinct strategies per sub-goal; then escalate once; then stop with a concise diagnosis. Never repeat the same action on the same error.
- Expected-fail: first verify fail is normal — scoped fix sub-goal, not panic or contract rewrite.

## Context
- Repos: <manifest — path · Linear project · brain project_id>
- Wayfind decisions: <named decisions from resume / map Decisions-so-far>
- Prior learnings: <brain recall query, if any>

## Run-as
<exact invocation, e.g.:>
- **Cold-start loop (recommended):** the paste line from "How to run" above. **or**
- `/goal <condition>` — only if this file is already in context. **or**
- invoke the Workflow tool with `.claude/workflows/<script>.js` (fan-out only). **or**
- Routine: schedule `<cadence>` with this prompt, push=draft-PR.
"""

_FEATURE_MAP = r"""# Claude feature map — intent → mechanism → model tier

Read this when choosing how a chunk of an orchestration prompt should run. Put each
step on the cheapest, most durable mechanism that fits — and the cheapest model tier
that still gets it right. Spend the frontier model only where judgement is
load-bearing (hard reasoning, and the independent verify/judge step).

## The two planes

- **Coordination plane** (research/audit/triage/synthesis/dispatch/**verification**):
  fan-out is good — you can usefully spend tokens in parallel. Token-spend-in-parallel
  is the test for whether to fan out at all.
- **Execution plane** (writing code): sequential, one repo at a time. Coupled coding
  is the worst fit for fan-out (tight dependencies, shared context, error cascade).

## Decide-vs-execute chunk taxonomy

Fog chunks belong on `/tapps-wayfind`; clear chunks belong to orchestration-prompt.

| Chunk kind | Fog? | Handle with |
|---|---|---|
| **Decide** — preference, tradeoff, scope, "which approach?" | yes until locked | `/tapps-wayfind` (decision / research tickets) |
| **Map / chart** — surface fog, wire blocking | yes | `/tapps-wayfind chart` |
| **Research-to-decide** | yes | wayfind `research` tickets (not an orch Goal) |
| **Execute** — code edit, migration, deploy, mechanical fan-out | no (route clear) | execution plane |
| **Verify / judge** — refute proof, run checks | no | coordination plane + frontier verifier |
| **Fix after expected-fail** — scoped gap repair | no | expected-fail fix loop |
| **Research-to-execute** (facts for a clear build) | no | coordination plane OK |

## Mechanism catalog

| Mechanism | What it is | Best for | Watch out |
|---|---|---|---|
| **`/goal <condition>`** | Drives turn-after-turn until a fast model judges the condition met (against Claude's *surfaced output*, not by running commands) | One job to a provable finish | Condition must be demonstrable + ground-truth-anchored; decompose large goals |
| **`/loop [interval] <prompt>`** | Re-runs a prompt on a timer / each turn | Polling, babysitting a build/PR | Session-bound — dies with the terminal; never your durable layer |
| **Scheduled Routine** | Saved config run on cloud cron | "Nightly: take top backlog item, open a draft PR" | Keep a human review gate |
| **`claude -p` + cron / CI** | Headless one-shot via external scheduler | Durable recurring runs, zero preview risk | Feature-light; no session persistence |
| **Workflow tool** | Deterministic JS orchestration (`phase/agent/parallel/pipeline`), budget-capped, resumable, per-stage `model`/`effort` | Bounded parallel multi-repo sweeps; fan-out verify | Per-invocation, not a persistent loop |
| **Subagents** | Focused workers in isolated context, report back | 3–5 parallel research/review/**verify** tasks | Don't fan out coupled coding; declare minimal tools |
| **Verifier subagent** | A fresh-context agent prompted to *refute* a claim, re-running the check | Confirming a sub-goal's proof independently of the executor | The whole point is a *different* context — don't reuse the executor |
| **brain / `tapps_memory`** | Shared episodic+semantic memory (per-repo `project_id`) | Recall prior attempts; avoid rediscovery | Cross-project recall needs an explicit `project_id` |

## Model-tier selector

| The chunk is… | Tier |
|---|---|
| Mechanical fan-out, read/summarize, codemod, rename | cheap / low-effort |
| Hard reasoning, ambiguous fix, architecture, design | frontier / high-effort |
| **Independent verify / judge** | **frontier / high-effort** (a weak verifier defeats the pattern) |
| Recurring poll, status check | cheap |

Running the harness cheap and spending the strong model only on reasoning + verify is
exactly how a modest base model reaches frontier-level reliability.

## `/goal` vs `/loop`

- `/goal` = **drive one job to done.** Condition-checked, self-terminating.
- `/loop` = **poll/repeat on a cadence.** No notion of "done".
- Recurring autonomous work that must survive the terminal → **Routine** (or
  `claude -p`+cron), not `/loop`.

## Anti-patterns to encode against

- **Inventing a Goal under fog** → refuse; `/tapps-wayfind` until the route is clear.
- One enormous goal → sequence narrow sub-goals.
- Unbounded loop (no cap/budget) → always set max iterations or a token budget.
- **Self-verification only** (loops.md #4 *self-declared convergence*) → an
  independent, adversarial verifier owns the stop field; the creator never does.
- **Vacuous verify** (loops.md #1) → a presence-style predicate ("output non-empty",
  "node completed", "tool returned") reads as "output correct" while the thing it
  guards is inert. An uncheckable criterion is itself a FAIL.
- **Prose judge** (loops.md #2) → a judge with no result schema answers in prose, the
  stop field never resolves, and the loop runs to max iterations every time. Declare
  a schema on every member a convergence or goal expression reads.
- **Gate outside the harness** (loops.md #3) → a policy/human gate that lives only in
  a wrapper script is bypassed by anyone invoking the loop directly. Put the gate in
  the spec, where it travels with the run.
- **Unreachable bar** (loops.md #6) → a bar no correct run can meet ("utterly
  perfect") plus a human-only brake converts every unattended run into
  max-iterations × worst-case spend. Pair reachable wording with a cap and a budget.
- **Fan-out on ambiguity** (loops.md #7) → decomposing hardest when the goal is
  vaguest multiplies the ambiguity. Foggy goals collapse to one agent; open questions
  lead with research, not execution.
- **Critic grades the tool, not the artifact** (loops.md #8) → the judge scores
  intermediate tool output or the builder's summary instead of the shipped artifact,
  so the loop optimizes the wrong surface. Judges receive artifacts, never narration.
- **Inert capability** → a granted tool that silently refuses (no targets, missing
  key, unreachable server) degrades the agent into a confident wrong answer that
  reads as success. Prove each tool executes once in Sub-goal 0.
- Paying frontier rates for mechanical fan-out → tier the model per chunk.
- Parallel agents on coupled code → sequential per-repo dispatch (serial writes).
- Vague / absent done-condition (loops.md #5 *goal-less workflow*) → "every step
  completed" is not success; demand a demonstrable, ground-truth-anchored condition.
- Context rot (re-reading the same files each iteration) → prune + targeted grep.
- **Features before a validation contract** → write behavioral assertions first when
  changing software behavior; map sub-goals to `fulfills` IDs.
- **Forcing attempt-1 green** → expected-fail fix loop with attempt cap; scoped fix
  sub-goals; never weaken the contract to pass.
- Unstructured "done" handoffs → record completed / undone / commands+exit codes / issues.

## Missions → orchestration-prompt (what we steal, what we don't)

Factory Missions ([architecture](https://factory.ai/news/missions-architecture)) is a
multi-day product runtime. This skill emits **prompts**, not a Missions runner.
Steal the control loop; skip Mission Control UI, computer-use fleets, and
multi-day orchestrators:

| Missions idea | Emit in the prompt as… |
|---|---|
| Validation contract before features | Validation contract table + Done-when = all IDs green |
| Creator ≠ verifier | Fresh verifier subagent; verifier does not implement fixes |
| Scrutiny + user-testing | Deterministic checks + behavioral smoke against assertions |
| Serial feature execution | Serial writes / one repo at a time; parallel read-only OK |
| Structured handoffs | Record fields: completed · undone · cmds+exits · issues |
| Fix features after fail | Expected-fail fix loop ≤3 rounds, then escalate/stop |
"""

_COLD_START_AND_VERIFY = r"""# Cold-start preflight & verification depth

Consult while *filling* the prompt template — not while deciding the shape of the
loop. `SKILL.md` carries the rules; this file carries the checklists.

## Sub-goal 0 preflight — prove the loop can work before it spends

Everything here is **self-healing**: the loop establishes it, never a "set this up
first" note the user must action.

### 1. Capability preflight (every prompt)

A mechanism that is *listed* is not a mechanism that *works*. Each of these fails
silently and leaves the agent producing a confident, degraded answer:

- A tool granted with no targets/allowlist — the call is refused, the agent falls
  back to weaker evidence and mentions it once in passing.
- A degraded index or cache — partial results returned as if complete.
- An unreachable MCP server or expired auth — the tool simply never fires.

**Rule:** for every tool the loop depends on, Sub-goal 0 executes it once for real
against a known-good input and asserts the result. A grant is not a capability.
Make "ran with a refused tool" a required-fail cap, not a warning.

### 2. Harness-compatibility sweep

The runner session carries the *project's own* harness: PreToolUse/PostToolUse hooks
that gate tool calls (issue-tracker write sentinels, prod guards) and MCP standing
instructions that nudge per-edit behavior (quality checks after every file edit, doc
lookups). Enumerate the gates and nudges the loop's calls will actually hit; bake
each unlock/refresh step into Sub-goal 0 or the relevant loop step; and in Guardrails
explicitly **adopt or override** each standing nudge (e.g. "quality pipeline runs at
the epic gate, not per edit — this overrides the per-edit nudge"). A prompt that
fights its own project's hooks burns its budget on diagnose loops.

### 3. Deploy-freshness + smoke/health (live or deployed targets only)

1. **Merged is not live.** If the target is a baked image, compare the latest merged
   commit to the build time and rebuild/redeploy (preserving overlays) when the
   default branch is newer. Make "ran against a stale image" a required-fail cap.
2. **Smoke before spend.** After any rebuild/deploy and before the real run, hit
   `/health` plus one cheap end-to-end call to prove runtime + auth + transport.

### 4. Wayfind resume

Cold-start State opens with a brain search for `memory_group=wayfind` / `wayfind:*`
keyed to the map or destination. Prefer those hits over inventing Context; the issue
tracker remains source of truth for open tickets.

## Verification depth

Scale the verifier to the stakes. All layers keep creator ≠ verifier.

| Stakes | Verification |
|---|---|
| Routine, reversible | One fresh-context verifier prompted to refute |
| Behavioral change | Two layers: **scrutiny** + **behavioral** (below) |
| High-stakes / irreversible | N independent verifiers, majority rules |

- **Scrutiny layer** — lint, types, tests, `tapps_validate_changed`. Necessary,
  never sufficient when the contract is behavioral.
- **Behavioral layer** — smoke or a scripted user flow exercised against the
  validation-contract assertion IDs. This is the layer that catches "the tests pass
  and the feature still does not work".
- **N verifiers** — prefer *perspective-diverse* lenses over N identical refuters
  when a finding can fail in more than one way (correctness, security,
  does-it-reproduce). In a Workflow this is a `parallel()` of verify agents keyed off
  each finding; kill the finding when a majority refute.

**Grade the artifact, never the run.** "Node completed", "agent returned", "no
exception raised" are not evidence. The verifier re-runs the deterministic check and
reads the shipped output. Default to "not done" on any doubt.
"""

_LEARNINGS_SEED = """\
# orchestration-prompt learnings (project-scoped)

Append one-line lessons as you generate prompts. Keep them project-scoped; never
bleed across repos. This file is created once by the scaffolder and never
overwritten on upgrade — it's yours.

<!-- Example: -->
<!-- - Validation goals need a verified-correct-negative Done-when, or the loop chases an unreachable target. (2026-06-18) -->
"""

# Companion files refreshed on every upgrade (canonical platform docs).
ORCHESTRATION_PROMPT_COMPANION_FILES: dict[str, str] = {
    "assets/prompt-template.md": _PROMPT_TEMPLATE,
    "references/claude-feature-map.md": _FEATURE_MAP,
    "references/cold-start-and-verify.md": _COLD_START_AND_VERIFY,
}

# Files created once and NEVER overwritten (project-owned).
ORCHESTRATION_PROMPT_CREATE_ONLY_FILES: dict[str, str] = {
    "learnings.md": _LEARNINGS_SEED,
}

__all__ = [
    "ORCHESTRATION_PROMPT_COMPANION_FILES",
    "ORCHESTRATION_PROMPT_CREATE_ONLY_FILES",
    "ORCHESTRATION_PROMPT_SKILL_BODY",
]

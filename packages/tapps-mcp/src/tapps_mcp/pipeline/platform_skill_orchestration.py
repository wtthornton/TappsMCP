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
  Generate a ready-to-run orchestration PROMPT with an explicit Goal (verifiable
  done-condition), a Loop (state→decide→execute→verify→repeat with termination),
  an independent verification pass, and the right Claude Code feature + model tier
  for each step (subagents, Workflow tool, /goal, /loop, Routines, brain memory).
  Use whenever the user wants to orchestrate multi-step, multi-repo, autonomous, or
  recurring work — "create a prompt to…", "orchestrate…", "make a goal for…",
  "work the backlog", "loop until X" — even if they don't say "orchestrate".
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

## Why this exists (the 2026 shift)

Work moved from *prompt engineering* to **loop / harness engineering**: an agent is
an LLM wrapped in a loop with tools, and the leverage is in the loop's shape — its
goal, its termination, its verification, and which capability + model tier handles
each step — not in clever phrasing. Empirically the *harness* (planning →
delegation → **independent verification** → context management), not the model,
does most of the work: a well-shaped loop lets a cheaper or open model match a
frontier one on verification-friendly tasks. A good orchestration prompt makes the
loop explicit so Claude drives itself to a *provable* finish instead of stopping at
"good enough".

Every prompt rests on six load-bearing parts. If any is missing, the loop never
terminates, terminates without finishing, verifies only by self-report, or can't be
cold-started by a fresh session.

## The method

### 1. Pin the Goal to a *verifiable, demonstrable* done-condition

A `/goal` run checks completion by sending the condition + conversation to a fast
model after each turn. **That evaluator does not run commands or read files** — it
judges only what Claude *surfaced in its output*. So the condition must be
demonstrable, and it must be anchored to **ground truth, not narration**: name the
deterministic artifact that proves it (an exit code, a test-count line, a diff, a
query result the loop pasted), so a confident-but-wrong model can't score itself
green by asserting success.

- Good: "All five repos paste a `pytest` summary line showing 0 failures."
- Good: "Zero open P1 issues — paste the final query result."
- Weak: "The code is better" / "tests pass" (nothing in the transcript proves it).

**Then pressure-test for *reachability*, not just verifiability.** A condition can be
demonstrable yet impossible to satisfy without the system misbehaving. Distinguish
**validate** goals ("prove X works" — a correct *negative* IS success) from
**optimize** goals ("drive the metric to 100"). For a validation goal the Done-when
must accept a *verified-correct negative*, e.g. "a created card passing the gate
**OR** a verified zero-result run where every stage is green and the empty result is
*because* the gate correctly held all inputs (≥1 hold validated against ground
truth)." Otherwise the loop burns its whole budget chasing a target correct behavior
won't produce.

### 2. Decompose if the goal is large

Break it into **sequential sub-goals, each with its own narrow verifiable
condition**. The loop advances one sub-goal at a time; each is a checkpoint a fresh
context can resume from.

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

Give every chunk a **model tier**, not just a mechanism — this is how you get
"frontier results from a cheaper model": run the harness cheap, spend the strong
model only where judgement is load-bearing.

| The chunk is… | Mechanism | Model tier |
|---|---|---|
| "Look across all repos and tell me X" | Workflow / 3–5 subagents | cheap/low-effort (mechanical fan-out) |
| Mechanical edit, rename, codemod | per-repo dispatch | cheap/low-effort |
| Hard reasoning, design, ambiguous fix | `/goal` drive | frontier/high-effort |
| **Independent verify / judge (step 5)** | verifier subagent | **frontier/high-effort** |
| "Re-check Z every N minutes" | `/loop` → Routine | cheap |
| "Remember/recall across sessions" | brain (`tapps_memory`) | n/a |

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

### 5. Add an independent verification pass (the harness's biggest lever)

Self-verification is the weakest link: the same agent that did the work judges the
work and rationalizes its own output. The single largest quality gain in harness
engineering is a **separate, adversarial verifier** — this is what lets a modest
model ship reliable results.

- Put verification on the **coordination plane** as its own step: after Execute,
  spawn a **verifier subagent** (frontier tier) with a *fresh* context, prompted to
  **refute** the sub-goal's proof — re-run the deterministic check (tests, lint,
  build, the actual query) rather than trust the executor's narration. Default to
  "not done" on any doubt.
- For high-stakes or irreversible steps, use **N independent verifiers + majority**
  (perspective-diverse where the finding can fail multiple ways: correctness,
  security, does-it-reproduce), not one. In a Workflow, this is a `parallel()` of
  verify agents keyed off each finding.
- The verifier's verdict — not the executor's claim — is what advances the loop or
  triggers the diagnose branch.

### 6. Make it cold-start runnable (the drop-in test)

The point is a prompt a **brand-new session** can run with zero hand-holding.

- **Self-bootstrap launch line.** `/goal "<condition>"` carries only the *condition*
  into a fresh session — not the prompt body. So every emitted prompt needs a
  top-of-file **"How to run (cold start)"** block with one paste-able line that
  **reads the file in full first, then enters the loop**.
- **Self-healing preconditions.** Anything the loop needs (a runtime up, a
  scorer/tool built, a branch, auth reachable) is a **Sub-goal 0** the loop
  *establishes itself* — never a "set this up first" note the user must action.
- **Deploy-freshness + smoke/health gate** (any prompt that runs against a live or
  deployed target, not source): in Sub-goal 0, self-healing — (1) **merged ≠ live**:
  if the target is a baked image, compare latest merged commit to the build time and
  rebuild/redeploy (preserving overlays) if `main` is newer; make "ran against a
  stale image" a required-fail cap. (2) **smoke before spend**: after any
  rebuild/deploy and before the real run, hit `/health` and one cheap end-to-end
  call to prove runtime + auth + transport.

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
- **Scope** — name the exact repos/paths; reads can be fleet-wide, writes go through
  the owning repo's channel.
- **Budget** — every loop carries *both* an iteration cap and a token budget; set a
  Workflow `budget` to a token ceiling (≈ the autonomy cost gate) so it self-aborts.
- **Memory** — recall at the start, record the outcome (incl. failures) at each
  checkpoint, so learning survives the session.

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

## Engineering discipline (emit in every prompt's guardrails)

Produce *solutions*, not band-aids: root-cause not workarounds; **no
green-by-suppression** (never skip/disable a check to pass); **right-sized** (the
simplest thing that fully solves it); durable over expedient; match repo conventions;
no silent scope creep.

## Output

1. Read the workspace manifest (e.g. `fleet.md`) for the repos / Linear projects /
   brain ids involved, if the project has one.
2. Fill `assets/prompt-template.md` — keep only the sections the task needs. Always
   keep the **"How to run (cold start)"** block, a **Sub-goal 0** for self-healing
   preconditions, and the **Verify** step wired to an independent verifier.
3. If any chunk is multi-stage parallel work, also write the companion
   `.claude/workflows/<slug>.js` (schema + `budget` + per-stage `model`/`effort`) and
   point Run-as at it. A single coupled item (N=1) is a `/goal` drive, not a Workflow.
4. Save the prompt to `prompts/<short-slug>.md`.
5. **Completeness self-check** — every chunk names a concrete mechanism *and* model
   tier (no "may"); the loop has *both* an iteration cap and a budget; there's an
   **independent verification** step (not self-report); any fan-out has a schema'd
   return + per-agent contract; a memory recall+record step; an **Autonomy
   contract**; a **bounded diagnose-don't-repeat** path; a **context-hygiene** line;
   and the **Engineering discipline** line. For a live/deployed target, confirm
   Sub-goal 0 has the deploy-freshness + smoke/health gate. Run the **cold-start
   test**: a fresh session with nothing loaded can run it. Fix anything weak before
   saving.
6. Tell the user exactly how to run it — the `/goal` line, the `/loop` cadence, the
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

## How to run (cold start — paste into a NEW session)
<`/goal "<condition>"` alone does NOT load this file's body, so the launch line must
read the file first, then loop.>

- **Goal loop (recommended):** `Read prompts/<slug>.md in full, then execute it as a goal loop — run the Loop section repeatedly until Done-when holds, printing the score line every iteration. Establish your own preconditions per Sub-goal 0; do not stop unless an Autonomy hard-stop fires.`
- **Durable / recurring:** save as a Routine (one item per run) so it survives the terminal.

## Objective
<one sentence — the outcome, not the steps>

## Done-when (Goal condition — ground-truth, not narration)
<a single condition Claude's own output can demonstrate. Name the deterministic
artifact that proves it — exit code, test-count line, diff, pasted query result.>

## Sub-goals  (sequential; each a checkpoint)
0. **Establish preconditions (self-healing — the loop sets these up, NOT the user).** <runtime up, scorer/tool built, auth reachable, branch ready>
   - **Deploy freshness (live/deployed target only):** merged ≠ live. If baked image, compare latest merged commit to build time; rebuild/redeploy (preserve overlays) if `main` is newer. Stale image = required-fail cap.
   - **Smoke + health gate (after any deploy, before the real run):** `/health` is `ok|degraded` and one cheap end-to-end call succeeds.
   - proof: <preconditions verified; for live targets — image no older than latest merged commit + a 200/non-error smoke pasted>
1. <narrow, verifiable> — proof: <ground-truth artifact>
2. <…>

## Plane map  (mechanism + model tier per chunk)
| Step | Plane | Mechanism | Model tier | Notes |
|------|-------|-----------|-----------|-------|
| <audit/research> | coordination | Workflow / 3–5 subagents | cheap/low-effort | fan-out OK |
| <code change> | execution | dispatch to <repo> via PR | cheap unless hard | one repo at a time |
| <verify proof> | coordination | **verifier subagent (fresh context)** | **frontier/high-effort** | refutes the proof; re-runs the check |
| <recurring check> | execution | Routine / `claude -p`+cron | cheap | human-gated |

## Loop
- **State:** <read first — status, brain recall of prior attempts, Linear>
- **Decide:** <how to pick the next action / sub-goal>
- **Execute:** <the action, on the committed mechanism + tier>
- **Verify (independent):** spawn a fresh-context verifier (frontier tier) to *refute* the sub-goal's proof — re-run the deterministic check, don't trust the executor's claim. The verifier's verdict advances the loop.
- **On fail:** diagnose (error + state + brain recall) → hypothesis → fix → retry *differently*; ≤3 distinct strategies, then escalate once, then stop with a diagnosis
- **Record:** <save outcome + any failure-and-why to the brain>
- **Context hygiene:** prune stale reads; carry a compact state summary, not raw transcripts.
- **Repeat or stop:** loop until **Done-when** holds; caps: <N iterations> AND <token budget>

## Guardrails
- Termination: <goal condition>; caps: <N iterations> AND <token budget>.
- Independent verification (not self-report); ground-truth proof.
- No fan-out of coupled coding — sequential per-repo edits.
- Context hygiene — targeted grep over full re-Read.
- Scope: repos in play = <list>; reads fleet-wide, writes via owner.
- Memory: recall at start; record outcome (incl. failures) at each checkpoint.
- Discipline: root-cause not workarounds; no green-by-suppression; right-sized; durable; match conventions; no scope creep.

## Autonomy
- Act on every reversible, in-scope step — no "should I proceed?" checkpoints.
- Irreversible/outward step → produce the reversible precursor (draft PR / staged diff / proposal) and continue; human reviews async.
- Hard-stop once (batched, with a recommendation) only for: irreversible/outward with no precursor · projected next-step cost > ceiling · unsafe-to-guess ambiguity.

## Failure handling
- On failed verify: diagnose (error + state + brain recall) → hypothesis → fix → retry *differently*.
- ≤3 distinct strategies per sub-goal; then escalate once; then stop with a concise diagnosis. Never repeat the same action on the same error.

## Context
- Repos: <manifest — path · Linear project · brain project_id>
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

- One enormous goal → sequence narrow sub-goals.
- Unbounded loop (no cap/budget) → always set max iterations or a token budget.
- **Self-verification only** → add an independent, adversarial verifier.
- Paying frontier rates for mechanical fan-out → tier the model per chunk.
- Parallel agents on coupled code → sequential per-repo dispatch.
- Vague done-condition → demonstrable, ground-truth-anchored condition.
- Context rot (re-reading the same files each iteration) → prune + targeted grep.
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

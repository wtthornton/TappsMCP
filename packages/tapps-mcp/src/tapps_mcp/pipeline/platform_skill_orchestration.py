"""Platform ``orchestration-prompt`` skill — body + companion files."""

from __future__ import annotations

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
frontier one on verification-friendly work. Every prompt rests on nine load-bearing
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

### 0b. Harvest the user's standing constraints *before* shaping the goal

A constraint that lives only in conversation history **dies with the session**. The
runner is a fresh context: it knows nothing the prompt does not carry. Enumerate every
standing instruction the user has given — "don't touch production", "read-only for
now", "never force-push", "ask before spending" — and encode each in **two** places:
**Guardrails** states the rule; an **Autonomy hard-stop** enforces it at the moment of
action, so a loop optimizing for a green score cannot satisfy the goal by breaking it.

The failure this prevents is severe: a loop whose Done-when requires "system
configured" will configure the *live* system to score itself done. **Split such
goals** — "built and tested against fixtures" is automatable; "applied to production"
is a hard-stop needing authorization. If you cannot restate a constraint as a
condition checkable *at the moment of action*, it is not yet encoded.

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

**Require at least one clause where a *count must not shrink*.** Every "failures = 0"
condition is satisfiable by destruction: delete the tests, close the issues unfixed,
weaken the assertion. Discipline forbids green-by-suppression in prose, but the
Done-when never *proves* it did not happen — so pair every must-reach-zero clause with
a must-not-shrink one: "0 failing **and** ≥ N tests collected"; "36/36 green, where 36
is the enumerated total"; "every story Done **or** Cancelled *with a reason*". If a run
could satisfy the condition by removing the thing being measured, it is not finished.

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
always frontier tier). Selector table: `references/claude-feature-map.md`. For host-specific Run-as, checkpoint lanes, and MCP scope, read `references/host-feature-map.md`.

**Preflight the mechanism before you commit a chunk to it.** A mechanism that is
listed is not a mechanism that works: a granted tool with no targets, a degraded
index, an unreachable MCP server all fail *silently* and the loop degrades into a
confident wrong answer. Sub-goal 0 must prove each one executes once for real.

**Emit literal dispatch parameters, not adjectives.** "cheap tier" is not
dispatchable. Every subagent in an emitted prompt names `agentType` + `model` (+
`effort` where it runs in a Workflow): `Agent(subagent_type: "Explore", model:
"haiku", prompt: "<narrow question + return schema>")`. Three constraints that change
the design, not just the wording — full tables in `references/claude-feature-map.md`:

1. **`effort` is Workflow-only.** The Agent tool accepts `model` but **not** `effort`;
   an Agent subagent inherits the session's. If a step's effort is load-bearing —
   verification especially — put it in a Workflow and set `opts.effort`. Writing "use
   high effort" in an Agent prompt does nothing.
2. **`agentType` is a permission boundary.** `general-purpose` holds Edit/Write even
   when the prompt says read-only; `Explore` cannot write at all. Pick `Explore` for
   read-only work so the tool boundary enforces it, and check `git status` after any
   `general-purpose` fan-out.
3. **Tier by question shape, not output size.** A cheap model is reliable on closed,
   evidence-checkable questions and unreliable on open-ended judgement that gates an
   action. Narrow the question until cheap is safe, or pay frontier. **Never let a
   cheap model's verdict gate an irreversible step**; re-derive load-bearing
   conclusions from the evidence it returned.

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
- **Hand the verifier the *proof command*, not the claim.** A fresh context cannot
  see the executor's work, so a narrative ("the endpoint now returns 200") invites it
  to reason about plausibility instead of running anything — self-verification in
  disguise. Give it the exact command, the expected artifact, file:line anchors, and
  environment quirks (non-default ports, which interpreter, auth source). Its report
  must quote the output it actually observed.
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
  adopted or overridden, and a live target passes artifact-identity + `/health`.
  **Artifact identity is two distinct failures, both required-fail caps:** *stale*
  (merged ≠ live — rebuild if `main` is newer than the build) and *divergent* (built ≠
  loaded — a compose service with `build:` and no `image:`, a bind mount shadowing the
  baked path, a stale layer cache, or a container still on the previous image id).
  Verify by identity — running image id vs the one just built, or a sentinel string
  from the new source found inside the running artifact — never by the build's exit
  code. Checklists: `references/cold-start-and-verify.md` (incl. `tapps_session_start()` as first MCP call).

### 7. Context lifecycle — recycle at every sub-goal boundary (handoff → re-verify → clear → continue)

Context hygiene (§4) slows the rot; it does not reset it. A long run loses to its own
context twice. **Cost:** every turn re-pays for the whole transcript, so iteration 40 on
a 200k context costs a multiple of the same work done at 30k, and past ~600k tokens the
run gets disproportionately fragile to `529 Overloaded` kills. **Quality:** a context
thick with superseded reads degrades the judgement making the next decision. The fix is
a **shift boundary** — persist state, drop the transcript, rehydrate from the state: a
fresh worker on a new shift, not a longer one ("one-task-one-session").

**The boundary already exists in this method; the loop is simply never told to take it.**
§2 makes each sub-goal "a checkpoint a fresh context can resume from" and §6 requires the
prompt be cold-start runnable — together those mean a sub-goal boundary *is* a valid
context boundary. So every emitted prompt makes it explicit, as a first-class loop step:

1. `/tapps-handoff-session` — persist Done / Open / Next(P0) / Verify / cumulative caps.
2. **Re-verify the handoff before trusting it** — the mandatory gate below.
3. `/clear` — or the process boundary; see the run-shape table.
4. `/tapps-continue-session` — rehydrate from the handoff, not from a paste.

**This is a quality gain, not only a cost cut.** §5 wants the verifier to hold a *fresh*
context; a recycled context is exactly that, for free, at the boundary where the next
executor starts. And the cycle continuously exercises the cold-start property §6 only
asserts: if the handoff cannot restart the loop you learn it at sub-goal 1, while the
context is still alive to diagnose with — not at session death when it is gone.

**Mechanics: `/clear` is a built-in CLI command the model cannot invoke.** It is not a
skill and not a tool, so an autonomous loop cannot clear itself. Never emit a prompt
telling the loop to "run `/clear`" — it silently no-ops and the context keeps growing.
Name the realization per run shape instead:

| Run shape | What plays the role of `/clear` |
|---|---|
| **Attended operator** | The prompt prints a CHECKPOINT block and stops; the operator runs `/clear` then `/tapps-continue-session` (Cursor: **new chat**, no `/clear` API) |
| **Autonomous** | **One `claude -p` invocation per sub-goal** — the process boundary *is* the clear, and the handoff file is the only channel between runs |
| **Workflow / subagents** | Each agent already starts fresh; delegate the noisy work so it never enters the orchestrator's context, and let the handoff carry what a return schema does not |

The autonomous shape is the load-bearing one: it turns a monolithic run into a chain of
short, independently cheap invocations, and it is already this skill's execution-plane
tool (Routines / `claude -p` + cron).

**The trap: a handoff is a claim about the past.** Recycling destroys the context that
would have caught a wrong claim, so an unverified handoff converts a cost win into a
correctness loss — measured: a handoff under three hours old offered a PR as "open,
needs review" that had merged 43 minutes after the file was written, and listed two
already-fixed config drifts as live; three false items in a four-item **Open** section.
An age warning would never have fired. So the boundary carries a **mandatory re-verify
gate**, not just a save:

- **Handoff `Git:` sha vs `git log -1`** — differing means the file predates real work;
  `git log --oneline <handoff-sha>..HEAD` names what landed.
- **Every named PR / issue state re-read from the tracker** (`gh pr view`, `get_issue`),
  never from the file. A Done status is a claim in both directions — report it, never
  conclude from it alone.
- **Every metric re-read from its newest artifact** (test count, score, coverage), never
  inherited from prose.
- **On mismatch: correct the handoff *before* clearing**, and treat every **Open** item
  as unverified until re-probed.

`/tapps-continue-session` runs this gate on the resume side; the prompt still states it
so the boundary is enforced even when the resume happens in another host.

**One runner per handoff file.** Two loops sharing `.tapps-mcp/session-handoff.md`
silently overwrite each other — the second save wipes the first run's Open items and the
first run then rehydrates the *other* run's state, with no error anywhere. Before
chaining `claude -p` invocations, check for a concurrent lane; if two runs must overlap,
give each its own handoff path.

**When *not* to recycle.** The cycle costs a save plus a rehydrate and loses everything
nobody wrote down. Skip it inside one tightly-coupled sub-goal, when the remaining work
is smaller than the cycle's overhead, or when live state resists compression into ten
bullets — and say *which*, rather than silently dropping the boundary.

**Clearing resets the loop's own guardrails unless the handoff carries them** — attempt
cap, budget, and refuted strategies live in the transcript you just dropped, so a loop
that recycles three times has, in effect, no cap. Carry-forward contract and the
re-verify-on-resume rule: `references/cold-start-and-verify.md`.

## Guardrails every emitted prompt must carry

- **Verifiable termination** — the Goal condition *and* a hard cap (max iterations
  or a token budget) so a stuck loop stops instead of burning quota.
- **Independent verification** — the sub-goal's proof is confirmed by a verifier that
  did not produce the work (method §5), handed the *proof command* rather than the
  claim, against ground truth.
- **Standing user constraints** — every one restated as a Guardrail *and* an Autonomy
  hard-stop (method §0b); no Done-when clause is satisfiable by violating one.
- **No green-by-deletion** — at least one Done-when clause is a count that must not
  shrink, so the goal cannot be met by removing what is measured (method §1).
- **Every subagent dispatch names `agentType` + `model`** (and `effort` when it runs
  in a Workflow) — never "spawn an agent to…". Read-only work uses `Explore` so the
  tool boundary, not the prose, enforces it. No cheap-model verdict gates an
  irreversible step; load-bearing answers are re-derived from returned evidence.
- **Research grant** — every emitted prompt states that the loop has web access,
  `tapps_research` and `tapps_lookup_docs` (Context7-backed, local-cache-first, so
  effectively free to repeat), and **names the specific lookups required before the
  first line of code touching an external API**. A loop that writes against a
  versioned external surface from recalled syntax will hallucinate a schema that lints
  clean and fails at runtime. Research-to-*execute* is in scope; research-to-*decide*
  still goes to `/tapps-wayfind`.
- **Caps must not fire on *correct* behavior** — for every required-fail cap, ask "is
  there a legitimate correct run where this still fires?" Separate *broken* from
  *correct-empty* (the gate rightly held everything) or a correct negative scores red.
- **Terminal lessons-learned pass** — every emitted prompt ends with a REQUIRED final
  sub-goal that mines the run and appends to `learnings.md`, plus a Done-when clause
  gating on it. Without a clause in Done-when it is advisory, and an autonomous loop
  drops advisory work the moment the real goal goes green — which is exactly when the
  lessons are freshest. It is the one sub-goal that survives trimming. Point it at what
  an independent verifier *refuted* first: that is the run's densest source of
  transferable lesson, because each item is something the loop believed and got wrong.
- **No fan-out of coupled coding** — parallel agents editing related code cascade
  errors; keep code edits sequential, per repo.
- **Context hygiene** — prune stale reads each iteration; targeted grep over full
  re-Read (method §4).
- **Context lifecycle** — a long loop recycles instead of growing: at each sub-goal
  boundary (or ~50% context, whichever first) `/tapps-handoff-session` → **re-verify** →
  a real clear (subagent / next `claude -p` / operator `/clear`) → `/tapps-continue-session`
  (method §7). Never clear on an unverified handoff — check sha vs `git log -1`, re-read
  named PR/issue state from the tracker, re-read metrics from their newest artifact. One
  runner per handoff file. The handoff carries **cumulative** attempt-count,
  budget-spent, and refuted strategies, or the clear silently resets the caps and the
  loop repeats what already failed. Name the sub-goals where the boundary is skipped and
  why.
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
cost of the next step exceeds the configured ceiling (default ≈ USD 20; honor any higher
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
2. Read `references/host-feature-map.md` when the runner host is Cursor or when Run-as / checkpoint lanes differ by host.
3. Read the workspace manifest (e.g. `fleet.md`) for the repos / Linear projects /
   brain ids involved, if the project has one.
4. Fill `assets/prompt-template.md` — keep only the sections the task needs. Always
   keep **Prerequisites / Wayfind gate**, the **"How to run (cold start)"** block, a
   **Sub-goal 0** for self-healing preconditions, the **Verify** step wired to an
   independent verifier, the **Lessons learned** section with its REQUIRED final
   sub-goal *and* its Done-when clause, and — when changing software behavior — a
   **Validation contract** filled *before* execution sub-goals plus an
   **expected-fail fix loop** with attempt cap.
5. If any chunk is multi-stage parallel work, also write the companion
   `.claude/workflows/<slug>.js` (schema + `budget` + per-stage `model`/`effort`) and
   point Run-as at it. A single coupled item (N=1) is a `/goal` drive, not a Workflow.
6. Save the prompt to `prompts/<short-slug>.md`.
7. **Completeness self-check** — walk the **Guardrails** list above and confirm the
   emitted prompt satisfies every line; then run the **cold-start test** (a fresh
   session with nothing loaded can run it). Fix anything weak before saving.
   **Context lifecycle is checked explicitly**, because nothing else catches its
   absence: confirm the prompt names a context boundary per sub-goal (or says which
   sub-goals skip it and why), that the boundary carries the re-verify gate, and that
   the autonomous run shape is named as one `claude -p` per sub-goal rather than a
   `/clear` the loop cannot invoke. A template supplies the boundary by default, so a
   prompt that quietly drops it looks finished — this is the one guardrail whose failure
   mode is silence.
8. Tell the user exactly how to run it — the `/goal` line, the `/loop` cadence, the
   Routine schedule, or "invoke the Workflow tool `<script>`" — and from which
   session.

## Learn as you go (measured evolution)

`learnings.md` (project-scoped) is written on **two** occasions. Both are required —
the second is the one that gets forgotten, and it is the richer of the two.

**1. At generation time (you, writing the prompt).** Read `learnings.md` before
drafting and fold in relevant lessons. When a generation teaches a better pattern — or
the user edits your output before running it — append a one-line lesson.

**2. At the end of every RUN of an emitted prompt.** The prompt itself must carry the
terminal lessons-learned sub-goal and the Done-when clause that gates on it (see
Guardrails and `assets/prompt-template.md`). Generation-time lessons capture what you
learned *planning*; run-time lessons capture what the work actually cost — and those
are the ones a fresh session cannot rediscover. If a run finished without them, the
harness paid for the mistake and kept none of the value.

Keep lessons **project-scoped**; never bleed them across repos.

**What a lesson must be.** Transferable to a *different* task, concrete enough to
falsify later, and where possible carrying the cheap command that detects the trap.
Mine what an independent verifier **refuted** before anything else — a refuted claim
is by construction something the loop believed and got wrong, which is the densest
lesson available. Then what cost the most retries, then any premise that turned out
false, then evidence that did not prove what it appeared to.

**What a lesson is not.** A narration of the run (that is the handoff). A one-off
project fact — a ticket id, a port, a service quirk — which belongs in brain or a
project memory file. A near-duplicate of an existing bullet: read the file first and
*sharpen the existing line* instead. And never filler — **zero lessons is a legitimate
outcome**, stated in one line. A manufactured lesson corrupts this file the same way
an invented error corrupts a correction.

**Keep it readable.** This file is read in full before every generation, so every
stale bullet taxes every future run. Past roughly 120 bullets or 40 KB, merge
overlapping lines and delete ones overtaken by a fixed tool or a changed codebase.
Pruning is part of the loop, not cleanup deferred forever.

Treat this as a *measured* loop, not a scratchpad: the harness improves by observing
its own runs. When a golden set (`evals/evals.json`) and a gated improvement loop
(`SELF_IMPROVEMENT.md`) exist, promote a template change only when it shows measured
lift against the evals — don't hand-tune blind.
"""
)

_PROMPT_TEMPLATE = r"""# <Objective title>

> Generated by the `orchestration-prompt` skill. Keep only the sections this task
> needs. Run from the orchestrator session unless noted.
>
> **Structurally required — do not drop or reshape these:** `## How to run (cold start)`,
> `## Done-when`, `## Loop`, `## Guardrails`, `## Autonomy`, plus `## Standing constraints`
> whenever the user has given any. Keep bullets as bullets under every `##` heading —
> tooling that parses these files (and the sibling handoff linter) reads bullet lists, and
> silently rejects prose where it expects `- `.

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
- **Resuming mid-run (after a checkpoint):** `/tapps-continue-session` first, then the Goal-loop line above — the handoff supplies current sub-goal, cumulative caps, and refuted strategies. Re-verify live state before acting on any handoff claim.

## Standing constraints  (REQUIRED when the user has given any — they die with the session otherwise)
<Every persistent instruction the user has stated: "read-only for now", "don't touch
prod", "never force-push". Each must ALSO appear as an Autonomy hard-stop below —
Guardrails state the rule, the hard-stop enforces it at the moment of action.
If a Done-when clause could be satisfied by violating one of these, split the goal:
"built and tested against fixtures" is automatable; "applied to production" is gated.>

## Objective
<one sentence — the outcome, not the steps. Only fill if Prerequisites say route is clear.>

## Done-when (Goal condition — ground-truth, not narration)
<a single condition Claude's own output can demonstrate. Name the deterministic
artifact that proves it — exit code, test-count line, diff, pasted query result.
For software behavior: every validation-contract ID below is verified by an
independent verifier (paste evidence per ID).
MUST include one clause where a count must NOT shrink (">= N tests collected",
"36/36 of an enumerated total") — otherwise the goal is satisfiable by deletion.>

**REQUIRED final clause (never delete this one):** the lessons-learned pass has run
and the project's `orchestration-prompt/learnings.md` carries this run's transferable
lessons, or the run states in one line that it produced none and why. Paste the
appended bullets. A run that solved the problem and taught the harness nothing is only
half done.

## Validation contract (before execution — software behavior only)
<Skip for pure research/triage/docs. Write assertions BEFORE execution sub-goals.>

| ID | Behavioral assertion | Fulfilled by sub-goal | Evidence tool |
|----|----------------------|-----------------------|---------------|
| VAL-… | <user-visible / API / CLI outcome> | <sub-goal #> | <pytest / smoke / tapps_validate_changed / …> |

Coverage rule: every ID claimed exactly once; Done-when requires all IDs green.

## Sub-goals  (sequential; each a checkpoint)
0. **Establish preconditions (self-healing — the loop sets these up, NOT the user).** <runtime up, scorer/tool built, auth reachable, branch ready; wayfind resume already recalled in Prerequisites>
   - **TAPPS session bootstrap:** `tapps_session_start()` as the first MCP call (or `/tapps-continue-session` on resume).
   - **Deploy freshness (live/deployed target only):** merged ≠ live. If baked image, compare latest merged commit to build time; rebuild/redeploy (preserve overlays) if `main` is newer. Stale image = required-fail cap.
   - **Smoke + health gate (after any deploy, before the real run):** `/health` is `ok|degraded` and one cheap end-to-end call succeeds.
   - **Harness compatibility:** <PreToolUse gates + MCP standing nudges the loop's tool calls will hit → bake unlock/refresh steps here; adopt-or-override each nudge in Guardrails>
   - proof: <preconditions verified; for live targets — image no older than latest merged commit + a 200/non-error smoke pasted>
1. **(Software behavior) Finalize validation contract** — proof: contract table above complete + coverage check pasted
2. <narrow, verifiable execution> — fulfills: <VAL-…> — proof: <ground-truth artifact>
3. <…>
N. **Lessons learned (REQUIRED — always the last sub-goal, never dropped when trimming).**
   Run the pass in "Lessons learned" below and append to the project's
   `orchestration-prompt/learnings.md`. — proof: the appended bullets pasted, or one
   line saying nothing transferable came up and why.

**Context boundary between sub-goals** (recycle unless noted): `/tapps-handoff-session`
→ **re-verify the handoff** (see Loop → Recycle) → `/clear` → `/tapps-continue-session`.
Autonomous runs take it as a **process** boundary — one `claude -p` per sub-goal — since
`/clear` is a built-in CLI command the loop cannot invoke itself. Skip the boundary
inside a tightly-coupled sub-goal or when the remaining work is smaller than the cycle's
overhead; say which sub-goals skip it and why. One runner per handoff file.

## Plane map  (mechanism + literal dispatch parameters per chunk)
<`effort` applies only inside a Workflow — the Agent tool has no effort parameter and
inherits the session's. If a step's effort is load-bearing, run it in a Workflow.>

| Step | Plane | Mechanism | agentType | model | effort | Notes |
|------|-------|-----------|-----------|-------|--------|-------|
| <audit/research> | coordination | Workflow / 3–5 subagents | `Explore` | `haiku` | `low` | read-only enforced by agent type, not prose; research-to-*decide* stays on wayfind |
| <multi-file synthesis> | coordination | subagent | `Explore` | `sonnet` | `medium` | judgement about what matters |
| <code change> | execution | dispatch to <repo> via PR | `general-purpose` | `sonnet` | `low` | **serial writes** — one repo at a time |
| <hard/ambiguous fix> | execution | `/goal` drive | `general-purpose` | `opus` | `high` | load-bearing judgement |
| <verify proof> | coordination | **verifier subagent (fresh context)** | `general-purpose` | **`opus`** | **`high`–`xhigh`** | creator ≠ verifier; refutes proof; a weak verifier defeats the pattern |
| <fix after fail> | execution | fresh worker on scoped fix sub-goal | `general-purpose` | `sonnet` | `low` | expected-fail loop; do not reopen whole feature |
| <recurring check> | execution | Routine / `claude -p`+cron | `Explore` | `haiku` | `low` | human-gated |

Cheap-model rule: `haiku` answers closed, evidence-checkable questions. It does not
render verdicts that gate irreversible steps — narrow the question or pay for `opus`.

## Loop
- **State:** <read first — wayfind resume (`memory_group=wayfind`), status, brain recall of prior attempts, Linear, last handoff>
- **Decide:** <how to pick the next *execute* action / sub-goal — never invent decide work; if fog reappears → stop and `/tapps-wayfind`>
- **Execute:** <the action, on the committed mechanism + tier>
- **Verify (independent):** spawn a fresh-context verifier (frontier tier) to *refute* the sub-goal's proof — re-run scrutiny + behavioral checks against the validation contract. Hand it the **exact proof command, expected artifact, file:line anchors, and environment quirks** (non-default ports, which interpreter, auth source) — never the executor's narrative, or it will reason about plausibility instead of running anything. Its report must quote the output it observed. The verifier's verdict advances the loop.
- **On fail (expected-fail fix loop):** record structured handoff → scope narrow fix sub-goal → re-execute → re-verify; ≤**3** validation rounds per sub-goal (override: N=…), then escalate once, then stop with a diagnosis. Never weaken the contract to go green.
- **Record (structured handoff):** completed · undone · commands+exit codes · issues · procedures followed? · failure-and-why → brain
- **Context hygiene:** prune stale reads; carry a compact state summary, not raw transcripts.
- **Print every iteration:** `SCORE: <metric>/<total> · <metric2> · sub-goal <k>/<n> · iteration <i>/<cap>` — a long autonomous loop with no per-iteration signal is unmonitorable, and the trend is what tells a watching human whether to intervene.
- **Recycle (context boundary — at each sub-goal boundary or ~50% context, whichever first):** `/tapps-handoff-session` → **re-verify** → clear for real (autonomous: the next `claude -p`; attended: operator `/clear`; Cursor: new chat) → `/tapps-continue-session`. Never instruct yourself to run `/clear` — an agent cannot invoke a built-in CLI command. **The re-verify gate is mandatory:** clearing destroys the context that would catch a stale handoff, so before clearing check the handoff `Git:` sha against `git log -1` (`git log --oneline <sha>..HEAD` names what landed), re-read every named PR/issue state from the tracker, and re-read every quoted metric from its newest artifact. On mismatch, fix the handoff *before* clearing and treat every **Open** item as unverified until re-probed. Skip the boundary only inside a tightly-coupled sub-goal or when the remaining work is smaller than the cycle's overhead — say which and why. One runner per handoff file: two loops sharing it overwrite each other silently. See Checkpoint protocol below.
- **Repeat or stop:** loop until **Done-when** holds; caps: <N iterations> AND <token budget> — **both cumulative across shifts**, read from the handoff, never reset by a checkpoint

## Checkpoint protocol (context shift boundary)
<Keep for any loop expected to exceed one context window. Delete for short one-shot prompts.>

- **Lane:** <delegated (subagents/Workflow) · process boundary (`claude -p` / Routine, one iteration per process) · declared checkpoint (operator types `/clear`)>
- **Trigger:** sub-goal boundary, or ~50% context / before a fan-out wave — whichever first.
- **Write:** `/tapps-handoff-session` → `.tapps-mcp/session-handoff.md` (lints + mirrors to brain in one call).
- **Resume:** `/tapps-continue-session` → rehydrates ~15 lines, not a transcript.
- **Carry-forward (must survive the clear, or the guardrails stop binding):**
  - Current sub-goal + the VAL IDs it must turn green
  - Attempt count vs cap — **cumulative**, e.g. `round 2 of 3`
  - Budget spent — **cumulative**
  - Strategies already tried and refuted, and why (preserves diagnose-don't-repeat)
  - The exact resume line from "How to run (cold start)"
- **On resume, re-verify before acting:** the handoff is a pointer, not a proof. Re-check live state (`git rev-parse --short HEAD`, PR state, `git merge-base --is-ancestor HEAD origin/master`, <target-specific>) — a claim true at checkpoint can be false an hour later. The independent verifier still runs; a checkpoint never replaces it.

**Declared-checkpoint block** (interactive lane — print verbatim, then stop):
```
CHECKPOINT <n> — sub-goal <k> complete. Handoff written.
Cumulative: round <a> of <cap> · budget <spent>/<ceiling>.
Next: /clear   then   /tapps-continue-session
```

## Guardrails
- Termination: <goal condition>; caps: <N iterations> AND <token budget>.
- Wayfind fog gate: no Goal invent while decide tickets / Not yet specified remain.
- Validation contract before features when changing behavior; coverage complete.
- Independent verification (creator ≠ verifier); ground-truth proof; verifier gets the proof command, not the claim; expected-fail fix loop with attempt cap.
- Standing constraints: <each one from the section above — and each also an Autonomy hard-stop>.
- No green-by-deletion: <the Done-when clause whose count must not shrink>.
- Every subagent dispatch names `agentType` + `model` (+ `effort` in a Workflow); read-only steps use `Explore`; no cheap-model verdict gates an irreversible step.
- Research grant: the loop has web + `tapps_research` + `tapps_lookup_docs` (cache-first, free to repeat). Never write against an external/versioned API from memory — required lookups: <list>.
- No fan-out of coupled coding — sequential per-repo edits (serial writes, parallel reads OK).
- Context hygiene — targeted grep over full re-Read.
- Context lifecycle — recycle at each sub-goal boundary: handoff → **re-verify** → clear → continue; never clear on an unverified handoff; one runner per handoff file; caps are cumulative across shifts, never reset by a clear; boundaries skipped only where the prompt says so and why.
- Scope: repos in play = <list>; reads fleet-wide, writes via owner.
- Memory: recall wayfind resume + prior attempts at start; record structured handoff (incl. failures) at each checkpoint.
- Lessons learned: the final sub-goal runs the "Lessons learned" pass and appends to `learnings.md`. It is REQUIRED and is the one sub-goal that survives any trim — a run that fixes the problem and teaches the harness nothing has paid full price for half the value. Mine what the verifier refuted first.
- Harness compatibility: <gated tool calls → unlock/refresh steps; MCP standing nudges → adopted or overridden>.
- Discipline: root-cause not workarounds; no green-by-suppression; right-sized; durable; match conventions; no scope creep.

## Autonomy
- Act on every reversible, in-scope step — no "should I proceed?" checkpoints.
- Irreversible/outward step → produce the reversible precursor (draft PR / staged diff / proposal) and continue; human reviews async.
- Hard-stop once (batched, with a recommendation) only for: <each standing constraint that guards a write> · irreversible/outward with no precursor · projected next-step cost > ceiling · unsafe-to-guess ambiguity · **validation contract itself is wrong** · **fog returned (open decide work)**.

## Failure handling
- On failed verify: diagnose (error + state + brain recall) → hypothesis → fix → retry *differently*.
- ≤3 distinct strategies per sub-goal; then escalate once; then stop with a concise diagnosis. Never repeat the same action on the same error.
- Expected-fail: first verify fail is normal — scoped fix sub-goal, not panic or contract rewrite.

## Context
- Repos: <manifest — path · Linear project · brain project_id>
- Wayfind decisions: <named decisions from resume / map Decisions-so-far>
- Prior learnings: <brain recall query, if any>

## Unverified assumptions  (optional — include whenever research fed this prompt)
<Claims the prompt relies on that were NOT confirmed against ground truth: a
source-read inference rather than an observed runtime behavior, a doc that
contradicts the code, a source that was unreachable during research. Without this
section the runner treats every stated fact as equally solid and builds on sand.
Name the cheap check that would settle each one, and require it before the fact is
depended upon.>
- <claim> — basis: <how it was derived> — confirm by: <the cheap check>

## Lessons learned  (REQUIRED — runs once, at the end, before Run-as is reported done)

Append to the project's `orchestration-prompt/learnings.md` (project-scoped; never
bleed lessons across repos). This is the harness improving from its own runs —
skipping it is how the same trap gets paid for twice.

**Mine these four sources, in order. Do not summarize the run.**

1. **What an independent verifier refuted** — the highest-value source by far. Anything
   a verifier caught is, by construction, something you believed and got wrong.
2. **What cost the most wall-clock or the most retries** — the wrong diagnosis, the
   silent tool failure, the poll that looked like a different problem.
3. **A premise that turned out false** — especially one this prompt itself asserted, or
   one that pre-specified the shape of an answer the evidence would not fit.
4. **Evidence that turned out not to prove what it seemed to** — a green check that did
   not discriminate, a count that was satisfiable another way.

**Each bullet must earn its line.** Bar:

- **Transferable** — it would change behavior on a *different* task.
- **Concrete and falsifiable** — name the real artifact, number, or error string.
- **Actionable** — name the cheap command that detects the trap next time.
- **Dated** — trailing `(YYYY-MM-DD)`, matching the file's house style.

**Do NOT write:** a narration of the run (that is the handoff's job) · a one-off
project fact such as a ticket id, port, or service quirk (those go to brain or a
project memory file) · a near-duplicate — read the file first and *sharpen the
existing bullet* instead · filler. **Zero lessons is a legitimate outcome** — say so
in one line. Manufacturing a lesson corrupts the file exactly the way over-confessing
an error corrupts a correction.

**Route each finding to the right home:** how to orchestrate/verify/diagnose better →
`learnings.md` · this run's state, commands, failures → brain, via the Record step ·
a durable fact about this repo or setup → a project memory file.

**Keep the file readable.** It is read in full before every generation. Past ~120
bullets or ~40 KB, spend part of this pass merging overlapping bullets and deleting
ones overtaken by a fixed tool or a changed codebase.

## Run-as
<exact invocation, e.g.:>
- **Cold-start loop (recommended):** the paste line from "How to run" above. **or**
- `/goal <condition>` — only if this file is already in context. **or**
- invoke the Workflow tool with `.claude/workflows/<script>.js` (fan-out only). **or**
- Routine: schedule `<cadence>` with this prompt, push=draft-PR. **or**
- **Chained (autonomous, context-recycling):** one `claude -p` per sub-goal, each run starting from `.tapps-mcp/session-handoff.md` and ending by rewriting it. The process boundary is the clear, so per-turn context cost stays flat and every sub-goal gets a fresh executor. Re-verify the handoff at the start of each run; one runner at a time — check for a concurrent lane before starting.
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
| **Issue-tracker write** (Linear/Jira/GitHub) | Creating or updating backlog items from inside the loop | Backlog-driven loops that file, close, or re-scope work as implementation reveals reality | Often **hook-gated** (e.g. a validation sentinel with a short TTL, plus a cache-first read gate). Route through the owning skill, never the raw API — and re-satisfy the gate if the loop has outlived the sentinel |
| **AgentForge agent / workflow** | Durable, versioned, published cognition running on the AF platform — survives the session, is Git-authored and independently invocable | Domain reasoning a project needs repeatedly: authoring, judging, analysis. **Where a project's agents should live**, rather than as LLM calls inside its own services | AF cannot see your repo or network — collect source locally and pass it as a declared workflow input. Side effects stay in the consumer |
| **AgentForge `expert-*` agents** | Pre-published platform experts (architecture, testing, security, performance, database, api-design, observability, …) | A second opinion during planning or review, at no authoring cost | They return analysis, not actions. Record where you *rejected* the advice and why |
| **`/tapps-handoff-session`** | Writes `.tapps-mcp/session-handoff.md`, lints, mirrors to brain, closes the session lifecycle — one call | Closing a shift: the checkpoint a cleared session resumes from | Must carry *cumulative* attempt-count + budget + refuted strategies, else the clear resets the loop's caps |
| **`/tapps-continue-session`** | Rehydrates a fresh session from the handoff (~15 lines) + `tapps_session_start` | Opening a shift; cold-starting a loop mid-run | Handoff is a pointer, not a proof — re-verify live state before acting on it |
| **`/clear`** | Built-in CLI command that drops the transcript | Operator-driven shift boundary in an attended run | **No agent can invoke it.** A prompt that tells the loop to run `/clear` silently no-ops — use a subagent, a new process, or an operator checkpoint |

## Model-tier selector — concrete parameters, not adjectives

"cheap tier" is not a dispatchable instruction. Emit the literal parameter values.

**Where each parameter is accepted (check before writing a dispatch line):**

| Caller | `agentType` | `model` | `effort` |
|---|---|---|---|
| **Agent tool** | `subagent_type:` | `model:` — `haiku` \| `sonnet` \| `opus` \| `fable` | **not accepted** — inherits the session's effort |
| **Workflow `agent()`** | `opts.agentType` | `opts.model` | `opts.effort` — `low` \| `medium` \| `high` \| `xhigh` \| `max` |

Consequence worth designing around: **if per-step effort matters, the chunk belongs in
a Workflow**, because the Agent tool cannot set it. Reaching for the Agent tool and
writing "use high effort" in the prose does nothing.

| The chunk is… | agentType | model | effort | Why |
|---|---|---|---|---|
| Poll a status, fetch a file, run a fixed command | `Explore` | `haiku` | `low` | Deterministic; no judgement |
| Mechanical fan-out, read/summarize, inventory | `Explore` | `haiku` | `low` | Read-only by construction |
| Codemod / rename / mechanical edit | `general-purpose` | `sonnet` | `low` | Needs write tools; low judgement |
| Multi-file research needing synthesis | `Explore` | `sonnet` | `medium` | Judgement in what matters, not what exists |
| Hard reasoning, ambiguous fix, architecture | `general-purpose` | `opus` | `high` | Load-bearing judgement |
| **Independent verify / judge** | `general-purpose` | `opus` | `high`–`xhigh` | A weak verifier defeats the whole pattern |
| Adversarial refute on an irreversible step | `general-purpose` | `opus` | `xhigh`–`max` | Cost of a wrong pass is unrecoverable |

## What a cheap model may decide (measured, not assumed)

Model tier must track **the shape of the question**, not the size of the output.

- **Safe on `haiku`:** closed questions with a mechanical answer — "does step X report
  success?", "which files match?", "is this value present?". A wrong answer is visible
  immediately because the evidence is right there.
- **Not safe on `haiku`:** open-ended judgement that *gates* an action — "is CI OK?",
  "is this change safe to merge?", "did anything regress?". Observed failure mode: a
  cheap verifier returned "NO NEW FAILURES FROM THIS PR" while a check on the exact
  changed path was failing *because of that PR*, having skipped the log-fetch step it
  was told to run. It reasoned backwards from the desired conclusion.

**Rule:** narrow the question until a cheap model can answer it from evidence, or pay
for a strong one. Never let a cheap model render a verdict that gates an irreversible
step. If a cheap agent's answer *is* load-bearing, the orchestrator re-derives the
conclusion from the evidence the agent returned, rather than accepting its verdict.

## Agent type is a permission boundary, not a label

`general-purpose` carries Edit/Write **even when the prompt says "read-only"** — a
research agent once silently modified a source file during a prompt-writing turn.
`Explore` has no write tools at all. For genuinely read-only work, pick `Explore` and
let the tool boundary enforce it; prose does not. After any fan-out that used
`general-purpose`, check `git status` before trusting the tree.

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
- **Verifier handed the claim instead of the proof command** → it reasons about
  plausibility and never runs anything; self-verification in disguise.
- **Done-when satisfiable by deletion** ("0 failures" with no floor on the count) →
  pair every must-reach-zero clause with a must-not-shrink one.
- **A user constraint left in chat history** → the fresh runner never sees it and will
  violate it to score green; restate it as a Guardrail *and* a hard-stop.
- **Trusting the build's exit code as proof the runtime changed** → verify artifact
  *identity* (running image id vs the one just built, or a sentinel from the new source
  found inside the running artifact).
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
- **Growing one context to the finish** → checkpoint at shift boundaries: handoff →
  real clear → continue.
- **Telling the loop to run `/clear`** → it cannot; pick a real clear mechanism.
- **Clearing without carrying cumulative caps** → attempt cap and budget reset each
  shift, so a capped loop becomes unbounded and re-tries refuted strategies.
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

### 0. TAPPS session bootstrap (every loop)

Before any other TAPPS MCP tool in a fresh session (including after
`/tapps-continue-session`, which calls this internally): run `tapps_session_start()`.
Skipping it leaves the checker matrix and project context stale — a required-fail
cap when the loop depends on quality gates or `usage_gaps` telemetry.
`usage_gaps.recurring_validation_skips` is **7-day rolling fleet telemetry**, not
proof the current call failed; still run `tapps_validate_changed` + `tapps_checklist`
at epic boundaries in execution repos with full `nlt-build`.

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

## Shift-boundary checkpoints — the context-recycle cycle (method §7)

A checkpoint discards the transcript — and the transcript is where the loop's own
guardrails were tracked. Clear without carrying them and the guardrails **silently stop
binding**: the attempt cap resets to zero, the budget resets to zero, and the fresh
session retries the strategy that just failed.

A checkpoint handoff must carry, on top of the stock Done/Open/Next/Verify fields:

- **Current sub-goal** + the validation-contract IDs it must turn green.
- **Attempt count vs cap** — *cumulative across shifts*, e.g. `round 2 of 3`.
- **Budget spent** — cumulative, so the ceiling still means something.
- **Strategies already tried and refuted, and why** — this is what preserves
  diagnose-don't-repeat across the boundary. Without it, clearing *causes* the
  repetition the failure-handling rule exists to forbid.
- **The exact resume line** (the cold-start launch line from §6).

**The handoff is a pointer, not a proof.** State recorded before the boundary describes
the world as it was. On resume, re-verify live state before acting — a PR that was
"open, merge pending" at checkpoint can be merged an hour later, flipping the correct
branch base. Treat every handoff claim as a hypothesis with a cheap test; the
independent verifier (§5) still runs, and a checkpoint never substitutes for it.

**The re-verify gate (mandatory, both sides of the boundary).** Run it before clearing
*and* on resume — clearing destroys the only context that could contradict the file:

| Check | Command | Failure it catches |
|---|---|---|
| Commit drift | `git log -1 --format=%h` vs the handoff **Git:** sha; then `git log --oneline <handoff-sha>..HEAD` | The file predates real work — every **Open** item is unverified until re-probed |
| Tracker state | `get_issue(<P0>)`, `gh pr view <N> --json state,mergedAt` | A merged PR offered as "needs review"; a P0 already Done or Canceled. Done is a claim in both directions — report it, never conclude from it alone |
| Metrics | Re-read from the newest artifact (test run, score report, coverage file) | A quoted count inherited from prose that the last commit already changed |

On any mismatch, **correct the handoff before clearing**. A known-wrong handoff inherited
by a fresh context is worse than no handoff: it reads as evidence.

**One runner per handoff file.** Two loops writing `.tapps-mcp/session-handoff.md`
overwrite each other with no error — the second save wipes the first run's state and the
first run rehydrates the other's. Check for a concurrent lane before chaining `claude -p`
invocations; give overlapping runs separate handoff paths.

**Declared-checkpoint block** (interactive lane — print verbatim, then stop):

```
CHECKPOINT <n> — sub-goal <k> complete. Handoff written.
Cumulative: round <a> of <cap> · budget <spent>/<ceiling>.
Next: /clear   then   /tapps-continue-session
```
"""

_HOST_FEATURE_MAP = r"""# Host feature map — Claude Code vs Cursor

Read when emitting **Run-as**, checkpoint lanes, or plane-map mechanism choices.
Default host = runner session: `.cursor/` present → Cursor; `.claude/` → Claude
Code; an explicit user flag overrides.

| Concern | Claude Code | Cursor |
|---|---|---|
| Goal loop | `/goal "<condition>"` (evaluates surfaced output only) | Explicit loop in prompt + paste ground-truth each iteration; optional `claude -p` for unattended |
| Fan-out verify | Workflow `parallel()` / subagents | `Task` tool (`explore`, `generalPurpose`, `shell`); Multitask Mode when parallel |
| Context reset | `/clear` (operator) · subagent · `claude -p` process boundary | **New chat** + `/tapps-continue-session` (no `/clear` API) |
| Recurring | Routine / `claude -p`+cron | Shell cron + `claude -p`; document in emitted prompt Run-as |
| MCP budget | Full six-server bundle common | ~40-tool cap — prefer `developer` bundle; orchestrator often memory-only |
| Plan vs execute | N/A | Plan Mode for fog; Agent Mode for execute (link to `/tapps-wayfind` for decide work) |
| TAPPS quality gate | Full `nlt-build` in execution repos | Orchestrator Cursor: often `nlt-memory` only — use `fleet-dispatch` for validate in owning repo |
| Session bootstrap | `tapps_session_start()` first MCP call every session | Same — required-fail if skipped when checkers are stale |

## Checkpoint resume by host

| Host | After `/tapps-handoff-session` |
|---|---|
| Claude Code | Operator runs `/clear`, then `/tapps-continue-session` |
| Cursor | **New chat** (Composer reset), then `/tapps-continue-session` |

Cross-ref: shift-boundary carry-forward in `references/cold-start-and-verify.md`;
cumulative handoff fields in `/tapps-handoff-session` and `/tapps-continue-session`.
"""

_LEARNINGS_SEED = """\
# orchestration-prompt learnings (project-scoped)

Append one-line lessons as you generate prompts. Keep them project-scoped; never
bleed across repos. This file is created once by the scaffolder and never
overwritten on upgrade — it's yours.

<!-- Example: -->
<!-- - Validation goals need a verified-correct-negative Done-when, or the loop chases an unreachable target. (2026-06-18) -->
"""
ORCHESTRATION_PROMPT_COMPANION_FILES: dict[str, str] = {
    "assets/prompt-template.md": _PROMPT_TEMPLATE,
    "references/claude-feature-map.md": _FEATURE_MAP,
    "references/cold-start-and-verify.md": _COLD_START_AND_VERIFY,
    "references/host-feature-map.md": _HOST_FEATURE_MAP,
}

ORCHESTRATION_PROMPT_CREATE_ONLY_FILES: dict[str, str] = {
    "learnings.md": _LEARNINGS_SEED,
}

__all__ = [
    "ORCHESTRATION_PROMPT_COMPANION_FILES",
    "ORCHESTRATION_PROMPT_CREATE_ONLY_FILES",
    "ORCHESTRATION_PROMPT_SKILL_BODY",
]

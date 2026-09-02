---
name: orchestration-prompt
user-invocable: true
model: claude-sonnet-5
description: >-
  Generate a ready-to-run orchestration PROMPT: a verifiable Goal, a bounded loop,
  and an independent creator-verifier pass. Refuses foggy Goals — redirects to
  /tapps-wayfind. Use whenever the user wants to orchestrate multi-step, multi-repo,
  autonomous, or recurring work — "create a prompt to…", "orchestrate…", "make a
  goal for…", "work the backlog", "loop until X" — even if they don't say
  "orchestrate".
argument-hint: "[free-form objective]"
---
<!-- BEGIN: tapps-skill orchestration-prompt v3.12.81 -->
<!-- upgrade-policy: managed-block. Edits made inside this BEGIN/END block are regenerated and lost on the next tapps_upgrade — put project-specific customizations below the END marker instead, where they survive every upgrade untouched. -->

# orchestration-prompt

You produce **prompts, not actions**. The output is a self-contained orchestration
prompt (a markdown file under `prompts/`) that the user — or a Routine, or a `/goal`
run — executes later. You write the *loop*; you do not run it.

## Terminal contract (hard stop — read before anything below)

**This skill AUTHORS a prompt. It never implements the work the prompt describes.** A
run terminates at exactly two things: a markdown file under `prompts/` and one fenced
launch block printed to the user (Output step 9). Branches, edits, dispatches, commits,
PRs and tracker writes that belong to the objective are the *runner's* job. Producing
any of them means this skill failed, however good the work itself was.

The input is always work-order-shaped — "orchestrate the burndown", "work the backlog",
"ship the epic" — so the shape of the sentence is never authorization to do the work. A
project autonomy rule that says to treat the request as standing authorization for every
step authorizes you to **write the prompt without asking**; it does not widen the scope
from authoring to implementing. Autonomy is about not pausing, not about scope.

**The only writes you may perform** are `prompts/<slug>.md`, the optional companion
`.claude/workflows/<slug>.js`, and `learnings.md`. Any other file touched on disk is a
defect, and Output step 7 checks for exactly that.

**Cargo convention.** Much of what follows is *cargo*: second-person text destined for
the emitted prompt and addressed to **its runner**, not to you. Every cargo section
opens with a `> **CARGO` marker line. When a cargo sentence says "decide and act on
every reversible, in-scope step", it is telling the runner to do that. Unmarked text is
method — addressed to you, the authoring session. If a second-person instruction is not
under a `> **CARGO` marker, it is for you; if it is, it is freight.

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

### 0c. Research preflight before design choices

**Prerequisite: `tapps_session_start()` must already have run.** A PreToolUse hook
blocks every other `tapps_*` tool call until session start has fired once this
session — a research step attempted before it silently fails, not just degrades.

Before pinning the Goal (§1) or choosing a mechanism (§3), run a research pass on any
design choice the prompt is about to bake in. **Route order:** `tapps_lookup_docs`
first (Context7-backed, cache-first, near-free to repeat) → `tapps_research` next →
raw web only after both. A raw-web finding is marked **`UNVERIFIED`** until a second
independent source, or a direct code read, confirms it — one web hit is a claim, not a
fact.

**Dispatch research, don't read it.** Fan research out to parallel `Explore`
subagents, each returning a structured verdict — never read search results or fetched
pages directly into the authoring context; that reintroduces exactly the token spend
delegation exists to avoid.

**Return schema — exactly four fields:**

- `claim` — the proposition being checked.
- `source` — the tool + library looked up (e.g. `tapps_lookup_docs("fastapi",
  "routing")`), or a URL plus the date it was read.
- `confidence` — `verified` (two sources agree, or a source plus a code read) /
  `reported` (one source, unconfirmed) / `unreachable` (the lookup failed or the
  source could not be reached).
- `contradicts` — the id/claim this one conflicts with, or `none`.

**A non-`none` `contradicts` is adjudicated in writing — never silently dropped.**
State which claim wins and why, and name the **reopen trigger**: the condition (a
later source, a code read that disagrees) under which the losing claim gets
re-examined. Silently picking a side and deleting the other loses the fact that the
harness was ever uncertain.

**Every non-`verified` finding flows into the emitted prompt's `## Unverified
assumptions` section** (§8 / template) — a `reported` or `unreachable` claim the
prompt depends on must stay visible to the runner, with the cheap check that would
settle it, not get buried in the authoring transcript.

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

**Disjoint file lists are not evidence of independence.** Two chunks can touch no file
in common and still be coupled, because one of them *computes* a set the other
*consumes*: the env-var names carrying required-interpolation markers in a compose file
that a CI placeholder env file has to mirror exactly, an enum a fixture enumerates, a
migration list a seed script replays, an exported-symbol set a barrel file re-exports.
Related code is the *obvious* coupling. Derived shared state is the one that ships,
because it **fails silently** — each half stays internally consistent, both verifiers go
green against their own half, and the mismatch only surfaces where the two artifacts
meet: a different machine, a later run, the CI runner rather than the laptop.

**The test to apply before pairing two chunks in a wave: what set does each one read
that the other writes?** Enumerate the derived sets in play — env-var names, marker
lists, generated fixtures, schema columns, exported symbols, lockfile entries, migration
ids — and for each one name its producer chunk and its consumer chunk. Any
producer/consumer pair spanning two chunks forces an order: the producer lands first,
the consumer re-derives afterwards. If you cannot name the derived sets, you have not
shown independence — you have only shown non-overlap. Carry the answer into the emitted
prompt as the Parallelization plan's `order-forced-by` field, so a later reader can audit
the claim instead of re-deriving it.

Give every chunk a **model tier**, not just a mechanism — run the harness cheap,
spend the strong model only where judgement is load-bearing (independent verify is
tiered by **proof shape** — see the table in method §5 — never uniformly maximal).
Selector table: `references/claude-feature-map.md`. For host-specific Run-as, checkpoint lanes, and MCP scope, read `references/host-feature-map.md`.

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

**Floor first; escalate only with a stated reason.** "Tier by question shape" reads as
neutral and so loses to whatever the session was already set to — which is how a
mechanical burndown and a contested identity read came to cost the same. State the
floor instead: **the emitted runner default is `sonnet` + `medium`** (and `haiku` +
`low` for closed transcription), carried literally in the emitted prompt's Session
setup line and in the launch block. A cell above the floor is legitimate, but it
carries a **one-clause reason in the same Plane-map row** — "gates a merge", "open
judgement", "cheaper tier failed this step twice". Those three are the escalation
criteria; a row that escalates without naming one is an unpriced default, not a
decision.

This is a change in posture, not in rigour. The proof-shape table (§5) still governs
verifier tiers, so a cheap *driver* never yields a cheap *verdict* on an irreversible
step — floor-and-justify sets where tiering starts, the table still says where a
verifier must end up.

**The top session dispatches, reads verdicts, and checkpoints — it does not do the work.**
The plane split says *where* a chunk runs; it never says the orchestrator itself is off the
hook, so prompts routinely assign half their sub-goals to `inline` and the one context that
cannot be reset spends frontier-tier tokens editing files and reading logs. State the
constraint on the top session directly: it decides what to dispatch, dispatches with literal
`agentType` + `model`, adjudicates verifier verdicts, makes the single gated or plugin-only
call a delegate structurally cannot reach, and checkpoints. It does **not** edit files, run
builds or migrations, run the test suite, trawl logs, or read large files into its own
context. Each of those is a dispatch.

**Give the orchestrator a measured budget, not an intention.** Target **under 15%** of the
run's total tokens for the top session, and require the emitted prompt's SCORE line to carry
an `orch-spend <n>%` field — alongside `pct <n>%` and `elapsed` — so the share is visible every iteration rather than discovered at
the end. An unmeasured share is one nobody notices growing.

**Two mechanical detectors — run them on the Plane map you just wrote, before you save:**

1. **Every `—` in the `agentType` column is orchestrator work.** A row with no agentType is a
   row nobody was dispatched for, so the top session does it. Five such rows is the whole
   budget (decide · dispatch · adjudicate · gated write · checkpoint); a sixth means a body of
   work leaked inline.
2. **An all-`—` `effort` column means effort control was surrendered** — `effort` is
   Workflow-only and an Agent subagent inherits the session's, so a prompt with no Workflow
   has no effort knob at all. That is a legitimate state; the prompt must *say* so. Silence
   reads as an omission, and the fix is to move the effort-load-bearing step into a Workflow,
   never to write "use high effort" into an Agent prompt.

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

- After Execute, spawn a **verifier subagent** (*fresh* context; tier it by the
  proof-shape table below, not at a uniform maximum) prompted to **refute** the proof:
  re-run the deterministic check rather than trust the executor's narration. Default to
  "not done" on any doubt.
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

**Tier the verifier by the shape of its proof.** "Verification matters, so
verification is frontier" is the expensive misreading. Eight verifiers all set to `opus`
spends frontier tokens re-reasoning about proofs an exit code had already settled, and
at the same time buries the two checks that genuinely needed judgement inside one
undifferentiated bill — so neither gets the effort it warranted. Read the proof first,
then pick the row:

| Proof shape | What the verifier actually does | model | effort |
|-------------|---------------------------------|-------|--------|
| **Deterministic** — exit code, `grep -c`, test-count line, file present | re-runs one command and reads its output; there is nothing to judge | `haiku` | `low` |
| **Comparative** — two outputs differ, a count did not shrink, a diff is confined to N files | re-runs both sides and compares; still closed, but it must compare the right two things | `sonnet` | `medium` |
| **Semantic** — "the section says what it claims", "the fix addresses the root cause", "the wording no longer instructs X" | reads artifacts and renders a judgement no command can settle | `opus` | `high` or `xhigh` |
| **Gates an irreversible step** — merge, deploy, delete, publish, tracker write | any shape, but a wrong PASS is unrecoverable | `opus` | `high`+ |

**Consequence overrides shape.** A deterministic proof whose verdict gates a deploy is
an `opus` row. Shape decides the tier only while the step is reversible.

**This table is authoritative.** A project note pinning verifier models means *pin explicitly, for a named reason, on the specific step where it applies* — never "pin
all high" as a blanket override of the table for the rest of the run.

**Verdict schemas carry evidence, not conclusions.** Every verifier's return schema
requires two fields beyond the verdict itself:

- **`observed_output`** — the literal text the verifier saw: the command's stdout, the
  pasted lines, the count. **An empty `observed_output` is a FAIL**, whatever the verdict
  field says — it means the verifier reasoned about plausibility instead of running
  anything, which is the exact failure an independent pass exists to eliminate.
- **`green_by_suppression`** (boolean) — true when the proof was satisfied by removing
  what it measures: the test was deleted, the assertion weakened, the file the grep
  counted is gone, the check skipped. A proof can be honestly green *and* be
  suppression; the verifier flags it, and the orchestrator treats a flagged proof as a
  fail.

**For cheap-tier verdicts the orchestrator reads `observed_output` and never the
conclusion sentence.** A `haiku` verifier's prose is the least reliable thing it returns
and its transcription of the command output is the most reliable; adjudicate on the
evidence field and treat the conclusion as commentary. That is precisely what makes a
cheap tier safe on a deterministic proof — the driver is not trusting the model's
judgement, only its copying.

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
overwrite each other — the second save wipes the first run's Open items and the first run
then rehydrates the *other* run's state. The write is no longer silent: the ownership
guard archives the incumbent and reports `conflict.foreign`, and under
`handoff_conflict_mode: block` it refuses outright. Do not rely on that as the plan.
Before chaining `claude -p` invocations, check for a concurrent lane; if two runs must
overlap, give each its own slot — `tapps_handoff_save(markdown=..., slot="<program>")`
and `/tapps-continue-session <slot>` — rather than sharing the default file.

**When *not* to recycle.** The cycle costs a save plus a rehydrate and loses everything
nobody wrote down. Skip it inside one tightly-coupled sub-goal, when the remaining work
is smaller than the cycle's overhead, or when live state resists compression into ten
bullets — and say *which*, rather than silently dropping the boundary.

**Clearing resets the loop's own guardrails unless the handoff carries them** — attempt
cap, budget, and refuted strategies live in the transcript you just dropped, so a loop
that recycles three times has, in effect, no cap. Carry-forward contract and the
re-verify-on-resume rule: `references/cold-start-and-verify.md`.

## Field rules

Twelve rules distilled from postmortems of this skill's own emitted prompts. Follow
each — they are not optional flavor text.

1. **Validate the instrument on a known-bad and a known-positive before trusting its
   verdict.** Method §6 preflights that a *mechanism* executes; nothing preflights
   that a *judgement instrument* — a verifier, linter, or scorer — actually
   discriminates. Before trusting a verdict, run the instrument once against a
   known-bad input and once against a known-good input and confirm it tells them
   apart. An instrument that passes everything (or fails everything) is a silent
   rubber stamp, not a check.
2. **Green-by-citation is distinct from green-by-suppression.** A cited source ("per
   the docs…") can be just as unearned as a deleted test if the citation is not tied
   to the claim it is supposed to establish. Every citation is quoted beside one
   sentence naming the exact proposition it establishes — a citation with no adjacent
   claim is decoration, not evidence.
3. **The verifier's control is the pre-change tree, not the fix's own tests.** A fix's
   own test suite is not a control group — it was written by the same actor with the
   same blind spots. Run the fix's proof against the unpatched tree and confirm it
   fails there; a proof that never ran against a failing baseline proves nothing about
   whether the fix did anything.
4. **A merge-gating verifier reports the PR's own CI by name and state, and re-runs
   the CI job's own command.** When a verdict gates a merge, name the actual CI
   check(s) on that PR and their actual state — not a locally-run proxy — and re-run
   the CI job's own command rather than an invented equivalent. A local pass that
   diverges from the CI command is not evidence the gate will pass.
5. **A measured number is a floor until the instrument is proven able to express it.**
   A wrapper script or CLI flag can silently discard the value it claims to report (a
   `--json` flag ignored, a count capped by a page size). Treat every measured number
   as a floor, not a fact, until the instrument is confirmed to express the true
   value — "0 failures" can mean "zero were counted", not "zero exist".
6. **Prove freshness per deployed layer and diff config per key hash; treat every
   deployment fact as point-in-time.** A multi-layer deploy (image, config map,
   running container, edge cache) can have one stale layer while the others are
   current — freshness is proven per layer, never once for the whole stack.
   Configuration is diffed by hashing each key, not by eyeballing a diff. No
   deployment fact survives past the moment it was checked.
7. **Run a blast-radius preflight before any state-touching verify step.** A command
   that reads as inert ("just checking the count") can still mutate or destroy state —
   a dry-run flag that is not actually a no-op, a script with a side-effecting import.
   Before running a verify step against live state, name what it could destroy and
   confirm the command is inert, rather than assuming from its name.
8. **A return schema separates queried-and-got-zero from the-query-failed;
   identifiers are resolved live at Sub-goal 0.** "Zero results" and "the query
   errored" are distinguishable fields in a return schema, never collapsed into one
   falsy value — a caller that cannot tell them apart treats a broken query as a
   clean negative. Identifiers (issue ids, repo paths, image tags) are resolved live
   at Sub-goal 0, never hardcoded from a stale prior run.
9. **Round-2 fix prompts gate on the delta and also sweep siblings by symbol.** A
   second-round fix sub-goal proves the specific delta the verifier flagged, and
   separately greps for other call sites of the same symbol or pattern — a bug fixed
   at one call site and left in three siblings is how a round-2 verify still turns up
   a fresh, different failure.
10. **A successor to a partially-failed program needs a disposition disjunction with
    a numeric floor and an anti-escape guard.** When a prior run stopped short, the
    next prompt's Done-when states an explicit disjunction of acceptable dispositions
    (e.g. "fixed OR cancelled with a written reason"), each with a numeric floor (N of
    M resolved), plus a guard against the trivial escape of cancelling everything to
    make the count balance.
11. **Agreement among artifacts is not corroboration — read the component with
    authority.** Two documents, dashboards, or logs that agree can both be downstream
    copies of the same stale source rather than independent confirmations. When a
    claim matters, read the component that actually has authority over it (the
    running config, the source serializer, the database row), not the artifact that
    merely displays it.
12. **A dispatched headless lane's structural limits are the author's problem,
    including that it dies when it returns.** A `claude -p` lane or a subagent that
    has returned cannot be polled, resumed, or asked a follow-up — and it cannot
    background work across its own return without losing it. Design the dispatch so
    the lane's own return is the last useful signal it gives; never assume a lane can
    pick back up after the dispatching call returns.

## Rulings

Verifier-tier guidance (method §5) is authoritative — see above. These eight rulings
resolve cases the proof-shape table does not spell out on its own.

1. A refuter may author a narrow fix and stay on as re-verifier while it owns the live
   repro, without weakening creator ≠ verifier before merge — the point of the rule is
   a fresh, adversarial perspective, not a fresh identity, and the agent already
   holding the live reproduction is best placed to confirm a scoped fix without
   re-establishing context from zero.
2. No-silent-scope-creep carries a data-loss carve-out — a delegate may step outside
   its named scope to stop in-flight data loss — and the carve-out is void the moment
   it is silent: acting outside scope is legitimate only if it is surfaced immediately,
   in the same report, never discovered later in a diff.
3. Shared quota is a coupling the independence test (method §3) must see. Two lanes
   with disjoint file lists can still contend for the same rate limit, API quota, or
   worker pool — that is a derived-state coupling exactly like an env-var set, and it
   forces the same `order-forced-by` treatment: a fan-out and the lanes beside it may
   need sequencing, not just disjoint paths.
4. Billing topology — which account or budget a dispatch's spend lands against — is
   frequently unresolved. Probe it at Sub-goal 0, as a live check, never cite it in a
   prompt as a known fact until it has been probed for that run.
5. Content-diff freshness (a built artifact's content hash vs source) is necessary but
   not sufficient — see method §6's stale/divergent distinction. It is repeated per
   deployed layer, never asserted once for a whole stack, and it expires: a freshness
   check from an hour ago is not evidence for the current run.
6. Cheap-tier transcription (method §5's `haiku`/`low` row) is reliable only when the
   return schema carries keyed pairs — `{name: value}` — never two parallel lists
   (`names: […]`, `values: […]`) the reader must zip back together by position. A
   cheap model transcribing two lists can silently misalign them; a keyed schema makes
   that structurally impossible.
7. On visual/UI work, one named artifact handover to the operator — a screenshot, a
   rendered page, a design-canvas link — is allowed before the verification tail
   spends its budget, so a human sees the actual visual result once early rather than
   only after several rounds of automated verify already ran. This is a single named
   handover, not a standing checkpoint.
8. The word "plane" is reserved for the coordination-versus-execution distinction
   (method §3). Do not reuse it for the build-time-versus-runtime distinction — use
   "surface" there instead ("build surface" vs "runtime surface"), so a reader can
   rely on "plane" meaning one specific thing throughout an emitted prompt.

## Verification routing and honest reporting

Ten rules promoted from a consuming project's local region, where they were working and
reaching nobody else. The Field rules above are about *whether a proof is sound*; these
are about *who runs it, over what population, and how its result gets reported*.

1. **Route a verifier by the permission its proof needs — a third axis beside proof
   shape and blast radius.** An adversarial brief that says "break the code and count the
   failures" cannot run on `Explore`: it is read-only, so `git init`, `git worktree add`,
   a scratch commit and every temporary mutation are refused. The agent behaves correctly
   and fabricates nothing — it reports the write-requiring steps UNVERIFIED — so a whole
   verification round buys static analysis instead of the mutation evidence that was
   asked for. Mutation tests, negative controls and scratch-repo reproductions need
   `general-purpose`; `Explore` stays the default only for genuinely read-only proofs.
   This is the routing axis whose failure returns a *non-answer*, so state the proof's
   write needs in the dispatch alongside `agentType` and `model`.
2. **Dry-run every string a verifier will execute, on the target tree, before the
   verifier launches — an amendment is a proof command too.** A proof command that is
   wrong about reality (a path that does not exist in that worktree, a venv binary in a
   venv-less tree, a summary table the page never had) makes the verifier report RED
   honestly, which is the right failure mode and still costs a whole fresh-context round.
   A clause *appended* to an already-verified proof row is a new command and gets the same
   dry-run. Every numeric floor also names the artifact it is counted from. Three riders
   on Workflow spend: a cached resume replays results keyed on (prompt, opts) and is blind
   to repo state, so any stage reading mutable state is re-launched fresh rather than
   resumed; guard the cheap pre-stage of an expensive gate, or a pre-stage failing for
   environment reasons silently cancels the stage that was the point; and a *mechanical*
   merge gate needs no fresh context at all — `git range-diff` printing `=` proves a
   rebase patch-identical for a few hundred tokens where a two-agent verification round
   costs six figures. Reserve fresh contexts for reads that actually need independence.
3. **Scope verification to the artifact, not to the diff.** Every mechanism in a program
   scoped to *change* is structurally blind to a falsehood already on the main line: a
   claim that contradicts the record beside it can survive round after round of review,
   because every reviewer was scoped to the diff and nobody was ever asked *is what is
   already here true?* A clean identity read is evidence about what the reader looked at,
   never proof of absence. Attribute a defect with a content search over history (`git
   log -S` on the string), never from the most recent nearby merge.
4. **Give every cross-cutting claim exactly one owner.** Per-artifact ownership makes
   cross-artifact truth nobody's job — splitting findings per page and fixing each page
   against its own record produces a second round whose findings are almost entirely
   *between* the pages. Either one lane owns a **claim** across every artifact that makes
   it, or the shared fact moves into one record the artifacts derive from. Scope
   owner-facing lanes by **what the recipient actually opens** (the zip, the PDF inside
   it, the email), not by file ownership: enumerate the shipped manifest first and make
   it the lane's file list. And a lane whose evidence runs a tool it does not own
   *reports* the failing line — it does not edit the tool, or two lanes fix the same
   shared bug two different ways and the fold conflicts irreconcilably.
5. **"Disjoint files" is measured, not argued.** The derived-shared-state test (§3) is the
   sophisticated half of the independence question and it can be right while the trivial
   half was never checked at all — a plan can correctly serialise one lane behind a shared
   derived set and, in the same paragraph, call two others "disjoint files *and* disjoint
   derived sets" when both edit the same module and both append to the same test file.
   Intersect the intended file lists mechanically before fanning out and record the result
   in the Parallelization plan. An elaborate dependency argument is not evidence that
   anyone ran the simple check.
6. **Prose is the unguarded surface — and a prose rule beside the code it governs does not
   stop the code.** The defects that survive their author's own review are overwhelmingly
   *prose*, and the code beside them is usually correct, which is exactly why nobody looks:
   a comment asserting that a dry-run previews what the real run does, when it compares
   pre-change state; a runbook naming a file that does not exist; a generator comment
   naming a failure mode precisely, a few hundred lines above the shipped instance of it.
   None is reachable by any test. Two consequences. Prose can assert a *consumer* that was
   never built, which makes an unshipped feature read as shipped and leaves every artifact
   agreeing about it — so grep for the reader, not just the writer. And where a preview and
   a real run must agree, **assert that they are equal**, never that both were "computed by
   the same logic": the latter is satisfiable by calling the right helper on the wrong
   state, which is the bug it was meant to exclude. Whenever you are about to add a standing
   constraint to a prompt, ask first whether the *dispatcher* could refuse the thing
   mechanically — an injected rule is still a reminder, and reminders lose to defaults.
7. **Never read tracker state as evidence that work happened.** An integration can write
   it: merging a PR whose title carried an issue id has auto-completed that issue seconds
   later, `completedAt` matching the merge, with most acceptance boxes unticked and no
   agent or human write behind it. Keep ids out of PR titles and branch names and put them
   in the body; make "is this PR attached to that issue?" a **pre-merge** check; re-read
   every issue that must stay open after every merge. The claim runs both ways — a
   prompt's own summary of tracker state is a handoff claim, not a fact, so a prompt that
   restates tracker state says so in the same breath. Close an issue by ticking each box
   with its evidence pointer, or leaving it unticked and saying in the body why:
   unticked-and-silent is the only version that is not honest.
8. **"Blocked" is a first-class lane outcome — say so, or lanes optimise for the number.**
   A lane that cannot clear a gate honestly, refuses to bypass it, and reports blocked with
   a diagnosis has usually located a real defect in the *gate*. A prompt silent on this
   reads as "return green", which is an instruction to suppress. State explicitly that
   blocked-with-a-diagnosis is a fully acceptable outcome, and that the diagnosis is the
   deliverable in that case.
9. **Read the spec adversarially before you read the code: could an implementation tick
   every box and leave the defect live?** Ask it of the *specification*, deliberately
   without reading the implementation. Reading the code finds one bug; reading the spec
   finds the generator of bugs. This is the emission-time twin of §1's must-not-shrink
   clause — both ask what a green run could look like while the goal is still unmet.
10. **Enforcement before remediation deadlocks; ship the ratchet instead.** An absolute
    per-file threshold fails any change touching a legacy file *including one that improves
    it*, so the only ways past are an override or an unrelated refactor — and a rule
    obeyable only by bypassing it enforces nothing. The ratchet is strictly harder to cheat
    than the flat bar: new files are never grandfathered, a passing file may never fall
    below the bar, only an already-under file gets the decrease-only test, and an
    unscoreable baseline falls back to absolute — unknown refuses, it never skips. Two
    riders: wire it into **every** enforcement point at once (landing it in CI but not the
    local hook just moves the deadlock one layer down), and **track the ratcheted
    population**, or the exemption becomes permanent.

**The identity read is a SEND gate, not a merge gate.** This amends the
artifact-identity guardrail below. An open-ended "would we ship this to the customer"
read re-reviews from scratch, so its bar moves every round and it never converges — it
can refuse a merge three rounds running, each time on real but *new* items, while
blocking strict improvements to something nobody sees until the outward step. **Merge**
on deterministic verification plus integration floors plus a post-merge live re-fetch;
run the expensive identity read **once**, immediately before the outward step it actually
protects. The two decisions have different blast radii and different convergence
properties, and conflating them turns an attempt cap into a wall. Note also what the
sibling gates cannot see: an integrity check proves the artifact was *not altered*, which
is exactly why it passes an artifact that is the wrong thing rendered faithfully.
Fidelity and identity answer different questions.

## Guardrails every emitted prompt must carry

> **CARGO — text for the emitted prompt, addressed to its runner.** Not an
> instruction to you, the authoring session (see Terminal contract).

- **Verifiable termination** — the Goal condition *and* a hard cap (max iterations
  or a token budget) so a stuck loop stops instead of burning quota.
- **Independent verification** — the sub-goal's proof is confirmed by a verifier that
  did not produce the work (method §5), handed the *proof command* rather than the
  claim, against ground truth. Its tier follows the **proof-shape table** (method §5)
  rather than a uniform frontier default, and its verdict schema carries
  `observed_output` (empty = FAIL) and `green_by_suppression`; cheap-tier verdicts are
  adjudicated on `observed_output`, never on the conclusion sentence.
- **Standing user constraints** — every one restated as a Guardrail *and* an Autonomy
  hard-stop (method §0b); no Done-when clause is satisfiable by violating one.
- **No green-by-deletion** — at least one Done-when clause is a count that must not
  shrink, so the goal cannot be met by removing what is measured (method §1).
- **Artifact identity, not just validity** — gates check form only (schema, exit code,
  geometry, provenance, signature) and will happily pass an artifact that is the wrong
  *thing* entirely. Every emitted prompt whose loop produces something a human or
  customer will look at needs one delegated step — named `agentType` + `model=opus`
  and tiered as open judgement rather than a closed check — that opens the artifact
  and answers *is this the thing that was asked for*, in words. Drop this guardrail
  only when the loop produces no artifact a human or customer will look at.
- **Execution-path proof before "this change takes effect"** — name the file, the
  checkout it resolves from, and the revision the consumer loads, then prove it with a
  marker check against that exact file — never a merge SHA or a branch name alone.
  Merging to a default branch is not the same as the consumer seeing it: a consumer
  can load a stale checkout, or one on a different branch, that never sees the merge.
  Forbid delegates from locating the tool by filesystem search — pin the path and
  hard-stop on mismatch. Drop this guardrail only when the change's producer and
  consumer are the same checkout.
- **Driver discipline — the orchestrator dispatches, it does not execute** (this is
  the Orchestrator-discipline guardrail; the emitted prompt carries it as the single
  required `## Driver discipline` section). The top session decides what to dispatch,
  dispatches, adjudicates verdicts, makes the gated or plugin-only calls a delegate
  cannot reach, and checkpoints. It edits no files, runs no builds, runs no probes,
  tails no logs, and gathers no per-iteration state. Every Plane-map row whose Owner is
  not `driver` is delegated, `orch-spend` stays under 15%, and the two detectors
  (method §3) have been run against the map.
- **Every dispatch carries a return schema** alongside `agentType` + `model` — a
  schema-less dispatch comes back as prose the driver must re-read, spending exactly
  the tokens the delegation was meant to save.
- **Test scope — no regression or full-suite run until the plan is complete.** Per-item
  proof runs **only the tests the change adds or touches**, with the command and its
  exit code pasted. A whole-suite run proves nothing that item owns, and on a large
  suite it approaches the wall-clock ceiling that kills a headless lane outright. One
  full **enumeration** per wave is enough to catch a collection error (a
  `--collect-only` count, not an execution), and exactly one regression run at program
  end, after the plan is complete — that run is the operator's call, not a per-item
  step.
- **Tier by question shape, not importance** — closed and evidence-checkable (line
  counts, string presence, exit codes) goes cheap *even at high stakes*; open judgement
  gating an irreversible step goes frontier *even when it looks small*. Defaulting
  everything to frontier is the expensive failure this rule exists to stop.
- **Dispatch each wave in full before polling it** — independent chunks grouped into a
  `### Parallel wave schedule`, with the constraint that actually binds stated (usually
  one working tree per repo). Serialising independent lanes buys no safety and costs
  wall-clock.
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
- **Parallel where independent, serial where coupled** — lanes that share no derived
  state fan out and dispatch to the background at iteration 1; the moment one lane reads
  a set another lane writes, they serialise and the emitted prompt names that set in the
  Parallelization plan's `order-forced-by` field. Disjoint file lists are not evidence of
  independence (method §3) — the coupling that fails silently is the one where each half
  is internally consistent.
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
  the owning repo's channel. **The session's workspace directory list is the scope
  fence — a fleet-registry row is not an in-scope target by itself**; a manifest can
  list far more repos than this session actually has open. Naming a repo in the
  prompt is inert: the boundary is crossed only when a tool call's *path argument*
  points outside the workspace. Audit by grepping the transcript for path
  **arguments**, never for repo names — a mention proves nothing either way. Every
  fan-out brief names the permitted paths and the dispatched agent's return schema
  reports the paths it actually read, so the fence stays auditable after the fact.
  Out-of-scope work discovered mid-run is a hard-stop to surface immediately, never a
  silent skip.
- **Budget** — every loop carries *both* an iteration cap and a token budget; set a
  Workflow `budget` to a token ceiling (≈ the autonomy cost gate) so it self-aborts.
- **Memory** — recall at the start, record the outcome (incl. failures) at each
  checkpoint, so learning survives the session.
- **Harness compatibility** — every tool call the loop makes that is gated by a
  project hook has its unlock/refresh step in the prompt, and every MCP standing
  nudge is explicitly adopted or overridden (method §6).

## Autonomy contract (every emitted prompt carries this)

> **CARGO — text for the emitted prompt, addressed to its runner.** Not an
> instruction to you, the authoring session (see Terminal contract).

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

> **CARGO — text for the emitted prompt, addressed to its runner.** Not an
> instruction to you, the authoring session (see Terminal contract).

On a failed verify, do **not** re-run the same action. Diagnose first: read the
actual error, inspect state/files, recall prior failures from the brain, research the
cause. Form a specific hypothesis, apply a fix, retry with *something changed*. Bound
it: max **3 distinct strategies** per sub-goal, then escalate once (more capable
model / different approach), then **stop and surface a concise diagnosis**. Repeating
the same action on the same error is forbidden.

## Expected-fail fix loop (Missions-inspired)

> **CARGO — text for the emitted prompt, addressed to its runner.** Not an
> instruction to you, the authoring session (see Terminal contract).

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

> **CARGO — text for the emitted prompt, addressed to its runner.** Not an
> instruction to you, the authoring session (see Terminal contract).

Produce *solutions*, not band-aids: root-cause not workarounds; **no
green-by-suppression** (never skip/disable a check to pass); **right-sized** (the
simplest thing that fully solves it); durable over expedient; match repo conventions;
no silent scope creep.

**Scope admission is announced, not forbidden.** A flat "no scope creep" is right about
*silence* and wrong about *scope* — it tells a lane to walk past a live Urgent defect it
is standing on. File everything you find. Admit into the current run only what is filed
**Urgent or High**, say so out loud in the same report that discovers it, and add it to
the SCORE denominator so `pct` tells the truth about the larger population rather than
quietly shrinking its own target. Everything below High is filed and left for the
operator. What stays forbidden is the *silent* version: work that appears in the diff
and nowhere in the report.

## Output

1. **Fog preflight (method §0).** If foggy, refuse and point at `/tapps-wayfind` —
   do not emit a prompt. If clear, recall `memory_group=wayfind` resume when present.
2. Read `references/host-feature-map.md` when the runner host is Cursor or when Run-as / checkpoint lanes differ by host.
3. Read the workspace manifest (e.g. `fleet.md`) for the repos / Linear projects /
   brain ids involved, if the project has one. **The manifest is a registry, not a
   scope grant** — it can list far more repos than this session's actual workspace
   directory list has open. Treat a manifest row as a candidate to confirm against the
   open workspace, never as authorization by itself.
4. Fill `assets/prompt-template.md` — keep only the sections the task needs. Always
   keep **Prerequisites / Wayfind gate**, the **"How to run (cold start)"** block,
   **`## Driver discipline`** with its Owner-column Plane map and
   **`### Parallel wave schedule`**, the **`## Parallelization plan`** that says which
   lanes are serial and why, a
   **Sub-goal 0** for self-healing preconditions, the **Verify** step wired to an
   independent verifier, the **Lessons learned** section with its REQUIRED final
   sub-goal *and* its Done-when clause, and — when changing software behavior — a
   **Validation contract** filled *before* execution sub-goals plus an
   **expected-fail fix loop** with attempt cap. Drop the template's
   **artifact-identity** Guardrails bullet only when the loop produces no artifact a
   human or customer will look at; drop the **execution-path proof** Guardrails
   bullet only when the change's producer and consumer are the same checkout.
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
   **Then assert no files were written outside `prompts/<slug>.md`, the optional
   `.claude/workflows/<slug>.js`, and `learnings.md`.** A stray branch, edit or commit
   means the terminal contract was broken and the run is a failure whatever the prompt
   scored.
8. Tell the user exactly how to run it — the `/goal` line, the `/loop` cadence, the
   Routine schedule, or "invoke the Workflow tool `<script>`" — and from which
   session.
9. **Launch block — REQUIRED, and the last thing the run produces.** Print exactly one
   fenced block and nothing after it. It carries a concrete `/model` and a concrete
   `/effort` — real values, never placeholders, because the runner otherwise inherits
   whatever the pasting session happened to be set to — and a line that reads the prompt
   file *before* looping, since `/goal "<condition>"` does not load the file's body:

   ```text
   /model sonnet
   /effort medium
   Read prompts/<slug>.md in full, then execute it as a goal loop from <cwd>: run the
   Loop section once per iteration, print the SCORE line every iteration, establish
   your own preconditions per Sub-goal 0, and stop only when Done-when holds or an
   Autonomy hard-stop fires.
   ```

   Then stop. Do not create a branch, dispatch a lane, or start Sub-goal 0 yourself —
   that is the terminal contract, and this block is where the skill ends.

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

## Multi-session programs

Everything above assumes **one driver session**. A program run by two or more interactive
sessions has a different failure surface than a single-driver loop — see
`.claude/rules/agent-to-agent.md` for the transport, identity/authority caveat, coordination
protocol, epistemic discipline, and the N-party scaling analysis (§7) this section builds on.
Restating that protocol here, instead of pointing at it, is the exact drift this repo exists
to remove.

### When to emit a multi-session program

Emit one **only** when the work has an irreducible need for a second interactive driver:

- **A second reader for claims** — a second session earns its keep on *claims in prose*, never
  by re-running measurements (`.claude/rules/agent-to-agent.md` §5, where the assertions-vs-
  second-reader split was measured).
- **A hard contract edge** where two drivers must hold opposite sides.

Do **not** add a session to parallelise dispatch — one driver fans out lanes perfectly well, and
a second driver doubles the operator's authorisation load (below). More sessions buy review
coverage, never separation of powers (agent-to-agent.md §2, §7 — same account, same credential,
same blast radius at any N).

### What the prompt MUST carry when there is more than one driver

Add these to the nine load-bearing parts; a multi-session prompt missing them is incomplete —
each is governed in full by `.claude/rules/agent-to-agent.md`, referenced here rather than
restated:

10. **Partition** — which paths each session owns, as a table (agent-to-agent.md §4). An
    unassigned path is unassigned, not free.
11. **Integrator** — the single session that merges; everyone else opens PRs (agent-to-agent.md
    §4, §7.3).
12. **Review ring** — each session adversarially reads exactly one other's *conclusions*
    (agent-to-agent.md §5, §7.4 — a ring covers every claim once, all-pairs does not scale).
13. **Authorisation clause** — a peer relaying an operator decision tells you a decision EXISTS,
    not that it applies to you; confirm it in your own window (agent-to-agent.md §3, §7.5).
14. **Session roster with worktrees** — one worktree per session (agent-to-agent.md §7.1: the
    single highest-value change, and cheap).

### How it gets kicked off

`dispatch-lane.sh` is the kickoff for one lane. **`scripts/start-program.sh` is the kickoff for
one program**, and it is what turns the items above from prose into state:

```
scripts/start-program.sh <slug> <driver-prompt> <integrator> <session>...
```

It measures how many live sessions share the working tree, cuts a worktree per session, writes
`reports/programs/<slug>/partition.md` (committed, so it binds sessions that were not in the
room), assigns the ring, and prints the exact text to paste into each session. It deliberately
does not message anyone: authorisation is per-session and a script must not appear to grant it.

So the full chain is:

```
/orchestration-prompt  ->  prompts/<slug>.md          (the program prompt; no action)
scripts/start-program.sh  ->  worktrees + partition   (only if >1 driver)
  human pastes kickoff text into each session
each driver  ->  prompts/<slug>-lane-*.md
scripts/dispatch-lane.sh  ->  claude -p in a worktree ->  PR
  integrator verifies independently  ->  merge
```

When emitting a multi-session prompt, include the literal `start-program.sh` invocation in the
prompt's kickoff section, and point every driver at `.claude/rules/agent-to-agent.md` — the
transport, the identity/authority caveat, the epistemic discipline, and the N-party scaling
analysis live there, and restating them in the prompt is the drift shape this repo exists to
remove.

### Cost discipline

The 2026-09-01 CEG program produced 59 commits, 53 lane prompts and ~20 long peer messages in a
day. It was correct — it caught three false claims on one client-facing page — and it was far more
expensive than it needed to be. The waste was concentrated and it was mechanical, not intellectual:

| Sink | What it cost | The fix, now available |
|---|---|---|
| Hand-rolled probes | 9 wrong results; 2–5 calls each to diagnose and redo; one measurement took 8 calls | `scripts/measure.py` — mandatory known-positive assertion, prints the denominator, diagnoses a miss instead of returning empty |
| Re-derived git facts | two-dot vs three-dot diffs, stale HEAD searches, "is this branch really unmerged" | `scripts/gitfacts.sh adds\|landed\|content\|stale\|sessions` |
| Peer status prose | ~20 messages, much of it status | `status/<session>.md` in the program dir; peers **read** state |
| Operator interrupts | ~6 separate asks across two windows | `decisions.md` — one table answered at kickoff |

**Emit these into every multi-session prompt:**

- Point at `measure.py` / `gitfacts.sh` by name and forbid hand-rolled equivalents. An ad-hoc
  one-liner used as evidence never gets the validation a test would get.
- Require a **denominator** with every count. "16 lines", "16 shown heroes" and "89 candidate
  records" are three different answers to what sounds like one question, and conflating two of
  them while holding a green assertion is how a wrong finding reaches a peer's queue.
- Put the **decision budget** in the prompt's kickoff, not in the loop. Authorisation cannot be
  relayed between sessions (`agent-to-agent.md` §3), so every un-batched decision costs one
  operator interrupt *per session*.
- Say explicitly that a second session reviews **conclusions, not measurements**. Re-running a
  peer's greps is the lowest-value work a second session can do, and it is the default thing an
  idle one will reach for.

**The single highest-leverage change is not a rule, it is that the checks became commands.** Nine
probe failures in one day were nine defaults being wrong; a prose rule saying "validate your probe"
was already in force and did not prevent any of them. `measure.py` refuses to emit results at all
unless a known-positive assertion passes — the constraint that replaces the reminder.
<!-- END: tapps-skill -->

<!-- tapps-skill-project-customizations: preserved from the pre-marker version — review and trim any content the managed block above now covers -->

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

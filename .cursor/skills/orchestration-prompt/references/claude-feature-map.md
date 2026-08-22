# Claude feature map — intent → mechanism → model tier

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

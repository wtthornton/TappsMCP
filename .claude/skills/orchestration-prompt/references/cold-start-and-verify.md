# Cold-start preflight & verification depth

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

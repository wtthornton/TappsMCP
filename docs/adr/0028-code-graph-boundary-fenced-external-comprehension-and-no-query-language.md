# 28. Code-graph boundary — fenced external comprehension tool + no query language

Date: 2026-07-01

## Status

Accepted (2026-07-01; TAP-4554)

Ratifies [SPIKE-code-graph-vs-codebase-memory-mcp](../spikes/SPIKE-code-graph-vs-codebase-memory-mcp.md).

## Context

tapps-mcp already ships a persistent, deterministic call graph
([ADR-0017](0017-function-level-call-graph-python-first.md), extended to
TypeScript in [ADR-0026](0026-typescript-call-graph-via-tree-sitter.md), shared
out-of-band in [ADR-0027](0027-shareable-call-graph-artifact.md)). It exists for
one job: make the review gate **blast-radius aware** — `tapps_call_graph`
(callers / callees / bounded chains), `tapps_diff_impact` (git-changed files →
ranked affected tests), route/impact queries. That graph is a single
deterministic store we control ([ADR-0004](0004-deterministic-tools-only-contract.md)).

Two adjacent decisions have been pending and are now forced by the spike:

1. **External code-graph tools.** codebase-memory-mcp (DeusData) indexes any
   codebase into a persistent, Cypher-queryable knowledge graph via tree-sitter
   (158 languages, LSP-like resolution, route/IaC edges, zst shareable
   artifact), pitched at ~99% token reduction for *comprehension*. The spike's
   key finding: it is pure AST, so it does **not** violate ADR-0004 — the real
   differences are **scope** (polyglot + route/IaC edges) and **shape** (an
   external C binary + a second SQLite store + a query language). Adopting it as
   a graph source would create a **second code-graph store with its own query
   language** — the parallel source of truth that
   [integration-hygiene](../../.claude/rules/integration-hygiene.md) forbids.
   The spike lays out three options (status-quo / fenced external comprehension
   MCP / extend our own graph to tree-sitter) and recommends never adopting it
   *as the graph*.

2. **A general graph-query language.** codebase-memory-mcp exposes an openCypher
   subset. Our graph today answers fixed, purpose-built questions only. Whether
   to grow a general query language (Cypher/openCypher) over the review graph is
   a standing question the spike surfaces but does not itself decide.

Both decisions are governed by the same two invariants:

- **Single source of truth (integration-hygiene).** A second graph store, or a
  second query surface over the same graph, is a parallel decision path that
  drifts from the store the review gate actually trusts.
- **Don't build/duplicate an MCP surface for something already covered
  ([ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md)).** The taxonomy's
  zero-duplication rule says a new server/tool surface must not re-implement a
  capability an existing tapps-mcp surface already owns. An *external*,
  auth-light, stateless comprehension MCP that never touches our graph/memory is
  a legitimate opt-in — it isn't a tapps-mcp-owned surface and doesn't duplicate
  the review graph — but wiring one *as* a graph or memory source is exactly the
  duplication that rule rejects.

## Decision

### Decision 1 — external code-graph tool is a fenced, opt-in comprehension tool, or it is rejected

An external code-graph / codebase-memory tool (e.g. codebase-memory-mcp) is
**not adopted by default.** It is permitted only in one narrow, fenced shape:

> An **optional, opt-in MCP** an operator may enable for agents working large
> polyglot repos, used **only** for read/comprehension queries (its
> `search_graph` / `trace_path` surface). It is a *reading aid for the agent*,
> nothing else.

**Fencing constraints (all mandatory — any breach means reject, not adopt):**

- **Never a graph source.** It must not feed, replace, or shadow the tapps-mcp
  call graph. The review graph stays the single deterministic store we control
  ([ADR-0004](0004-deterministic-tools-only-contract.md) /
  [ADR-0017](0017-function-level-call-graph-python-first.md)).
- **Never a memory source.** It must not become a second memory/brain surface.
  Memory flows through `tapps_memory` + `BrainBridge` only
  (integration-hygiene, [ADR-0001](0001-in-process-agentbrain-via-brainbridge.md)).
- **Never in the deterministic review tool chain.** It must not be routed
  through the review gate, `tapps_diff_impact`, `tapps_validate_changed`, or any
  gate verdict. Those stay ADR-0004-deterministic and served by our own graph.

**Concrete adoption threshold.** Even fenced, wiring it is justified **only when
all three hold** for a specific target repo:

1. **Measured** comprehension token cost on that repo (agent tokens spent
   grepping/reading to understand structure) exceeds **~50k tokens per
   comprehension task** on a recurring basis — i.e. token cost is the actual,
   quantified pain, not a hypothetical.
2. **Our own graph cannot serve the query** — the repo is polyglot beyond
   Python + TypeScript ([ADR-0026](0026-typescript-call-graph-via-tree-sitter.md)),
   or needs route/IaC/cross-service edges our graph does not model, so extending
   our own graph ([ADR-0026] tree-sitter path) is not the cheaper fix.
3. The tool stays **fully fenced** per the constraints above.

Absent a measured token cost over that bar on a repo our own graph provably
can't serve, the answer is **status-quo (Option 1): don't wire it.** For repos
inside our Python + TypeScript reach, the preferred investment is extending our
own graph (the spike's Option 3), not bolting on an external store.

### Decision 2 — no general graph-query language (no Cypher)

The review graph is served by **fixed, purpose-built tools only**:
`tapps_call_graph` (callers / callees / bounded chains), `tapps_diff_impact`,
and the route/impact queries. **A general graph-query language
(Cypher / openCypher) is explicitly NOT adopted** over the tapps-mcp graph.

Rationale:

- **The fixed surface matches the use-case.** The graph exists for review
  blast-radius — "who calls this", "what does this change hit", "which tests".
  Those are a small, closed set of questions the fixed tools answer directly. A
  general query language solves a comprehension/exploration problem we don't
  have on this store.
- **Deterministic, small, testable tool contract.** Fixed tools keep the
  contract enumerable and the outputs stable fixtures
  ([ADR-0004](0004-deterministic-tools-only-contract.md)). A query language
  makes the input space open-ended, the output shape query-dependent, and the
  fixtures brittle.
- **No query engine as attack/complexity surface.** A general query interpreter
  (parser + planner + evaluator over user-supplied query strings) is a standing
  complexity and injection surface with no offsetting review-path benefit. The
  fixed tools have no such surface.

If genuine ad-hoc graph exploration is ever needed, that is a *comprehension*
need — served (if at all) by the fenced external comprehension tool of Decision
1, never by growing a query language on the review-critical store.

## Consequences

### Positive

- The review graph stays exactly one deterministic store with a small, fixed,
  ADR-0004-testable tool contract — no second store, no second query surface, no
  drift (integration-hygiene single-source-of-truth intact).
- No query-engine attack/complexity surface is introduced.
- Token-cost pain on large polyglot repos still has a sanctioned escape hatch (a
  fenced, opt-in comprehension MCP) — but only when measured cost clears the bar
  and our own graph can't serve it, so the default remains "don't wire it."
- Aligns with [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) zero-duplication:
  no tapps-mcp-owned surface re-implements comprehension, and no external surface
  is allowed to shadow the graph/memory we own.

### Negative / constraints

- Non-Python/TypeScript repos get no symbol graph in the review path unless the
  fenced comprehension tool is opted into for *comprehension only* — review
  there stays lint-level (accepted; the spike's Option 1 trade-off).
- Agents cannot run ad-hoc graph queries against the review store; new
  review-graph questions require a new fixed tool, deliberately gated by an ADR
  or story rather than a query string.

### Revisiting

Reversing either decision requires a **fresh ADR backed by telemetry**, not an
ad-hoc PR:

- **Decision 1:** measured comprehension token cost over the ~50k threshold on a
  specific repo our own graph provably cannot serve, plus evidence the fencing
  holds. Wiring it *as* a graph or memory source (breaking any fence) is not a
  revisit — it is out of scope and rejected here.
- **Decision 2:** a demonstrated review-path need the fixed tools cannot meet,
  with the query surface's cost (complexity + attack surface + fixture
  instability) weighed against that need in the new ADR.

## Alternatives considered

1. **Adopt codebase-memory-mcp as the graph source.** Rejected — a second
   code-graph store with its own query language is the parallel-source-of-truth
   integration-hygiene forbids and regresses the single deterministic store
   ADR-0004/0017 established. The spike explicitly recommends "never Option
   'adopt as the graph'."
2. **Extend our own graph to tree-sitter for TS/Go/Rust now
   ([ADR-0026](0026-typescript-call-graph-via-tree-sitter.md) path, spike Option
   3).** Not decided *here* — it is the preferred long-term investment for repos
   in reach and is tracked separately; this ADR only bounds the *external tool*
   and the *query-language* questions.
3. **Add a general Cypher/openCypher query surface over our graph.** Rejected
   (Decision 2) — open-ended input, brittle fixtures, and a query-engine
   attack/complexity surface, with no review-path benefit over the fixed tools.

## References

- [SPIKE-code-graph-vs-codebase-memory-mcp](../spikes/SPIKE-code-graph-vs-codebase-memory-mcp.md) — the spike this ADR ratifies (Options 1/2/3 + recommendation)
- [ADR-0004](0004-deterministic-tools-only-contract.md) deterministic-tools-only — same input, same output; no LLM in the tool chain
- [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) needs-based MCP taxonomy — zero-duplication rule for MCP surfaces
- [ADR-0017](0017-function-level-call-graph-python-first.md) function-level call graph — the single review-graph store, fixed tools, non-goals
- [ADR-0026](0026-typescript-call-graph-via-tree-sitter.md) TypeScript call graph — the extend-our-own-graph path
- [ADR-0027](0027-shareable-call-graph-artifact.md) shareable call-graph artifact — cache-never-a-source-of-truth boundary
- [.claude/rules/integration-hygiene.md](../../.claude/rules/integration-hygiene.md) — single-source-of-truth / bridge-only / no parallel action surface
- `docs/CALL_GRAPH.md` — consumer guide for the fixed graph tools
- [TAP-4554](https://linear.app/tappscodingagents/issue/TAP-4554) this ADR

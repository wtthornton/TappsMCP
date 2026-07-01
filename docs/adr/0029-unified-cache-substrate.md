# 29. Unified cache substrate — one atomic primitive, pluggable staleness, no code-as-provider and no vector-RAG

Date: 2026-07-01

## Status

Accepted (2026-07-01; TAP-4556)

Ratifies [DESIGN-unified-cache-substrate-and-context-layer](../design/DESIGN-unified-cache-substrate-and-context-layer.md).

## Context

tapps-mcp caches two unrelated kinds of "knowledge" the same shape — *on-demand
tool + on-disk cache + graceful degradation* — but has grown **five parallel
file-cache implementations**, each re-writing atomic-write, staleness, and
(sometimes) warming/metrics:

| # | Cache | File | Staleness model | Provider |
|---|---|---|---|---|
| 1 | Docs (`KBCache`) | `tapps_core/knowledge/cache.py` | TTL / clock (24h + per-lib) | Context7 (network) + breaker |
| 2 | Code graph | `tapps_mcp/project/call_graph_cache.py` | content fingerprint (per-file sha) + `INDEX_VERSION` | local tree-sitter/ast build |
| 3 | Per-file tool results | `tapps_mcp/tools/content_hash_cache.py` | SHA-256 content hash | local (scoring/gate/security) |
| 4 | Dependency scan | `tapps_mcp/tools/dependency_scan_cache.py` | session / TTL | local (pip-audit) |
| 5 | Linear snapshots | `server_linear_tools.py` + `tools/linear_list_gateway.py` + `docs-mcp/.../linear_gateway.py` | TTL (`cached_at`/`expires_at`) | agent-fetched |

The two anchor caches make the split concrete. `KBCache` is a
**TTL / network-provider** cache: 24h clock with per-library overrides, a
Context7 fetch behind a circuit breaker, a `filelock`-guarded markdown+sidecar
layout, and the only `CacheStats` in the set. `call_graph_cache` is a
**fingerprint / local-build** cache: per-file sha plus `INDEX_VERSION`, a
deterministic local tree-sitter/ast build, a `mkstemp`+`replace` atomic write,
and no metrics. Their `_write_atomic` bodies are *different mechanisms*; their
staleness models (a clock vs a content hash) are *irreconcilable by nature*.

This is the load-bearing decision for the consolidation epic (TAP-4555): the
substrate boundary must be ratified **before** any code moves, because the two
tempting wrong turns are both cheap to start and expensive to unwind:

- **"Code becomes a `KBCache` provider."** Superficially "merge the caches", but
  it jams a fingerprint/local-build cache into a TTL/network-provider cache —
  forcing a clock onto a content hash and a fetch-with-breaker onto a
  deterministic build.
- **"Vector-RAG over the repo."** The 2026 research the design doc cites is
  explicit that structural graph beats vector retrieval for code (SWE-bench
  Verified leaders don't vector-index the target repo; code relevance ≠ text
  similarity). Routing the code graph through embeddings would regress
  [ADR-0004](0004-deterministic-tools-only-contract.md) determinism and the
  fixed-tool boundary [ADR-0028](0028-code-graph-boundary-fenced-external-comprehension-and-no-query-language.md)
  just set.

This ADR fixes the boundary and rules both out. It decides *what is shared*; it
does **not** authorize the P1–P3 code — each phase stays a separate go/no-go.

### 2026 research grounding (verified independently, not relayed from the design doc)

The design doc's direction was re-checked against current (mid-2026) primary
sources rather than cited second-hand:

- **Structural graph / AST beats vector RAG for code.** The SWE-bench Verified
  leaderboard (>80%) is dominated by agentic systems, and none of the top
  entries use vector retrieval over the target repo; Cursor, Claude Code, Codex,
  Cline, and Devin all use grep-like structural retrieval over embeddings for
  code, where exactness and composability matter. Embeddings flatten the import /
  call / type structure that carries code relevance. (Grewal 2026; MindStudio
  "Why Cursor, Claude Code, and Devin Use grep, Not Vectors"; SparkCo agent-memory
  comparison 2026.)
- **Tree-sitter file-incremental via content-hash is the 2026 consensus, and it
  is exactly our fingerprint model.** Incremental re-index by per-file content
  hash is ~4× faster than full re-index; Claude Code's own LSP-integration
  experiment *regressed* (symbol-resolution failures, +8.5% tokens, no quality
  gain). `call_graph_cache`'s per-file sha + `INDEX_VERSION` is the
  research-backed staleness model — keeping it (not generalizing it to a clock)
  is the correct call. (sheeptechnologies RFC-001; AutomaDocs "Tree-sitter vs
  LSP"; arXiv 2603.27277.)
- **Hybrid vector+graph and layered memory are real — but at the retrieval/memory
  layer, not the cache substrate.** 2026 memory architectures converge on
  episodic (vector, recent interactions) + semantic (graph, multi-hop) + state
  layers; the sanctioned hybrid is *vector for entry-points + graph for
  traversal*. This is a **retrieval-semantics** decision, orthogonal to *how a
  derived artifact is cached on disk*. It informs P3's boundary (below), not this
  substrate. (mem0 State-of-Agent-Memory 2026; Atlan "Agent Memory Architectures
  2026"; DigitalApplied "Vector, Graph, Episodic 2026".)

## Decision

### Decision 1 — one shared substrate: primitive + pluggable staleness + unified metrics/warming

A thin shared substrate lands in `tapps_core.cache`. **Only the mechanical,
domain-independent machinery is shared; every domain difference stays
pluggable.**

Shared (the substrate):

- **`AtomicJsonCache`** — the single read / write / atomic-replace primitive,
  replacing the five hand-rolled `_write_atomic` copies. Mechanics only (temp
  file + `os.replace`, locking, JSON (de)serialization) — it holds no staleness
  or provider opinion.
- **`StalenessStrategy` protocol** — `TTLStaleness` | `FingerprintStaleness` |
  `VersionStaleness` (`INDEX_VERSION`). Pluggable **because the models are
  irreconcilable**; the substrate composes a strategy, it does not unify them.
- **Unified `CacheStats`** — every cache reports hit/miss/stale into one surface
  (`tapps_stats` / `server_metrics_tools`), taking metrics from 1/5 to 5/5.
- **One session-start warmer** — schedules docs + code + (optionally) the rest,
  replacing the three warmers (`knowledge/warming.py`, `experts/rag_warming.py`,
  `_schedule_call_graph_rebuild`).
- **Degradation contract** — stale/absent → domain fallback (docs:
  serve-stale + refresh; code: local rebuild), preserving the
  [ADR-0027](0027-shareable-call-graph-artifact.md) "cache is never a source of
  truth" boundary.

Domain-specific (stays where it lives, never absorbed into the substrate):

- **Staleness implementation** — a clock (TTL) vs a content hash (fingerprint)
  vs an index version. Composed, never collapsed.
- **Provider / network** — Context7 fetch + circuit breaker for docs; a local
  deterministic build for the code graph and per-file tools. The substrate never
  learns to fetch.
- **Retrieval mechanism** — docs are semantic/external; the code graph is a
  deterministic structural graph. These do not converge onto one query surface.

### Decision 2 — reject "code-as-`KBCache`-provider"

The code graph is **not** modeled as a `KBCache` provider, and `KBCache` staleness
is **not** generalized to swallow fingerprinting. They share `AtomicJsonCache`
and the `CacheStats` surface and nothing else. `KBCache` keeps
`TTLStaleness` + its Context7 provider + breaker; `call_graph_cache` keeps
`FingerprintStaleness` + `VersionStaleness` + its local build. A clock and a
content hash are different staleness models on purpose; merging them produces a
cache that fits neither and re-introduces the coupling this epic exists to remove.

### Decision 3 — reject "vector-RAG over code"; the hybrid retrieval layer is out of scope, not foreclosed

Code retrieval stays a **deterministic structural graph**
([ADR-0004](0004-deterministic-tools-only-contract.md) /
[ADR-0017](0017-function-level-call-graph-python-first.md) /
[ADR-0026](0026-typescript-call-graph-via-tree-sitter.md)). No phase of this epic
introduces embeddings, vector similarity, or RAG over the repository **as a code
retrieval path**. The verified 2026 evidence above is unambiguous that structural
graph beats vector RAG for code and that grep+graph is what the leading agents
ship.

This decision draws a deliberate line between two layers that the naive framing
conflates:

- **Cache substrate (this epic's scope).** How a *derived artifact* is written,
  invalidated, measured, and warmed on disk. Vector similarity has no place here
  regardless of domain — a cache is not a retriever.
- **Retrieval semantics (out of scope).** *How* an agent finds relevant context.
  The research-sanctioned hybrid — *vector for entry-points + graph for
  traversal*, inside a layered episodic/semantic/state memory model — is a real
  2026 direction, but it is a **retrieval-layer** decision, not a cache-substrate
  one.

**Resolution of the scoping question (Q2):** the hybrid retrieval layer is
**scoped out of this epic entirely, and gated behind a fresh, telemetry-backed
ADR — but it is explicitly *not* foreclosed.** The door stays open for the P3
context-retrieval layer to front code(graph) + docs(semantic) + brain(episodic)
behind a common provider protocol, *if and only if* a future ADR shows a measured
retrieval need the deterministic graph cannot meet and weighs it against the
ADR-0004 determinism / ADR-0028 fixed-tool cost. What is foreclosed here, and only
here, is: (a) modeling the code graph as a vector-RAG source, and (b) letting any
such hybrid ride in on this cache-substrate work without its own decision. Keeping
these two layers separate is the load-bearing point — the substrate must not grow
a retrieval opinion, and the retrieval layer must not smuggle vector RAG into the
deterministic code path.

### Decision 4 — success metric: net code goes DOWN across P1–P3, or stop

The substrate is justified only if it **removes more than it adds**. The metric
is **cumulative net lines of code across the affected cache implementations must
go DOWN by the end of P3** — the design doc's over-build guard rail is binding,
not advisory.

Two honest qualifications on how that metric applies per phase:

- **P1 is the pilot and front-loads the substrate.** Extracting `AtomicJsonCache`
  + `StalenessStrategy` and migrating a single consumer (`call_graph_cache`,
  byte-equivalent) is expected to be **net-up in isolation** — it adds the shared
  primitive while removing only one `_write_atomic` copy. That is acceptable
  *only* because the primitive is the prerequisite that makes P3's deletions
  (4 more `_write_atomic` copies, 3 warmers → 1, 3 Linear gateways → 1) possible.
  P1's gate is therefore **"does it prove the primitive works byte-equivalent,
  and is the trajectory to a cumulative net-down credible?"** — not "is this one
  phase net-down."
- **Each phase is a separate go/no-go on that trajectory.** If at any phase the
  running total is not on track to end net-down — i.e. the abstraction is adding
  more than the remaining consumers can remove — that phase **stops** and the
  substrate is reconsidered. P3 (the unified context-retrieval layer over code +
  docs + brain) proceeds **only** if P1–P2 have shown the substrate earns its
  keep and the cumulative count is trending down.

The number to watch is the epic-wide total (5 `_write_atomic` copies → 1,
3 warmers → 1, 3 Linear gateways → 1, metrics unified), not any single phase's
diff.

## Consequences

### Positive

- One atomic-write primitive and one metrics surface replace five hand-rolled
  copies; metrics coverage goes 1/5 → 5/5; three warmers become one.
- The two staleness models stay explicitly separate, so neither the docs cache
  nor the code cache is contorted to fit the other.
- Determinism and the fixed-tool boundary
  ([ADR-0004](0004-deterministic-tools-only-contract.md) /
  [ADR-0028](0028-code-graph-boundary-fenced-external-comprehension-and-no-query-language.md))
  are preserved — no embeddings enter the code path.
- The net-code-down metric gives every phase an objective kill switch, guarding
  against the over-abstraction the design review flagged.

### Negative / constraints

- A shared `StalenessStrategy` protocol is a new seam every cache must adopt;
  the payoff is realized only as consumers migrate (P1 pilot →
  P3 remainder), so intermediate states carry both the substrate and not-yet-migrated
  copies.
- The back-compat re-export shims (`tapps_mcp/knowledge/cache.py`,
  `warming.py`) persist until a major, adding a few low-value indirection lines
  that the net-code-down metric must account for.

### Revisiting

- **Decisions 2 & 3** (no code-as-provider, no vector-RAG) reverse only via a
  fresh ADR backed by telemetry — a measured retrieval need the deterministic
  graph provably cannot meet, weighed against the determinism/fixture cost.
  Collapsing the two staleness models is out of scope, not a revisit.
- **Decision 4** (net-code-down) is the standing gate: a phase that cannot meet
  it does not proceed by exception; the boundary is re-opened here instead.

## Outcome (2026-07-01, P1–P3 measured)

The phases shipped (TAP-4560 / TAP-4561 / TAP-4562) and the Decision 4 metric
was measured honestly: **cumulative net code went UP ~+287 lines (excl. tests),
not down.** The design doc's deletion inventory did not survive contact with the
code — only 2 real `_write_atomic` copies existed (not 5), 2 warmers (not 3),
the "3 Linear gateways" are two deliberately distinct Agent-Gateway sentinel
checks (TAP-2009 write-gate, TAP-2010 read-gate) plus one real cache and are
**not collapsible**, and the content-hash / dependency-scan caches are
in-memory (no file migration applies).

What the +287 lines bought: metrics coverage 1/5 → 5/5 caches
(`tapps_stats.caches`), zero hand-rolled atomic-write copies, three staleness
models behind one protocol, one session-start warmer entry, byte-equivalent
migrations throughout. Real consolidation value — but the Decision 4 gate is
the gate: **further substrate phases (including the P3 unified
context-retrieval layer) are STOPPED** and require a fresh ADR with a
justification that does not lean on deletion volume, per this ADR's Revisiting
clause.

## Alternatives considered

1. **Merge all five caches into one `KBCache`-shaped cache.** Rejected
   (Decision 2) — forces a clock onto a content hash and a network fetch onto a
   local build; the result fits neither domain and re-couples what the epic
   exists to separate.
2. **Add vector/RAG retrieval over the code graph as part of the substrate.**
   Rejected (Decision 3) — 2026 evidence has structural graph beating vector RAG
   for code, and it would regress ADR-0004 determinism and the ADR-0028
   fixed-tool boundary. Out of scope for a cache-substrate epic.
3. **Leave the five caches as-is (status quo).** Rejected — the fragmentation
   (5× atomic-write, metrics on 1/5, three warmers) is the documented cost this
   epic removes; the substrate pays for itself only under the net-code-down
   metric, which status quo cannot deliver.
4. **Build the substrate but keep it code-only (skip the shared primitive).**
   Rejected — the value is precisely the *shared* atomic primitive + unified
   metrics across both domains; a code-only helper duplicates rather than
   consolidates.

## References

- [DESIGN-unified-cache-substrate-and-context-layer](../design/DESIGN-unified-cache-substrate-and-context-layer.md) — the design this ADR ratifies (fragmentation inventory, 2026 research, phase map)
- [ADR-0004](0004-deterministic-tools-only-contract.md) deterministic-tools-only — same input, same output; no LLM/embedding in the tool chain
- [ADR-0016](0016-needs-based-nlt-mcp-taxonomy.md) needs-based MCP taxonomy — zero-duplication rule
- [ADR-0017](0017-function-level-call-graph-python-first.md) function-level call graph — the deterministic review-graph store
- [ADR-0026](0026-typescript-call-graph-via-tree-sitter.md) TypeScript call graph via tree-sitter — structural, not vector
- [ADR-0027](0027-shareable-call-graph-artifact.md) shareable call-graph artifact — cache-is-never-a-source-of-truth boundary
- [ADR-0028](0028-code-graph-boundary-fenced-external-comprehension-and-no-query-language.md) code-graph boundary — fixed tools, no query language
- `docs/CALL_GRAPH.md` — consumer guide for the fixed graph tools
- [TAP-4556](https://linear.app/tappscodingagents/issue/TAP-4556) this ADR · parent epic [TAP-4555](https://linear.app/tappscodingagents/issue/TAP-4555)

### 2026 research (verified for this ADR)

1. Grewal — AI Agents Don't Need Vector Search Anymore (2026): https://buzzgrewal.medium.com/ai-agents-dont-need-vector-search-anymore-inside-the-agentic-search-stack-replacing-rag-in-2026-58efcabe4f6f
2. MindStudio — Why Cursor, Claude Code, and Devin Use grep, Not Vectors (2026): https://www.mindstudio.ai/blog/is-rag-dead-what-ai-agents-use-instead
3. SparkCo — AI Agent Memory in 2026: RAG vs Vector Stores vs Graph (2026): https://sparkco.ai/blog/ai-agent-memory-in-2026-comparing-rag-vector-stores-and-graph-based-approaches
4. sheeptechnologies RFC-001 — Remove SCIP, adopt tree-sitter file-incremental indexing: https://github.com/orgs/sheeptechnologies/discussions/4
5. AutomaDocs — Tree-sitter vs LSP for Code Analysis (2026): https://automadocs.com/blog/tree-sitter-vs-lsp-code-analysis
6. arXiv 2603.27277 — Codebase-Memory: Tree-Sitter Knowledge Graphs via MCP: https://arxiv.org/html/2603.27277v1
7. mem0 — State of AI Agent Memory 2026: https://mem0.ai/blog/state-of-ai-agent-memory-2026
8. Atlan — Agent Memory Architectures: Patterns and Trade-offs (2026): https://atlan.com/know/agent-memory-architectures/
9. DigitalApplied — AI Agent Memory 2026: Vector, Graph, Episodic: https://www.digitalapplied.com/blog/ai-agent-memory-vector-graph-episodic-2026

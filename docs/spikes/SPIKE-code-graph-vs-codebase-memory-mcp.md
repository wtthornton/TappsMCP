# SPIKE — tapps-mcp code graph vs. codebase-memory-mcp

Date: 2026-07-01
Status: Draft (decision-support; not an ADR)
Owner: (unassigned)
Related: ADR-0004 (deterministic-tools-only), ADR-0016 (graph types), ADR-0017 (Python-first call graph)

## Question

codebase-memory-mcp (DeusData) indexes any codebase into a persistent, Cypher-queryable
knowledge graph via tree-sitter, pitched at ~99% token reduction for code comprehension.
tapps-mcp already ships a persistent Python-only call graph. **Should we adopt the C binary,
extend our own graph, or neither?**

## What each actually is

| | tapps-mcp graph | codebase-memory-mcp |
|---|---|---|
| Purpose | Refactor blast-radius + test impact for the review gate | Whole-codebase comprehension, token reduction |
| Parser | Python `ast` only | tree-sitter, 158 languages |
| Type resolution | in-repo static resolve; honest `resolution_gaps` | embedded LSP-like resolution (Py/TS/PHP/C#/Go/C/C++/Java/Kotlin/Rust) |
| Store | JSON on disk (`CALL_GRAPH_CACHE_REL`), fingerprint staleness | SQLite/WAL + zst shareable artifact (8–13:1) |
| Query | fixed tools: callers / callees / bounded chains / diff→tests | openCypher subset + BFS `trace_path` |
| Edges | CALLS, IMPORTS, TESTS | + HTTP/gRPC/GraphQL routes, IaC (Docker/K8s), cross-service |
| Extras | token-budgeted chains, gap taxonomy, health metrics | dead-code, Louvain communities, 3D UI, ADR CRUD, trace ingest |
| Determinism | ✅ ADR-0004 compliant (no LLM) | ✅ pure AST, no LLM |
| Distribution | Python pkg, in-process | single C static binary, curl/npm/brew |
| Maturity | GA (call graph); `dead_code` [Preview] | benchmarked at Linux-kernel scale |

## Key finding

The two are **not** in different philosophical camps. codebase-memory-mcp is deterministic
AST, so it does **not** violate ADR-0004. The real differences are **scope** (polyglot +
route/IaC edges) and **shape** (external C binary + second SQLite store + Cypher).

## The decision that matters

Adopting the binary as a graph source would create a **second code-graph store** with its own
query language — exactly the "parallel source of truth" that integration-hygiene.md warns
against, and a new MCP surface tool-transport-policy.md would flag (it wraps a binary; but it
is genuinely no-CLI-equivalent-in-tapps and stateful, so not an automatic reject).

Three coherent options:

1. **Neither / status-quo.** Keep Python-only. Accept that non-Python repos get lint-only
   review, no symbol graph.
2. **Adopt as an *external comprehension* tool, fenced off from the graph/memory path.**
   Wire codebase-memory-mcp as an optional MCP for agents on large polyglot repos, used
   ONLY for read/comprehension (search_graph, trace_path). Do **not** route it through the
   review gate or memory. Buys token savings without forking the review graph.
3. **Extend tapps-mcp's own graph to tree-sitter for TS (then Go/Rust).** Highest long-term
   coherence — one store, one query surface, ADR-0017 tier roadmap already anticipates this
   ("polyglot scoring does not imply polyglot call graphs *in v1*"). Most engineering cost.

## Recommendation

**Option 3 for the review-critical path, Option 2 as an opt-in for comprehension** — never
Option "adopt as the graph." Rationale:

- Our graph exists to make *review* blast-radius-aware; that must stay one deterministic
  store we control (ADR-0004/0016). Forking it to a C binary + Cypher regresses that.
- TS is the single highest-value gap (`scorer_typescript.py` already parses it; adding
  tree-sitter-typescript CALLS edges reuses that investment).
- For teams with huge polyglot monorepos where comprehension token-cost is the actual pain,
  a fenced-off external MCP is a cheap experiment that doesn't touch our invariants.

See recommendations list in the accompanying Linear epic (TappsMCP Platform).

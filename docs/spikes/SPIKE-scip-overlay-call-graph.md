# SPIKE — optional SCIP overlay for the call graph

Date: 2026-07-02
Status: Decided (decision-support; not an ADR)
Owner: Claude Agent
Related: TAP-4096 (this spike), TAP-4090 (parent), ADR-0004 (deterministic-tools-only), ADR-0017 (Python-first call graph), ADR-0026 (TypeScript call graph via tree-sitter), ADR-0028 (code-graph boundary)

## Question

Both call-graph ADRs deferred compiler-grade indexing. ADR-0017 rejected a "SCIP/LSP
indexer" for v1 ("heavy external deps; violates simple deterministic AST contract");
ADR-0026 *deferred* (did not reject) a "type-aware resolver (tsc / LSP / SCIP)" for
TypeScript, leaving instance-method resolution as an honest `receiver_untyped` gap.

Consumer repos increasingly emit an `index.scip` in CI (`scip-python`, `scip-typescript`).
**Should tapps-mcp grow an optional overlay that ingests an existing `index.scip` when
present to upgrade ambiguous CALLS edges — with the deterministic AST/tree-sitter index
remaining source of truth and fallback?**

This spike measures the real upgradeable-edge count on a live repo, locates the exact
plug points, prices the operational cost, and makes a **GO / NO-GO** call. No overlay is
implemented here.

## What SCIP is (verified via `tapps_lookup_docs scip`)

SCIP (SCIP Code Intelligence Protocol, Sourcegraph) is a Protobuf index of *occurrences*.
Every reference occurrence carries a fully-qualified, resolved **symbol string**, e.g.:

```
reference scip-typescript npm test_package 1.0.0 lib/`test.js`/someOtherFunction().
```

An indexer (`scip-python`, `scip-typescript`) runs the real type checker, so a call site
that our AST/tree-sitter pass can only record as a gap ("method on an untyped receiver")
appears in SCIP as a reference occurrence pointing at a concrete definition symbol. That
is precisely the disambiguation an overlay would consume: for a gap at `file:line`, look
up the SCIP reference occurrence at the same range, read its resolved symbol, and — if it
maps to an in-repo definition symbol — draw the edge.

## Current graph, verified against the code

- Source of truth is the deterministic index built by `build_call_graph_index`
  (`packages/tapps-mcp/src/tapps_mcp/project/call_graph.py:266-320`) and re-indexed
  incrementally by `update_call_graph_index` (`call_graph.py:322-366`).
- Edges (`CallEdge`) and gaps (`ResolutionGap`) are typed in
  `call_graph_types.py:50-69`; `INDEX_VERSION = 5` (`call_graph_types.py:17`).
- Gaps are classified in-repo vs external by `split_gap_counts`
  (`call_graph_gap_classify.py:110-121`), surfaced as `in_repo_gaps` / `in_repo_gap_rate`
  in `summarize_call_graph_cache` (`call_graph_cache.py:318-334`). This classifier is the
  spike's measurement input.
- The cache fingerprint is computed in `compute_index_fingerprint`
  (`call_graph_fingerprint.py:149-159`); a stale-overlay guard would weave an `index.scip`
  content hash into this payload.

The **in-repo gap reasons** an overlay could target (`call_graph_types.py:23-33`):
`unresolved_static_call` (Python), and the TS reasons `receiver_untyped`,
`unresolved_default_export`, `reexport_unresolved`, `path_alias_unresolved`.

## Measurement — real repo (`packages/tapps-mcp/src/tapps_mcp`, full-build, force_rebuild)

Ran `build_call_graph_index` over the live `tapps_mcp` package (`top_level_package="tapps_mcp"`):

| Metric | Value |
|---|---|
| edges | 6,470 |
| symbols | 2,114 |
| total resolution gaps | 10,251 |
| external gaps (classifier) | 3,848 |
| in-repo gaps (classifier) | 6,403 |
| in-repo gap rate | **0.99** |
| in-repo reasons | `{unresolved_static_call: 6,403}` |

At face value a 0.99 in-repo gap rate looks like a huge SCIP win. **It is not**, and the
honest breakdown is the load-bearing finding of this spike. Bucketing all 10,241
`unresolved_static_call` gaps by call-expression shape:

| Bucket | Count | Share | SCIP can upgrade? |
|---|---|---|---|
| builtin-rooted (`isinstance`, `len`, `str`, `sorted`, `dict`, `max`, …) | 3,505 | 34% | **No** — language builtins/external |
| method call `x.y()` on a receiver (`raw.get`, `logger.info`, `path.read_text`, …) | 5,972 | 58% | **Only if the receiver type resolves** |
| bare name matching a known repo symbol | 16 | 0.2% | Yes, cleanly |
| other bare name (imported / local / unknown) | 748 | 7% | Mixed |

### Why the classifier over-counts

`call_graph_gap_classify.expr_root` (`call_graph_gap_classify.py:77-85`) only strips the
leading token and checks it against Python stdlib/builtin *module* names. A call like
`raw.get(...)` roots to `raw` — not a stdlib module — so it is counted **in-repo**, and
`isinstance(...)` is a builtin *function* (in `_builtin_names`) so it is correctly external,
but the vast tail of `logger.info` / `x.append` / `path.read_text` method calls on
locals is scored in-repo. The classifier is honest about *resolution debt* (these really are
unresolved edges), but it is **not** a proxy for "edges SCIP would draw."

### The genuine SCIP-addressable ceiling

Real upside is the method-call bucket (5,972, 58%) **plus** the tiny bare-repo-symbol
bucket (16) — roughly **~6,000 edges, ~58% of unresolved_static_call**, and *only the
subset of those 5,972 whose receiver resolves to an in-repo class*. The builtin third
(34%) is pure external noise SCIP cannot and should not touch; a large part of the method
bucket resolves to stdlib/third-party types (`logger` → `structlog`, `path` → `pathlib`),
which SCIP will correctly classify as external, further shrinking the in-repo win. A
realistic in-repo-edge gain is materially **below** 58% — plausibly 20–35% of
`unresolved_static_call` on this codebase, concentrated in typed-receiver intra-repo method
dispatch.

This is exactly the `receiver_untyped` case ADR-0026 named as an honest gap — so SCIP's
value proposition is real and correctly scoped, but the headline 0.99 rate overstates it by
roughly 3×.

## Where it would plug in (real anchors)

1. **Full-build ingestion** — after `_finalize_index` inside `build_call_graph_index`
   (`call_graph.py:306-311`): if a config flag is set and `index.scip` exists, run a
   post-pass that walks `index.resolution_gaps`, matches each gap's `(file, line)` to a
   SCIP reference occurrence, and promotes it to a `CallEdge` **only** when the resolved
   symbol maps to an in-repo definition symbol already in `index.symbols`. AST edges are
   never removed; the overlay is strictly additive.
2. **Incremental path** — `update_call_graph_index` (`call_graph.py:322-366`) rebuilds via
   the same `_finalize_index`. The overlay post-pass must run there too, or the incremental
   result diverges from a full build and breaks the ADR-0004 byte-equivalence invariant
   documented at `call_graph.py:337-345`. Simplest correct rule: the overlay is part of
   finalize, gated on the SCIP file's presence + fingerprint, so both paths call it
   identically. A changed `.scip` file must force a full rebuild (the overlay is global,
   not per-file).
3. **Fingerprint / staleness** — `compute_index_fingerprint`
   (`call_graph_fingerprint.py:149-159`) must fold in the `index.scip` content hash (or
   its absence) so that (a) adding/removing/refreshing the overlay invalidates the cache
   and (b) a stale `.scip` older than the current tree is detectable. Because overlay
   presence changes edge content, **`INDEX_VERSION` must bump** (5 → 6) when the overlay
   ships, so pre-overlay caches are discarded via the existing
   `invalidate_call_graph_cache_if_schema_stale` path (`call_graph_cache.py:351-386`).
4. **Config flag** — a single boolean (default **off**), e.g.
   `call_graph.scip_overlay: false`, read where excludes/top-level-package are resolved.
   No `scip` runtime dependency enters the default install; the overlay only reads a
   pre-existing `index.scip` (produced by the consumer's CI), so tapps-mcp needs at most a
   small Protobuf reader, and only when the flag is on.

## Operational cost

- **Build env.** Producing `index.scip` requires `scip-python` / `scip-typescript` +
  the consumer's toolchain (a working type-checker, `node`/`pyright`), which is heavy and
  network/toolchain-bound — exactly the dependency ADR-0017/ADR-0004 refused to put in the
  default path. The overlay design avoids this by **consuming**, never producing, the
  index: tapps-mcp reads whatever the consumer's CI already emitted. If a repo does not emit
  one, behavior is identical to today.
- **Ingestion cost.** Reading and range-indexing an `index.scip` is O(occurrences); on a
  repo the size of tapps-mcp (≈2k symbols, ≈10k gap sites) this is a sub-second Protobuf
  parse + dict build, dwarfed by the AST/tree-sitter walk that already runs. Near-zero
  marginal build cost, as the ticket hypothesized — **but only when the `.scip` already
  exists**; the expensive part (generating it) stays in consumer CI.
- **Re-index cadence.** The `.scip` is only as fresh as the consumer's last CI index run.
  On a dirty working tree the overlay is stale by construction; the fingerprint guard makes
  that detectable, and the honest fallback is to skip overlay upgrades for files newer than
  the `.scip` and keep the AST gap. This adds a real correctness caveat: an overlay edge can
  be *wrong* if the `.scip` predates a refactor. Mitigation is to trust the overlay only for
  occurrences whose file content hash matches the `.scip`'s recorded state — extra
  bookkeeping the current pipeline does not have.
- **INDEX_VERSION / cache.** One-time `INDEX_VERSION` bump (5 → 6) on ship; existing
  invalidation machinery handles the migration. No new store, no second query surface
  (respecting ADR-0028's no-parallel-graph boundary).

## Recommendation — **NO-GO for now** (revisit if a consumer actually ships `index.scip`)

Recommend **NO-GO** on building the overlay in the current cycle, holding ADR-0017's
rejection and ADR-0026's deferral. Rationale, each grounded in the measurement above:

1. **The measured win is real but far smaller than the raw signal suggests.** The 0.99
   in-repo gap rate collapses to a genuine SCIP-addressable ceiling of ~58% (method calls)
   and a realistic in-repo gain well below that (≈20–35% after typed-receiver externals
   drop out). Precision improves; it does not transform the graph.
2. **No live consumer currently emits `index.scip`.** The entire value proposition is
   "near-zero marginal cost *because CI already produced the index*." No repo in the fleet
   produces one today, so shipping the overlay now buys precision for zero real inputs while
   adding a config flag, an `INDEX_VERSION` bump, a Protobuf reader, and a staleness-caveat
   surface that must be maintained.
3. **The staleness caveat is a new correctness liability.** A `.scip` that predates a
   refactor can produce a *wrong* overlay edge — the exact ADR-0004 failure mode ("never
   fabricate an edge") the current honest-gap design avoids. Getting this right requires
   per-occurrence content-hash matching the pipeline does not do yet; getting it wrong is
   worse than an honest gap.
4. **The cheaper deterministic lever is unspent.** Much of the 58% method bucket is
   intra-repo dispatch on receivers whose type is knowable from local assignment / import
   without SCIP. ADR-0026 already scoped `receiver_untyped` as the deferred TS resolver work
   (S4 lineage, TAP-4540). Improving in-repo receiver typing in the existing tree-sitter
   pass captures a chunk of the same edges with **no external toolchain, no staleness
   window, and no new dependency** — a strictly better first step.

### Trip-wire to flip to GO

Reverse this decision when **any** consumer repo starts emitting `index.scip` in CI as a
byproduct of other work (so the input cost is genuinely sunk) **and** that repo's
`in_repo_gap_rate` on the method-call bucket is material to a real review-gate miss. At that
point the overlay is the right, cheap, additive precision layer and the follow-up story
outline below applies.

### If GO — thin follow-up story outline (deferred)

1. **S1 — SCIP reader + occurrence index.** Optional Protobuf reader for `index.scip`,
   behind `call_graph.scip_overlay` (default off). Build a `(rel_path, line) -> resolved
   symbol` map. No graph wiring yet. No dep in default install.
2. **S2 — additive overlay post-pass in `_finalize_index`.** Promote a gap to a `CallEdge`
   only when its SCIP occurrence resolves to an in-repo `SymbolRecord`; AST edges untouched;
   overlay runs identically on full + incremental paths (byte-equivalence preserved).
3. **S3 — fingerprint + staleness + `INDEX_VERSION` bump.** Fold `.scip` content hash into
   `compute_index_fingerprint`; skip overlay upgrades for files newer than the `.scip`
   (content-hash match); bump `INDEX_VERSION` 5 → 6; verify `invalidate_*_if_schema_stale`
   migrates cleanly.
4. **S4 — measurement + gate.** Extend `summarize_call_graph_cache` to report
   `scip_upgraded_edges`; prove on the first real consumer that upgraded edges are correct
   (spot-check against the type checker) and that no wrong edge is drawn.

## Acceptance mapping

- **Evaluate ingesting `index.scip` (Py + TS) with gap-classifier quantification on a real
  repo** — done: live `build_call_graph_index` on `tapps_mcp` (6,470 edges, 6,403 in-repo
  gaps) plus honest bucketing exposing the ~58% ceiling and classifier over-count. TS shares
  the same `_finalize_index` / gap-reason machinery, so the same overlay design and the same
  caveats apply; the TS win concentrates in `receiver_untyped`.
- **Prototype semantics: upgrade only unambiguous occurrences, AST fallback, incremental
  behavior defined** — specified (additive-only post-pass in `_finalize_index`, runs on both
  build + `update_call_graph_index`, wrong-edge avoided via in-repo-symbol match +
  content-hash staleness). Not implemented, per spike scope.
- **Operational cost (build env, cadence, INDEX_VERSION/fingerprint) + go/no-go** — done
  above; verdict **NO-GO** with a concrete GO trip-wire.
- **No SCIP dep in default install; feature gated behind a config flag** — honored in the
  design (`call_graph.scip_overlay: false`, consume-only, reader loaded only when on).

## References

1. `docs/adr/0017-function-level-call-graph-python-first.md` — SCIP/LSP rejected for v1 (alternatives, lines 99-104).
2. `docs/adr/0026-typescript-call-graph-via-tree-sitter.md` — type-aware resolver (tsc/LSP/SCIP) deferred (alternatives, lines 159-171).
3. `docs/adr/0028-code-graph-boundary-fenced-external-comprehension-and-no-query-language.md` — no parallel graph store / query surface.
4. `docs/adr/0004-deterministic-tools-only-contract.md` — never fabricate an edge.
5. `packages/tapps-mcp/src/tapps_mcp/project/call_graph.py` — build/update index (anchors above).
6. `packages/tapps-mcp/src/tapps_mcp/project/call_graph_cache.py` — fingerprint, save/load, schema invalidation.
7. `packages/tapps-mcp/src/tapps_mcp/project/call_graph_gap_classify.py` — in-repo vs external gap split.
8. `packages/tapps-mcp/src/tapps_mcp/project/call_graph_fingerprint.py` — `compute_index_fingerprint`.
9. SCIP occurrence/symbol model — verified via `tapps_lookup_docs scip` (Sourcegraph SCIP, 2026-07-02).

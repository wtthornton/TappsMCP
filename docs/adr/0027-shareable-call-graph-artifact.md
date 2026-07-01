# 27. Shareable call-graph artifact (CI build + load-on-session-start)

Date: 2026-07-01

## Status

Proposed (2026-07-01; TAP-4553 — design only, implementation deferred to follow-on stories)

## Context

[ADR-0017](0017-function-level-call-graph-python-first.md) shipped the
function-level call graph and [ADR-0026](0026-typescript-call-graph-via-tree-sitter.md)
extended it to TypeScript. The index lives in an on-disk cache
(`CALL_GRAPH_CACHE_REL = ".tapps-mcp/call-graph-index.json"`, `INDEX_VERSION = 5`)
keyed by a whole-tree fingerprint (`call_graph_fingerprint.compute_index_fingerprint`),
with per-file content fingerprints (`compute_per_file_fingerprints`, TAP-4533)
that let `update_call_graph_index` re-parse only the changed subset.

Today the cache is **per-checkout and cold**. Each fresh checkout — every CI
runner, every new dev clone, every agent worktree — starts with `status: missing`
and pays a full `build_call_graph_index` walk. On a large TS/Python repo that
walk is the dominant cost of the first `tapps_call_graph`, and session start
already schedules a fire-and-forget rebuild for exactly this reason
(`session_start_helpers._schedule_call_graph_rebuild`, TAP-4266). The index is
deterministic (ADR-0004) and content-addressed, so nothing about it is
checkout-specific — the same tree always produces the same index. That makes it
a natural candidate to **build once in CI and share**, so a fresh checkout can
load a warm index instead of rebuilding from scratch.

The load-bearing risk is the same one that governs every cache in this repo: a
shared artifact must never become a *second source of truth*. A stale or
tampered artifact that is trusted blindly would serve a wrong graph — the
ADR-0004 failure mode and an integration-hygiene single-source-of-truth
violation. The design below is entirely about making the artifact a pure
accelerator that is provably safe to be wrong.

## Decision

Design (implementation deferred) a **shareable call-graph artifact**: a CI job
builds the index once and publishes it; a consumer's session start loads the
published artifact, verifies it against the working tree, and either uses it
as-is, cheaply patches it, or discards it and builds locally. The artifact is a
**cache, never a source of truth**.

### Artifact format & versioning

Reuse the existing on-disk index format verbatim — the artifact **is** the JSON
`index_to_dict(index)` payload, the same bytes `save_call_graph_index` writes to
`CALL_GRAPH_CACHE_REL`. No new schema. It carries:

- `version` = `INDEX_VERSION` (currently `5`) — the load-time gate.
- `fingerprint` — the whole-tree `compute_index_fingerprint` value.
- `per_file_fingerprints` — the `{relative_posix_path: sha256[:16]}` map
  (content-based, so stable across machines/checkouts) that makes staleness
  computable on load.
- `raw_by_file` — the per-file raw material `update_call_graph_index` needs to
  re-finalize incrementally.

Because both `version` and the fingerprints already live in the payload,
staleness is fully self-describing: a loader needs the artifact plus the working
tree, nothing external.

**Compression is optional and deferred.** The index is pretty-printed JSON
(`indent=2, sort_keys=True`) and compresses well; codebase-memory-mcp reports
~8–13:1 with zstd on comparable JSON. But compression is an orthogonal transport
concern, not a format change — the *decompressed* bytes are still the same
`index_to_dict` payload. Keep v1 simple: publish the raw JSON (or let the CI
provider's artifact store gzip it transparently). If artifact size becomes a
real cost, add gzip first (stdlib, zero deps) and only reach for zstd if
measured savings justify the dependency. Do **not** bake a compression codec
into the index schema.

### CI build step (deployment-topology-agnostic)

Describe the **shape**, not a vendor:

1. A CI job checks out the repo at a known commit and runs
   `build_call_graph_index(project_root, force_rebuild=True)`.
2. It publishes the resulting `CALL_GRAPH_CACHE_REL` file as a build artifact,
   keyed by something that identifies the tree — the commit SHA is the natural
   key, and the artifact's own `fingerprint` field already encodes tree state
   (git HEAD + dirty paths + grammar version + `INDEX_VERSION`).
3. Consumers fetch the most recent artifact for their base commit (exact SHA
   ideal; a recent ancestor is fine — the load flow reconciles the diff).

This maps onto any CI cache/artifact primitive (job artifacts, a keyed cache
store, an object bucket) without AF or tapps-mcp owning a server. The job is
pure `build_call_graph_index` + "write this file somewhere fetchable" — no new
runtime surface, consistent with ADR-0003 (no publish infrastructure of our own)
and the tool-transport policy (don't build a bespoke server for something a CI
primitive already does).

### Load-on-session-start flow

On session start (extending the existing
`_schedule_call_graph_rebuild` decision point), when a published artifact is
available:

1. **Version gate.** Deserialize with `index_from_dict`. If `version !=
   INDEX_VERSION`, discard and fall back to a local build. (The existing
   summarize path already treats a version mismatch as `stale`.)
2. **Whole-tree fast path.** Recompute `compute_index_fingerprint` for the
   working tree. If it equals the artifact's `fingerprint`, the tree is
   byte-identical to what CI indexed — use the artifact as-is; write it to
   `CALL_GRAPH_CACHE_REL` so subsequent tools hit a warm cache.
3. **Per-file reconciliation.** If the whole-tree fingerprint differs, compute
   the changed set: `compute_per_file_fingerprints(working_tree)` vs the
   artifact's `per_file_fingerprints`. The differing keys are the changed files;
   keys present only in the artifact are deletions.
4. **Cheap patch.** Feed that changed/deleted set to
   `update_call_graph_index(changed, deleted_paths=deleted)`. Per its contract
   (ADR-0004 / TAP-4533) the incremental result is **byte-equivalent** to a full
   rebuild for the same tree — it re-parses only the changed files and always
   re-runs the finalize/cross-file post-pass. This is the fast path for "clone
   was slightly behind CI" and for a warm worktree with a handful of local edits.
5. **Fallback.** If the artifact is missing, unreadable/corrupt, wrong version,
   or lacks a usable `raw_by_file` map (so the incremental base is unusable),
   fall back to `build_call_graph_index(force_rebuild=True)` — exactly the
   degradation `update_call_graph_index` already performs internally.

This is fire-and-forget, mirroring the existing background rebuild: session start
never blocks on it, and a slow or absent artifact just means the first
`tapps_call_graph` triggers the local build it would have anyway.

### The derived-cache boundary (load-bearing invariant)

The artifact is a **CACHE, never a source of truth.** The working tree on disk is
the only source of truth for the graph. Every load path above is designed so that
a stale, absent, corrupt, or even maliciously altered artifact degrades to a
**correct local build** — never to a wrong graph:

- **Staleness is always recomputed locally**, never trusted from the artifact.
  The version gate and both fingerprint checks run against the live tree, so an
  artifact that claims freshness it doesn't have is caught before any of its
  edges are served.
- **A changed subset is re-derived, not patched-in-place-and-hoped.** The
  incremental path's byte-equivalence guarantee (ADR-0004) means "load artifact +
  patch" and "full local build" converge on the same index; the artifact only
  saves parsing work for files that genuinely didn't change.
- **Corruption fails closed.** `load_call_graph_index` already returns `None` on
  unreadable/malformed JSON; a `None` artifact takes the full-build fallback.

This keeps the single-source-of-truth discipline (integration-hygiene): we do not
mirror server/CI-computed state into a client and re-derive decisions from it —
we treat the artifact as a warm start and re-verify against ground truth. The
artifact is never committed to git (a call-graph non-goal from ADR-0017 that
still holds — this ADR shares it *out-of-band via CI artifacts*, not in the tree).

## Consequences

### Positive

- Cold-start cost drops from a full walk to (best case) a fingerprint compare, or
  (common case) an incremental re-parse of the handful of files that drifted from
  the CI base — a large win for fresh CI runners, new clones, and agent worktrees.
- Zero new schema and zero new runtime surface: the artifact is the existing
  index bytes; the CI step is `build_call_graph_index` + a file publish; the
  loader composes primitives (`index_from_dict`, `compute_index_fingerprint`,
  `compute_per_file_fingerprints`, `update_call_graph_index`) that already exist
  and are already tested.
- The safety invariant is structural, not procedural: correctness never depends
  on the artifact being fresh, present, or honest.

### Negative / constraints

- The artifact only accelerates when the working tree is close to the CI base.
  A tree that has diverged heavily gets a large changed set and the incremental
  patch approaches a full rebuild — no worse than today, but no better either.
- Fingerprint recomputation on load is not free (it walks the tree's stat/hash);
  on a tiny repo the artifact fetch + verify can cost more than just building.
  The loader should keep the existing "build is cheap, skip the artifact" escape
  for small trees rather than always fetching.
- Artifact distribution is the operator's/CI's concern. tapps-mcp ships the
  build and load *logic*; it does not host a store or assume a specific provider.

### Follow-on implementation stories (NOT built here)

1. **CI build+publish job** — a topology-agnostic CI step that runs
   `build_call_graph_index(force_rebuild=True)` and publishes
   `CALL_GRAPH_CACHE_REL` keyed by commit, documented as a recipe (not wired to
   one vendor).
2. **Session-start artifact loader** — extend
   `session_start_helpers` (the `_schedule_call_graph_rebuild` decision point) to
   fetch a configured artifact, run the version/fingerprint gates, and dispatch
   to `update_call_graph_index` or the full-build fallback.
3. **Changed-set reconciliation helper** — a small pure function that diffs
   working-tree `compute_per_file_fingerprints` against an artifact's
   `per_file_fingerprints` and returns `(changed, deleted)` for
   `update_call_graph_index`.
4. **Optional compression** — gzip the published artifact (stdlib) behind a flag;
   evaluate zstd only if measured size justifies the dependency. Format-neutral:
   decompressed bytes remain the `index_to_dict` payload.

## Alternatives considered

1. **Commit the index to git.** Rejected — an ADR-0017 non-goal
   ("Committing `call-graph-index.json` to git"). It bloats history, churns on
   every edit, and makes the cache look like a source of truth. Out-of-band CI
   artifacts share the same bytes without any of that.
2. **Trust the artifact without re-verification** (load it as the graph). Rejected
   — this is exactly the derived-cache boundary violation: a stale or tampered
   artifact would serve a wrong graph. The verify-then-patch flow is the whole
   point.
3. **A new compact/binary artifact schema.** Deferred — the JSON payload already
   deserializes via `index_from_dict` and compresses well; a new schema is a
   maintenance surface with no proven need. Add transport compression before a
   format change.
4. **An AF/tapps-mcp-owned artifact server or cache service.** Rejected — CI
   artifact/cache primitives already do "build once, fetch by key"; building a
   server duplicates a solved primitive and adds a runtime surface (contra
   ADR-0003 and the tool-transport policy).

## References

- [ADR-0004](0004-deterministic-tools-only-contract.md) deterministic tools — the graph is content-addressed and reproducible
- [ADR-0017](0017-function-level-call-graph-python-first.md) function-level call graph (index, cache, non-goals)
- [ADR-0026](0026-typescript-call-graph-via-tree-sitter.md) TypeScript call graph (fingerprint folds grammar version + suffixes)
- `packages/tapps-mcp/src/tapps_mcp/project/call_graph_cache.py` — `index_to_dict` / `index_from_dict`, `load`/`save`, `INDEX_VERSION` gate
- `packages/tapps-mcp/src/tapps_mcp/project/call_graph_fingerprint.py` — whole-tree + `compute_per_file_fingerprints`
- `packages/tapps-mcp/src/tapps_mcp/project/call_graph.py` — `build_call_graph_index`, `update_call_graph_index` (incremental entry point)
- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py` — `_schedule_call_graph_rebuild` (TAP-4266) load-flow extension point
- `docs/CALL_GRAPH.md` consumer guide
- [TAP-4553](https://linear.app/tappscodingagents/issue/TAP-4553) this ADR

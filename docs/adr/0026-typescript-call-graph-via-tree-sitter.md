# 26. TypeScript call graph via tree-sitter (language dispatch + honesty boundary)

Date: 2026-07-01

## Status

Accepted (2026-07-01; TAP-4541 / S1–S4: TAP-4537, TAP-4538, TAP-4539, TAP-4540)

## Context

[ADR-0017](0017-function-level-call-graph-python-first.md) shipped a
**Python-first**, **AST-only**, **deterministic** function-level call graph
(`CALLS` edges, `resolution_gaps`, no LLM in the tool chain per
[ADR-0004](0004-deterministic-tools-only-contract.md)). It explicitly scoped v1
to Python: "Polyglot **scoring** (TS/Go/Rust) does not imply polyglot call
graphs in v1 — Python only."

Real consumers include TypeScript/React frontends. On those repos the call graph
is blind: `tapps_call_graph`, symbol blast radius, and `diff_impact` return
nothing for `.ts`/`.tsx` symbols, so agents fall back to grep for TS refactors.
The `tree-sitter` + `tree-sitter-typescript` grammar is **already vendored** for
polyglot scoring (`scorer_typescript`), so the parser cost is sunk — what was
missing was the analysis layer that turns a TS parse tree into symbols and edges.

The load-bearing risk is honesty. TypeScript resolution is fundamentally harder
than Python's: instance-method dispatch needs the receiver's type (which a
non-type-checking static pass cannot know), default exports and re-export barrels
need another module's export surface, and `@/`-style path aliases need
`tsconfig`. A naive analyzer that guesses fabricates wrong edges — the exact
failure mode ADR-0004 forbids.

## Decision

Extend the call graph to TypeScript via **tree-sitter**, behind a
**suffix-keyed language-dispatch layer**. The Python `ast` path is unchanged;
TS is an additional analyzer, not a rewrite. Delivered in four stories:

- **S1 (TAP-4537)** language-dispatch scaffold + `.ts`/`.tsx` walk.
- **S2 (TAP-4538)** per-file tree-sitter symbol + in-module edge extraction.
- **S3 (TAP-4539)** per-file cross-module resolution (imports) + TS gap reasons.
- **S4 (TAP-4540)** cross-file post-pass (default exports, path aliases, re-exports).

### Language dispatch

`call_graph._analyzer_for(suffix)` routes `.py` → the Python `analyze_file` and
`.ts`/`.tsx` → the tree-sitter `analyze_file_ts`. `build_call_graph_index` walks
`_PY_SUFFIXES + _TS_SUFFIXES` in one pass; TS paths become slash-delimited module
names via `_ts_file_to_module` (strip a leading `src/`, drop the suffix), Python
paths keep `import_graph._file_to_module`. A future Go/Rust analyzer slots into
the same `_analyzer_for` table without touching the walk or the index schema.

Graceful degradation: if `tree_sitter` / `tree_sitter_typescript` is not
installed, `analyze_file_ts` returns an empty result (no crash); a genuine syntax
error yields a `ParseFailure`, not an exception.

### Index version & cache invalidation

- `call_graph_types.INDEX_VERSION` is bumped to **3** (S1). `SymbolRecord` and
  `ResolutionGap` gain a `language` field defaulting to `"python"`, so a cached
  **v2** index (which lacks the field) still deserializes, and a version mismatch
  triggers a rebuild + info-log.
- The fingerprint (`call_graph_fingerprint`) folds `.ts`/`.tsx` into its
  suffix set (`_FINGERPRINT_SUFFIXES`) — both in the git-dirty-path component and
  the mtime component — so a new or edited TS file invalidates the cache.
- The fingerprint also folds the installed **`tree-sitter-typescript` grammar
  version** (`ts:<version>`, or `ts:absent` when the optional grammar is not
  installed). A grammar upgrade changes the fingerprint and forces a rebuild, so
  parse-behavior changes never serve a stale index.

### Resolution model and the honesty boundary

This is the load-bearing part. **v1 resolves** (draws a `CALLS` edge only when
the callee is a real qualified symbol in the global table):

- **In-module** calls to top-level functions, arrow-function `const`s, and class
  methods; **intra-class** `this.method()` (S2).
- **Named / aliased imports** from an in-repo relative module (`import {shout as
  loud} from "./util"` → de-aliased) and **namespace imports** (`import * as U
  from "./util"` → `U.greet()`) (S3).
- **Default exports**, **`@/`/`~/` path aliases** (via `tsconfig.json`
  `compilerOptions.paths` + `baseUrl`), and **re-export chains** (`export {a as
  b} from "./y"`, `export * from "./y"`) — resolved by the S4 **cross-file
  post-pass** (`resolve_ts_cross_file`), which follows barrels to the origin
  symbol with a depth cap (`_MAX_REEXPORT_DEPTH = 16`) and cycle guard.

Everything else stays an **honest `ResolutionGap`**, never a guessed edge:

- **Receiver-untyped instance methods** (`obj.format()`, chained `a.b().c()`) —
  the receiver's type is unknown without a type checker (`receiver_untyped`).
- **Non-`@/`/`~/` alias sigils** — scoped npm packages (`@angular/core`) start
  with `@` but are external, so `_is_path_alias` deliberately excludes them; they
  fall through to `import_unresolved`.
- **Unresolved defaults / broken chains / external packages** — a default export
  with no nameable origin, a re-export chain that lands nowhere, or a bare
  `fs`/`lodash` import.

The per-file analyzer cannot see other modules' export tables, so S3 records the
deferrable cases as `DeferredCall` records (carrying the gap it *would* emit plus
structured hints: import kind, imported name, target module, raw specifier) and
exposes each module's `ModuleExports`. The S4 post-pass promotes a `DeferredCall`
to an edge **only** when it lands on a real symbol; otherwise the recorded gap is
emitted verbatim.

**Phantom-edge demotion (ADR-0004 enforcement).** S3 can eagerly resolve a named
import to `<module>.<name>` before the post-pass knows whether `<module>` really
defines or re-exports `<name>`. When the post-pass finds such an edge whose callee
module neither defines the symbol nor resolvably re-exports it (a broken re-export
chain), `resolve_ts_cross_file` returns it in `dangling_callees` and
`build_call_graph_index` **demotes the edge to a `reexport_unresolved` gap** — the
fabricated target is removed rather than kept. Barrel edges that *do* resolve are
rewritten to point at the origin symbol (`edge_rewrites`), not the re-export.

`DeferredCall`, `ModuleExports`, and `_DeferredMeta` are **build-time-only** — they
carry cross-file resolution state and are not persisted in the on-disk index.

### Gap taxonomy

Four TS-specific `ResolutionGapReason` values are added: `receiver_untyped`,
`unresolved_default_export`, `reexport_unresolved`, `path_alias_unresolved`.

`ResolutionGap.language` (default `"python"`) makes the classifier
(`call_graph_gap_classify.is_external_gap`) **language-aware**. A TS gap is
classified purely on its `reason` (`_TS_EXTERNAL_REASONS`), **not** run through
the Python stdlib/builtin name heuristics — those would misclassify both
directions (`fs`/`lodash` are not Python stdlib; `os`/`time` are not TS
externals). External TS reasons (`import_unresolved`, `dynamic_dispatch`,
`callback_opaque`, `framework_hof`) do **not** inflate `in_repo_gap_rate`; the
deferred in-repo classes (`receiver_untyped`, default/re-export/path-alias) count
as in-repo resolution debt so the blast-radius trust signal stays honest.

## Consequences

### Positive

- TS/React refactors get deterministic caller/callee/blast-radius answers instead
  of grep, sharing the same MCP tools, index, cache, and `diff_impact` path.
- The dispatch table is the extension point: **Go/Rust can slot in later** behind
  `_analyzer_for` without changing the walk or index schema.
- The honesty boundary is preserved end-to-end — no fabricated edges, phantom
  edges are demoted, and gaps carry specific, language-tagged reasons.

### Negative / constraints

- **Real React frontends will show a higher (but honest) gap rate** than Python
  repos until deeper resolution lands — `receiver_untyped` instance-method
  dispatch is the dominant unresolved class and needs type information v1 does
  not compute.
- **Anonymous inline-callback calls are dropped**, not mis-attributed: `_walk_calls`
  does not descend into a nested arrow/function/method body it did not register as
  a symbol, rather than crediting those calls to the enclosing caller.
- **`console`-style global members** (`console.log`, and any `obj.method()` on an
  untyped receiver) are counted `receiver_untyped` — treated as in-repo debt, not
  silently dropped.
- `tsconfig` support is deliberately small: the common `{"@/*": ["src/*"]}`
  wildcard plus exact aliases; `extends`, JSON5 comments, and project references
  degrade to "no aliases" (empty map), keeping the honest gap rather than
  guessing.

## Alternatives considered

1. **A separate TS call-graph tool / server** — Rejected: TS belongs behind the
   same `_analyzer_for` dispatch and the same index/cache, exactly as Python
   sits alongside the module import graph in ADR-0017.
2. **A type-aware resolver (tsc / LSP / SCIP)** — Deferred, not adopted for v1:
   heavy external deps and a network/toolchain dependency that violate the
   simple, deterministic, offline AST contract (ADR-0004). Instance-method
   resolution stays an honest gap until this is revisited.
3. **Guess instance-method targets by method name** — Rejected: name-only
   matching fabricates edges across unrelated classes — the ADR-0004 failure
   mode. Better an honest `receiver_untyped` gap than a wrong edge.

## References

- [ADR-0004](0004-deterministic-tools-only-contract.md) deterministic tools — never fabricate an edge
- [ADR-0017](0017-function-level-call-graph-python-first.md) function-level call graph (Python-first)
- [TAP-4537](https://linear.app/tappscodingagents/issue/TAP-4537) S1 language-dispatch scaffold
- [TAP-4538](https://linear.app/tappscodingagents/issue/TAP-4538) S2 per-file tree-sitter analysis
- [TAP-4539](https://linear.app/tappscodingagents/issue/TAP-4539) S3 cross-module resolution + TS gap reasons
- [TAP-4540](https://linear.app/tappscodingagents/issue/TAP-4540) S4 cross-file post-pass
- `docs/CALL_GRAPH.md` consumer guide

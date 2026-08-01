# 32. Usage-gap doc coverage: local modules, any-topic cache, resolution confidence

Date: 2026-08-01

## Status

accepted

## Context

AgentForge-shaped kit scripts and similar non-package layouts were thrashing
Context7: same-directory siblings (`af_eval_cli`) were classified as external
libraries, and `is_library_cached` / `KBCache.has` defaulted to `topic=overview`,
so valid topic-specific lookups left `libraries_without_lookup` sticky.
TAP-5273 correctly strengthened `lookup_docs_underused` for real misses, but
historical `lookup_docs_called=false` loops plus false-positive locals / overview
gating re-fired with copy that claimed lookups never happened.

## Decision

1. **Local/sibling exclusion (TAP-5420)** — `extract_external_imports` skips
   modules that resolve to a `.py` / package under the edited file's ancestor
   chain up to `project_root` (kit scripts without `__init__.py` included).
2. **Any-topic (or lookup event) coverage (TAP-5421 / TAP-5419)** —
   `KBCache.has_any_topic` + `is_library_cached` treat any cached topic as
   warmed; `usage._lookup_gap_libraries` also drops libraries present in
   recent `.lookup-docs-events.jsonl`. `KBCache.has(library)` keeps the
   overview default for get/put semantics.
3. **Unstick + copy (TAP-5422)** — after retrospective lookups clear the
   uncached list, `lookup_docs_underused` clears without a new Python edit.
   Recommendations distinguish `session-never` / `historical-miss` /
   `still-uncached` and never claim "never called" when `used_lookup` is true.
4. **Resolution confidence (TAP-5423)** — `LookupResult` exposes
   `matched_library_id`, `resolution_confidence`, and `likely_local_module`.
   Strong basename divergence skips trustworthy cache warm and lookup-event
   telemetry.

**Docs gaps are cache-coverage checks** (any topic under the library cache dir,
or a recent lookup event), not purely call-count checks. Default topic for
explicit `has()` / `get()` remains `overview`.

## Consequences

**Positive**

- Kit/script sibling imports no longer nag Context7.
- Topic-specific research clears usage gaps without an overview warm.
- Agents see when a Context7 hit is a weak / likely-local mismatch.

**Tradeoffs**

- Ancestor walk for local modules is best-effort filesystem resolution; a
  top-level local directory that shadows a real PyPI name will be treated as
  local (intentional for in-repo ground truth).

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| Require overview for coverage | Forces thrash just to clear telemetry |
| Suppress underused whenever any lookup ran | Hides true still-uncached externals |
| Package allowlist UI | Out of scope; filesystem resolution is enough for kit layouts |

## Refs

TAP-5419, TAP-5420, TAP-5421, TAP-5422, TAP-5423, TAP-5273, TAP-618, ADR-0021

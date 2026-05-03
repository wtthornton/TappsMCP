# Auto-warm tapps_lookup_docs cache from TECH_STACK.md on session_start

## What

The file cache in tapps-core/knowledge/cache.py works (24h TTL, per-library overrides) but cold sessions hit Context7 on every first lookup.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py:1-600`
- `packages/tapps-core/src/tapps_core/knowledge/warming.py:1-200`
- `packages/tapps-core/src/tapps_core/knowledge/cache.py:1-300`

## Acceptance

- [ ] session_start warms cache for top 10 libraries from TECH_STACK.md when warm_cache_from_tech_stack=true (default)
- [ ] Response surfaces warmed_libraries list and per-library cache status
- [ ] tapps_doctor reports cache hit ratio for tapps_lookup_docs over last 7 days
- [ ] Cold-session lookup of a TECH_STACK library returns in under 100ms p95
- [ ] session_start(quick=True) and warm_cache_from_tech_stack=false skip warming

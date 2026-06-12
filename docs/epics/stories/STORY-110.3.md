# session_end_helpers.py: retrievable session_search on handoff close

## What

Improve `tapps_session_end` session_search so HTTP-only consumers get useful indexed session chunks when the session_start sentinel is stale; document empty `processed_events` / `session_search.results`.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/session_end_helpers.py`
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (`tapps_session_end` payload)
- `packages/tapps-mcp/tests/unit/test_session_lifecycle.py:262-350`
- `AGENTS.md` (session_end behavior note)

## Acceptance

- [ ] session_search query uses handoff P0 / project id / summary tags when sentinel missing or stale
- [ ] Response documents why `flywheel.processed_events: 0` when sentinel absent
- [ ] No regression when fresh session_start sentinel exists
- [ ] Unit tests mock `memory_search_sessions` with semantic query expectations

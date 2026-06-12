# handoff_schema.py: brain mirror metadata and structured recall

## What

Attach handoff section metadata to brain mirror entries and improve CLI JSON clarity (`memory_group: null` hint); enable `memory get` consumers to navigate Done/Open/P0 without re-parsing raw markdown.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/handoff_schema.py`
- `packages/tapps-mcp/src/tapps_mcp/cli.py` (`memory save` / `memory get` output)
- `packages/tapps-core/src/tapps_core/brain_bridge.py` (save metadata passthrough)
- `docs/MEMORY_REFERENCE.md`

## Acceptance

- [ ] Brain save for `session-handoff` includes structured metadata: sections, `linear_p0`, `updated_at`, `git_sha`
- [ ] `memory get --key session-handoff` JSON includes `handoff_sections` or equivalent without embedding vector in default output
- [ ] `memory save` JSON notes when `memory_group` is null and how to set it (if supported)
- [ ] Unit tests for metadata round-trip on save/get

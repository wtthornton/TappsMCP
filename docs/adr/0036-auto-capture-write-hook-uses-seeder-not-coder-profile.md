# 36. Auto-capture write hook uses "seeder", not "coder", profile

Date: 2026-08-27

## Status

Accepted (corrects one call-site assignment from [ADR-0012](0012-brain-capability-profile-per-consumer-role.md); the rest of ADR-0012's role table is unchanged).

## Context

[ADR-0012](0012-brain-capability-profile-per-consumer-role.md) assigned `BRAIN_PROFILE_HOOKS`
("coder") to both memory hooks — `memory/auto_capture` and `memory/compact_index` — reasoning
that "they only call the coder subset; coder is correct for them." That reasoning holds for
`compact_index` (`bridge.index_session()` → `memory_index_session`, a tool the "coder" profile
exposes) but not for `auto_capture`: it writes via `bridge.save()`, which calls `memory_save`
directly, and ADR-0012's own tool table lists `memory_save` as one of the tools **excluded**
from "coder" ("but not the low-level `memory_save`/`memory_get`/`memory_search`/`memory_list`/
`memory_supersede` ...").

This was invisible for the life of PR #311 (TAP-6733): that PR fixed transcript reading so
`run_auto_capture` correctly extracted 1-2 durable facts per Stop event, but every subsequent
`bridge.save()` call was rejected with `ToolNotInProfileError` ("tapps-brain tool 'memory_save'
is hidden by profile 'coder'"), and the CLI's stdout (`{"saved":0,"facts":1,"reason":
"save_failed"}`) and stderr WARNING never surfaced the per-fact `errors` that named the real
cause — so the auto-capture hook silently saved 0 rows in every deployed consumer on a
brain >= v3.20.0 (the version that started enforcing profile gates on every `tools/call`).
Verified independently: a real Stop payload run through the merged fix produced `saved=0` with
`private_memories` unchanged (delta 0) for `project_id='nlt-orchestrator'`.

## Decision

1. Add `BRAIN_PROFILE_WRITE_HOOK = "seeder"` next to the other named profile constants in
   `tapps_core.brain_bridge` (ADR-0012's pattern). "seeder" — described in ADR-0012's own
   profile table as the 6-tool "bulk ingestion scripts (write-only)" profile — is the
   least-privilege profile that exposes `memory_save`/`memory_supersede`.
2. `memory/auto_capture.py`'s `create_brain_bridge(settings, default_profile=...)` call uses
   `BRAIN_PROFILE_WRITE_HOOK` instead of the literal `"coder"` (previously `BRAIN_PROFILE_HOOKS`
   would have been the "obvious" fix, but it is wrong for this call site specifically).
   `memory/compact_index.py` keeps `"coder"` — its `index_session()` call is genuinely
   in-profile, so ADR-0012's original reasoning still holds there.
3. As with every profile constant, a consumer can still override via `memory.brain_profile` in
   `.tapps-mcp.yaml` or `TAPPS_BRAIN_PROFILE`; that value wins over `default_profile` (unchanged
   resolution order from ADR-0012).
4. Surface the failure class this masked: `tapps-mcp auto-capture`'s JSON stdout line now
   includes the per-fact `errors` array (from `run_auto_capture`'s `result["errors"]`, already
   populated but previously dropped at the CLI boundary) whenever `saved == 0`, and the stderr
   WARNING names them too — not just the bare `reason` string.

## Consequences

**Positive:**

- `tapps-mcp auto-capture` writes durable facts to the deployed brain again on any brain
  version, instead of silently discarding every extracted fact. Verified against a live
  `tapps-brain-db`: `private_memories` for a real project went from 65 to 69 rows across two
  real Stop-payload proof runs (facts=1 and facts=3), with no code path changed except the
  profile.
- A future regression back to a profile that hides `memory_save` fails loudly: a unit test
  asserts `create_brain_bridge`'s `default_profile` kwarg is `BRAIN_PROFILE_WRITE_HOOK`, not
  `BRAIN_PROFILE_HOOKS`.
- An operator reading `auto-capture.log` can now see *why* nothing was saved (e.g. a
  profile-gate rejection, a transient bridge error) instead of only the generic
  `reason=save_failed`.

**Negative:**

- The auto-capture write path is on a profile (`seeder`) distinct from the read/reinforce hooks
  (`coder`) that also run from the Stop/SessionEnd hook family — two narrow profiles instead of
  one, for two hook modules that both call themselves "hooks." This is the accurate shape (one
  is a write, one is not) but it's one more profile name to track.

**Neutral:**

- `BRAIN_PROFILES_NARROW_OK` already contained the bare string `"seeder"` (added speculatively,
  unused by any call site); it is now referenced via `BRAIN_PROFILE_WRITE_HOOK` with the same
  value, and finally has a real caller.

## Alternatives considered

**Widen "coder" to include `memory_save`.** Rejected: that is a tapps-brain (producer)
change to `mcp_profiles.yaml`, out of scope for a tapps-mcp consumer-side fix, and would
silently grant `memory_save` to every other "coder" consumer (least-privilege violation) to fix
one call site.

**Route `auto_capture`'s save through the `brain_*` facade so "coder" suffices**, mirroring
ADR-0012's rejected alternative for the server bridge. Rejected for the same reason: `coder`'s
facade has no equivalent for a single-key `memory_save`; the facade is a strict subset.

## Refs

- [ADR-0012](0012-brain-capability-profile-per-consumer-role.md) — original profile-per-role
  decision; role table's own exclusion of `memory_save` from "coder" is what this ADR acts on.
- `packages/tapps-mcp/src/tapps_mcp/memory/auto_capture.py` — the corrected call site.
- `packages/tapps-mcp/src/tapps_mcp/cli_ops_audit.py:auto_capture` — the CLI error-surfacing fix.
- Linear: TAP-6733.

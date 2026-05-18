# 11. Pin tapps-brain by release tag instead of commit SHA

Date: 2026-05-18

## Status

accepted (supersedes [ADR-0010](0010-pin-tapps-brain-version-floor-at-3180.md); historical chain: [ADR-0002](0002-pin-tapps-brain-version-floor-at-372.md) → [ADR-0009](0009-pin-tapps-brain-version-floor-at-3170.md) → ADR-0010 → ADR-0011)

## Context

ADR-0010 fixed the tapps-brain version floor at 3.18.0 and pinned the workspace `[tool.uv.sources]` entry to commit SHA `afb9fbe05f8befe0544399f9d824e891059a566f`. In its "Alternatives considered" section, ADR-0010 explicitly rejected pinning by tag:

> Switch the Git rev to a tag (`tag = "v3.18.0"`) instead of a SHA. **Rejected for now**: tag-based resolution is racier under uv's lockfile semantics than an immutable commit SHA. The comment in `[tool.uv.sources]` already records the path to swap to a tag once the upstream release tags are durable; this ADR keeps the SHA pin for resolver determinism.

The unblock criterion ("once the upstream release tags are durable") was deliberately left open. Two things have changed since:

1. **`v3.18.0` tag is published and stable.** `git -C ../tapps-brain rev-list -n 1 v3.18.0` resolves to `afb9fbe05f...` — the exact SHA ADR-0010 pinned. The tapps-brain release process now publishes immutable tags on every minor (`v3.18.0`, `v3.19.0`, `v3.20.0`, `v3.20.1` all exist in the upstream repo) and the team controls both repos, so a force-moved tag would be an internal regression — not an external supply-chain attack the tag pin needs to defend against.

2. **`uv.lock` re-asserts the determinism guarantee.** Whether the spec is `rev = "<sha>"` or `tag = "v3.18.0"`, the resolved commit SHA is recorded in `uv.lock` and committed to the repo. Subsequent `uv sync` calls without `--upgrade` resolve to the locked SHA regardless of how the spec is written. The race ADR-0010 worried about (tag moves between resolves) only matters under `uv sync --upgrade`, which is an explicit operator action, not the default path.

The SHA pin's downside has remained: `rev = "afb9fbe05f8befe0544399f9d824e891059a566f"` is opaque to a reviewer. ADR-0010 calls out the v3.18.0 floor in prose, but `pyproject.toml:11` only shows the SHA — a reader has to cross-reference against the tapps-brain repo to confirm which version is actually pinned.

## Decision

Swap the workspace-root `[tool.uv.sources]` pin from commit SHA to release tag:

```toml
# before
tapps-brain = { git = "https://github.com/wtthornton/tapps-brain.git", rev = "afb9fbe05f8befe0544399f9d824e891059a566f" }

# after
tapps-brain = { git = "https://github.com/wtthornton/tapps-brain.git", tag = "v3.18.0" }
```

The version floor itself is unchanged — `packages/tapps-core/pyproject.toml` still declares `tapps-brain>=3.18.0,<4`, and `_BRAIN_VERSION_FLOOR` in `packages/tapps-core/src/tapps_core/brain_bridge.py` stays at `"3.18.0"`. Only the source-spec form changes; the resolved artifact is byte-identical.

`uv.lock` is regenerated and committed in the same change so the resolved SHA is captured for reproducible installs.

## Consequences

**Positive:**

- `pyproject.toml:11` is now self-describing: the line announces v3.18.0 without a cross-repo `git log` lookup.
- ADR-0010's prose and the actual pin agree at-a-glance — they both say "3.18.0".
- Future floor bumps require less churn: update one tag string, regen the lock, update the ADR. No new SHA hex to copy around.

**Negative:**

- A force-moved upstream tag would change what a fresh `uv sync --upgrade` resolves to. Mitigation: tapps-brain is internally controlled; the team's release policy treats tags as immutable. `uv.lock` continues to pin the resolved SHA regardless, so day-to-day sync calls without `--upgrade` are unaffected.
- This is the second supersede in three ADRs for the brain pin (ADR-0009 → ADR-0010 → ADR-0011). The history is documented; future readers should consult the chain.

**Neutral:**

- Runtime behavior is unchanged. `BrainBridge`, `_BRAIN_VERSION_FLOOR`, and the version-probe in `tapps_session_start` all keep operating against the same v3.18.0 artifact.
- No callsite migration required.

## Alternatives considered

**Keep the SHA pin and document the version in a comment only.** Rejected: the current pyproject already has a comment ("v3.18.0 commit SHA"), and the audit gap persisted anyway because reviewers tend to skip comment blocks. Putting the version in the spec itself is the durable fix.

**Drop the `[tool.uv.sources]` entry entirely and rely on `packages/tapps-core/pyproject.toml`'s version pin.** Rejected: that route resolves tapps-brain from PyPI, but tapps-brain is not published to PyPI (per [ADR-0003](0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md)). The Git source must remain.

**Pin by tag at a later release (`v3.20.1`).** Out of scope. The version floor is 3.18.0 per ADR-0010 and the bridge has no callsite that requires 3.20.x. Future floor bumps go through their own ADR.

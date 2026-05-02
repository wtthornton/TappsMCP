# 6. tapps_validate_changed requires explicit file_paths

Date: 2026-05-02

## Status

accepted

## Context

`tapps_validate_changed` runs the full quality pipeline (scoring, gate, security scan) against a set of files. Two natural call shapes were available: (a) auto-detect mode — scan every git-changed file under the project root and validate all of them, or (b) explicit-list mode — caller passes `file_paths="a.py,b.py"` and only those run. Auto-detect mode is convenient but pathological in practice: large refactors and rebases routinely touch hundreds of files, and the agent ends up running the slow path (mypy strict, bandit, radon) over files that aren't relevant to the current task.</parameter>
<parameter name="decision">**`tapps_validate_changed` should always be called with an explicit `file_paths` argument.** This is not a runtime constraint (auto-detect still works for `tapps doctor`-style use) but a documented call convention enforced by the project's `CLAUDE.md`. Default mode is `quick=True`; the slower `quick=False` mode is reserved for pre-release / security-audit calls. Agents that fail to pass `file_paths` are flagged via the checklist tool.</decision>
<parameter name="consequences">**Positive:** Validation completes in seconds rather than minutes; agents loop more aggressively on real validation feedback. **Positive:** The "validate before declaring complete" step stays cheap enough that agents actually do it. **Negative:** Callers must track which files they touched. Acceptable — the agent edited the files; tracking them is its native capability. **Neutral:** Auto-detect remains available as an escape hatch but is documented as not the recommended path.</consequences>
</invoke>

## Decision

Describe the decision that was made...

## Consequences

Describe the consequences of this decision...

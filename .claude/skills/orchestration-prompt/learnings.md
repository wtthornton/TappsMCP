# orchestration-prompt learnings (project-scoped)

Append one-line lessons as you generate prompts. Keep them project-scoped; never
bleed across repos. This file is created once by the scaffolder and never
overwritten on upgrade — it's yours.

<!-- Example: -->
<!-- - Validation goals need a verified-correct-negative Done-when, or the loop chases an unreachable target. (2026-06-18) -->

- Multi-epic single-repo drives: sequential `/goal` (not Workflow coding fan-out); override per-edit `tapps_quick_check` to story/epic gates when the epic itself targets gate latency. (2026-07-30)
- Metrics follow-on epics: order root-cause false-positive flags (diff_impact 100% degraded) before surfacing completeness UX, or agents paper over bad semantics. (2026-07-30)
- Reachability test on *reduction* targets: split the metric into reducible vs irreducible before writing a number into Done-when. A "36K→8K tool schema" target was unreachable — 7.8K of the 36K was param schedule, not prose; the honest floor was 16K. Chasing the bad number would have burned the budget deleting parameters. (2026-08-07)
- Reordering sub-goals after the contract table is written silently breaks the fulfills-coverage mapping. Re-run the coverage check *after* any resequencing, not just at first draft. (2026-08-07)
- When the epic edits the harness it runs under (hook/skill templates), add an explicit "do not run `tapps_upgrade` mid-loop" guardrail plus the deploy-lag note — measure from source via a committed script, deploy only at the end. (2026-08-07)

- [high] **A worktree dispatch needs its `.mcp.json` headers rewritten, not just copied.** `.mcp.json` is gitignored, so a `git worktree` has none — and copying it verbatim is *worse than missing*: all six `X-Tapps-Project-Root` headers still name the original checkout, so every `tapps_*` gate call scores the wrong tree and returns a meaningless green. Copy it, rewrite the six headers to the worktree path, `uv sync` (a fresh worktree has no `.venv`), then prove it by asserting `tapps_session_start().project_root == <worktree>`. Encode that assertion as a required-fail cap in Sub-goal 0 of any worktree run. Worktree isolation is the right move whenever another session already holds the main checkout. — (urgent-high-burndown, 2026-08-26)

- [high] **Check whether a "fix" already exists in a consumer repo before scoping it here.** TAP-6498 (Urgent) and TAP-6496 read as greenfield, but both were already implemented and merged in WebStoreDNA's *scaffolded copies* (PRs #125/#124) while this repo's canonical generator still carried the old behaviour — so the real work was a port-back with a working reference implementation, not a fresh build. Linear `attachments[]` is where this surfaces; read it before estimating. The asymmetry is itself a filed defect (TAP-6497, managed-block markers), which is why port-backs must sequence *after* it — otherwise `tapps_upgrade` eats the consumer fix and recreates the defect. — (urgent-high-burndown, 2026-08-26)

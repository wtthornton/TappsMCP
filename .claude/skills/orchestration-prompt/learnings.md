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

# orchestration-prompt learnings (project-scoped)

Append one-line lessons as you generate prompts. Keep them project-scoped; never
bleed across repos. This file is created once by the scaffolder and never
overwritten on upgrade — it's yours.

<!-- Example: -->
<!-- - Validation goals need a verified-correct-negative Done-when, or the loop chases an unreachable target. (2026-06-18) -->

- Multi-epic single-repo drives: sequential `/goal` (not Workflow coding fan-out); override per-edit `tapps_quick_check` to story/epic gates when the epic itself targets gate latency. (2026-07-30)
- Metrics follow-on epics: order root-cause false-positive flags (diff_impact 100% degraded) before surfacing completeness UX, or agents paper over bad semantics. (2026-07-30)

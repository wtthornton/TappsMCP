# Stage 5 of 5: Verify

## Objective

Final verification that all required quality steps were completed. The checklist reviews which tools were called during the session and flags any missing steps.

## Allowed Tools

- `tapps_checklist` - Reports which tools were called and which required/recommended steps are missing for this task type.

## Constraints

- Do NOT skip this stage - it is the final safety net.
- If the checklist reports missing required steps, go back and complete them.
- The task is not done until the checklist shows all required steps completed.

## Steps

1. Determine the task type: "feature", "bugfix", "refactor", "security", or "review".
2. Call `tapps_checklist(task_type="<type>")`.
3. Review the result:
   - **Required** steps missing: go back and complete them.
   - **Recommended** steps missing: complete if time allows, or note as accepted risk.
   - **Optional** steps missing: safe to skip.
4. If you completed additional steps, re-run the checklist to confirm.

## Task Type Guide

| Task Type | When to Use |
|-----------|-------------|
| `feature` | Adding new functionality |
| `bugfix` | Fixing a bug |
| `refactor` | Restructuring without behavior change |
| `security` | Security-focused changes |
| `review` | General code review |

## Exit Criteria

- [ ] Checklist run with correct task type.
- [ ] All required steps completed.
- [ ] Final results recorded in TAPPS_HANDOFF.md.
- [ ] TAPPS_RUNLOG.md updated with final entries.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Checklist result (all_passed / missing items)
- Final status: DONE or accepted risks

## Pipeline Complete

The task has been through all 5 TAPPS quality stages. The work is ready for commit/review.

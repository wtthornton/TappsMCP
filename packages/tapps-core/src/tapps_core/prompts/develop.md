# Stage 3 of 5: Develop

## Objective

Write or modify code with rapid quality feedback. Use quick scoring to catch lint issues and maintain code quality during development.

## Allowed Tools

- `tapps_score_file` - Use with `quick=True` for fast lint-only feedback during editing. Use with `fix=True` to auto-fix ruff issues.

## Constraints

- Use `quick=True` mode only - save full scoring for the Validate stage.
- Do NOT call quality gate or security scan yet - those are for Validate.
- Fix lint issues as you go - do not accumulate them.
- Iterate: edit -> score (quick) -> fix -> score (quick) -> continue.

## Steps

1. Write or modify code for the task.
2. Call `tapps_score_file(file_path="<path>", quick=True)` after each significant edit.
3. If lint issues are found, either fix manually or call `tapps_score_file(file_path="<path>", quick=True, fix=True)` to auto-fix.
4. Repeat the edit-score-fix loop until the file is clean.
5. Move to Validate when you believe the implementation is complete.

## Edit-Lint-Fix Loop

```
while not done:
    1. Edit code
    2. tapps_score_file(quick=True)
    3. If issues found:
       - tapps_score_file(quick=True, fix=True)  # auto-fix
       - OR fix manually
    4. Repeat
```

## Exit Criteria

- [ ] Implementation is functionally complete.
- [ ] Quick scoring shows no lint issues (or only accepted exceptions).
- [ ] Files in scope recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Files created or modified
- Quick score results (final)
- Any deferred issues or known limitations

## Next Stage

**Validate** - Run full scoring, quality gate, and security scan on all changed files.

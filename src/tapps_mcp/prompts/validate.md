# Stage 4 of 5: Validate

## Objective

Run comprehensive quality checks on all changed files. Full scoring includes type checking, security analysis, and complexity metrics beyond what quick mode provides.

## Allowed Tools

- `tapps_score_file` - Use with `quick=False` (default) for full 7-category scoring including mypy, bandit, and radon.
- `tapps_quality_gate` - Evaluate pass/fail against the quality preset. Work is not done until this passes.
- `tapps_security_scan` - Run dedicated security analysis if the code touches security-sensitive areas.
- `tapps_validate_config` - Validate Dockerfiles, docker-compose, or infrastructure config if changed.

## Constraints

- Run full scoring on ALL changed files, not just the primary one.
- The quality gate MUST pass before advancing. If it fails, fix issues and re-run.
- Security scan is required if the change touches authentication, authorization, input handling, or secrets.
- Do NOT skip validation to save time.

## Steps

1. Call `tapps_score_file(file_path="<path>")` (full mode) on each changed file.
2. Review the 7-category breakdown: complexity, security, maintainability, test coverage, performance, structure, devex.
3. Fix any issues found (type errors, security findings, high complexity).
4. Call `tapps_quality_gate(file_path="<path>")` on each changed file.
5. If the gate fails, fix the failures and re-run from step 1.
6. If security-relevant code was changed, call `tapps_security_scan(file_path="<path>")`.
7. If config files were changed, call `tapps_validate_config(file_path="<path>")`.

## Gate Failure Resolution

```
while gate fails:
    1. Read gate failures and warnings
    2. Fix the lowest-scoring categories
    3. Re-run tapps_score_file (full)
    4. Re-run tapps_quality_gate
```

## Exit Criteria

- [ ] Full scoring completed on all changed files.
- [ ] Quality gate passes on all changed files.
- [ ] Security scan clean (if applicable).
- [ ] Config validation clean (if applicable).
- [ ] Results recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Full scores for each file (overall + category breakdown)
- Gate pass/fail results and preset used
- Security scan results (if run)
- Any warnings accepted with justification

## Next Stage

**Verify** - Run the checklist to confirm no required steps were missed.

# Testing strategies playbook

## When to use

Before adding or changing tests, or when fixing regressions without a failing test.

## Workflow

1. Call `tapps_session_start()` if not already called this session.
2. Call `tapps_lookup_docs(library="pytest", topic="fixtures and parametrize")` before writing test code.
3. After code edits, run `tapps_diff_impact(file_paths="...")` to rank affected tests.
4. Use `tapps_quick_check(file_path="...")` on each changed Python test module.
5. Close with `/tapps-finish-task` and `task_type=qa`.

## Checklist

- [ ] New behavior has a test that fails before the fix and passes after.
- [ ] Tests are deterministic (no time/network flakiness without explicit mocks).
- [ ] Fixtures live in conftest when shared across modules.
- [ ] Async tests use the project's async pytest plugin conventions.

## Exit criteria

All changed Python files pass `tapps_validate_changed`; affected tests identified via diff impact when available.

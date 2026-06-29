# Software architecture playbook

## When to use

Cross-module refactors, new packages, boundary moves, or deleting modules.

## Workflow

1. Call `tapps_impact_analysis(file_path="...", granularity="both")` when symbols matter.
2. Use `tapps_dependency_graph` to detect circular imports before large moves.
3. Use `tapps_call_graph` for function-level refactors.
4. Close with `/tapps-finish-task` and `task_type=refactor`.

## Checklist

- [ ] Blast radius documented before edits.
- [ ] Circular dependencies resolved or explicitly accepted.
- [ ] Public vs internal module boundaries respected.

## Exit criteria

Impact/call graph tools used when API or symbol signatures change; gate pass on edits.

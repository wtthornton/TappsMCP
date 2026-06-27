# Performance optimization playbook

## When to use

Latency regressions, hot paths, N+1 queries, or large refactor blast-radius review.

## Workflow

1. Call `tapps_session_start()` and read `data.call_graph` staleness hint.
2. Use `tapps_call_graph(symbol="...", query="callers")` before changing hot functions.
3. Use `tapps_impact_analysis` for module-level blast radius.
4. Iterate with `tapps_quick_check` after edits.
5. Close with `/tapps-finish-task` and `task_type=refactor`.

## Checklist

- [ ] Measure before optimizing (profile or benchmark when possible).
- [ ] Callers of changed symbols reviewed via call graph.
- [ ] No premature micro-optimizations without evidence.

## Exit criteria

Changed code passes gate; call graph consulted when symbols changed.

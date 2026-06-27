# Frontend / UX playbook

## When to use

UI components, styling, routing, accessibility, or client-side performance work.

## Workflow

1. Call `tapps_session_start()` if not already called.
2. Call `tapps_lookup_docs` for the UI library in use (e.g. `react` + `accessibility`).
3. Score changed files with `tapps_score_file` / `tapps_quick_check` (Python backend) or manual review for TS/CSS.
4. Close with `/tapps-finish-task` and `task_type=frontend`.

## Checklist

- [ ] Keyboard navigation and focus order considered.
- [ ] Color contrast and semantic HTML where applicable.
- [ ] No hard-coded secrets in client bundles.
- [ ] Loading and error states handled for async UI.

## Persona (optional)

For implementation voice and UX craft, install [agency-agents](https://github.com/msitarzewski/agency-agents) Frontend Developer — TappsMCP owns enforcement, not persona.

## Exit criteria

Lookup docs called for external UI libraries; quality gate pass on scored files.

# API design playbook

## When to use

New endpoints, request/response models, versioning, or public API changes.

## Workflow

1. Call `tapps_lookup_docs` for the web framework in use (e.g. FastAPI routing, Pydantic models).
2. Run `tapps_impact_analysis(file_path="...")` before changing public module APIs.
3. Edit loop with `tapps_quick_check`.
4. Close with `/tapps-finish-task` and `task_type=feature`.

## Checklist

- [ ] Request/response schemas explicit and validated.
- [ ] Error responses consistent and documented.
- [ ] Breaking changes flagged for consumers.
- [ ] Importers of changed modules identified via impact analysis.

## Exit criteria

Gate pass on changed files; impact analysis when public API touched.

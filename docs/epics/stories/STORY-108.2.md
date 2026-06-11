# document_judges.py: optional shell audit judge preset

## What

document_judges.py: optional shell audit judge preset

## Where

- `packages/tapps-mcp/src/tapps_mcp/pipeline/document_judges.py:44-85`
- `packages/tapps-mcp/tests/unit/test_document_judges.py:1-120`

## Acceptance

- [ ] - [ ] When report-studio CLI is on PATH or pyproject scripts entry exists
- [ ] discovered preset includes optional shell judge for audit CLI
- [ ] Shell judge uses when_changed globs for reports/**
- [ ] templates/**
- [ ] brands/**
- [ ] src/**
- [ ] Judge is blocking only when consumer has built reference PDF fixture path discoverable
- [ ] dry_run init/upgrade preview lists discovered shell judge without hard-coded ReportLab paths

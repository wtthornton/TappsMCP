# session_start_helpers.py: document-quality lookup_docs pack

## What

Add generic document-quality lookup_docs topic pack for PDF/HTML output pitfalls.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/session_start_helpers.py:800-810`
- `packages/tapps-mcp/src/tapps_mcp/server.py:1-50`

## Acceptance

- [ ] - [ ] search_first includes document-quality topic with generic PDF/HTML guidance triggers
- [ ] tapps_lookup_docs(library=document-quality
- [ ] topic=...) returns cached guidance on links
- [ ] outlines
- [ ] thin pages
- [ ] Guidance is library-agnostic; reportlab/weasyprint topics remain separate library lookups
- [ ] Unit test asserts document-quality entry present when reports/ or document tooling detected

## Refs

docs/epics/EPIC-107.md

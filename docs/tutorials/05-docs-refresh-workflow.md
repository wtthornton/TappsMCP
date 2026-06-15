# Tutorial: Documentation refresh workflow

**Time:** ~2 hours (full pass). **Outcome:** Tier-1 docs accurate, API/diagrams regenerated, link graph clean, CI docs gate green.

Uses **nlt-project-docs** tools. Enable `nlt-build` + `nlt-project-docs` for this session.

## Phase 0 — Scope and cleanup

1. Move smoke/test artifacts to `docs/archive/smoke/`
2. Define tier-1 files: `PURPOSE.md`, `ONBOARDING.md`, `ARCHITECTURE.md`, `CONFIG_REFERENCE.md`, `MEMORY_REFERENCE.md`, `TROUBLESHOOTING.md`, `docs/api/*`, `docs/adr/*`, `docs/operations/*`
3. Exclude `docs/archive/**` from validation runs

## Phase 1 — Navigation

```text
docs_check_cross_refs(doc_dirs="docs", exclude="docs/archive")
docs_check_links(broken_only=true)
```

Fix:

- Relative links from `docs/` → use `../CONTRIBUTING.md` not `docs/CONTRIBUTING.md`
- Handoff docs in `docs/handoff/` → use `../../packages/...` for source links
- Orphan epics → regenerate index

```text
docs_generate_doc_index(doc_dirs="docs,README.md,AGENTS.md", output_path="docs/INDEX.md")
```

## Phase 2 — Narrative docs

Hand-edit after generation (generators leave placeholders):

```text
docs_generate_purpose(output_path="docs/PURPOSE.md")
docs_generate_onboarding(output_path="docs/ONBOARDING.md")
docs_generate_llms_txt(mode="compact", output_path="llms.txt")
```

Add NLT taxonomy (ADR-0016), Python 3.12+, developer bundle defaults.

## Phase 3 — API and diagrams

```text
docs_generate_api(source_path="packages/tapps-mcp/src/tapps_mcp", output_path="docs/api/tapps-mcp.md")
docs_generate_api(source_path="packages/tapps-core/src/tapps_core", output_path="docs/api/tapps-core.md")
docs_generate_api(source_path="packages/docs-mcp/src/docs_mcp", output_path="docs/api/docs-mcp.md")
docs_generate_architecture(output_path="docs/architecture.html")
docs_generate_interactive_diagrams(output_path="docs/diagrams/interactive.html")
```

Update `docs/ARCHITECTURE.md` narrative for NLT profiles (don't rely on HTML alone).

## Phase 4 — Tutorials and troubleshooting

- Add domain tutorials (NLT modes, this workflow)
- Extend `TROUBLESHOOTING.md` for Cursor transcript parsing / MCP reload

## Phase 5 — CI gate

Add `.github/workflows/docs-quality.yml`:

```yaml
- run: uv run python scripts/docs-quality-gate.py
```

## Verification checklist

```text
docs_check_completeness()          # target ≥ 98
docs_check_cross_refs(...)         # target ≥ 90
docs_check_freshness(summary_only=true)
docs_check_drift(ignore_patterns="defaults")
docs_check_diataxis()
```

## When to re-run

- After ADR changes affecting MCP taxonomy
- Before release (with `tapps_validate_changed` on Python changes)
- When `docs_check_drift` exceeds 5% on `packages/`

# Epic 83: llms.txt & Machine-Readable Documentation

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1.5 weeks (1 developer)
**Dependencies:** Epic 3 (README Generation)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that every project using DocsMCP automatically produces machine-readable documentation optimized for AI coding assistants. The llms.txt standard and structured frontmatter make DocsMCP the first documentation tool purpose-built for the AI-assisted development era.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP auto-generates llms.txt files (the emerging standard for machine-readable project summaries), structured frontmatter metadata for all generated docs, and an AGENTS.md-aware machine summary -- making every project's documentation optimally consumable by AI coding assistants.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The llms.txt standard is emerging in 2026 as the machine-readable equivalent of robots.txt -- a structured file that tells AI assistants what a project does, how it is organized, and where to find key information. Projects with llms.txt get dramatically better AI assistance. DocsMCP already generates AGENTS.md and project scans -- synthesizing this into llms.txt is a natural extension. Combined with structured frontmatter, this makes DocsMCP the first documentation tool purpose-built for the AI-assisted development era.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] New `docs_generate_llms_txt` tool produces valid llms.txt from project analysis
- [ ] llms.txt includes: project name, description, tech stack, entry points, key files, documentation map
- [ ] Format follows the emerging spec with structured markdown and machine-parseable headings
- [ ] New `docs_generate_frontmatter` tool adds/updates YAML frontmatter to existing markdown files
- [ ] Frontmatter includes: title, description, category, diataxis_type, last_modified, tags
- [ ] `docs_generate_readme` and `docs_generate_api` include frontmatter when configured
- [ ] llms.txt generation integrated into `docs_project_scan` as optional output
- [ ] Unit tests validate llms.txt structure and frontmatter injection

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [83.1](EPIC-83/story-83.1-llms-txt-generator.md) -- llms.txt Generator

**Points:** 5

Create `docs_generate_llms_txt` MCP tool synthesizing project metadata, tech stack, file structure, entry points, and documentation map into structured llms.txt.

**Tasks:**
- [ ] Create `generators/llms_txt.py` with `LlmsTxtGenerator` class
- [ ] Synthesize data from project_scan, module_map, metadata, and git history
- [ ] Generate sections: Project Overview, Tech Stack, Entry Points, Key Files, Documentation Map, API Summary
- [ ] Support both `llms.txt` (compact) and `llms-full.txt` (detailed) output modes
- [ ] Register `docs_generate_llms_txt` in `server_gen_tools.py`
- [ ] Add tests with multi-package project fixtures

**Definition of Done:** llms.txt Generator is implemented, tests pass, and documentation is updated.

---

### [83.2](EPIC-83/story-83.2-structured-frontmatter-system.md) -- Structured Frontmatter System

**Points:** 5

Create `docs_generate_frontmatter` tool injecting/updating YAML frontmatter in existing markdown files with auto-detected metadata.

**Tasks:**
- [ ] Create `generators/frontmatter.py` with `FrontmatterGenerator` class
- [ ] Implement frontmatter parsing (preserve existing fields, merge new)
- [ ] Auto-detect title from first H1 heading
- [ ] Auto-detect description from first paragraph
- [ ] Auto-detect tags from content keywords and file path
- [ ] Integrate Diataxis classifier (Epic 82) for `diataxis_type` field
- [ ] Register `docs_generate_frontmatter` in `server_gen_tools.py`
- [ ] Add tests for injection, update, and preservation scenarios

**Definition of Done:** Structured Frontmatter System is implemented, tests pass, and documentation is updated.

---

### [83.3](EPIC-83/story-83.3-integration-existing-generators.md) -- Integration with Existing Generators

**Points:** 3

Add optional frontmatter output to README, API, ADR, and contributing generators. Add llms.txt generation as optional step in `docs_project_scan`.

**Tasks:**
- [ ] Add `include_frontmatter` parameter to README, API, ADR generators
- [ ] Add `generate_llms_txt` option to `docs_project_scan`
- [ ] Update AGENTS.md template with llms.txt tool reference
- [ ] Add integration tests

**Definition of Done:** Integration with Existing Generators is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- The llms.txt spec is still emerging -- implement a forward-compatible superset covering the most common fields
- Frontmatter must use `---` delimiters and valid YAML
- Existing files with frontmatter must have their fields preserved (merge, not overwrite)
- The llms.txt should be regenerable (idempotent) so it can be auto-updated in CI
- Consider supporting `llms-full.txt` (detailed) and `llms.txt` (compact) variants per the spec

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- AI-powered content summarization for llms.txt (use deterministic extraction only)
- External API integration (llms.txt is a local file)
- Frontmatter enforcement (optional feature, not a gate)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| llms.txt adoption | 0 | 25 | projects generating llms.txt in first 90 days |
| Frontmatter coverage | 0% | 60% | generated docs with structured frontmatter |
| AI context quality | qualitative | improved | measured by user feedback |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 83.1: llms.txt Generator
2. Story 83.2: Structured Frontmatter System
3. Story 83.3: Integration with Existing Generators

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| llms.txt spec not yet finalized | Medium | Medium | Implement superset; track spec changes; version field for forward compat |
| Frontmatter injection could break non-standard headers | Medium | Medium | Robust parsing with dry-run mode; preserve existing fields |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/generators/llms_txt.py` | 83.1 | New file: LlmsTxtGenerator |
| `packages/docs-mcp/src/docs_mcp/generators/frontmatter.py` | 83.2 | New file: FrontmatterGenerator |
| `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` | 83.1, 83.2 | Register new tools |
| `packages/docs-mcp/src/docs_mcp/generators/readme.py` | 83.3 | Add include_frontmatter param |

<!-- docsmcp:end:files-affected -->

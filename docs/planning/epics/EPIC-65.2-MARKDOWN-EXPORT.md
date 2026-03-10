# Epic 65.2: Markdown Export & Curation (2026 Best Practices)

**Status:** Complete
**Priority:** P1 | **LOE:** 3-5 days | **Source:** [EPIC-65-MEMORY-2026-BEST-PRACTICES](../EPIC-65-MEMORY-2026-BEST-PRACTICES.md)
**Dependencies:** Epic 23, 42 (memory foundation, export action — both complete)

## Problem Statement

`tapps_memory(action="export")` currently outputs JSON. For human-in-the-loop curation (Obsidian, VS Code, manual review), Markdown export with grouping and frontmatter improves workflow. Aligns with RAG 2025 "content optimization" and Neuronex "human-in-the-loop."

## Stories

### Story 65.2.1: Markdown format for export

**Files:** `packages/tapps-core/src/tapps_core/memory/io.py`, `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py`

1. Extend `tapps_memory(action="export")` with `format` parameter: `"json"` (default) | `"markdown"`
2. When `format="markdown"`:
   - Output Markdown with optional Obsidian frontmatter per entry
   - Group by tier (architectural, pattern, context)
   - Within tier, sort by key or updated_at
3. Frontmatter fields: `tags`, `created_at`, `updated_at`, `confidence`, `source`, `tier`
4. Path validation: `file_path` must be within project root (existing security)

**Acceptance criteria:**
- `tapps_memory(action="export", format="markdown", file_path="...")` writes valid Markdown
- Entries grouped by tier
- Frontmatter optional (config or param)

### Story 65.2.2: Obsidian-style output options

**Files:** `packages/tapps-core/src/tapps_core/memory/io.py`

1. Add export options:
   - `include_frontmatter: bool` (default: true)
   - `group_by: "tier" | "tag" | "none"`
   - `include_metadata: bool` (created_at, confidence in body)
2. Obsidian-friendly: YAML frontmatter, `#` headings per tier

**Acceptance criteria:**
- Configurable grouping and frontmatter
- Output parseable by Obsidian

## Testing

- Unit: export markdown format shape and content
- Unit: export with/without frontmatter, different group_by
- Integration: export → verify file written, re-import JSON round-trip

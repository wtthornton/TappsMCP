# Feature Request: Epic-to-fix_plan Sync & Format Enforcement

**From:** TappsMCP project (MCP-connected consuming project)
**For:** Ralph (autonomous dev agent / fix_plan optimizer)
**Date:** 2026-03-24
**Context:** During a session reviewing TappsMCP Epics 89-90, we identified that the fix_plan format for story-backed work should follow a strict pointer convention. Ralph should own the generation and enforcement of this format.

---

## Problem

When external tools (TappsMCP, docs-mcp) produce epics and stories, those specs need to flow into Ralph's `fix_plan.md` as executable work items. Today this is done manually, and the person or agent writing fix_plan items tends to either:

1. **Over-specify** — re-summarize the story inline, creating a second source of truth that drifts from the actual story file
2. **Under-specify** — write vague items with no link to the story, so Ralph has to guess what to do
3. **Mis-sequence** — ignore the implementation order defined in the epic

The stories are already right-sized for one Ralph loop iteration. The fix_plan shouldn't re-spec them — it should point at them.

---

## Proposed Capability

### 1. Epic Ingestion: Append stories to fix_plan

Ralph should be able to ingest an epic file (or a directory of story files) and append a new `##` phase section to `fix_plan.md` with properly formatted pointer items.

**Input:** An epic markdown file path (e.g., `docs/planning/epics/EPIC-89-CROSS-PROJECT-TOOL-PARITY.md`)

**Output:** A new phase appended to `fix_plan.md`:

```markdown
## Phase N: Cross-Project Tool Parity (Epic 89)

<!-- Epic: docs/planning/epics/EPIC-89-CROSS-PROJECT-TOOL-PARITY.md -->
<!-- Source: TappsMCP issue #76 -->

- [ ] 89.1: Execute story — docs/planning/epics/EPIC-89/story-89.1-impact-analysis-project-root.md
- [ ] 89.2: Execute story — docs/planning/epics/EPIC-89/story-89.2-session-start-project-root.md
- [ ] 89.3: Execute story — docs/planning/epics/EPIC-89/story-89.3-installed-checkers-environment-context.md
- [ ] 89.4: Execute story — docs/planning/epics/EPIC-89/story-89.4-shell-bash-project-detection.md
```

**Key behaviors:**

- **Respect implementation order** from the epic's `## Implementation Order` section (not just file order)
- **One item per story** — the story file IS the spec, the fix_plan item is a pointer
- **Phase heading** includes epic number and title for traceability
- **HTML comments** with epic path and source issue for auditing
- **Auto-detect phase number** from existing fix_plan sections

### 2. Format Enforcement: Validate fix_plan structure

Ralph should validate fix_plan.md for consistency on every read (start of loop). Rules:

**Item format rules:**
- Story-backed items MUST follow: `- [ ] {story_id}: Execute story — {story_file_path}`
- Story file path MUST resolve to an existing file
- Item text MUST NOT exceed 120 characters (prevents inline spec creep)
- Ad-hoc items (no story file) are allowed but should not reference story IDs

**Phase structure rules:**
- Each `##` phase must have at least one `- [ ]` or `- [x]` item
- Epic-backed phases should have the epic path in an HTML comment
- Phase numbering should be sequential
- No duplicate story IDs across phases

**Consistency rules:**
- All `- [x]` items should appear before `- [ ]` items within a phase (completed work rises to top) — OR original order is preserved (configurable)
- If a story file is deleted or moved, flag the dangling reference

### 3. Multi-Epic Support

A single fix_plan may contain phases from multiple epics, plus ad-hoc phases with no backing epic. The sync capability should:

- Append new epic phases without disturbing existing phases
- Handle the case where some stories from an epic are already in fix_plan (skip duplicates)
- Support re-syncing if the epic's story list changes (new stories added, stories removed)

---

## How This Fits Ralph's Execution Contract

Ralph's loop (from PROMPT.md) is:

1. Read fix_plan.md, select first unchecked `- [ ]` item
2. Implement the smallest complete change
3. Mark `[x]`, commit
4. At epic boundary (last item in `##` section), run QA
5. Report status, stop

**Story pointer items fit this perfectly:**

- **Step 1:** Ralph reads the fix_plan item, sees it's a story pointer, reads the story file
- **Step 2:** The story has Tasks, AC, and DoD — Ralph implements against these
- **Step 3:** Marks the fix_plan item `[x]` (story completion tracked in fix_plan, not in the story file)
- **Step 4:** Epic boundary = last story in the phase, triggers QA — matches epic boundary concept
- **Step 5:** Status block as normal

The story file replaces inline task description. Ralph's existing loop doesn't change — it just follows the pointer before implementing.

---

## Examples

### Correct (pointer style)

```markdown
## Phase 5: Cross-Project Tool Parity (Epic 89)

<!-- Epic: docs/planning/epics/EPIC-89-CROSS-PROJECT-TOOL-PARITY.md -->

- [x] 89.1: Execute story — docs/planning/epics/EPIC-89/story-89.1-impact-analysis-project-root.md
- [ ] 89.2: Execute story — docs/planning/epics/EPIC-89/story-89.2-session-start-project-root.md
```

### Correct (ad-hoc, no story — existing Phase 1 style)

```markdown
## Phase 1: Critical Deploy Blockers (Quick Fixes)

- [x] C1: Replace `import logging` with `structlog` in server_scoring_tools.py (lines 11, 47).
```

### Incorrect (inline spec creep)

```markdown
- [ ] 89.1: Add `project_root: str = ""` parameter to `tapps_impact_analysis()` in
  `server_analysis_tools.py:245`. When non-empty, resolve to Path and use instead of
  `settings.project_root`. Update `_validate_file_path_lazy()` call to accept the
  overridden root. Thread project_root to `build_impact_memory_context()` call.
```

This duplicates the story. If the story is updated, this item drifts.

### Incorrect (vague pointer)

```markdown
- [ ] 89.1: Do the impact analysis thing
```

No story path, no way for Ralph to find the spec.

---

## Suggested Implementation

This could be implemented as:

1. **A Ralph command/mode:** `ralph sync-epic <epic-path>` that appends a phase to fix_plan
2. **A validation step** in Ralph's loop preamble (before selecting the first unchecked item)
3. **A section in PROMPT.md** documenting the pointer convention so Ralph follows it when humans manually add items

The validation is lightweight — file existence checks, line length, regex matching. No external tool dependencies required.

---

## Relationship to TappsMCP

TappsMCP owns:
- Epic and story file format (structural validation via `tapps_checklist`)
- Story content quality (AC, tasks, DoD completeness)
- Code quality after Ralph implements (scoring, security, gates)

Ralph owns:
- fix_plan format and sequencing
- Epic-to-fix_plan sync
- Execution loop and QA boundaries
- Deciding when a story is "done" (marking `[x]`)

The contract boundary: TappsMCP produces well-structured stories, Ralph consumes them as pointers in fix_plan. Neither tool needs to know the other's internals.

---

## Acceptance Criteria

- [ ] Ralph can ingest an epic file and append a correctly formatted phase to fix_plan.md
- [ ] Story items use pointer format with resolvable file paths
- [ ] Implementation order from epic is respected in fix_plan sequencing
- [ ] fix_plan validation catches: missing story files, inline spec creep (>120 chars), duplicate story IDs
- [ ] Ad-hoc items (no story) continue to work as they do today
- [ ] Multi-epic fix_plans work (multiple phases from different epics)
- [ ] Existing Phases 1-4 format is not broken or reformatted

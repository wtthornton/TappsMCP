# Tapps Platform Kickoff Prompt

Copy the prompt below into Claude Code to begin Phase 1.

---

## Prompt

```
Read the following PRDs before doing anything:
- docs/planning/TAPPS_PLATFORM_PRD.md (architecture, extraction plan, all epics/stories)
- docs/planning/DOCSMCP_PRD.md (DocsMCP feature spec)

You are kicking off the Tapps Platform restructure. This converts TappsMCP from
a single package into a uv workspace monorepo with 3 packages: tapps-core,
tapps-mcp, and docs-mcp.

## Quality Pipeline

Call tapps_session_start first. Use TappsMCP on itself throughout:
- tapps_quick_check after editing any Python file
- tapps_validate_changed before completing each epic
- tapps_checklist(task_type="refactor") at each epic boundary

## Team Structure

Create a team named "tapps-platform" with these teammates:

1. **architect** (general-purpose) — Owns Epic 0: Create the uv workspace
   structure, root pyproject.toml, package scaffolds, shared CI config.
   Must verify `uv sync --all-packages` works before done.

2. **extractor** (general-purpose) — Owns Epic 1: Extract Tier 1 packages
   (common/, config/, security/, prompts/) from tapps_mcp to tapps_core.
   Resolve the 4 circular dependencies documented in the PRD Section 6.3.
   Create backward-compatible re-exports in tapps_mcp. All 2700+ existing
   tests must pass after each story.

3. **validator** (general-purpose) — Runs continuously after architect and
   extractor complete stories. Runs the full test suite, mypy --strict,
   ruff check, and tapps_validate_changed. Reports failures back to the
   team immediately.

## Execution Plan

Start with Epic 0 (Workspace Foundation), then Epic 1 (Tier 1 Extraction).
Do NOT start Epic 2 yet — it requires Epic 1 to stabilize first.

Stories within each epic can be parallelized where the PRD shows no
dependency. The PRD "Depends" column defines the ordering.

## Critical Rules

- GREEN TESTS AT EVERY STEP. No story is complete unless all tests pass.
- `from tapps_mcp.config import load_settings` must still work after
  extraction (backward compat via re-exports).
- Do not move scoring/, tools/, gates/, project/, validators/, pipeline/,
  distribution/ — these stay in tapps-mcp per the PRD.
- Follow existing code conventions in CLAUDE.md (Python 3.12+, mypy strict,
  structlog, pathlib, ruff line-length 100).

Begin by reading both PRDs, then create the team and start Epic 0.
```

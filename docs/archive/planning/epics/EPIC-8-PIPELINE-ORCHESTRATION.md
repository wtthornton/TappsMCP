# Epic 8: Pipeline Orchestration & Workflow Prompts

**Status:** Complete - 7 stories, 17 source files, 66 new tests (952 total), 7 skipped
**Priority:** P1 — High (unlocks structured quality workflows for every TappsMCP consumer)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 1 (Core Quality), Epic 2 (Knowledge), Epic 3 (Expert System), Epic 4 (Project Context)
**Blocks:** None (standalone value — any project using TappsMCP benefits immediately)

---

## Goal

Make the 5-stage TAPPS quality pipeline (Discover - Research - Develop - Validate - Verify) available to **every project** that connects to TappsMCP, on **every platform** (Claude Code, Cursor, any MCP client) — without requiring manual prompt setup, file copying, or platform-specific configuration.

Today TappsMCP exposes 13+ tools but leaves orchestration knowledge in the repo's docs. A developer who installs TappsMCP gets the tools but has no idea there's a structured pipeline to follow. This epic fixes that gap by shipping pipeline workflow prompts as first-class MCP primitives.

## Problem Statement

| Gap | Impact |
|---|---|
| Pipeline exists only as a local system prompt | Other projects don't benefit |
| No MCP prompts registered | LLM hosts can't discover the workflow |
| `tapps_server_info` mentions workflow as prose | Not structured enough for LLMs to follow |
| Handoff/runlog files are ad-hoc | No validation, no template, no tooling |
| Platform-specific setup (CLAUDE.md, .cursorrules) | Manual and fragile |

## Solution

Ship the pipeline as **MCP prompts** (protocol-native, cross-platform), enhance `tapps_server_info` with structured pipeline metadata, and provide a `tapps_init` bootstrap tool.

## The 5-Stage Pipeline

```
Discover ──► Research ──► Develop ──► Validate ──► Verify ──► DONE
   │             │            │            │            │
   ▼             ▼            ▼            ▼            ▼
server_info   lookup_docs  score_file   score_file   checklist
project_      consult_     (quick)      (full)
profile       expert                    quality_gate
                                        security_scan
```

Each stage has:
- **Allowed tools**: Only specific TappsMCP tools are relevant
- **Constraints**: Hard boundaries on what the LLM should/shouldn't do
- **Exit criteria**: What must be true before advancing
- **Handoff output**: What to persist for the next stage

## 2026 Best Practices Applied

- **MCP Prompts** (`@mcp.prompt()`): Protocol-native workflow delivery — any MCP client can request stage instructions without platform-specific config.
- **Content shipped in package**: Stage prompt markdown files live in `src/tapps_mcp/prompts/` and are distributed via PyPI/Docker. No separate download needed.
- **Progressive disclosure**: `tapps_server_info` tells the LLM about the pipeline; `@mcp.prompt()` provides full stage details on demand. Two levels of detail, zero context waste.
- **Platform-agnostic core**: MCP prompts work everywhere. Platform-specific rule files (CLAUDE.md, .cursorrules) are generated on demand by `tapps_init`, not required.

## Acceptance Criteria

- [ ] 5 stage prompt files ship with the package (`src/tapps_mcp/prompts/`)
- [ ] `@mcp.prompt("tapps_pipeline")` returns stage-specific instructions for any of the 5 stages
- [ ] `@mcp.prompt("tapps_pipeline_overview")` returns a summary of all stages (for LLM orientation)
- [ ] `tapps_server_info` response includes structured `pipeline` field with stages, tools, and constraints
- [ ] `tapps_init` tool bootstraps handoff/runlog templates and optionally generates platform rule files
- [ ] Handoff file format has a Pydantic model for validation
- [ ] All prompt content is loaded from files (not hardcoded strings in Python)
- [ ] Works cross-platform: Claude Code, Cursor, any MCP client that supports prompts
- [ ] Graceful fallback: clients that don't support MCP prompts still get pipeline info from `tapps_server_info`
- [ ] Unit tests: ~30 tests covering prompt loading, MCP prompt handlers, init tool, handoff validation
- [ ] No changes required in consuming projects — pipeline is available the moment TappsMCP is connected

---

## Stories

### 8.1 — Stage Prompt Content Files

**Points:** 3

Create the 5 stage prompt markdown files that define the pipeline workflow. These are the source of truth for all pipeline instructions.

**Tasks:**
- Create `src/tapps_mcp/prompts/` package directory with `__init__.py`
- Create stage prompt files:
  - `discover.md` — Instructions for Discover stage (tapps_server_info + tapps_project_profile)
  - `research.md` — Instructions for Research stage (tapps_lookup_docs + tapps_consult_expert)
  - `develop.md` — Instructions for Develop stage (tapps_score_file quick, edit-lint-fix loops)
  - `validate.md` — Instructions for Validate stage (full scoring + gate + security scan)
  - `verify.md` — Instructions for Verify stage (tapps_checklist)
- Create `overview.md` — Pipeline summary with stage map, tool assignments, and flow diagram
- Create `handoff_template.md` — Template for TAPPS_HANDOFF.md files
- Create `runlog_template.md` — Template for TAPPS_RUNLOG.md files
- Implement `prompt_loader.py`:
  - `load_stage_prompt(stage: str) -> str` — Load a single stage prompt
  - `load_overview() -> str` — Load the pipeline overview
  - `load_handoff_template() -> str` — Load handoff template
  - `list_stages() -> list[str]` — Return ordered stage names
  - Uses `importlib.resources` for package-safe file loading
- Write ~5 unit tests for prompt loader (file loading, invalid stage handling, completeness check)

**Stage prompt content requirements:**
Each stage file must include:
1. **Stage name and position** (e.g., "Stage 2 of 5: Research")
2. **Objective** — What this stage accomplishes
3. **Allowed tools** — Exact tool names with parameter hints
4. **Constraints** — What the LLM must NOT do in this stage
5. **Exit criteria** — What must be true before advancing
6. **Handoff instructions** — What to write to TAPPS_HANDOFF.md
7. **Next stage** — Name and first action of the next stage

**Definition of Done:** All prompt files exist, load correctly via `importlib.resources`, and contain complete stage instructions.

---

### 8.2 — MCP Prompt Handlers

**Points:** 3

Register `@mcp.prompt()` handlers so any MCP client can request pipeline instructions.

**Tasks:**
- Register `tapps_pipeline` prompt in `server.py`:
  ```python
  @mcp.prompt()
  def tapps_pipeline(stage: str = "discover") -> str:
      """TAPPS quality pipeline — structured 5-stage workflow.

      Get instructions for a specific pipeline stage. Stages run in order:
      discover -> research -> develop -> validate -> verify.

      Args:
          stage: Pipeline stage to get instructions for.
                 One of: discover, research, develop, validate, verify.
      """
  ```
- Register `tapps_pipeline_overview` prompt:
  ```python
  @mcp.prompt()
  def tapps_pipeline_overview() -> str:
      """Get a summary of the full TAPPS 5-stage quality pipeline.

      Returns stage names, tool assignments, flow diagram, and
      handoff file format. Use this to understand the full pipeline
      before starting.
      """
  ```
- Input validation: reject invalid stage names with clear error
- Return prompt content loaded from stage files (story 8.1)
- Write ~5 unit tests:
  - Each stage returns non-empty content
  - Invalid stage returns error
  - Overview returns pipeline summary
  - Prompt is discoverable via MCP prompt listing

**Definition of Done:** Both prompts are callable via MCP protocol. Any MCP client can list and invoke them.

---

### 8.3 — Enhanced `tapps_server_info` Response

**Points:** 2

Add structured pipeline metadata to `tapps_server_info` so LLMs get pipeline awareness on the very first tool call, even without MCP prompt support.

**Tasks:**
- Add `pipeline` field to `tapps_server_info` response:
  ```python
  "pipeline": {
      "name": "TAPPS Quality Pipeline",
      "stages": ["discover", "research", "develop", "validate", "verify"],
      "current_hint": "Start with tapps_pipeline_overview prompt, or follow stages in order.",
      "stage_tools": {
          "discover": ["tapps_server_info", "tapps_project_profile"],
          "research": ["tapps_lookup_docs", "tapps_consult_expert", "tapps_list_experts"],
          "develop": ["tapps_score_file"],
          "validate": ["tapps_score_file", "tapps_quality_gate", "tapps_security_scan"],
          "verify": ["tapps_checklist"],
      },
      "handoff_file": "docs/TAPPS_HANDOFF.md",
      "runlog_file": "docs/TAPPS_RUNLOG.md",
      "prompts_available": True,
  }
  ```
- Keep existing `recommended_workflow` field for backward compatibility
- Add `prompts_available: True` flag so LLMs know to request `tapps_pipeline` prompt
- Write ~3 unit tests: pipeline field present, stages correct, tool mapping accurate

**Definition of Done:** `tapps_server_info` returns structured pipeline metadata alongside existing fields.

---

### 8.4 — Handoff & Runlog Models

**Points:** 2

Create Pydantic models for handoff and runlog files, enabling validation and programmatic access.

**Tasks:**
- Create `src/tapps_mcp/pipeline/` package with `__init__.py`
- Create `src/tapps_mcp/pipeline/models.py`:
  ```python
  class PipelineStage(str, Enum):
      DISCOVER = "discover"
      RESEARCH = "research"
      DEVELOP = "develop"
      VALIDATE = "validate"
      VERIFY = "verify"

  class StageResult(BaseModel):
      stage: PipelineStage
      completed_at: datetime
      tools_called: list[str]
      findings: list[str]
      decisions: list[str]
      files_in_scope: list[str] = []
      open_questions: list[str] = []

  class HandoffState(BaseModel):
      current_stage: PipelineStage
      objective: str
      stage_results: list[StageResult] = []
      next_stage_instructions: str = ""

  class RunlogEntry(BaseModel):
      timestamp: datetime
      stage: PipelineStage
      action: str
      details: str
  ```
- Create `src/tapps_mcp/pipeline/handoff.py`:
  - `render_handoff(state: HandoffState) -> str` — Render to markdown
  - `parse_handoff(content: str) -> HandoffState` — Parse from markdown (best-effort)
  - `render_runlog_entry(entry: RunlogEntry) -> str` — Render single entry
- Write ~8 unit tests: model validation, render/parse round-trip, edge cases

**Definition of Done:** Handoff and runlog have validated models. Render/parse work for standard format.

---

### 8.5 — `tapps_init` Bootstrap Tool

**Points:** 3

New MCP tool that bootstraps pipeline files in the consuming project.

**Tasks:**
- Register `tapps_init` tool in `server.py`:
  ```python
  @mcp.tool()
  def tapps_init(
      create_handoff: bool = True,
      create_runlog: bool = True,
      platform: str = "",
  ) -> dict[str, Any]:
      """Bootstrap TAPPS pipeline in the current project.

      Creates handoff and runlog template files. Optionally generates
      platform-specific rule files for Claude Code or Cursor.

      Call once per project to set up the pipeline workflow.

      Args:
          create_handoff: Create docs/TAPPS_HANDOFF.md template.
          create_runlog: Create docs/TAPPS_RUNLOG.md template.
          platform: Generate platform rules. One of: "claude", "cursor", "".
                    Empty string skips platform-specific files.
      """
  ```
- Implementation:
  - Create `docs/` directory if it doesn't exist
  - Write `docs/TAPPS_HANDOFF.md` from template (story 8.1)
  - Write `docs/TAPPS_RUNLOG.md` from template
  - If `platform="claude"`: append pipeline reference to `CLAUDE.md` (create if missing)
  - If `platform="cursor"`: create `.cursor/rules/tapps-pipeline.md` with pipeline instructions
  - Skip files that already exist (don't overwrite) — report as "already exists"
  - Path validation: all writes within project root
- Create `src/tapps_mcp/pipeline/init.py` for the bootstrap logic
- Write ~8 unit tests:
  - Creates handoff template
  - Creates runlog template
  - Skips existing files
  - Claude platform rules
  - Cursor platform rules
  - Empty platform skips rule generation
  - Path validation (no writes outside project root)

**Definition of Done:** `tapps_init` creates pipeline files in any project. Platform-specific rules generated on demand.

---

### 8.6 — Platform Rule Content

**Points:** 2

Create the platform-specific rule content that `tapps_init` generates.

**Tasks:**
- Create `src/tapps_mcp/prompts/platform_claude.md`:
  - CLAUDE.md snippet that references the TAPPS pipeline
  - Tells Claude Code to call `tapps_server_info` at session start
  - References `tapps_pipeline` MCP prompt for stage instructions
  - Includes the full 5-stage constraint system
  - Compact format (minimize context window cost — target < 800 tokens)
- Create `src/tapps_mcp/prompts/platform_cursor.md`:
  - `.cursor/rules/` compatible format
  - Same content adapted for Cursor's rule system
  - Includes `alwaysApply: true` frontmatter if Cursor supports it
- Both files reference MCP prompts as primary source, with inline fallback for clients that don't support MCP prompts
- Write ~3 unit tests: files load correctly, contain required sections, stay under token budget

**Definition of Done:** Platform rules exist for Claude and Cursor. Both reference MCP prompts with inline fallback.

---

### 8.7 — Integration Tests

**Points:** 2

End-to-end tests for the full pipeline integration.

**Tasks:**
- Test MCP prompt listing includes `tapps_pipeline` and `tapps_pipeline_overview`
- Test `tapps_server_info` pipeline field matches registered prompts
- Test `tapps_init` → handoff file → `HandoffState` model round-trip
- Test stage prompt content references only tools that exist in `tapps_server_info`
- Test pipeline stage ordering is consistent across all surfaces (prompts, server_info, models)
- Test prompt content doesn't exceed reasonable token limits (< 2000 tokens per stage)
- Test `tapps_init` with `platform="claude"` produces valid CLAUDE.md content
- Test `tapps_init` with `platform="cursor"` produces valid Cursor rules content
- Cross-platform: file creation works on Windows + Linux

**Definition of Done:** ~8 integration tests pass. Pipeline is consistent across all delivery mechanisms.

---

## File Map (New Files)

```
src/tapps_mcp/
├── prompts/
│   ├── __init__.py
│   ├── prompt_loader.py          # Load stage prompts from markdown files
│   ├── overview.md               # Full pipeline summary
│   ├── discover.md               # Stage 1 instructions
│   ├── research.md               # Stage 2 instructions
│   ├── develop.md                # Stage 3 instructions
│   ├── validate.md               # Stage 4 instructions
│   ├── verify.md                 # Stage 5 instructions
│   ├── handoff_template.md       # TAPPS_HANDOFF.md template
│   ├── runlog_template.md        # TAPPS_RUNLOG.md template
│   ├── platform_claude.md        # CLAUDE.md snippet
│   └── platform_cursor.md        # .cursor/rules snippet
├── pipeline/
│   ├── __init__.py
│   ├── models.py                 # HandoffState, RunlogEntry, PipelineStage
│   ├── handoff.py                # Render/parse handoff markdown
│   └── init.py                   # Bootstrap logic for tapps_init
└── server.py                     # Modified: +2 @mcp.prompt(), +1 @mcp.tool(), enhanced server_info

tests/unit/
├── test_prompt_loader.py         # ~5 tests
├── test_pipeline_models.py       # ~8 tests
├── test_pipeline_init.py         # ~8 tests
├── test_mcp_prompts.py           # ~5 tests
└── test_pipeline_integration.py  # ~8 tests (integration)
```

## Performance Targets

| Surface | Target | Notes |
|---|---|---|
| `tapps_pipeline` prompt | < 50ms | File read from package |
| `tapps_pipeline_overview` prompt | < 50ms | File read from package |
| `tapps_server_info` (with pipeline field) | < 100ms | Same as current + dict addition |
| `tapps_init` | < 500ms | File writes only |

## Key Design Decisions

1. **Prompts over tools for workflow delivery**: MCP prompts are the right primitive — they provide context without side effects. Tools are for actions. The pipeline is context.

2. **Content in files, not Python strings**: Stage prompts are markdown files, not hardcoded strings in `server.py`. This makes them easy to review, edit, and version independently of code changes.

3. **`importlib.resources` for loading**: Package-safe file loading that works in editable installs, wheel installs, and zip imports. No `__file__` path manipulation.

4. **Handoff models are optional**: The pipeline works with plain markdown handoff files. The Pydantic models enable validation and programmatic access but aren't required for basic use.

5. **`tapps_init` is non-destructive**: Never overwrites existing files. Reports "already exists" and moves on. This prevents accidentally clobbering a project's in-progress handoff.

6. **Platform rules are generated, not required**: MCP prompts are the primary delivery. Platform-specific rules (CLAUDE.md, .cursorrules) are a convenience for clients that don't support MCP prompts.

## Dependencies

- **Python packages:** None new. Uses `importlib.resources` (stdlib), Pydantic (already a dependency).
- **MCP SDK:** `@mcp.prompt()` decorator — already available in `mcp[cli]>=1.26.0`.
- **Epics 0-4:** All tools referenced by the pipeline must exist. All complete.

## Risks

| Risk | Mitigation |
|---|---|
| MCP prompt support varies across clients | Fallback: `tapps_server_info` provides inline pipeline guidance |
| Stage prompts become stale if tools change | Test (story 8.7) validates prompts reference only existing tools |
| Handoff markdown parsing is fragile | Best-effort parsing; models are optional, not required |
| Platform rule files may conflict with user's existing rules | `tapps_init` never overwrites; appends to CLAUDE.md |
| Token budget for stage prompts | Test enforces < 2000 tokens per stage |

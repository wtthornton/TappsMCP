# Epic 45: Business Expert Lifecycle Management

- **Status:** Complete
- **Priority:** P2 - Medium Value (quality-of-life for business expert setup)
- **Estimated LOE:** ~1.5 weeks (1 developer)
- **Dependencies:** Epic 43 (Business Expert Foundation), Epic 44 (Business Expert Consultation and Integration)
- **Blocks:** None

---

## Goal

Provide MCP-native tools for creating, managing, and scaffolding business experts. Instead of requiring users to manually write YAML config and create directories, this epic adds a `tapps_manage_experts` MCP tool and integrates expert scaffolding into `tapps_init`. The LLM can create business experts conversationally ("add a Home Assistant expert for this project") and the tool handles YAML generation, directory creation, and starter knowledge scaffolding.

## Motivation

While users can manually create `.tapps-mcp/experts.yaml` and knowledge directories (Epic 43 makes this work), the intended workflow is LLM-driven: the user describes their project's business domains, and the LLM uses TappsMCP tools to set everything up. This epic makes that workflow smooth. It also provides expert lifecycle operations (list, add, remove, scaffold, validate) and integrates with the existing `tapps_init` pipeline.

### User Stories Driving This Epic

1. **First-Time Setup (LLM-driven):** User prompts: "I'm building a Home Assistant integration project. Add a Home Assistant expert and a Home Automation expert." The LLM calls `tapps_manage_experts(action="add", ...)` twice, which creates `experts.yaml`, scaffolds knowledge directories, and generates starter knowledge files -- all via MCP tool calls.
2. **Enriching Knowledge:** User says: "Add this to the Home Assistant expert's knowledge base: we use ESPHome for all custom sensors, and our naming convention is `sensor.<room>_<type>_<id>`." The LLM writes a new knowledge file to `.tapps-mcp/knowledge/home-assistant/project-conventions.md`.
3. **Removing an Expert:** User says: "Remove the CFO expert, we don't need it anymore." The LLM calls `tapps_manage_experts(action="remove", expert_id="expert-cfo")`.
4. **Validating Setup:** User says: "Check my business expert setup." The LLM calls `tapps_manage_experts(action="validate")` and reports any issues.

## Design Decisions

1. **Single MCP tool with actions.** Following the `tapps_memory` pattern (11 actions on one tool), we create `tapps_manage_experts` with actions: `list`, `add`, `remove`, `scaffold`, `validate`. This avoids tool proliferation while keeping the interface clean.

2. **No interactive CLI wizard.** The original TappsCodingAgents had an `ExpertSetupWizard` with interactive prompts. For MCP, we use the action-based tool pattern. The LLM drives the setup conversationally. MCP elicitation (where supported) can be used for confirmation.

3. **Idempotent scaffolding.** `scaffold` action creates the knowledge directory and starter files only if they do not already exist. Re-running is safe.

4. **`tapps_init` integration.** When `tapps_init` runs and detects an existing `.tapps-mcp/experts.yaml`, it validates and reports the business expert status. An optional `scaffold_experts: bool` parameter scaffolds knowledge directories for any experts missing them.

5. **Atomic YAML writes.** All YAML modifications write to a temp file first, then rename. This prevents corruption from interrupted writes.

## Acceptance Criteria

- [ ] `tapps_manage_experts(action="list")` returns all business experts with their knowledge status
- [ ] `tapps_manage_experts(action="add", ...)` creates/appends to `.tapps-mcp/experts.yaml` and optionally scaffolds knowledge directory
- [ ] `tapps_manage_experts(action="remove", expert_id="...")` removes an expert from YAML config
- [ ] `tapps_manage_experts(action="scaffold", expert_id="...")` creates knowledge directory with starter template
- [ ] `tapps_manage_experts(action="validate")` checks all business expert configs and knowledge directories
- [ ] `tapps_init` reports business expert status when `experts.yaml` exists
- [ ] `tapps_init` can scaffold knowledge directories for configured experts
- [ ] All YAML modifications are atomic (write to temp file, rename) to prevent corruption
- [ ] All file writes pass through `PathValidator`
- [ ] Adding an expert with a duplicate `expert_id` returns a clear error
- [ ] Adding an expert with an `expert_id` that collides with a built-in expert returns a clear error
- [ ] Unit tests: ~35 tests
- [ ] All new files pass quality gate (standard preset, score >= 70)

---

## Stories

### 45.1 -- tapps_manage_experts MCP Tool

**Points:** 8

Create the `tapps_manage_experts` MCP tool with 5 actions for business expert lifecycle management.

**Tasks:**
- Create `packages/tapps-mcp/src/tapps_mcp/server_expert_tools.py`:
  ```python
  """Business expert management tool handlers for TappsMCP.

  Provides the tapps_manage_experts MCP tool with actions:
  list, add, remove, scaffold, validate.
  """
  from __future__ import annotations

  import time
  from pathlib import Path
  from typing import TYPE_CHECKING, Any

  from tapps_mcp.server_helpers import error_response, success_response

  if TYPE_CHECKING:
      from mcp.server.fastmcp import FastMCP

  from mcp.types import ToolAnnotations

  _ANNOTATIONS_EXPERT_MGMT = ToolAnnotations(
      readOnlyHint=False,
      destructiveHint=False,
      idempotentHint=False,
      openWorldHint=False,
  )

  _VALID_ACTIONS = {"list", "add", "remove", "scaffold", "validate"}


  async def tapps_manage_experts(
      action: str,
      expert_id: str = "",
      expert_name: str = "",
      primary_domain: str = "",
      description: str = "",
      keywords: str = "",  # comma-separated
      rag_enabled: bool = True,
      knowledge_dir: str = "",
  ) -> dict[str, Any]:
      """Manage user-defined business experts for project-specific domain guidance.

      Actions:
          list: Show all configured business experts and their knowledge status.
          add: Add a new business expert to .tapps-mcp/experts.yaml.
          remove: Remove a business expert by expert_id.
          scaffold: Create knowledge directory with starter template for an expert.
          validate: Check all business expert configs and knowledge directories.

      Args:
          action: One of "list", "add", "remove", "scaffold", "validate".
          expert_id: Expert identifier (required for add, remove, scaffold).
              Must start with "expert-" (e.g., "expert-home-assistant").
          expert_name: Human-readable name (required for add).
          primary_domain: Domain slug (required for add, e.g., "home-automation").
          description: Short description (optional, for add).
          keywords: Comma-separated detection keywords (optional, for add).
          rag_enabled: Enable RAG for this expert (default True, for add).
          knowledge_dir: Override knowledge directory name (optional, for add).
      """
      ...


  def register(mcp_instance: FastMCP) -> None:
      mcp_instance.tool(annotations=_ANNOTATIONS_EXPERT_MGMT)(tapps_manage_experts)
  ```
- Implement the 5 action handlers:
  - `_handle_list(project_root)`: Load from YAML, validate knowledge dirs, return structured result with expert details and knowledge file counts
  - `_handle_add(project_root, ...)`: Validate params, read existing YAML (or create new), check for ID collisions (both within YAML and against built-in experts), append entry, write atomically, optionally scaffold knowledge directory
  - `_handle_remove(project_root, expert_id)`: Read YAML, remove entry by `expert_id`, write atomically. Error if expert_id not found.
  - `_handle_scaffold(project_root, expert_id)`: Look up expert in YAML, create knowledge directory with README.md and starter overview.md using templates from `business_templates.py`
  - `_handle_validate(project_root)`: Run `validate_business_knowledge()`, return structured result with valid/missing/empty/warnings
- Implement atomic YAML write helper:
  ```python
  def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
      """Write YAML atomically via temp file + rename."""
      ...
  ```
- Register the tool in `server.py` imports (add `import tapps_mcp.server_expert_tools`)
- Add `tapps_manage_experts` to `_FALLBACK_TOOL_LIST` in `server.py`
- Add `_record_call("tapps_manage_experts")` at the top of the handler
- Register in checklist task map (`tools/checklist.py`)
- Create `packages/tapps-mcp/tests/unit/test_server_expert_tools.py`:
  - Test: list action with no config returns empty list
  - Test: list action with config returns experts with knowledge status
  - Test: add action creates new `experts.yaml` when none exists
  - Test: add action appends to existing `experts.yaml`
  - Test: add action rejects duplicate `expert_id`
  - Test: add action rejects `expert_id` colliding with built-in expert
  - Test: add action rejects missing required fields (`expert_name`, `primary_domain`)
  - Test: remove action removes expert from YAML
  - Test: remove action handles non-existent `expert_id` gracefully
  - Test: scaffold action creates directory and README
  - Test: scaffold action is idempotent (re-run safe)
  - Test: validate action reports missing knowledge dirs
  - Test: validate action reports valid setup
  - Test: invalid action rejected with clear error message
  - Test: atomic YAML write survives interrupted write (temp file cleanup)

**Definition of Done:** `tapps_manage_experts` works for all 5 actions. Atomic YAML writes. Path security enforced. Registered in server imports and checklist. ~18 new tests.

---

### 45.2 -- tapps_init Business Expert Integration

**Points:** 5

Integrate business expert status reporting and optional scaffolding into the `tapps_init` pipeline, so that project initialization includes business expert setup when configured.

**Tasks:**
- Modify `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`:
  - In `bootstrap_pipeline()` (or the appropriate sub-function), after main initialization:
    - Check if `.tapps-mcp/experts.yaml` exists
    - If exists, call `load_and_register_business_experts(project_root)` and include result in init response
    - Report: number of business experts loaded, knowledge directory status, any warnings
  - Add `scaffold_experts: bool = False` to `BootstrapConfig`:
    - When True and `experts.yaml` exists, scaffold knowledge directories for any expert missing one
    - Uses `scaffold_knowledge_directory()` from `business_knowledge.py`
- Modify `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`:
  - Add `scaffold_experts: bool = False` parameter to `tapps_init` MCP tool
  - Pass through to `BootstrapConfig`
  - Update docstring to mention business expert scaffolding
- Add to AGENTS.md templates and tool docstring that `tapps_init` reports business expert status
- Create `packages/tapps-mcp/tests/unit/test_init_business_experts.py`:
  - Test: `tapps_init` without `experts.yaml` has no business expert section in response
  - Test: `tapps_init` with valid `experts.yaml` reports loaded count and expert names
  - Test: `tapps_init` with `scaffold_experts=True` creates missing knowledge dirs
  - Test: `tapps_init` with invalid `experts.yaml` reports errors gracefully (does not fail init)
  - Test: `dry_run=True` does not create directories or modify files

**Definition of Done:** `tapps_init` detects and reports business expert configuration. Optional scaffolding works. No change to init behavior when no `experts.yaml` exists. ~8 new tests.

---

### 45.3 -- Knowledge File Starter Templates

**Points:** 3

Create meaningful starter knowledge file templates that are generated when scaffolding a business expert. These templates guide users (and the LLM) on what knowledge to add and in what format.

**Tasks:**
- Create `packages/tapps-core/src/tapps_core/experts/business_templates.py`:
  ```python
  """Starter templates for business expert knowledge directories.

  Generated when scaffolding a new business expert's knowledge directory.
  """
  from __future__ import annotations


  def generate_readme_template(
      expert_name: str,
      primary_domain: str,
      description: str,
  ) -> str:
      """Generate a README.md for the knowledge directory."""
      return f"""# {expert_name} Knowledge Base

  Domain: `{primary_domain}`
  {description}

  ## Adding Knowledge

  Place markdown (.md) files in this directory. Each file should contain
  domain-specific knowledge that the expert can reference when answering
  questions.

  ### File Format

  Files should be plain markdown with descriptive filenames. Optionally
  include YAML frontmatter:

  ```yaml
  ---
  title: Topic Title
  tags: [tag1, tag2]
  ---
  ```

  ### Best Practices

  - One topic per file (e.g., `mqtt-configuration.md`, `entity-naming.md`)
  - Use headers (##, ###) to structure content for better RAG chunking
  - Include code examples where relevant
  - Keep files under 50KB for optimal RAG retrieval
  - Use descriptive filenames (they appear in source citations)
  """


  def generate_starter_knowledge(
      expert_name: str,
      primary_domain: str,
      description: str,
  ) -> str:
      """Generate a starter knowledge file with domain overview."""
      ...
  ```
- Implement `generate_starter_knowledge()`:
  - Generates `overview.md` with domain description, common topics placeholder, and example Q&A format
  - Includes a "Getting Started" section suggesting what knowledge to add first
- Modify `packages/tapps-core/src/tapps_core/experts/business_knowledge.py`:
  - Update `scaffold_knowledge_directory()` to use these templates
  - Write both `README.md` and `overview.md` during scaffold
- Create `packages/tapps-core/tests/unit/test_business_templates.py`:
  - Test: README template includes expert name and domain
  - Test: starter knowledge includes description
  - Test: templates are valid markdown (no broken headers or unclosed code blocks)
  - Test: templates handle special characters in names (quotes, ampersands)

**Definition of Done:** Scaffolded knowledge directories include helpful README and starter knowledge file. Templates are customized per expert. ~5 new tests.

---

### 45.4 -- AGENTS.md and Documentation Updates

**Points:** 3

Update all documentation artifacts to reflect the business expert system: AGENTS.md templates, README.md tool reference, and platform rules.

**Tasks:**
- Modify `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_high.md`:
  - Add `tapps_manage_experts` to the tool reference section with action descriptions
  - Add "Business Experts" section explaining the capability and workflow
  - Update `tapps_consult_expert` description to mention business expert support
  - Update `tapps_list_experts` description to mention business experts
- Modify `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_medium.md`:
  - Same updates as high template (adjusted for medium engagement tone)
- Modify `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_low.md`:
  - Same updates as low template (adjusted for low engagement tone)
- Update platform rules templates (`platform_claude_*.md`, `platform_cursor_*.md`) if they reference expert domain lists
- Update `README.md` tool count (from 28 to 29) and add `tapps_manage_experts` to tool reference table
- Add a knowledge file `packages/tapps-core/src/tapps_core/experts/knowledge/development-workflow/business-experts.md` documenting the feature for the development-workflow expert domain
- Update `CLAUDE.md` module map to include new files (`business_config.py`, `business_knowledge.py`, `business_loader.py`, `business_templates.py`, `server_expert_tools.py`)
- Add `mcp__tapps-mcp__tapps_manage_experts` to `.claude/settings.json` auto-approval patterns in `tapps_init` generation

**Definition of Done:** All documentation artifacts reflect business experts. AGENTS.md includes the new tool and explains the feature. Tool count is accurate. ~4 new tests (template content validation).

---

## Summary

| Story | Points | New Files | Modified Files | Est. Tests |
|-------|--------|-----------|----------------|------------|
| 45.1 | 8 | 2 (server_expert_tools.py, test) | 2 (server.py, checklist.py) | ~18 |
| 45.2 | 5 | 1 (test) | 2 (init.py, server_pipeline_tools.py) | ~8 |
| 45.3 | 3 | 2 (business_templates.py, test) | 1 (business_knowledge.py) | ~5 |
| 45.4 | 3 | 1 (knowledge .md) | 8+ (templates, README, CLAUDE.md, settings) | ~4 |
| **Total** | **19** | **6** | **13+** | **~35** |

## Cross-References

- **Epic 43** ([EPIC-43-BUSINESS-EXPERT-FOUNDATION.md](EPIC-43-BUSINESS-EXPERT-FOUNDATION.md)): Provides config loading, registry, and knowledge validation used by the management tool
- **Epic 44** ([EPIC-44-BUSINESS-EXPERT-CONSULTATION.md](EPIC-44-BUSINESS-EXPERT-CONSULTATION.md)): Provides consultation routing that makes managed experts actually usable
- **Epic 23** ([EPIC-23-SHARED-MEMORY-FOUNDATION.md](EPIC-23-SHARED-MEMORY-FOUNDATION.md)): `tapps_memory` action-based tool pattern used as reference for `tapps_manage_experts`
- **Epic 33** ([EPIC-33-PLATFORM-ARTIFACT-CORRECTNESS.md](EPIC-33-PLATFORM-ARTIFACT-CORRECTNESS.md)): Platform artifact generation patterns for AGENTS.md and settings updates

---

## Cross-Epic Architecture Summary

```
                       .tapps-mcp/experts.yaml
                              |
                              v
                    BusinessExpertsConfig (Pydantic)
                              |
                    load_business_experts()           [Epic 43]
                              |
                              v
                    ExpertRegistry
                    +---------------------------+
                    | BUILTIN_EXPERTS (17, immutable) |
                    | _business_experts (0-20, runtime) |
                    +---------------------------+
                              |
             +----------------+----------------+
             |                                 |
   DomainDetector                      engine.py
   .detect_from_question_merged()      .consult_expert()      [Epic 44]
             |                                 |
   Scores question against             _resolve_domain() uses merged registry
   DOMAIN_KEYWORDS + business keywords  _retrieve_knowledge() checks is_builtin
             |                                 |
             v                                 v
   Ranked DomainMapping list           VectorKnowledgeBase
                                       (bundled OR .tapps-mcp/knowledge/)
                                               |
                                               v
                                       ConsultationResult
                                       (with is_builtin flag)

   tapps_manage_experts                                        [Epic 45]
   +-- list: show experts + knowledge status
   +-- add: append to experts.yaml + scaffold
   +-- remove: remove from experts.yaml
   +-- scaffold: create knowledge dir + templates
   +-- validate: check configs + knowledge dirs
```

**Dependency chain:** Epic 43 (Foundation) --> Epic 44 (Consultation) --> Epic 45 (Lifecycle)

**Total estimated effort across all 3 epics:** ~6 weeks (1 developer)
- Epic 43: ~2 weeks, 19 points, ~56 tests
- Epic 44: ~2-2.5 weeks, 24 points, ~50 tests
- Epic 45: ~1.5 weeks, 19 points, ~35 tests
- **Grand total:** 62 points, ~141 new tests

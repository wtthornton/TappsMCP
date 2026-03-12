# Epic 43: Business Expert Foundation

- **Status:** Complete
- **Priority:** P1 - High Value (unlocks project-specific domain guidance)
- **Estimated LOE:** ~2 weeks (1 developer)
- **Dependencies:** None (builds on top of existing Epic 3 expert system)
- **Blocks:** Epic 44 (Business Expert Consultation and Integration), Epic 45 (Business Expert Lifecycle Management)

---

## Goal

Establish the data model, configuration loading, and registry extension layer that allows users to define custom "business experts" via YAML configuration files stored in `.tapps-mcp/experts.yaml`, with knowledge files stored in `.tapps-mcp/knowledge/<domain>/*.md`. Business experts are a separate layer on top of the immutable 17 built-in technical experts. This epic creates the foundation: the config schema, YAML loader, merged registry, and knowledge directory structure -- but does not yet wire them into the consultation engine or MCP tools.

## Motivation

TappsMCP currently has 17 hardcoded technical-domain experts (security, testing, architecture, etc.). The original TappsCodingAgents supported a two-layer system where customers could add business-domain experts (e.g., "Home Assistant Expert", "Lease Manager Expert", "CFO Expert") to get project-specific guidance. This capability was intentionally dropped during extraction to keep the initial scope manageable. Restoring it -- adapted for the MCP architecture -- allows teams to get domain-specific guidance for their unique business context without modifying TappsMCP source code.

### User Stories Driving This Epic

1. **First-Time Setup:** User prompts LLM: "I'm building a Home Assistant integration project. Add a Home Assistant expert and a Home Automation expert." The LLM creates `experts.yaml`, scaffolds knowledge dirs, and generates starter knowledge files.
2. **Adding to Existing Setup:** User prompts: "Add a Lease Manager expert to my business experts." The LLM appends to `experts.yaml` and creates the knowledge directory.

## Design Decisions

1. **Simplified routing model.** The original TappsCodingAgents used a "51% primary authority" weight distribution model. For MCP, where each consultation returns a single expert's answer, we simplify to: business domains route to business experts, technical domains route to built-in experts. When a query matches both, the explicit `domain` parameter disambiguates; auto-detection prefers business experts for business-tagged keywords and built-in experts for technical keywords. No weight distribution needed.

2. **Config location.** Business expert configuration lives at `{project_root}/.tapps-mcp/experts.yaml`. This follows the existing convention where all TappsMCP project-local data is under `.tapps-mcp/` (memory at `.tapps-mcp/memory/`, RAG indices at `.tapps-mcp/rag_index/`, learning at `.tapps-mcp/learning/`).

3. **Knowledge path.** Business expert knowledge files live at `{project_root}/.tapps-mcp/knowledge/<domain>/*.md`. This parallels the built-in expert knowledge at `packages/tapps-core/src/tapps_core/experts/knowledge/<domain>/`.

4. **ExpertConfig model reuse.** The existing `ExpertConfig` model in `tapps_core/experts/models.py` already has all needed fields (expert_id, expert_name, primary_domain, description, rag_enabled, knowledge_dir). We add an `is_builtin` field (default `True`) to distinguish layers, and a `keywords` field for custom domain detection routing.

5. **Package placement.** The business expert loader and config schema go in `tapps-core` (since `engine.py` is in `tapps-core` and needs to access both expert types). The MCP tool additions go in `tapps-mcp`.

## 2026 Best Practices Applied

- **Pydantic v2** for all config validation with `ConfigDict(extra="forbid")`
- **Path security** via `PathValidator` for all file I/O
- **Graceful degradation** when `experts.yaml` is missing (empty list, not error)
- **structlog** for all logging (no print statements)
- **Type annotations** everywhere for `mypy --strict`

## Acceptance Criteria

- [ ] `BusinessExpertEntry` Pydantic model validates YAML expert definitions with required fields (`expert_id`, `expert_name`, `primary_domain`) and optional fields (`description`, `keywords`, `rag_enabled`, `knowledge_dir`)
- [ ] `load_business_experts()` reads `.tapps-mcp/experts.yaml` and returns validated `ExpertConfig` instances with `is_builtin=False`
- [ ] `ExpertConfig` model gains `is_builtin: bool = True` and `keywords: list[str] = []` fields (backward-compatible defaults)
- [ ] `ExpertRegistry` gains methods to merge business experts: `get_all_experts_merged()`, `get_expert_for_domain_merged()`, `get_business_domains()`, `register_business_experts()`
- [ ] Built-in experts remain immutable -- `BUILTIN_EXPERTS` list is never modified
- [ ] Business expert IDs must not collide with built-in expert IDs (validation error on collision)
- [ ] Knowledge directory validation: warn (do not error) when a business expert's knowledge directory is empty or missing
- [ ] YAML schema supports 1-20 business experts (hard cap to prevent abuse)
- [ ] Invalid YAML produces structured error with field-level details, not a crash
- [ ] Unit tests: ~56 tests covering model validation, YAML loading, registry merging, collision detection, edge cases
- [ ] All new Python files pass quality gate (standard preset, score >= 70)

---

## Stories

### 43.1 -- Extend ExpertConfig Model

**Points:** 3

Add `is_builtin` and `keywords` fields to the existing `ExpertConfig` Pydantic model in `tapps_core`. These fields allow distinguishing built-in vs. business experts and powering custom domain detection keywords.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/models.py`:
  - Add `is_builtin: bool = Field(default=True, description="Whether this is a built-in technical expert.")` to `ExpertConfig`
  - Add `keywords: list[str] = Field(default_factory=list, description="Custom keywords for domain detection routing.")` to `ExpertConfig`
  - Keep `model_config = ConfigDict(extra="forbid")` -- these new fields have defaults, so all existing instantiations remain valid
- Modify `packages/tapps-core/src/tapps_core/experts/models.py`:
  - Add `is_builtin: bool = Field(default=True, description="Whether this is a built-in expert.")` to `ExpertInfo`
  - Add `keywords: list[str] = Field(default_factory=list, description="Custom domain detection keywords.")` to `ExpertInfo`
- Verify that all 17 existing `BUILTIN_EXPERTS` entries in `registry.py` still instantiate correctly (they use default `is_builtin=True`)
- Update existing tests in `packages/tapps-core/tests/unit/test_expert_models.py` to assert the new fields default correctly

**Definition of Done:** `ExpertConfig(expert_id="x", expert_name="X", primary_domain="y")` still works unchanged. `ExpertConfig(..., is_builtin=False, keywords=["home automation"])` also works. `ExpertInfo` includes the new fields. All existing tests pass. ~8 new tests.

---

### 43.2 -- Business Expert YAML Schema and Loader

**Points:** 5

Create the YAML configuration schema for business experts and the loader function that reads `.tapps-mcp/experts.yaml`, validates entries, and returns `ExpertConfig` instances.

**Tasks:**
- Create `packages/tapps-core/src/tapps_core/experts/business_config.py`:
  ```python
  """Business expert YAML configuration loader.

  Reads user-defined business experts from
  ``{project_root}/.tapps-mcp/experts.yaml``.
  """
  from __future__ import annotations

  from pathlib import Path
  from typing import Any

  import structlog
  import yaml
  from pydantic import BaseModel, ConfigDict, Field, field_validator

  from tapps_core.experts.models import ExpertConfig

  logger = structlog.get_logger(__name__)

  _MAX_BUSINESS_EXPERTS = 20
  _MAX_KEYWORDS_PER_EXPERT = 50


  class BusinessExpertEntry(BaseModel):
      """Schema for a single expert entry in experts.yaml."""
      model_config = ConfigDict(extra="forbid")

      expert_id: str = Field(description="Unique ID (e.g., 'expert-home-assistant').")
      expert_name: str = Field(description="Human-readable name.")
      primary_domain: str = Field(description="Domain slug (e.g., 'home-automation').")
      description: str = Field(default="", description="Short description.")
      keywords: list[str] = Field(default_factory=list, description="Detection keywords.")
      rag_enabled: bool = Field(default=True, description="Enable RAG for this expert.")
      knowledge_dir: str | None = Field(default=None, description="Override knowledge dir name.")

      @field_validator("expert_id")
      @classmethod
      def validate_expert_id(cls, v: str) -> str:
          if not v.startswith("expert-"):
              msg = "expert_id must start with 'expert-'"
              raise ValueError(msg)
          return v


  class BusinessExpertsConfig(BaseModel):
      """Root schema for .tapps-mcp/experts.yaml."""
      model_config = ConfigDict(extra="forbid")
      experts: list[BusinessExpertEntry] = Field(default_factory=list)


  def load_business_experts(project_root: Path) -> list[ExpertConfig]:
      """Load business experts from .tapps-mcp/experts.yaml."""
      ...
  ```
- Implement `load_business_experts()`:
  - Read `{project_root}/.tapps-mcp/experts.yaml`
  - Return empty list if file does not exist (graceful degradation)
  - Parse via `yaml.safe_load()` into `BusinessExpertsConfig` Pydantic model
  - Convert each `BusinessExpertEntry` to `ExpertConfig(is_builtin=False, ...)`
  - Enforce `_MAX_BUSINESS_EXPERTS` cap
  - Log structured warnings for empty/missing knowledge directories
  - Pass all file paths through `tapps_core.security.path_validator.PathValidator` to prevent directory traversal
- Create `packages/tapps-core/tests/unit/test_business_config.py`:
  - Test: valid YAML with 1, 3, 20 experts
  - Test: missing file returns empty list
  - Test: invalid YAML raises structured error
  - Test: expert_id not starting with "expert-" raises ValueError
  - Test: duplicate expert_ids in YAML raises validation error
  - Test: exceeding `_MAX_BUSINESS_EXPERTS` raises error
  - Test: extra fields rejected (`extra="forbid"`)
  - Test: empty experts list is valid
  - Test: keywords list validation

**Definition of Done:** `load_business_experts(project_root)` returns validated `ExpertConfig` list from YAML. Graceful degradation when file is missing. Field-level validation errors. ~18 new tests.

---

### 43.3 -- Extend ExpertRegistry with Merged Access

**Points:** 5

Extend `ExpertRegistry` to support a merged view of built-in + business experts. The class remains the single source of truth for expert lookups. Built-in experts are immutable class attributes; business experts are loaded at runtime and cached per project root.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/experts/registry.py`:
  - Add class-level storage for business experts:
    ```python
    # Business experts (loaded at runtime from .tapps-mcp/experts.yaml)
    _business_experts: ClassVar[list[ExpertConfig]] = []
    _business_domains: ClassVar[set[str]] = set()
    ```
  - Add `register_business_experts(cls, experts: list[ExpertConfig]) -> None`:
    - Validate no ID collision with `BUILTIN_EXPERTS`
    - Validate no duplicate IDs within business experts
    - Store in `_business_experts`
    - Build `_business_domains` set
  - Add `clear_business_experts(cls) -> None` (for testing and re-loading)
  - Add `get_all_experts_merged(cls) -> list[ExpertConfig]`:
    - Returns `list(BUILTIN_EXPERTS) + list(_business_experts)`
  - Add `get_expert_for_domain_merged(cls, domain: str) -> ExpertConfig | None`:
    - Check built-in first, then business (built-in wins on collision -- but collision should be prevented at registration)
  - Add `get_business_experts(cls) -> list[ExpertConfig]`
  - Add `get_business_domains(cls) -> set[str]`
  - Add `is_business_domain(cls, domain: str) -> bool`
  - Keep existing methods unchanged (they only query `BUILTIN_EXPERTS`)
- Modify `packages/tapps-core/tests/unit/test_expert_registry.py`:
  - Add tests for `register_business_experts` (valid case)
  - Add test for ID collision detection (raises ValueError)
  - Add test for `get_all_experts_merged` includes both layers
  - Add test for `get_expert_for_domain_merged` prefers built-in
  - Add test for `get_business_domains` returns only business domains
  - Add test for `is_business_domain` returns True for registered, False for built-in
  - Add test for `clear_business_experts` resets state
  - Add autouse fixture to reset business experts after each test
- Add `ExpertRegistry.clear_business_experts()` call to `packages/tapps-core/tests/conftest.py` autouse fixture

**Definition of Done:** `ExpertRegistry` can hold business experts alongside built-in ones. All existing tests still pass (no behavioral change for built-in-only queries). Business experts are queryable. ID collisions are rejected. ~12 new tests.

---

### 43.4 -- Business Expert Knowledge Directory Validation

**Points:** 3

Add validation and scaffolding helpers for business expert knowledge directories. When business experts are loaded, check that their knowledge directory exists under `.tapps-mcp/knowledge/<domain>/` and contains at least one `.md` file. Provide a helper to scaffold empty knowledge directories with a README template.

**Tasks:**
- Create `packages/tapps-core/src/tapps_core/experts/business_knowledge.py`:
  ```python
  """Business expert knowledge directory utilities.

  Validates and scaffolds knowledge directories for user-defined
  business experts under {project_root}/.tapps-mcp/knowledge/.
  """
  from __future__ import annotations
  from dataclasses import dataclass, field
  from pathlib import Path

  import structlog
  from tapps_core.experts.domain_utils import sanitize_domain_for_path
  from tapps_core.experts.models import ExpertConfig

  logger = structlog.get_logger(__name__)


  @dataclass
  class KnowledgeValidationResult:
      """Result of validating knowledge directories for business experts."""
      valid: list[str] = field(default_factory=list)
      missing: list[str] = field(default_factory=list)
      empty: list[str] = field(default_factory=list)
      warnings: list[str] = field(default_factory=list)


  def validate_business_knowledge(
      project_root: Path,
      experts: list[ExpertConfig],
  ) -> KnowledgeValidationResult:
      """Check that each business expert has a knowledge directory with .md files."""
      ...


  def get_business_knowledge_path(
      project_root: Path,
      expert: ExpertConfig,
  ) -> Path:
      """Return the knowledge directory path for a business expert."""
      dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
      return project_root / ".tapps-mcp" / "knowledge" / dir_name


  def scaffold_knowledge_directory(
      project_root: Path,
      expert: ExpertConfig,
  ) -> Path:
      """Create an empty knowledge directory with a README template."""
      ...
  ```
- Implement `validate_business_knowledge()`:
  - For each expert, check `get_business_knowledge_path()` exists and contains `.md` files
  - Populate `KnowledgeValidationResult` with valid/missing/empty/warnings
  - Do not raise on missing directories (warn only)
- Implement `scaffold_knowledge_directory()`:
  - Create the directory if it does not exist
  - Write a README.md template explaining the knowledge file format
  - Path-validate all writes via `PathValidator`
- Create `packages/tapps-core/tests/unit/test_business_knowledge.py`:
  - Test: valid directory with .md files
  - Test: missing directory
  - Test: empty directory (no .md files)
  - Test: scaffold creates directory and README
  - Test: knowledge_dir override respected
  - Test: domain slug sanitization
  - Test: path traversal attempt rejected

**Definition of Done:** Knowledge directories for business experts are validated with structured results. Scaffolding creates starter structure. Path security enforced. ~10 new tests.

---

### 43.5 -- Settings Integration and Auto-Loading

**Points:** 3

Wire business expert loading into the TappsMCP settings and session start flow. Business experts should be automatically loaded from `.tapps-mcp/experts.yaml` when `tapps_session_start` runs, and registered with the `ExpertRegistry`.

**Tasks:**
- Modify `packages/tapps-core/src/tapps_core/config/settings.py`:
  - Add `business_experts_enabled: bool = Field(default=True, description="Enable loading business experts from .tapps-mcp/experts.yaml.")` to `TappsMCPSettings`
  - Add `business_experts_max: int = Field(default=20, ge=0, le=50, description="Maximum number of business experts to load.")` to `TappsMCPSettings`
- Create `packages/tapps-core/src/tapps_core/experts/business_loader.py`:
  ```python
  """Business expert auto-loading integration.

  Called during session start to load and register business experts.
  """
  from __future__ import annotations
  from dataclasses import dataclass, field
  from pathlib import Path

  import structlog

  logger = structlog.get_logger(__name__)


  @dataclass
  class BusinessExpertLoadResult:
      """Result of loading business experts."""
      loaded: int = 0
      errors: list[str] = field(default_factory=list)
      warnings: list[str] = field(default_factory=list)
      expert_ids: list[str] = field(default_factory=list)
      knowledge_status: dict[str, str] = field(default_factory=dict)


  def load_and_register_business_experts(project_root: Path) -> BusinessExpertLoadResult:
      """Load business experts from YAML and register them."""
      ...
  ```
- Implement `load_and_register_business_experts()`:
  - Check `settings.business_experts_enabled`
  - Call `load_business_experts(project_root)` from `business_config.py`
  - Call `ExpertRegistry.register_business_experts(experts)`
  - Call `validate_business_knowledge(project_root, experts)`
  - Return structured result with load status and knowledge validation
- Add call to `load_and_register_business_experts` in `tapps_session_start` (in `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py`)
  - After existing initialization, before returning
  - Include result summary in session start response
- Modify `packages/tapps-core/tests/conftest.py` to reset business experts in autouse fixture
- Modify `packages/tapps-mcp/tests/conftest.py` to reset business experts in autouse fixture
- Create `packages/tapps-core/tests/unit/test_business_loader.py`:
  - Test: loading from valid YAML registers experts
  - Test: missing YAML returns empty result (graceful)
  - Test: disabled via settings returns empty result
  - Test: knowledge validation results included
  - Test: ID collision error reported in result.errors

**Definition of Done:** Business experts automatically load and register during `tapps_session_start`. Settings control enable/disable and max count. Graceful degradation when no config file exists. ~8 new tests.

---

## Summary

| Story | Points | New Files | Modified Files | Est. Tests |
|-------|--------|-----------|----------------|------------|
| 43.1 | 3 | 0 | 2 (models.py, ExpertInfo) | ~8 |
| 43.2 | 5 | 2 (business_config.py, test) | 0 | ~18 |
| 43.3 | 5 | 0 | 2 (registry.py, test) + conftest | ~12 |
| 43.4 | 3 | 2 (business_knowledge.py, test) | 0 | ~10 |
| 43.5 | 3 | 2 (business_loader.py, test) | 3 (settings, conftest, pipeline_tools) | ~8 |
| **Total** | **19** | **6** | **7** | **~56** |

## Cross-References

- **Epic 3** ([EPIC-3-EXPERT-SYSTEM.md](EPIC-3-EXPERT-SYSTEM.md)): Original expert system extraction -- this epic extends it
- **Epic 35** ([EPIC-35-EXPERT-ADAPTIVE-INTEGRATION.md](EPIC-35-EXPERT-ADAPTIVE-INTEGRATION.md)): Adaptive domain detection -- must work with business experts (Epic 44)
- **Epic 44** ([EPIC-44-BUSINESS-EXPERT-CONSULTATION.md](EPIC-44-BUSINESS-EXPERT-CONSULTATION.md)): Wires business experts into consultation pipeline
- **Epic 45** ([EPIC-45-BUSINESS-EXPERT-LIFECYCLE.md](EPIC-45-BUSINESS-EXPERT-LIFECYCLE.md)): MCP tool for managing business experts

## Storage Layout

```
{project_root}/
  .tapps-mcp/
    experts.yaml                    # Business expert configuration
    knowledge/                      # Business expert knowledge base
      home-assistant/
        README.md                   # Scaffolded template
        integrations.md             # User-added knowledge
        automation-patterns.md
      lease-management/
        README.md
        lease-lifecycle.md
      financial-operations/
        README.md
```

## Example experts.yaml

```yaml
experts:
  - expert_id: expert-home-assistant
    expert_name: Home Assistant Expert
    primary_domain: home-assistant
    description: "Expert in Home Assistant integrations, automations, and device management."
    keywords: ["hass", "home assistant", "automation", "zigbee", "z-wave", "esphome", "blueprint"]
    rag_enabled: true

  - expert_id: expert-lease-manager
    expert_name: Lease Manager Expert
    primary_domain: lease-management
    description: "Expert in lease lifecycle, tenant onboarding, rent calculations, and compliance."
    keywords: ["lease", "tenant", "rent", "property", "landlord", "renewal"]
    rag_enabled: true

  - expert_id: expert-cfo
    expert_name: CFO / Financial Expert
    primary_domain: financial-operations
    description: "Expert in budgeting, forecasting, revenue analysis, and financial reporting."
    keywords: ["budget", "forecast", "revenue", "expense", "p&l", "cash flow", "financial"]
    rag_enabled: true
```

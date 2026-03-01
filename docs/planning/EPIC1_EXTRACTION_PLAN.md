# Epic 1: Tier 1 Extraction Plan

Based on extractor research. All source at `packages/tapps-mcp/src/tapps_mcp/`.

## Circular Dependency Resolutions (Story 1.1)

### Resolution 1: common/nudges.py → experts.models.LOW_CONFIDENCE_THRESHOLD
- **Source**: `experts/models.py:48` defines `LOW_CONFIDENCE_THRESHOLD = 0.5`
- **Consumer**: `common/nudges.py:15` imports it, uses at line 120 in lambda
- **Fix**: Create `common/constants.py`, move `LOW_CONFIDENCE_THRESHOLD = 0.5` there
- **Also move**: `HIGH_CONFIDENCE_THRESHOLD = 0.7` from experts/models.py
- **Update imports in**: `common/nudges.py`, `experts/models.py`, `experts/engine.py`

### Resolution 2: common/nudges.py → pipeline.models.{PipelineStage, STAGE_ORDER, STAGE_TOOLS}
- **Source**: `pipeline/models.py:11-49` defines PipelineStage (StrEnum), STAGE_ORDER, STAGE_TOOLS
- **Consumer**: `common/nudges.py:16` imports all three, uses at lines 42, 319-328
- **Fix**: Create `common/pipeline_models.py`, move PipelineStage, STAGE_ORDER, STAGE_TOOLS there
- **Update imports in**: `common/nudges.py` (use common/pipeline_models)
- **Add re-exports in**: `pipeline/models.py` (re-export from common/pipeline_models)
- **No change needed**: `pipeline/handoff.py`, `server.py` (they import from pipeline.models which re-exports)

### Resolution 3: security/security_scanner.py → scoring.models.SecurityIssue
- **Source**: `scoring/models.py:41-51` defines SecurityIssue (Pydantic BaseModel)
- **Consumer**: `security/security_scanner.py:8` imports it (runtime, Pydantic field)
- **Fix**: Move SecurityIssue to `common/models.py`
- **Add re-exports in**: `scoring/models.py` (re-export from common/models)
- **No change needed**: `tools/bandit.py`, `tools/parallel.py` (import from scoring.models)
- **IMPORTANT**: `security/security_scanner.py` ALSO imports `tools.bandit` — it must STAY in tapps-mcp, not move to tapps-core

### Resolution 4: memory/{store,injection}.py → knowledge/rag_safety.py
- **Source**: `knowledge/rag_safety.py` defines check_content_safety(), SafetyCheckResult, _sanitise_content(), _INJECTION_PATTERNS
- **Consumers**: `memory/store.py:14`, `memory/injection.py:14`
- **Fix**: Create `security/content_safety.py` with all rag_safety content
- **Update imports in**: `memory/store.py`, `memory/injection.py` (import from security.content_safety)
- **Add re-exports in**: `knowledge/rag_safety.py` (thin wrapper re-exporting from security.content_safety)
- **No change needed**: `knowledge/warming.py`, `knowledge/lookup.py` (import from knowledge.rag_safety)

## Extraction Stories (1.2-1.6)

### Story 1.2: Extract common/ to tapps-core
Copy `common/` to `packages/tapps-core/src/tapps_core/common/`.
Files to copy: `__init__.py`, `constants.py` (new), `pipeline_models.py` (new), `exceptions.py`, `logging.py`, `models.py` (with SecurityIssue added), `utils.py`
Files to KEEP in tapps-mcp: `nudges.py`, `output_schemas.py`, `elicitation.py` (MCP-specific)

### Story 1.3: Extract config/ to tapps-core
Copy `config/` to `packages/tapps-core/src/tapps_core/config/`.
Files: `__init__.py`, `settings.py`, `default.yaml`
No dependencies on other tapps_mcp packages — clean extraction.

### Story 1.4: Extract security/ (core parts) to tapps-core
Copy to `packages/tapps-core/src/tapps_core/security/`:
- `path_validator.py`, `io_guardrails.py`, `governance.py`, `api_keys.py`, `secret_scanner.py`
- `content_safety.py` (new, from resolution 4)
KEEP in tapps-mcp: `security_scanner.py` (depends on tools.bandit)

### Story 1.5: Already handled in resolution 4 (content_safety.py creation)

### Story 1.6: Extract prompts/ to tapps-core
Copy `prompt_loader.py` to `packages/tapps-core/src/tapps_core/prompts/`.
Parameterize the package name for `importlib.resources`.
Copy base template files shared across servers.

## Re-export Surface (Story 1.7)

tapps_mcp must re-export from tapps_core for backward compatibility:
- `tapps_mcp.common` → re-export exceptions, logging, models, utils from tapps_core.common
- `tapps_mcp.config` → re-export load_settings, TappsMCPSettings from tapps_core.config
- `tapps_mcp.security` → re-export PathValidator, check_content_safety etc from tapps_core.security
- `tapps_mcp.prompts` → re-export prompt_loader from tapps_core.prompts

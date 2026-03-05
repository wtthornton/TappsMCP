# Configuration Reference

TappsMCP is configured via `.tapps-mcp.yaml` in the project root. Settings can also be overridden with environment variables using the `TAPPS_MCP_` prefix.

**Precedence** (highest to lowest):

1. Environment variables (`TAPPS_MCP_*`)
2. Project-level `.tapps-mcp.yaml`
3. Built-in defaults

## CLI

```bash
# View effective configuration
tapps-mcp show-config

# View config for a specific project
tapps-mcp show-config --project-root /path/to/project
```

## All Fields

### Core Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `project_root` | path | current directory | Project root boundary. All file paths must be within this directory. |
| `host_project_root` | string or null | `null` | Optional host path the client uses for the same project (for Docker/Cursor mapping). |
| `quality_preset` | string | `"standard"` | Quality gate preset: `standard` (70+), `strict` (80+), or `framework` (75+). |
| `log_level` | string | `"INFO"` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `log_json` | bool | `false` | Output JSON-formatted logs. |

### API Keys

| Field | Type | Default | Description |
|---|---|---|---|
| `context7_api_key` | secret string | `null` | Context7 API key for documentation lookup and cache warming. |

### Scoring Weights

Nested under `scoring_weights`. Must sum to approximately 1.0.

| Field | Type | Default | Description |
|---|---|---|---|
| `complexity` | float | `0.18` | Weight for cyclomatic complexity scoring. |
| `security` | float | `0.27` | Weight for security scoring. |
| `maintainability` | float | `0.24` | Weight for maintainability scoring. |
| `test_coverage` | float | `0.13` | Weight for test coverage scoring. |
| `performance` | float | `0.08` | Weight for performance scoring. |
| `structure` | float | `0.05` | Weight for project structure scoring. |
| `devex` | float | `0.05` | Weight for developer experience scoring. |

### Quality Gate

Nested under `quality_gate`.

| Field | Type | Default | Description |
|---|---|---|---|
| `overall_min` | float | `70.0` | Minimum overall score to pass the quality gate. |
| `security_min` | float | `0.0` | Minimum security category score. |
| `maintainability_min` | float | `0.0` | Minimum maintainability category score. |

### Adaptive Learning

Nested under `adaptive`.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable adaptive weight adjustment based on feedback. |
| `learning_rate` | float | `0.1` | Learning rate for weight adjustment (0.0-1.0). |
| `min_outcomes` | int | `5` | Minimum outcome records before adaptive adjustment activates. |

### Tool Settings

| Field | Type | Default | Description |
|---|---|---|---|
| `tool_timeout` | int | `30` | Timeout for individual external tool invocations (seconds). Min: 5. |

### Dead Code Detection

| Field | Type | Default | Description |
|---|---|---|---|
| `dead_code_enabled` | bool | `true` | Enable dead code detection via vulture. |
| `dead_code_min_confidence` | int | `80` | Minimum confidence threshold (0-100). |
| `dead_code_whitelist_patterns` | list[string] | `["test_*", "conftest.py"]` | File patterns to exclude from dead code findings. |

### Dependency Scanning

| Field | Type | Default | Description |
|---|---|---|---|
| `dependency_scan_enabled` | bool | `true` | Enable dependency vulnerability scanning via pip-audit. |
| `dependency_scan_severity_threshold` | string | `"medium"` | Minimum severity: `critical`, `high`, `medium`, `low`, `unknown`. |
| `dependency_scan_ignore_ids` | list[string] | `[]` | Vulnerability IDs to exclude (e.g., `CVE-2024-12345`). |
| `dependency_scan_source` | string | `"auto"` | Scan source: `auto`, `environment`, `requirements`, `pyproject`. |

### LLM Engagement

| Field | Type | Default | Description |
|---|---|---|---|
| `llm_engagement_level` | string | `"medium"` | How intensely the LLM should use TappsMCP tools. `high` = mandatory enforcement, `medium` = balanced, `low` = optional guidance. |
| `destructive_guard` | bool | `false` | Generate a PreToolUse hook that blocks destructive Bash commands. |

### Business Experts

| Field | Type | Default | Description |
|---|---|---|---|
| `business_experts_enabled` | bool | `true` | Enable loading business experts from `.tapps-mcp/experts.yaml`. |
| `business_experts_max` | int | `20` | Maximum number of business experts to load (0-50). |

### Memory Subsystem

Nested under `memory`.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable the memory subsystem. |
| `gc_enabled` | bool | `true` | Enable garbage collection. |
| `contradiction_check_on_start` | bool | `true` | Run contradiction detection at session start. |
| `max_memories` | int | `500` | Maximum number of active memories per project. |
| `gc_auto_threshold` | float | `0.8` | Run GC at session start when usage exceeds this fraction of max_memories. |
| `inject_into_experts` | bool | `true` | Inject relevant memories into expert consultations. |

#### Memory Decay

Nested under `memory.decay`.

| Field | Type | Default | Description |
|---|---|---|---|
| `architectural_half_life_days` | int | `180` | Half-life for architectural memories (days). |
| `pattern_half_life_days` | int | `60` | Half-life for pattern memories (days). |
| `context_half_life_days` | int | `14` | Half-life for context memories (days). |
| `confidence_floor` | float | `0.1` | Minimum decayed confidence (0.0-1.0). |

### Knowledge Cache

| Field | Type | Default | Description |
|---|---|---|---|
| `cache_max_mb` | int | `100` | Maximum knowledge cache size in MB before LRU eviction. |

### Expert Fallback

| Field | Type | Default | Description |
|---|---|---|---|
| `expert_auto_fallback` | bool | `true` | Automatic Context7 lookup when expert RAG has no matches. |
| `expert_fallback_max_chars` | int | `1200` | Maximum characters merged from Context7 fallback content. |

### Docker Settings

Nested under `docker`.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable Docker MCP transport. |
| `transport` | string | `"auto"` | MCP transport mode: `auto`, `docker`, `exe`, or `uv`. |
| `profile` | string | `"tapps-standard"` | Docker MCP Toolkit profile name. |
| `image` | string | `"ghcr.io/tapps-mcp/tapps-mcp:latest"` | Docker image for TappsMCP. |
| `docs_image` | string | `"ghcr.io/tapps-mcp/docs-mcp:latest"` | Docker image for DocsMCP. |
| `companions` | list[string] | `["context7"]` | Companion MCP servers to recommend. |

## Example Configurations

### Minimal (defaults only)

```yaml
# .tapps-mcp.yaml
# Empty file - all defaults apply
# quality_preset: standard, engagement: medium
```

### Strict Quality Enforcement

```yaml
# .tapps-mcp.yaml
quality_preset: strict
llm_engagement_level: high

scoring_weights:
  security: 0.30
  maintainability: 0.25

quality_gate:
  overall_min: 80.0
  security_min: 8.0

tool_timeout: 45

memory:
  max_memories: 1000
  gc_auto_threshold: 0.7
```

### Non-Python / Lightweight Project

```yaml
# .tapps-mcp.yaml
quality_preset: standard
llm_engagement_level: low

dead_code_enabled: false
dependency_scan_enabled: false

adaptive:
  enabled: false

memory:
  enabled: false
```

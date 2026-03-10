# `packages.tapps-core.src.tapps_core`

Tapps Core: Shared infrastructure library for the Tapps platform.

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.adaptive`

Adaptive learning and intelligence subsystem.

Public API exports for the adaptive package.

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.adaptive.models`

Pydantic models for the adaptive learning subsystem.

## Classes

### `CodeOutcome`(BaseModel)

A single code-quality outcome record.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `workflow_id` | `str` | `Field(description='Unique workflow identifier.')` |
| `file_path` | `str` | `Field(description='Path to the scored file.')` |
| `initial_scores` | `dict[str, float]` | `Field(default_factory=dict, description='Scores from the first review pass (metric -> 0-10).')` |
| `final_scores` | `dict[str, float]` | `Field(default_factory=dict, description='Scores from the last review pass (metric -> 0-10).')` |
| `iterations` | `int` | `Field(default=1, ge=1, description='Number of review iterations.')` |
| `expert_consultations` | `list[str]` | `Field(default_factory=list, description='Expert IDs consulted during the workflow.')` |
| `time_to_correctness` | `float` | `Field(default=0.0, ge=0.0, description='Seconds to reach quality threshold.')` |
| `first_pass_success` | `bool` | `Field(default=False, description='Whether the code met the quality gate on the first pass.')` |
| `timestamp` | `str` | `Field(default_factory=_utc_now_iso, description='ISO-8601 UTC timestamp.')` |
| `agent_id` | `str | None` | `Field(default=None, description='Generating agent ID.')` |
| `prompt_hash` | `str | None` | `Field(default=None, description='SHA-256 hash of the original prompt.')` |

### `ExpertPerformance`(BaseModel)

Aggregated performance metrics for a single expert.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `expert_id` | `str` | `Field(description='Expert identifier.')` |
| `consultations` | `int` | `Field(default=0, ge=0, description='Total consultations.')` |
| `avg_confidence` | `float` | `Field(default=0.0, ge=0.0, le=1.0, description='Average confidence.')` |
| `first_pass_success_rate` | `float` | `Field(default=0.0, ge=0.0, le=1.0, description='Fraction of first-pass successes.')` |
| `code_quality_improvement` | `float` | `Field(default=0.0, description='Average quality improvement (final - initial score).')` |
| `domain_coverage` | `list[str]` | `Field(default_factory=list, description='Domains this expert has been consulted on.')` |
| `weaknesses` | `list[str]` | `Field(default_factory=list, description='Identified weakness areas.')` |
| `last_updated` | `str` | `Field(default_factory=_utc_now_iso, description='ISO-8601 UTC timestamp.')` |

### `ExpertWeightMatrix`(BaseModel)

Expert-to-domain voting weight matrix.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `weights` | `dict[str, dict[str, float]]` | `Field(default_factory=dict, description='Mapping of expert_id -> {domain -> weight}.')` |
| `domains` | `list[str]` | `Field(default_factory=list, description='All domains in the matrix.')` |
| `experts` | `list[str]` | `Field(default_factory=list, description='All expert IDs in the matrix.')` |

**Methods:**

#### `get_expert_weight`

```python
def get_expert_weight(self, expert_id: str, domain: str) -> float:
```

Return the weight for *expert_id* in *domain* (0.0 if absent).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |
| `domain` | `str` |  | *required* |

#### `get_primary_expert`

```python
def get_primary_expert(self, domain: str) -> str | None:
```

Return the primary expert for *domain* (weight >= 0.51), or ``None``.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` |  | *required* |

#### `get_primary_expert_domain`

```python
def get_primary_expert_domain(self, expert_id: str) -> str | None:
```

Return the domain where *expert_id* is primary, or ``None``.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |

#### `validate_matrix`

```python
def validate_matrix(self) -> list[str]:
```

Return a list of validation errors (empty if valid).

### `AdaptiveWeightsSnapshot`(BaseModel)

Persisted snapshot of adaptive scoring weights.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `weights` | `dict[str, float]` | `Field(description='Learned scoring weights.')` |
| `correlations` | `dict[str, float]` | `Field(default_factory=dict, description='Last computed metric correlations.')` |
| `outcomes_analyzed` | `int` | `Field(default=0, ge=0, description='Number of outcomes used.')` |
| `timestamp` | `str` | `Field(default_factory=_utc_now_iso, description='ISO-8601 UTC timestamp.')` |
| `learning_rate` | `float` | `Field(default=0.1, ge=0.0, le=1.0, description='Learning rate used.')` |

### `ExpertWeightsSnapshot`(BaseModel)

Persisted snapshot of expert voting weights.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `matrix` | `ExpertWeightMatrix` | `Field(description='The expert weight matrix.')` |
| `timestamp` | `str` | `Field(default_factory=_utc_now_iso, description='ISO-8601 UTC timestamp.')` |
| `performance_summary` | `dict[str, Any]` | `Field(default_factory=dict, description='Summary of expert performance at snapshot time.')` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.adaptive.persistence`

File-based implementations of the adaptive tracking protocols.

Provides JSONL-backed :class:[`FileOutcomeTracker`](#fileoutcometracker) and
:class:[`FilePerformanceTracker`](#fileperformancetracker) that satisfy the protocol interfaces
defined in :mod:`tapps_core.adaptive.protocols`.

## Classes

### `FileOutcomeTracker`

JSONL file-backed outcome tracker.

**Methods:**

#### `__init__`

```python
def __init__(self, project_root: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

#### `save_outcome`

```python
def save_outcome(self, outcome: CodeOutcome) -> None:
```

Append *outcome* as a JSONL record.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcome` | `CodeOutcome` |  | *required* |

#### `load_outcomes`

```python
def load_outcomes(self, limit: int | None = None, workflow_id: str | None = None) -> list[CodeOutcome]:
```

Load outcomes from disk, optionally filtered by *workflow_id*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `limit` | `int \| None` |  | None |
| `workflow_id` | `str \| None` |  | None |

#### `get_statistics`

```python
def get_statistics(self) -> dict[str, Any]:
```

Return aggregate statistics over stored outcomes.

### `FilePerformanceTracker`

JSONL file-backed expert performance tracker.

**Methods:**

#### `__init__`

```python
def __init__(self, project_root: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

#### `track_consultation`

```python
def track_consultation(self, expert_id: str, domain: str, confidence: float, query: str | None = None) -> None:
```

Append a consultation record.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |
| `domain` | `str` |  | *required* |
| `confidence` | `float` |  | *required* |
| `query` | `str \| None` |  | None |

#### `calculate_performance`

```python
def calculate_performance(self, expert_id: str, days: int = 30) -> ExpertPerformance | None:
```

Calculate aggregated performance for *expert_id* within *days*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |
| `days` | `int` |  | 30 |

#### `get_all_performance`

```python
def get_all_performance(self, days: int = 30) -> dict[str, ExpertPerformance]:
```

Calculate performance for every tracked expert.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `days` | `int` |  | 30 |

## Functions

### `save_json_atomic`

```python
def save_json_atomic(data: dict[str, Any] | list[Any], target: Path) -> None:
```

Write *data* to *target* atomically via a temporary file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `data` | `dict[str, Any] \| list[Any]` |  | *required* |
| `target` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 83.3%*


---

# `packages.tapps-core.src.tapps_core.adaptive.protocols`

Protocol interfaces for metrics tracking.

These protocols define the contracts consumed by adaptive scoring and expert
adaptation engines.  Epic 7 (Metrics & Dashboard) will provide richer
implementations; for now, :mod:`tapps_core.adaptive.persistence` supplies
simple file-based concrete classes.

## Classes

### `OutcomeTrackerProtocol`(Protocol)

Structural protocol for outcome tracking.

**Methods:**

#### `save_outcome`

```python
def save_outcome(self, outcome: CodeOutcome) -> None:
```

Persist a single :class:`CodeOutcome`.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcome` | `CodeOutcome` |  | *required* |

#### `load_outcomes`

```python
def load_outcomes(self, limit: int | None = None, workflow_id: str | None = None) -> list[CodeOutcome]:
```

Load stored outcomes, optionally filtered.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `limit` | `int \| None` |  | None |
| `workflow_id` | `str \| None` |  | None |

#### `get_statistics`

```python
def get_statistics(self) -> dict[str, Any]:
```

Return aggregate statistics over all stored outcomes.

### `PerformanceTrackerProtocol`(Protocol)

Structural protocol for expert performance tracking.

**Methods:**

#### `track_consultation`

```python
def track_consultation(self, expert_id: str, domain: str, confidence: float, query: str | None = None) -> None:
```

Record a single expert consultation.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |
| `domain` | `str` |  | *required* |
| `confidence` | `float` |  | *required* |
| `query` | `str \| None` |  | None |

#### `calculate_performance`

```python
def calculate_performance(self, expert_id: str, days: int = 30) -> ExpertPerformance | None:
```

Calculate aggregated performance for *expert_id* over *days*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |
| `days` | `int` |  | 30 |

#### `get_all_performance`

```python
def get_all_performance(self, days: int = 30) -> dict[str, ExpertPerformance]:
```

Calculate performance for every tracked expert.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `days` | `int` |  | 30 |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.adaptive.scoring_engine`

Adaptive scoring engine using Pearson correlation analysis.

Analyzes historical code-quality outcomes to identify which scoring
categories best predict first-pass success, then adjusts category
weights accordingly.

## Classes

### `AdaptiveScoringEngine`

Adjusts scoring category weights based on outcome correlations.

**Methods:**

#### `__init__`

```python
def __init__(self, outcome_tracker: OutcomeTrackerProtocol, learning_rate: float = DEFAULT_LEARNING_RATE, *, metrics_dir: Path | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcome_tracker` | `OutcomeTrackerProtocol` |  | *required* |
| `learning_rate` | `float` |  | DEFAULT_LEARNING_RATE |
| `metrics_dir` | `Path \| None` |  | None |

#### async `adjust_weights`

```python
async def adjust_weights(self, outcomes: list[CodeOutcome] | None = None, current_weights: dict[str, float] | None = None) -> dict[str, float]:
```

Compute adjusted scoring weights from outcome history.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcomes` | `list[CodeOutcome] \| None` |  | None |
| `current_weights` | `dict[str, float] \| None` |  | None |

#### `get_recommendation`

```python
def get_recommendation(self, outcomes: list[CodeOutcome] | None = None) -> dict[str, Any]:
```

Produce a diagnostic report without applying changes.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcomes` | `list[CodeOutcome] \| None` |  | None |

#### `save_snapshot`

```python
def save_snapshot(self, weights: dict[str, float], snapshot_path: Path) -> None:
```

Persist a :class:`AdaptiveWeightsSnapshot` to *snapshot_path*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `weights` | `dict[str, float]` |  | *required* |
| `snapshot_path` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `DEFAULT_LEARNING_RATE` | `` | `0.1` |
| `MIN_OUTCOMES_FOR_ADJUSTMENT` | `` | `5` |

---

*Documentation coverage: 87.5%*


---

# `packages.tapps-core.src.tapps_core.adaptive.scoring_wrapper`

Thin adapter wiring adaptive weights into CodeScorer.

Provides caching and a convenience method that returns a
:class:`~tapps_core.config.settings.ScoringWeights` instance ready to
be passed to :class:`~tapps_mcp.scoring.scorer.CodeScorer`.

## Classes

### `AdaptiveScorerWrapper`

Caching wrapper around :class:`AdaptiveScoringEngine`.

**Methods:**

#### `__init__`

```python
def __init__(self, outcome_tracker: OutcomeTrackerProtocol | None = None, adaptive_engine: AdaptiveScoringEngine | None = None, *, enabled: bool = True) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `outcome_tracker` | `OutcomeTrackerProtocol \| None` |  | None |
| `adaptive_engine` | `AdaptiveScoringEngine \| None` |  | None |
| `enabled` | `bool` |  | True |

#### async `get_adaptive_weights`

```python
async def get_adaptive_weights(self, *, force_reload: bool = False) -> dict[str, float] | None:
```

Return adaptive weights, or ``None`` if disabled / unavailable.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `force_reload` | `bool` |  | False |

#### `get_weights_as_settings`

```python
def get_weights_as_settings(self, default: ScoringWeights | None = None) -> ScoringWeights:
```

Convert cached adaptive weights into a :class:`ScoringWeights` instance.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `default` | `ScoringWeights \| None` |  | None |

#### async `track_outcome`

```python
async def track_outcome(self, workflow_id: str, file_path: Path, scores: dict[str, float], *, expert_consultations: list[str] | None = None, agent_id: str | None = None, prompt_hash: str | None = None) -> None:
```

Record an outcome via the underlying tracker.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `workflow_id` | `str` |  | *required* |
| `file_path` | `Path` |  | *required* |
| `scores` | `dict[str, float]` |  | *required* |
| `expert_consultations` | `list[str] \| None` |  | None |
| `agent_id` | `str \| None` |  | None |
| `prompt_hash` | `str \| None` |  | None |

#### staticmethod `hash_prompt`

```python
def hash_prompt(prompt: str) -> str:
```

Return a deterministic 16-char hex hash of *prompt*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `prompt` | `str` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 85.7%*


---

# `packages.tapps-core.src.tapps_core.adaptive.voting_engine`

Adaptive voting engine for expert weight adjustment.

Adjusts expert voting weights based on performance data while enforcing
the 51% primary expert constraint.

## Classes

### `AdaptiveVotingEngine`

Adjusts expert voting weights based on consultation performance.

**Methods:**

#### `__init__`

```python
def __init__(self, performance_tracker: PerformanceTrackerProtocol) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `performance_tracker` | `PerformanceTrackerProtocol` |  | *required* |

#### async `adjust_voting_weights`

```python
async def adjust_voting_weights(self, performance_data: dict[str, ExpertPerformance] | None = None, current_matrix: ExpertWeightMatrix | None = None) -> ExpertWeightMatrix:
```

Compute adjusted voting weights.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `performance_data` | `dict[str, ExpertPerformance] \| None` |  | None |
| `current_matrix` | `ExpertWeightMatrix \| None` |  | None |

#### `save_snapshot`

```python
def save_snapshot(self, matrix: ExpertWeightMatrix, snapshot_path: Path, performance_data: dict[str, ExpertPerformance] | None = None) -> None:
```

Persist an :class:`ExpertWeightsSnapshot`.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `matrix` | `ExpertWeightMatrix` |  | *required* |
| `snapshot_path` | `Path` |  | *required* |
| `performance_data` | `dict[str, ExpertPerformance] \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 80.0%*


---

# `packages.tapps-core.src.tapps_core.adaptive.weight_distributor`

Expert weight distribution utility.

Implements the 51% primary / 49% distributed formula for expert voting
weights across domains.

## Classes

### `WeightDistributor`

Static utility for computing expert weight distributions.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `PRIMARY_WEIGHT` | `ClassVar[float]` | `0.51` |
| `OTHER_WEIGHT` | `ClassVar[float]` | `0.49` |

**Methods:**

#### staticmethod `calculate_weights`

```python
def calculate_weights(domains: list[str], expert_primary_map: dict[str, str]) -> ExpertWeightMatrix:
```

Build an :class:`ExpertWeightMatrix` from a domain-to-primary mapping.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domains` | `list[str]` | All domains in the matrix. | *required* |
| `expert_primary_map` | `dict[str, str]` | Mapping of ``domain -> primary_expert_id``. | *required* |

**Returns:** A validated :class:`ExpertWeightMatrix`.

**Raises:**

- ValueError: If validation fails (missing domains, duplicate primaries).

#### staticmethod `recalculate_on_domain_add`

```python
def recalculate_on_domain_add(current_matrix: ExpertWeightMatrix, new_domain: str, new_expert_id: str) -> ExpertWeightMatrix:
```

Return a new matrix with *new_domain* added under *new_expert_id*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `current_matrix` | `ExpertWeightMatrix` |  | *required* |
| `new_domain` | `str` |  | *required* |
| `new_expert_id` | `str` |  | *required* |

#### staticmethod `format_matrix`

```python
def format_matrix(matrix: ExpertWeightMatrix) -> str:
```

Return a human-readable table representation of *matrix*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `matrix` | `ExpertWeightMatrix` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common`

Common utilities shared across Tapps platform modules.

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.common.constants`

Shared constants used across Tapps platform modules.

Centralised here to break circular dependencies between packages
(e.g. ``common.nudges`` needing thresholds that were previously
defined in ``experts.models``).

## Constants

| Name | Type | Value |
|------|------|-------|
| `LOW_CONFIDENCE_THRESHOLD` | `float` | `0.5` |
| `HIGH_CONFIDENCE_THRESHOLD` | `float` | `0.7` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common.exceptions`

Exception hierarchy for the Tapps platform.

## Classes

### `TappsMCPError`(Exception)

Base exception for all TappsMCP errors.

### `ConfigurationError`(TappsMCPError)

Raised when configuration is invalid or missing.

### `PathValidationError`(TappsMCPError, ValueError)

Raised when path validation fails.

### `SecurityError`(TappsMCPError)

Base exception for security-related errors.

### `FileOperationError`(TappsMCPError)

Raised when file operations fail.

### `ToolExecutionError`(TappsMCPError)

Raised when an external tool execution fails.

### `ToolNotFoundError`(ToolExecutionError)

Raised when a required external tool is not installed.

### `QualityGateError`(TappsMCPError)

Raised when quality gate evaluation fails.

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common.logging`

Structured logging setup using structlog.

## Functions

### `setup_logging`

```python
def setup_logging(level: str = 'INFO', json_output: bool = False) -> None:
```

Configure structlog for the Tapps platform.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `level` | `str` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). | 'INFO' |
| `json_output` | `bool` | If True, output JSON-formatted logs. Otherwise, use colored console output. | False |

### `get_logger`

```python
def get_logger(name: str) -> structlog.stdlib.BoundLogger:
```

Get a bound structlog logger.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `name` | `str` | Logger name (typically ``__name__``). | *required* |

**Returns:** A bound structlog logger instance.

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common.models`

Shared Pydantic v2 models for the Tapps platform.

## Classes

### `ToolResponse`(BaseModel)

Standard response envelope for all TappsMCP tools.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `tool` | `str` | `Field(description='Name of the tool that produced this response.')` |
| `success` | `bool` | `Field(description='Whether the tool executed successfully.')` |
| `elapsed_ms` | `int` | `Field(description='Execution time in milliseconds.')` |
| `data` | `dict[str, Any]` | `Field(default_factory=dict, description='Tool-specific result data.')` |
| `error` | `ErrorDetail | None` | `Field(default=None, description='Error details if success is False.')` |
| `degraded` | `bool` | `Field(default=False, description='True if some external tools were unavailable and results are partial.')` |

### `ErrorDetail`(BaseModel)

Structured error detail for tool responses.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `code` | `str` | `Field(description='Machine-readable error code.')` |
| `message` | `str` | `Field(description='Human-readable error message.')` |
| `details` | `dict[str, Any] | None` | `Field(default=None, description='Additional error context.')` |

### `InstalledTool`(BaseModel)

Information about an installed external tool.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` | `Field(description="Tool name (e.g. 'ruff', 'mypy').")` |
| `version` | `str | None` | `Field(default=None, description='Installed version string.')` |
| `available` | `bool` | `Field(description='Whether the tool is available on PATH.')` |
| `install_hint` | `str | None` | `Field(default=None, description='Install command hint when tool is not available.')` |

### `SecurityIssue`(BaseModel)

A single security finding from bandit or heuristic scan.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `code` | `str` | `Field(description="Rule code, e.g. 'B101'.")` |
| `message` | `str` | `Field(description='Description of the issue.')` |
| `file` | `str` | `Field(description='File path.')` |
| `line` | `int` | `Field(description='Line number.')` |
| `severity` | `str` | `Field(default='medium', description='critical | high | medium | low | info.')` |
| `confidence` | `str` | `Field(default='medium', description='high | medium | low.')` |
| `owasp` | `str | None` | `Field(default=None, description='OWASP category if mapped.')` |

### `Context7Diagnostic`(BaseModel)

Context7 API key availability check.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `api_key_set` | `bool` | `Field(description='Whether TAPPS_MCP_CONTEXT7_API_KEY is configured.')` |
| `status` | `str` | `Field(description="'available' if key is set, 'no_key' otherwise.")` |

### `CacheDiagnostic`(BaseModel)

Cache directory health check.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `cache_dir` | `str` | `Field(description='Absolute path to the cache directory.')` |
| `exists` | `bool` | `Field(description='Whether the cache directory exists.')` |
| `writable` | `bool` | `Field(description='Whether the cache directory is writable.')` |
| `entry_count` | `int` | `Field(default=0, description='Number of cached documentation entries.')` |
| `total_size_bytes` | `int` | `Field(default=0, description='Total size of cached content in bytes.')` |
| `stale_count` | `int` | `Field(default=0, description='Number of stale (past TTL) entries.')` |

### `VectorRagDiagnostic`(BaseModel)

Vector RAG optional dependency status.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `faiss_available` | `bool` | `Field(description='Whether faiss-cpu is importable.')` |
| `sentence_transformers_available` | `bool` | `Field(description='Whether sentence-transformers is importable.')` |
| `numpy_available` | `bool` | `Field(description='Whether numpy is importable.')` |
| `status` | `str` | `Field(description="'full_vector' if all deps present, 'keyword_only' otherwise.")` |

### `KnowledgeDomainInfo`(BaseModel)

File count for a single knowledge domain.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` | `Field(description='Domain name.')` |
| `file_count` | `int` | `Field(description='Number of markdown knowledge files.')` |

### `KnowledgeBaseDiagnostic`(BaseModel)

Knowledge base integrity check.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_domains` | `int` | `Field(description='Number of expert domains with knowledge directories.')` |
| `total_files` | `int` | `Field(description='Total markdown knowledge files across all domains.')` |
| `expected_domains` | `int` | `Field(description='Number of domains defined in ExpertRegistry.')` |
| `missing_domains` | `list[str]` | `Field(default_factory=list, description='Domains defined in the registry but missing knowledge directories.')` |
| `domains` | `list[KnowledgeDomainInfo]` | `Field(default_factory=list, description='Per-domain file counts.')` |

### `StartupDiagnostics`(BaseModel)

Aggregate startup diagnostics for all subsystems.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `context7` | `Context7Diagnostic` | `Field(description='Context7 API key status.')` |
| `cache` | `CacheDiagnostic` | `Field(description='Cache directory health.')` |
| `vector_rag` | `VectorRagDiagnostic` | `Field(description='Vector RAG dependency status.')` |
| `knowledge_base` | `KnowledgeBaseDiagnostic` | `Field(description='Knowledge base integrity.')` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common.pipeline_models`

Pipeline stage definitions shared across Tapps platform modules.

Centralised here to break the circular dependency between
``common.nudges`` and ``pipeline.models``.

## Classes

### `PipelineStage`(StrEnum)

The 5 stages of the TAPPS quality pipeline.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `DISCOVER` |  | `'discover'` |
| `RESEARCH` |  | `'research'` |
| `DEVELOP` |  | `'develop'` |
| `VALIDATE` |  | `'validate'` |
| `VERIFY` |  | `'verify'` |

## Constants

| Name | Type | Value |
|------|------|-------|
| `STAGE_ORDER` | `list[PipelineStage]` | `[PipelineStage.DISCOVER, PipelineStage.RESEARCH, PipelineStage.DEVELOP, PipelineStage.VALIDATE, PipelineStage.VERIFY]` |
| `STAGE_TOOLS` | `dict[PipelineStage, list[str]]` | `{PipelineStage.DISCOVER: ['tapps_server_info', 'tapps_project_profile', 'tapps_session_start', 'tapps_memory'], PipelineStage.RESEARCH: ['tapps_lookup_docs', 'tapps_consult_expert', 'tapps_list_experts'], PipelineStage.DEVELOP: ['tapps_score_file'], PipelineStage.VALIDATE: ['tapps_score_file', 'tapps_quality_gate', 'tapps_security_scan', 'tapps_validate_config', 'tapps_validate_changed', 'tapps_quick_check'], PipelineStage.VERIFY: ['tapps_checklist', 'tapps_memory']}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.common.utils`

Shared utility functions to eliminate cross-module duplication.

## Functions

### `should_skip_path`

```python
def should_skip_path(path: Path) -> bool:
```

Return True if any component of *path* is in SKIP_DIRS or matches a skip prefix.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `path` | `Path` |  | *required* |

### `utc_now`

```python
def utc_now() -> datetime:
```

Return the current UTC datetime (timezone-aware).

### `ensure_dir`

```python
def ensure_dir(path: Path) -> Path:
```

Create directory (and parents) if it does not exist. Returns the path.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `path` | `Path` |  | *required* |

### `read_text_utf8`

```python
def read_text_utf8(path: Path) -> str:
```

Read a file as UTF-8 text.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `path` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `SKIP_DIRS` | `frozenset[str]` | `frozenset({'.git', '.venv', 'venv', 'env', 'ENV', 'node_modules', '__pycache__', '.pytest_cache', 'dist', 'build', '.tox', '.eggs', 'htmlcov', '.mypy_cache', '.tapps-agents', '.tapps-mcp-cache', 'site-packages'})` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.config`

Configuration: settings, defaults, YAML loading.

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.config.feature_flags`

Unified feature flags for optional dependencies.

Detects optional packages once (lazily on first access) and caches the
results.  Replaces scattered ``try: import X except ImportError`` patterns
across the codebase with a single source of truth.

Usage::

    from tapps_core.config.feature_flags import feature_flags

    if feature_flags.faiss:
        import faiss
        ...

    if feature_flags.radon:
        from radon.complexity import cc_visit
        ...

## Classes

### `FeatureFlags`

Lazy-evaluated feature flags for optional dependencies.

**Methods:**

#### `__init__`

```python
def __init__(self) -> None:
```

#### property `faiss`

```python
def faiss(self) -> bool:
```

True when `[`faiss`](#faiss)` (faiss-cpu) is importable.

#### property `numpy`

```python
def numpy(self) -> bool:
```

True when `[`numpy`](#numpy)` is importable.

#### property `sentence_transformers`

```python
def sentence_transformers(self) -> bool:
```

True when `[`sentence_transformers`](#sentence-transformers)` is importable.

#### property `radon`

```python
def radon(self) -> bool:
```

True when both ``radon.complexity`` and ``radon.metrics`` are importable.

#### `reset`

```python
def reset(self) -> None:
```

Clear the cached detection results (for test isolation).

#### `as_dict`

```python
def as_dict(self) -> dict[str, bool]:
```

Return all evaluated flags as a plain dict.

## Constants

| Name | Type | Value |
|------|------|-------|
| `feature_flags` | `` | `FeatureFlags()` |

---

*Documentation coverage: 88.9%*


---

# `packages.tapps-core.src.tapps_core.config.settings`

TappsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``TAPPS_MCP_*``)
    2. Project-level ``.tapps-mcp.yaml``
    3. Built-in defaults

## Classes

### `ScoringWeights`(BaseSettings)

Weights for the 7-category scoring system.  Must sum to ~1.0.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_WEIGHT_')` |
| `complexity` | `float` | `Field(default=0.18, ge=0.0, le=1.0)` |
| `security` | `float` | `Field(default=0.27, ge=0.0, le=1.0)` |
| `maintainability` | `float` | `Field(default=0.24, ge=0.0, le=1.0)` |
| `test_coverage` | `float` | `Field(default=0.13, ge=0.0, le=1.0)` |
| `performance` | `float` | `Field(default=0.08, ge=0.0, le=1.0)` |
| `structure` | `float` | `Field(default=0.05, ge=0.0, le=1.0)` |
| `devex` | `float` | `Field(default=0.05, ge=0.0, le=1.0)` |

### `QualityPreset`(BaseSettings)

Quality gate thresholds.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_GATE_')` |
| `overall_min` | `float` | `Field(default=70.0, ge=0.0, le=100.0)` |
| `security_min` | `float` | `Field(default=0.0, ge=0.0, le=100.0)` |
| `maintainability_min` | `float` | `Field(default=0.0, ge=0.0, le=100.0)` |

### `AdaptiveSettings`(BaseSettings)

Settings for the adaptive learning subsystem.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_ADAPTIVE_')` |
| `enabled` | `bool` | `Field(default=False, description='Enable adaptive weight adjustment.')` |
| `learning_rate` | `float` | `Field(default=0.1, ge=0.0, le=1.0, description='Learning rate for weight adjustment (0.0-1.0).')` |
| `min_outcomes` | `int` | `Field(default=5, ge=1, description='Minimum outcome records before adaptive adjustment activates.')` |

### `MemoryDecaySettings`(BaseSettings)

Decay half-life configuration for the memory subsystem.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_MEMORY_DECAY_')` |
| `architectural_half_life_days` | `int` | `Field(default=180, ge=1, description='Half-life for architectural memories (days).')` |
| `pattern_half_life_days` | `int` | `Field(default=60, ge=1, description='Half-life for pattern memories (days).')` |
| `context_half_life_days` | `int` | `Field(default=14, ge=1, description='Half-life for context memories (days).')` |
| `confidence_floor` | `float` | `Field(default=0.1, ge=0.0, le=1.0, description='Minimum decayed confidence.')` |

### `MemorySettings`(BaseSettings)

Settings for the shared memory subsystem.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_MEMORY_')` |
| `enabled` | `bool` | `Field(default=True, description='Enable the memory subsystem.')` |
| `gc_enabled` | `bool` | `Field(default=True, description='Enable garbage collection.')` |
| `contradiction_check_on_start` | `bool` | `Field(default=True, description='Run contradiction detection at session start.')` |
| `max_memories` | `int` | `Field(default=1500, ge=1, description='Maximum number of active memories per project.')` |
| `gc_auto_threshold` | `float` | `Field(default=0.8, ge=0.0, le=1.0, description='Run GC at session start when usage exceeds this fraction of max_memories.')` |
| `inject_into_experts` | `bool` | `Field(default=True, description='Inject relevant memories into expert consultations (Epic 25).')` |
| `decay` | `MemoryDecaySettings` | `Field(default_factory=MemoryDecaySettings)` |

### `DockerSettings`(BaseModel)

Docker MCP distribution settings.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `enabled` | `bool` | `Field(default=False, description='Enable Docker MCP transport.')` |
| `transport` | `str` | `Field(default='auto', description="MCP transport mode: 'auto', 'docker', 'exe', or 'uv'.")` |
| `profile` | `str` | `Field(default='tapps-standard', description='Docker MCP Toolkit profile name.')` |
| `image` | `str` | `Field(default='ghcr.io/tapps-mcp/tapps-mcp:latest', description='Docker image for TappsMCP server.')` |
| `docs_image` | `str` | `Field(default='ghcr.io/tapps-mcp/docs-mcp:latest', description='Docker image for DocsMCP server.')` |
| `companions` | `list[str]` | `Field(default_factory=lambda: ['context7'], description='Companion MCP servers to recommend.')` |

### `TappsMCPSettings`(BaseSettings)

Root settings for TappsMCP server.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='TAPPS_MCP_', env_nested_delimiter='__', extra='ignore')` |
| `project_root` | `Path` | `Field(default_factory=Path.cwd, description='Project root boundary - all file paths must be within this directory.')` |
| `host_project_root` | `str | None` | `Field(default=None, description='Optional host path the client uses for the same project (e.g. C:\\projects\\myapp). When set, absolute paths under this are mapped to project_root so Cursor/Docker work together.')` |
| `quality_preset` | `str` | `Field(default='standard', description='Quality gate preset: standard, strict, or framework.')` |
| `log_level` | `str` | `Field(default='INFO', description='Logging level.')` |
| `log_json` | `bool` | `Field(default=False, description='Output JSON-formatted logs.')` |
| `context7_api_key` | `SecretStr | None` | `Field(default=None, description='Context7 API key (optional).')` |
| `scoring_weights` | `ScoringWeights` | `Field(default_factory=ScoringWeights)` |
| `quality_gate` | `QualityPreset` | `Field(default_factory=QualityPreset)` |
| `adaptive` | `AdaptiveSettings` | `Field(default_factory=AdaptiveSettings)` |
| `tool_timeout` | `int` | `Field(default=30, ge=5, description='Timeout for individual external tool invocations (seconds).')` |
| `dead_code_enabled` | `bool` | `Field(default=True, description='Enable dead code detection via vulture in scoring.')` |
| `dead_code_min_confidence` | `int` | `Field(default=80, ge=0, le=100, description='Minimum confidence threshold for dead code findings (0-100).')` |
| `dead_code_whitelist_patterns` | `list[str]` | `Field(default_factory=lambda: ['test_*', 'conftest.py'], description='File name patterns to exclude from dead code findings (fnmatch).')` |
| `dependency_scan_enabled` | `bool` | `Field(default=True, description='Enable dependency vulnerability scanning via pip-audit.')` |
| `dependency_scan_severity_threshold` | `str` | `Field(default='medium', description='Minimum severity to include: critical, high, medium, low, unknown.')` |
| `dependency_scan_ignore_ids` | `list[str]` | `Field(default_factory=list, description='Vulnerability IDs to exclude (e.g. CVE-2024-12345).')` |
| `dependency_scan_source` | `str` | `Field(default='auto', description='Scan source: auto, environment, requirements, pyproject.')` |
| `llm_engagement_level` | `Literal['high', 'medium', 'low']` | `Field(default='medium', description="How intensely the LLM should use TappsMCP tools. 'high' = mandatory enforcement, 'medium' = balanced, 'low' = optional guidance.")` |
| `destructive_guard` | `bool` | `Field(default=False, description='When True, generate a PreToolUse hook that blocks Bash commands containing destructive patterns (rm -rf, format c:, etc.). Opt-in only.')` |
| `business_experts_enabled` | `bool` | `Field(default=True, description='Enable loading business experts from .tapps-mcp/experts.yaml.')` |
| `business_experts_max` | `int` | `Field(default=20, ge=0, le=50, description='Maximum number of business experts to load.')` |
| `memory` | `MemorySettings` | `Field(default_factory=MemorySettings)` |
| `cache_max_mb` | `int` | `Field(default=100, ge=1, description='Maximum knowledge cache size in MB before LRU eviction triggers.')` |
| `expert_auto_fallback` | `bool` | `Field(default=True, description='Enable automatic Context7 lookup hints/content when expert RAG has no matches.')` |
| `expert_fallback_max_chars` | `int` | `Field(default=1200, ge=200, description='Maximum number of characters merged from Context7 fallback content.')` |
| `docker` | `DockerSettings` | `Field(default_factory=DockerSettings)` |

## Functions

### `load_settings`

```python
def load_settings(project_root: Path | None = None) -> TappsMCPSettings:
```

Load settings with correct precedence.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path \| None` | Override for project root.  When ``None``, uses CWD. | None |

**Returns:** Fully resolved ``TappsMCPSettings``.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `PRESETS` | `dict[str, dict[str, float]]` | `{'standard': {'overall_min': 70.0, 'security_min': 0.0, 'maintainability_min': 0.0}, 'strict': {'overall_min': 80.0, 'security_min': 8.0, 'maintainability_min': 7.0}, 'framework': {'overall_min': 75.0, 'security_min': 8.5, 'maintainability_min': 7.5}}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts`

Expert system — 16-domain RAG-backed expert consultation.

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.experts.adaptive_domain_detector`

Adaptive domain detector for expert routing.

Detects domain suggestions from prompts, code patterns, and consultation
gaps.  Complements the existing :class:`DomainDetector` with adaptive
capabilities based on usage history.

## Classes

### `DomainSuggestion`(BaseModel)

A suggested domain with confidence and evidence.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` | `Field(description='Suggested domain name.')` |
| `confidence` | `float` | `Field(ge=0.0, le=1.0, description='Detection confidence.')` |
| `source` | `str` | `Field(description='Detection source (prompt, code_pattern, consultation_gap).')` |
| `evidence` | `list[str]` | `Field(default_factory=list, description='Supporting evidence.')` |
| `keywords` | `list[str]` | `Field(default_factory=list, description='Matched keywords.')` |
| `priority` | `str` | `Field(default='normal', description='Priority: low, normal, high, critical.')` |
| `usage_frequency` | `int` | `Field(default=0, ge=0, description='Times this domain was detected.')` |

### `AdaptiveDomainDetector`

Detects domains from prompts, code, and consultation history.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `DOMAIN_KEYWORDS` | `ClassVar[dict[str, list[str]]]` | `{'oauth2': ['oauth', 'oauth2', 'openid', 'oidc', 'jwt', 'refresh token', 'access token'], 'api-clients': ['api client', 'rest client', 'http client', 'sdk', 'api wrapper'], 'graphql': ['graphql', 'gql', 'query mutation', 'schema stitching', 'apollo'], 'microservices': ['microservice', 'service mesh', 'grpc', 'protobuf', 'sidecar'], 'event-driven': ['event driven', 'event sourcing', 'cqrs', 'message queue', 'pub sub'], 'websocket': ['websocket', 'ws://', 'wss://', 'socket.io', 'real-time'], 'mqtt': ['mqtt', 'mosquitto', 'paho', 'iot protocol', 'qos level'], 'grpc': ['grpc', 'protobuf', 'protocol buffers', 'grpc-web'], 'serverless': ['serverless', 'lambda', 'cloud function', 'faas'], 'kubernetes': ['kubernetes', 'k8s', 'helm', 'kustomize', 'kubectl'], 'docker': ['docker', 'dockerfile', 'container', 'docker-compose'], 'ci-cd': ['ci/cd', 'pipeline', 'github actions', 'jenkins', 'gitlab ci'], 'monitoring': ['monitoring', 'prometheus', 'grafana', 'alerting', 'observability'], 'authentication': ['authentication', 'login', 'session', 'password', 'mfa', '2fa'], 'authorization': ['authorization', 'rbac', 'permissions', 'access control', 'acl'], 'database': ['database', 'sql', 'nosql', 'orm', 'migration', 'schema'], 'caching': ['caching', 'redis', 'memcached', 'cache invalidation', 'ttl'], 'search': ['search', 'elasticsearch', 'full-text', 'indexing', 'lucene'], 'queue': ['message queue', 'rabbitmq', 'kafka', 'celery', 'task queue'], 'testing': ['testing', 'unit test', 'integration test', 'e2e', 'test coverage']}` |
| `CODE_PATTERNS` | `ClassVar[dict[str, list[str]]]` | `{'oauth2': ['OAuth2Session', 'refresh_token', 'authorization_code'], 'websocket': ['ws://', 'wss://', 'WebSocket\\(', 'socketio'], 'mqtt': ['mqtt\\.Client', 'paho\\.mqtt', 'on_message'], 'database': ['CREATE\\s+TABLE', 'SELECT\\s+.+\\s+FROM', 'sqlalchemy', '\\.execute\\('], 'docker': ['FROM\\s+\\w+:\\w+', 'ENTRYPOINT\\s+\\[', 'docker-compose']}` |

**Methods:**

#### `__init__`

```python
def __init__(self, project_root: str | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str \| None` |  | None |

#### async `detect_domains`

```python
async def detect_domains(self, prompt: str | None = None, code_context: str | None = None, consultation_history: list[dict[str, Any]] | None = None) -> list[DomainSuggestion]:
```

Detect domains from all available signals.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `prompt` | `str \| None` |  | None |
| `code_context` | `str \| None` |  | None |
| `consultation_history` | `list[dict[str, Any]] \| None` |  | None |

#### async staticmethod `detect_recurring_patterns`

```python
async def detect_recurring_patterns(detection_history: list[DomainSuggestion]) -> list[DomainSuggestion]:
```

Identify domains that appear frequently in detection history.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `detection_history` | `list[DomainSuggestion]` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 83.3%*


---

# `packages.tapps-core.src.tapps_core.experts.business_config`

YAML schema and loader for user-defined business experts.

## Classes

### `BusinessExpertEntry`(BaseModel)

Schema for a single expert entry in experts.yaml.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `ConfigDict(extra='forbid')` |
| `expert_id` | `str` | `Field(description="Unique expert identifier (must start with 'expert-').")` |
| `expert_name` | `str` | `Field(description='Human-readable expert name.')` |
| `primary_domain` | `str` | `Field(description='Primary domain of authority.')` |
| `description` | `str` | `Field(default='', description="Short description of the expert's focus.")` |
| `keywords` | `list[str]` | `Field(default_factory=list, description='Custom keywords for domain detection routing.')` |
| `rag_enabled` | `bool` | `Field(default=True, description='Whether RAG retrieval is enabled.')` |
| `knowledge_dir` | `str | None` | `Field(default=None, description='Override knowledge directory name.')` |

### `BusinessExpertsConfig`(BaseModel)

Root schema for .tapps-mcp/experts.yaml.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `ConfigDict(extra='forbid')` |
| `experts` | `list[BusinessExpertEntry]` | `Field(default_factory=list)` |

## Functions

### `load_business_experts`

```python
def load_business_experts(project_root: Path) -> list[ExpertConfig]:
```

Load user-defined business experts from .tapps-mcp/experts.yaml.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.business_knowledge`

Business expert knowledge directory utilities.

Validates and scaffolds knowledge directories for user-defined
business experts under {project_root}/.tapps-mcp/knowledge/.

## Classes

### `KnowledgeValidationResult`

Decorators: `@dataclass`

Result of validating knowledge directories for business experts.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `valid` | `list[str]` | `field(default_factory=list)` |
| `missing` | `list[str]` | `field(default_factory=list)` |
| `empty` | `list[str]` | `field(default_factory=list)` |
| `warnings` | `list[str]` | `field(default_factory=list)` |

## Functions

### `get_business_knowledge_path`

```python
def get_business_knowledge_path(project_root: Path, expert: ExpertConfig) -> Path:
```

Return the knowledge directory path for a business expert.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Project root directory. | *required* |
| `expert` | `ExpertConfig` | Expert configuration. | *required* |

**Returns:** Path to the knowledge directory under .tapps-mcp/knowledge/.

### `validate_business_knowledge`

```python
def validate_business_knowledge(project_root: Path, experts: list[ExpertConfig]) -> KnowledgeValidationResult:
```

Validate knowledge directories for a list of business experts.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Project root directory. | *required* |
| `experts` | `list[ExpertConfig]` | List of expert configurations to validate. | *required* |

**Returns:** Validation result with valid, missing, empty, and warnings lists.

### `scaffold_knowledge_directory`

```python
def scaffold_knowledge_directory(project_root: Path, expert: ExpertConfig) -> Path:
```

Create a knowledge directory with a README template for a business expert.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Project root directory. | *required* |
| `expert` | `ExpertConfig` | Expert configuration. | *required* |

**Returns:** Path to the created (or existing) knowledge directory.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.business_loader`

Business expert auto-loading integration.

Called during session start to load and register business experts
from ``.tapps-mcp/experts.yaml``.

## Classes

### `BusinessExpertLoadResult`

Decorators: `@dataclass`

Result of loading and registering business experts.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `loaded` | `int` | `0` |
| `errors` | `list[str]` | `field(default_factory=list)` |
| `warnings` | `list[str]` | `field(default_factory=list)` |
| `expert_ids` | `list[str]` | `field(default_factory=list)` |
| `knowledge_status` | `dict[str, str]` | `field(default_factory=dict)` |

## Functions

### `load_and_register_business_experts`

```python
def load_and_register_business_experts(project_root: Path) -> BusinessExpertLoadResult:
```

Load business experts from YAML and register them with the registry.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Project root directory. | *required* |

**Returns:** Structured result with load status and knowledge validation.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.business_templates`

Starter templates for business expert knowledge directories.

## Functions

### `generate_readme_template`

```python
def generate_readme_template(expert_name: str, primary_domain: str, description: str = '') -> str:
```

Generate a README.md for the knowledge directory.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_name` | `str` | Human-readable expert name. | *required* |
| `primary_domain` | `str` | Primary domain of authority. | *required* |
| `description` | `str` | Short description (unused in README, reserved for future use). | '' |

**Returns:** Markdown content for the README.md file.

### `generate_starter_knowledge`

```python
def generate_starter_knowledge(expert_name: str, primary_domain: str, description: str = '') -> str:
```

Generate a starter overview.md knowledge file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_name` | `str` | Human-readable expert name. | *required* |
| `primary_domain` | `str` | Primary domain of authority. | *required* |
| `description` | `str` | Short description of the expert's focus area. | '' |

**Returns:** Markdown content for the overview.md starter file.

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.confidence`

Confidence scoring for expert consultations.

Computes a weighted confidence score from multiple factors:

- **RAG quality** (40%) — how many knowledge chunks matched and their scores.
- **Domain relevance** (30%) — whether the question maps to a technical domain.
- **Source coverage** (30%) — fraction of query keywords covered by sources.

This is a simplified version of the TappsCodingAgents ``ConfidenceCalculator``
with the ``ProjectProfile`` and agent-threshold dependencies removed.

## Functions

### `compute_confidence`

```python
def compute_confidence(factors: ConfidenceFactors, domain: str) -> float:
```

Compute a 0.0-1.0 confidence score from *factors* and *domain*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `factors` | `ConfidenceFactors` | Pre-computed confidence factors. | *required* |
| `domain` | `str` | The expert domain that handled the consultation. | *required* |

**Returns:** Confidence score clamped to ``[0.0, 1.0]``.

### `compute_rag_quality`

```python
def compute_rag_quality(chunk_scores: list[float]) -> float:
```

Derive a RAG-quality factor from individual chunk scores.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `chunk_scores` | `list[float]` | List of ``KnowledgeChunk.score`` values (0.0-1.0). | *required* |

**Returns:** Quality score in ``[0.0, 1.0]``.

### `compute_chunk_coverage`

```python
def compute_chunk_coverage(keywords: set[str], chunk_texts: list[str]) -> float:
```

Fraction of *keywords* that appear in at least one chunk.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `keywords` | `set[str]` | The normalised query keywords. | *required* |
| `chunk_texts` | `list[str]` | Lowered content of each retrieved chunk. | *required* |

**Returns:** Coverage ratio in ``[0.0, 1.0]``.

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.domain_detector`

Lightweight domain detector — maps questions and repo signals to expert domains.

This is a simplified version of the TappsCodingAgents ``DomainStackDetector``
stripped of its ``ProjectProfile`` dependency.  It provides two capabilities:

1. **Question routing** — keyword analysis to find the best domain for a user
   question.
2. **Repo signal detection** — file-system scanning to detect the project's
   technology stack and map it to relevant domains.

## Classes

### `DomainDetector`

Detects the best expert domain for a question or project.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `REPO_FILE_SIGNALS` | `ClassVar[dict[str, list[str]]]` | `{'Dockerfile': ['cloud-infrastructure', 'development-workflow'], 'docker-compose.yml': ['cloud-infrastructure', 'development-workflow'], 'docker-compose.yaml': ['cloud-infrastructure', 'development-workflow'], 'k8s': ['cloud-infrastructure'], 'kubernetes': ['cloud-infrastructure'], '.github/workflows': ['development-workflow'], '.gitlab-ci.yml': ['development-workflow'], 'Makefile': ['development-workflow'], 'pyproject.toml': ['code-quality-analysis'], 'setup.py': ['code-quality-analysis'], 'package.json': ['user-experience'], 'tsconfig.json': ['user-experience'], 'requirements.txt': ['code-quality-analysis'], 'pytest.ini': ['testing-strategies'], 'conftest.py': ['testing-strategies'], '.security': ['security'], 'sonar-project.properties': ['code-quality-analysis']}` |

**Methods:**

#### classmethod `detect_from_question`

```python
def detect_from_question(cls, question: str) -> list[DomainMapping]:
```

Score *question* against all built-in domains and return ranked results.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The user's question text. | *required* |

**Returns:** List of :class:`DomainMapping` sorted by confidence (descending).
    Only domains with a positive score are included.

#### classmethod `detect_from_question_merged`

```python
def detect_from_question_merged(cls, question: str) -> list[DomainMapping]:
```

Score *question* against built-in AND business domains.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The user's question text. | *required* |

**Returns:** List of :class:`DomainMapping` sorted by confidence (descending).
    Only domains with a positive score are included.

#### classmethod `detect_from_project`

```python
def detect_from_project(cls, project_root: Path) -> list[DomainMapping]:
```

Scan *project_root* for technology signals.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |

**Returns:** List of :class:`DomainMapping` sorted by confidence.

## Constants

| Name | Type | Value |
|------|------|-------|
| `DOMAIN_KEYWORDS` | `dict[str, list[str]]` | `{'security': ['security', 'vulnerability', 'cve', 'owasp', 'xss', 'sql injection', 'csrf', 'authentication', 'authorization', 'encryption', 'tls', 'ssl', 'secret', 'credential', 'token', 'jwt', 'oauth', 'cors', 'sanitize', 'exploit', 'attack', 'threat', 'firewall', 'penetration'], 'performance-optimization': ['performance', 'speed', 'latency', 'throughput', 'bottleneck', 'profiling', 'cache', 'caching', 'optimise', 'optimize', 'memory', 'cpu', 'benchmark', 'slow', 'fast', 'concurrency', 'async', 'parallel', 'thread', 'pool', 'batch'], 'testing-strategies': ['test', 'testing', 'unit test', 'integration test', 'e2e', 'coverage', 'mock', 'stub', 'fixture', 'assert', 'pytest', 'jest', 'junit', 'tdd', 'bdd', 'regression', 'snapshot', 'cypress'], 'code-quality-analysis': ['code quality', 'lint', 'linting', 'ruff', 'pylint', 'flake8', 'static analysis', 'complexity', 'cyclomatic', 'maintainability', 'refactor', 'clean code', 'code smell', 'technical debt', 'mypy', 'type check', 'typing', 'mypy strict', 'bandit', 'radon', 'vulture', 'quality gate', 'scoring pipeline'], 'software-architecture': ['architecture', 'design pattern', 'microservice', 'monolith', 'modular', 'dependency injection', 'solid', 'clean architecture', 'hexagonal', 'event driven', 'cqrs', 'domain driven', 'layered', 'system design', 'scalability'], 'development-workflow': ['ci', 'cd', 'pipeline', 'workflow', 'deploy', 'deployment', 'build', 'release', 'git', 'branch', 'merge', 'pr', 'code review', 'devops', 'automation', 'makefile', 'docker compose', 'github actions', 'dependabot', 'oidc', 'trusted publishing', 'trivy', 'hadolint', 'ghcr', 'sarif'], 'data-privacy-compliance': ['privacy', 'gdpr', 'hipaa', 'compliance', 'regulation', 'pii', 'data protection', 'consent', 'audit', 'retention', 'anonymize', 'pseudonymize', 'data subject', 'breach notification'], 'accessibility': ['accessibility', 'a11y', 'wcag', 'aria', 'screen reader', 'keyboard navigation', 'contrast', 'alt text', 'assistive', 'inclusive', 'disability'], 'user-experience': ['ux', 'user experience', 'usability', 'ui', 'frontend', 'react', 'vue', 'angular', 'css', 'responsive', 'mobile', 'animation', 'component', 'layout', 'design system'], 'documentation-knowledge-management': ['documentation', 'docs', 'readme', 'changelog', 'api docs', 'docstring', 'sphinx', 'mkdocs', 'wiki', 'knowledge base', 'technical writing'], 'ai-frameworks': ['ai', 'machine learning', 'ml', 'llm', 'gpt', 'claude', 'transformer', 'neural', 'model', 'prompt', 'agent', 'rag', 'embedding', 'fine-tune', 'langchain', 'openai'], 'agent-learning': ['agent learning', 'memory', 'adaptive', 'reinforcement', 'feedback loop', 'self-improve', 'experience', 'session memory', 'knowledge graph', 'learning rate', 'memory system', 'memory store', 'memory persistence', 'memory decay', 'memory tier', 'shared memory', 'contradiction detection'], 'observability-monitoring': ['observability', 'monitoring', 'logging', 'metrics', 'tracing', 'alert', 'dashboard', 'prometheus', 'grafana', 'datadog', 'sentry', 'log level', 'structured log', 'opentelemetry'], 'api-design-integration': ['api', 'rest', 'graphql', 'grpc', 'endpoint', 'route', 'request', 'response', 'status code', 'pagination', 'versioning', 'webhook', 'swagger', 'openapi', 'integration'], 'cloud-infrastructure': ['cloud', 'aws', 'azure', 'gcp', 'kubernetes', 'k8s', 'docker', 'terraform', 'infrastructure', 'iac', 'serverless', 'lambda', 'ec2', 's3', 'container', 'helm', 'istio'], 'database-data-management': ['database', 'sql', 'nosql', 'postgres', 'mysql', 'mongodb', 'redis', 'migration', 'schema', 'query', 'index', 'orm', 'sqlalchemy', 'prisma', 'transaction', 'replication'], 'github': ['github', 'github actions', 'github workflow', 'pull request template', 'issue template', 'issue form', 'dependabot', 'codeql', 'code scanning', 'secret scanning', 'push protection', 'codeowners', 'copilot coding agent', 'copilot agent', 'copilot review', 'agentic workflow', 'copilot setup steps', 'artifact attestation', 'github runner', 'github mcp', 'github project', 'merge queue', 'branch protection', 'ruleset', 'github api']}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.domain_utils`

Utility functions for domain name handling.

## Functions

### `sanitize_domain_for_path`

```python
def sanitize_domain_for_path(domain: str) -> str:
```

Sanitise a domain name or URL for use as a directory path.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` | Domain name or URL (e.g. ``"home-automation"`` or ``"https://www.home-assistant.io/docs/"``). | *required* |

**Returns:** Sanitised string safe for use as a directory name.

## Constants

| Name | Type | Value |
|------|------|-------|
| `DOMAIN_TO_DIRECTORY_MAP` | `dict[str, str]` | `{'performance-optimization': 'performance', 'ai-agent-framework': 'ai-frameworks', 'testing-strategies': 'testing'}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.engine`

Expert consultation engine — orchestrates RAG lookup and confidence scoring.

This is the main entry point for expert consultations.  It:

1. Detects the best domain for the user's question.
2. Loads the domain's knowledge base (RAG).
3. Searches for relevant chunks.
4. Computes a confidence score.
5. Returns a :class:`ConsultationResult`.

## Functions

### `consult_expert`

```python
def consult_expert(question: str, domain: str | None = None, max_chunks: int = 5, max_context_length: int = 3000) -> ConsultationResult:
```

Run an expert consultation for *question*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The user's question (natural language). | *required* |
| `domain` | `str \| None` | Optional domain override.  When ``None``, the best domain is detected automatically from the question text. | None |
| `max_chunks` | `int` | Maximum RAG chunks to retrieve. | 5 |
| `max_context_length` | `int` | Maximum character length of the context block. | 3000 |

**Returns:** A :class:`ConsultationResult` with the expert's knowledge-backed
    answer, confidence score, and source references.

### `list_experts`

```python
def list_experts() -> list[ExpertInfo]:
```

Return info for every registered expert, including knowledge-file counts.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.hot_rank`

Hot-rank — adaptive ranking from usage + feedback signals.

Consumes metrics from the feedback tracker, expert performance tracker, and
RAG metrics tracker to compute a hot-rank score for domains.  This score can
be used as a tie-breaker in retrieval ranking to prioritise domains and sources
that historically produce helpful results.

Includes guardrails against popularity-only lock-in: new/under-served domains
get a minimum exploration bonus.

## Classes

### `DomainHotRank`

Decorators: `@dataclass`

Hot-rank score for a single domain.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` |  |
| `score` | `float` |  |
| `consultations` | `int` | `0` |
| `avg_confidence` | `float` | `0.0` |
| `helpful_rate` | `float` | `0.0` |
| `recency_weight` | `float` | `0.0` |
| `exploration_bonus` | `float` | `0.0` |

## Functions

### `compute_hot_rank`

```python
def compute_hot_rank(domain: str, consultations: int, avg_confidence: float, helpful_rate: float, days_since_last: float = 0.0) -> DomainHotRank:
```

Compute hot-rank for a domain.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` | Domain identifier. | *required* |
| `consultations` | `int` | Total consultation count. | *required* |
| `avg_confidence` | `float` | Average confidence score. | *required* |
| `helpful_rate` | `float` | Fraction of consultations marked helpful. | *required* |
| `days_since_last` | `float` | Days since the most recent consultation. | 0.0 |

**Returns:** DomainHotRank with computed score and component breakdown.

### `get_domain_hot_ranks`

```python
def get_domain_hot_ranks(metrics_dir: Path) -> list[DomainHotRank]:
```

Compute hot-ranks for all domains using stored metrics.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `metrics_dir` | `Path` | Directory containing metrics files. | *required* |

**Returns:** Sorted list of DomainHotRank (highest score first).

### `apply_hot_rank_boost`

```python
def apply_hot_rank_boost(chunks: list[Any], domain: str, metrics_dir: Path | None = None, boost_factor: float = 0.05) -> list[Any]:
```

Apply a hot-rank tie-breaker boost to chunk scores.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `chunks` | `list[Any]` | List of KnowledgeChunk objects (must have a ``score`` attribute). | *required* |
| `domain` | `str` | The domain being queried. | *required* |
| `metrics_dir` | `Path \| None` | Path to metrics directory (if None, no boost applied). | None |
| `boost_factor` | `float` | Maximum score boost (default 0.05 = 5%). | 0.05 |

**Returns:** The same chunks list (scores modified in place).

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.knowledge_freshness`

Knowledge file freshness tracking.

Tracks metadata about knowledge files (last updated, deprecation status)
and identifies stale files that may need review.

## Classes

### `KnowledgeFileMetadata`(BaseModel)

Metadata for a single knowledge file.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` | `Field(description='Relative path to the knowledge file.')` |
| `last_updated` | `str` | `Field(description='ISO-8601 UTC timestamp of last update.')` |
| `version` | `str | None` | `Field(default=None, description='Version tag.')` |
| `deprecated` | `bool` | `Field(default=False, description='Whether the file is deprecated.')` |
| `deprecation_date` | `str | None` | `Field(default=None, description='ISO-8601 deprecation date.')` |
| `replacement_file` | `str | None` | `Field(default=None, description='Path to replacement file.')` |
| `author` | `str | None` | `Field(default=None, description='Author of the file.')` |
| `tags` | `list[str]` | `Field(default_factory=list, description='Tags for categorisation.')` |
| `description` | `str | None` | `Field(default=None, description='Short description.')` |

### `KnowledgeFreshnessTracker`

Tracks knowledge file metadata and detects staleness.

**Methods:**

#### `__init__`

```python
def __init__(self, metadata_file: Path | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `metadata_file` | `Path \| None` |  | None |

#### `update_file_metadata`

```python
def update_file_metadata(self, file_path: Path, *, version: str | None = None, author: str | None = None, tags: list[str] | None = None, description: str | None = None) -> None:
```

Update or create metadata for *file_path*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `version` | `str \| None` |  | None |
| `author` | `str \| None` |  | None |
| `tags` | `list[str] \| None` |  | None |
| `description` | `str \| None` |  | None |

#### `mark_deprecated`

```python
def mark_deprecated(self, file_path: Path, *, replacement_file: str | None = None, deprecation_date: str | None = None) -> None:
```

Mark *file_path* as deprecated.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `replacement_file` | `str \| None` |  | None |
| `deprecation_date` | `str \| None` |  | None |

#### `get_file_metadata`

```python
def get_file_metadata(self, file_path: Path) -> KnowledgeFileMetadata | None:
```

Return metadata for *file_path*, or ``None`` if not tracked.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

#### `get_stale_files`

```python
def get_stale_files(self, knowledge_dir: Path, max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> list[tuple[Path, KnowledgeFileMetadata]]:
```

Return files older than *max_age_days*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |
| `max_age_days` | `int` |  | _DEFAULT_MAX_AGE_DAYS |

#### `get_deprecated_files`

```python
def get_deprecated_files(self, knowledge_dir: Path) -> list[tuple[Path, KnowledgeFileMetadata]]:
```

Return all deprecated files within *knowledge_dir*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |

#### `scan_and_update`

```python
def scan_and_update(self, knowledge_dir: Path) -> dict[str, Any]:
```

Scan *knowledge_dir* and update metadata for any new files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |

#### `get_summary`

```python
def get_summary(self, knowledge_dir: Path) -> dict[str, Any]:
```

Return a summary of knowledge file freshness.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 90.9%*


---

# `packages.tapps-core.src.tapps_core.experts.knowledge_ingestion`

Knowledge ingestion pipeline for project documentation.

Scans project documentation (architecture docs, ADRs, runbooks, etc.)
and ingests them into the knowledge base as domain-tagged markdown files.

## Classes

### `IngestionResult`(BaseModel)

Result of a knowledge ingestion run.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `source_type` | `str` | `Field(description='Type of sources ingested.')` |
| `entries_ingested` | `int` | `Field(default=0, ge=0, description='Successful entries.')` |
| `entries_failed` | `int` | `Field(default=0, ge=0, description='Failed entries.')` |
| `errors` | `list[str]` | `Field(default_factory=list, description='Error messages.')` |

### `KnowledgeEntry`(BaseModel)

A single knowledge entry to be ingested.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `title` | `str` | `Field(description='Entry title.')` |
| `content` | `str` | `Field(description='Markdown content.')` |
| `domain` | `str` | `Field(description='Target domain.')` |
| `source` | `str` | `Field(description='Source file path or identifier.')` |
| `source_type` | `str` | `Field(description='Source type (e.g. architecture, adr).')` |
| `metadata` | `dict[str, Any]` | `Field(default_factory=dict, description='Extra metadata.')` |

### `KnowledgeIngestionPipeline`

Ingests project documentation into the knowledge base.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `PROJECT_SOURCE_PATTERNS` | `ClassVar[dict[str, list[str]]]` | `{'architecture': ['docs/**/architecture*.md', 'ARCHITECTURE.md', 'docs/design/**/*.md'], 'adr': ['docs/adr/**/*.md', 'docs/decisions/**/*.md'], 'runbook': ['docs/runbook*.md', 'docs/ops/**/*.md'], 'requirements': ['docs/requirements*.md', 'docs/specs/**/*.md']}` |
| `DEFAULT_DOMAIN_MAP` | `ClassVar[dict[str, list[str]]]` | `{'architecture': ['general', 'api-design'], 'adr': ['general'], 'runbook': ['devops', 'monitoring'], 'requirements': ['general']}` |

**Methods:**

#### `__init__`

```python
def __init__(self, project_root: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

#### `ingest_project_sources`

```python
def ingest_project_sources(self) -> IngestionResult:
```

Scan project for documentation and ingest into knowledge base.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 83.3%*


---

# `packages.tapps-core.src.tapps_core.experts.knowledge_validator`

Knowledge base file validator.

Validates markdown knowledge files for structural quality, correct
Python code blocks, cross-reference integrity, and formatting.

## Classes

### `ValidationIssue`(BaseModel)

A single validation issue found in a knowledge file.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` | `Field(description='Path to the file.')` |
| `severity` | `str` | `Field(description='Severity: error, warning, or info.')` |
| `line_number` | `int | None` | `Field(default=None, description='Line number (1-indexed).')` |
| `message` | `str` | `Field(description='Human-readable description.')` |
| `rule` | `str` | `Field(description='Machine-readable rule identifier.')` |

### `ValidationResult`(BaseModel)

Result of validating a single knowledge file.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` | `Field(description='Path to the file.')` |
| `is_valid` | `bool` | `Field(description='True if no errors were found.')` |
| `issues` | `list[ValidationIssue]` | `Field(default_factory=list, description='All issues found.')` |
| `file_size` | `int` | `Field(default=0, ge=0, description='File size in bytes.')` |
| `line_count` | `int` | `Field(default=0, ge=0, description='Number of lines.')` |
| `has_headers` | `bool` | `Field(default=False, description='Whether the file has markdown headers.')` |
| `has_code_blocks` | `bool` | `Field(default=False, description='Whether the file has code blocks.')` |
| `has_examples` | `bool` | `Field(default=False, description='Whether the file has examples.')` |

### `KnowledgeBaseValidator`

Validates knowledge base markdown files.

**Methods:**

#### `__init__`

```python
def __init__(self, knowledge_dir: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |

#### `validate_all`

```python
def validate_all(self) -> list[ValidationResult]:
```

Validate all ``*.md`` files in the knowledge directory.

#### `validate_file`

```python
def validate_file(self, file_path: Path) -> ValidationResult:
```

Validate a single knowledge file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

#### staticmethod `get_summary`

```python
def get_summary(results: list[ValidationResult]) -> dict[str, Any]:
```

Aggregate validation results into a summary.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `results` | `list[ValidationResult]` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 87.5%*


---

# `packages.tapps-core.src.tapps_core.experts.models`

Pydantic models for the expert system.

## Classes

### `ExpertConfig`(BaseModel)

Configuration for a single domain expert.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `ConfigDict(extra='forbid')` |
| `expert_id` | `str` | `Field(description="Unique expert identifier (e.g., 'expert-security').")` |
| `expert_name` | `str` | `Field(description='Human-readable expert name.')` |
| `primary_domain` | `str` | `Field(description='Domain where this expert has primary authority.')` |
| `description` | `str` | `Field(default='', description="Short description of the expert's focus.")` |
| `rag_enabled` | `bool` | `Field(default=True, description='Whether RAG retrieval is enabled.')` |
| `knowledge_dir` | `str | None` | `Field(default=None, description='Override knowledge directory name (default: derived from domain).')` |
| `is_builtin` | `bool` | `Field(default=True, description='Whether this is a built-in technical expert.')` |
| `keywords` | `list[str]` | `Field(default_factory=list, description='Custom keywords for domain detection routing.')` |

### `KnowledgeChunk`(BaseModel)

A chunk of knowledge retrieved via RAG search.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `content` | `str` | `Field(description='Chunk text content.')` |
| `source_file` | `str` | `Field(description='Relative path to the source knowledge file.')` |
| `line_start` | `int` | `Field(description='Start line (1-indexed).')` |
| `line_end` | `int` | `Field(description='End line.')` |
| `score` | `float` | `Field(default=0.0, description='Relevance score (0.0-1.0).')` |

### `ConfidenceFactors`(BaseModel)

Factors used in confidence calculation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `rag_quality` | `float` | `Field(default=0.0, description='RAG retrieval quality (0.0-1.0).')` |
| `domain_relevance` | `float` | `Field(default=1.0, description='How relevant the domain is (0.0-1.0).')` |
| `source_count` | `int` | `Field(default=0, description='Number of knowledge sources found.')` |
| `chunk_coverage` | `float` | `Field(default=0.0, description='Fraction of query keywords covered by chunks.')` |

### `ConsultationResult`(BaseModel)

Result from an expert consultation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` | `Field(description='Domain that handled the consultation.')` |
| `expert_id` | `str` | `Field(description='Expert ID that responded.')` |
| `expert_name` | `str` | `Field(description='Human-readable expert name.')` |
| `answer` | `str` | `Field(description='Expert response text (markdown).')` |
| `confidence` | `float` | `Field(description='Confidence score (0.0-1.0).')` |
| `factors` | `ConfidenceFactors` | `Field(default_factory=ConfidenceFactors, description='Breakdown of confidence factors.')` |
| `sources` | `list[str]` | `Field(default_factory=list, description='Knowledge file sources used.')` |
| `chunks_used` | `int` | `Field(default=0, description='Number of RAG chunks used in response.')` |
| `detected_domains` | `list[DomainMapping]` | `Field(default_factory=list, description='Top domain matches when auto-detecting (empty when domain was explicit).')` |
| `recommendation` | `str` | `Field(default='', description='Actionable next-step recommendation based on confidence level.')` |
| `low_confidence_nudge` | `str | None` | `Field(default=None, description='Actionable nudge when confidence is low (e.g. suggest tapps_lookup_docs).')` |
| `suggested_tool` | `str | None` | `Field(default=None, description='Suggested tool to call next when confidence/context is insufficient.')` |
| `suggested_library` | `str | None` | `Field(default=None, description='Suggested library name for documentation lookup.')` |
| `suggested_topic` | `str | None` | `Field(default=None, description='Suggested topic to look up for documentation fallback.')` |
| `fallback_used` | `bool` | `Field(default=False, description='Whether automatic docs fallback content was merged into the answer.')` |
| `fallback_library` | `str | None` | `Field(default=None, description='Library used for automatic docs fallback lookup.')` |
| `fallback_topic` | `str | None` | `Field(default=None, description='Topic used for automatic docs fallback lookup.')` |
| `adaptive_domain_used` | `bool` | `Field(default=False, description='Whether the adaptive domain detector was used for domain resolution.')` |
| `stale_knowledge` | `bool` | `Field(default=False, description='Whether retrieved knowledge may be outdated (all top chunks > 365 days old).')` |
| `oldest_chunk_age_days` | `int | None` | `Field(default=None, description='Age in days of the oldest knowledge source file used.')` |
| `freshness_caveat` | `str | None` | `Field(default=None, description='Caveat message when knowledge sources are potentially outdated.')` |

### `DomainMapping`(BaseModel)

A detected domain with confidence score.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` | `Field(description='Expert domain name.')` |
| `confidence` | `float` | `Field(description='Detection confidence (0.0-1.0).')` |
| `signals` | `list[str]` | `Field(default_factory=list, description='Signal descriptions.')` |
| `reasoning` | `str` | `Field(default='', description='Why this domain was detected.')` |

### `StackDetectionResult`(BaseModel)

Result of project stack detection.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `detected_domains` | `list[DomainMapping]` | `Field(default_factory=list, description='Detected domains sorted by confidence.')` |
| `primary_language` | `str | None` | `Field(default=None, description='Primary programming language.')` |
| `primary_framework` | `str | None` | `Field(default=None, description='Primary framework detected.')` |

### `ExpertInfo`(BaseModel)

Public info about an expert (for tapps_list_experts).

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `expert_id` | `str` | `Field(description='Unique expert identifier.')` |
| `expert_name` | `str` | `Field(description='Human-readable name.')` |
| `primary_domain` | `str` | `Field(description='Primary domain of authority.')` |
| `description` | `str` | `Field(default='', description='Short description.')` |
| `rag_enabled` | `bool` | `Field(default=True, description='Whether RAG is active.')` |
| `knowledge_files` | `int` | `Field(default=0, description='Number of knowledge files loaded.')` |
| `is_builtin` | `bool` | `Field(default=True, description='Whether this is a built-in expert.')` |
| `keywords` | `list[str]` | `Field(default_factory=list, description='Custom domain detection keywords.')` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.query_expansion`

Query expansion with synonym matching for improved domain detection.

Maps common variants, abbreviations, and related terms to their canonical
keyword forms used in ``DOMAIN_KEYWORDS``.  This improves recall when users
phrase questions differently from the keywords defined in the detector.

## Functions

### `expand_query`

```python
def expand_query(question: str) -> str:
```

Expand a question by appending canonical synonyms for matched variants.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `question` | `str` | The raw user question. | *required* |

**Returns:** The question with canonical synonyms appended (space-separated).

### `expand_keywords`

```python
def expand_keywords(keywords: list[str]) -> list[str]:
```

Expand a list of keywords by adding canonical forms for any synonyms.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `keywords` | `list[str]` | List of keyword strings. | *required* |

**Returns:** Expanded list with canonical forms appended (no duplicates).

## Constants

| Name | Type | Value |
|------|------|-------|
| `SYNONYMS` | `dict[str, str]` | `{'vuln': 'vulnerability', 'vulns': 'vulnerability', 'vulnerabilities': 'vulnerability', 'auth': 'authentication', 'authn': 'authentication', 'authz': 'authorization', 'passwd': 'credential', 'password': 'credential', 'inject': 'sql injection', 'sqli': 'sql injection', 'cross-site scripting': 'xss', 'cross site scripting': 'xss', 'pen test': 'penetration', 'pentest': 'penetration', 'perf': 'performance', 'slowness': 'slow', 'lag': 'latency', 'response time': 'latency', 'concurrent': 'concurrency', 'threading': 'thread', 'multiprocessing': 'parallel', 'mem': 'memory', 'unittest': 'unit test', 'unittests': 'unit test', 'spec': 'test', 'specs': 'test', 'e2e test': 'e2e', 'end-to-end': 'e2e', 'end to end': 'e2e', 'mocking': 'mock', 'faking': 'stub', 'test driven': 'tdd', 'behavior driven': 'bdd', 'linter': 'lint', 'type checking': 'type check', 'typechecking': 'type check', 'tech debt': 'technical debt', 'code review': 'code quality', 'refactoring': 'refactor', 'microservices': 'microservice', 'di': 'dependency injection', 'ddd': 'domain driven', 'event-driven': 'event driven', 'event sourcing': 'event driven', 'cicd': 'ci', 'ci/cd': 'ci', 'continuous integration': 'ci', 'continuous delivery': 'cd', 'continuous deployment': 'cd', 'deploying': 'deployment', 'branching': 'branch', 'merging': 'merge', 'pull request': 'pr', 'infra': 'infrastructure', 'iac': 'infrastructure as code', 'k8s': 'kubernetes', 'kube': 'kubernetes', 'containers': 'container', 'containerize': 'container', 'containerization': 'containerization', 'fargate': 'serverless', 'cloud function': 'serverless', 'db': 'database', 'postgres': 'postgres', 'postgresql': 'postgres', 'mysql': 'mysql', 'mongo': 'mongodb', 'mariadb': 'mysql', 'sqlite': 'database', 'dynamo': 'nosql', 'dynamodb': 'nosql', 'cassandra': 'nosql', 'restful': 'rest', 'rest api': 'rest', 'gql': 'graphql', 'ws': 'websocket', 'websockets': 'websocket', 'logs': 'logging', 'traces': 'tracing', 'apm': 'monitoring', 'telemetry': 'opentelemetry', 'otel': 'opentelemetry', 'artificial intelligence': 'ai', 'deep learning': 'machine learning', 'dl': 'machine learning', 'nlp': 'llm', 'natural language': 'llm', 'chatbot': 'agent', 'chat bot': 'agent', 'retrieval augmented': 'rag', 'embeddings': 'embedding', 'finetuning': 'fine-tune', 'fine tuning': 'fine-tune', 'doc': 'documentation', 'documenting': 'documentation', 'pii': 'pii', 'personal data': 'pii', 'anonymization': 'anonymize', 'pseudonymization': 'pseudonymize', 'data breach': 'breach notification', 'benchmarking': 'benchmark', 'agentbench': 'benchmark', 'evaluation': 'benchmark', 'eval': 'benchmark', 'ablation': 'benchmark', 'template optimization': 'template', 'templates': 'template', 'platform generation': 'platform', 'platform rules': 'platform', 'skill generation': 'platform', 'hook generation': 'hook', 'hooks': 'hook', 'adaptive feedback': 'adaptive', 'adaptive learning': 'adaptive', 'weight adjustment': 'adaptive', 'reinforcement': 'reinforce', 'reinforcing': 'reinforce', 'sidecar': 'progress', 'progress file': 'progress', 'ctx.info': 'progress'}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.rag`

Simple file-based RAG system for expert knowledge retrieval.

Provides keyword search over markdown files in a ``knowledge/`` directory.
No vector database required — uses TF-based scoring with markdown-aware
chunking, deduplication, and prioritisation.

## Classes

### `SimpleKnowledgeBase`

File-based knowledge base with keyword search.

**Methods:**

#### `__init__`

```python
def __init__(self, knowledge_dir: Path, domain: str | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |
| `domain` | `str \| None` |  | None |

#### property `file_count`

```python
def file_count(self) -> int:
```

Number of loaded knowledge files.

#### `list_files`

```python
def list_files(self) -> list[str]:
```

Return relative paths of all loaded knowledge files.

#### `search`

```python
def search(self, query: str, max_results: int = 5, context_lines: int = 10, *, relevance_threshold: float = 0.2) -> list[KnowledgeChunk]:
```

Search knowledge base for relevant chunks.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` | Search query (natural language or keywords). | *required* |
| `max_results` | `int` | Maximum number of chunks to return. | 5 |
| `context_lines` | `int` | Lines of context around keyword matches. | 10 |
| `relevance_threshold` | `float` | Minimum score (0-1) for chunks to include. Chunks below this are filtered out to improve relevance. | 0.2 |

**Returns:** List of :class:`KnowledgeChunk` sorted by relevance (desc).

#### `get_context`

```python
def get_context(self, query: str, max_length: int = 2000) -> str:
```

Return a formatted context string for *query*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `max_length` | `int` |  | 2000 |

#### `get_sources`

```python
def get_sources(self, query: str, max_results: int = 5) -> list[str]:
```

Return source-file relative paths for *query*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `max_results` | `int` |  | 5 |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 87.5%*


---

# `packages.tapps-core.src.tapps_core.experts.rag_chunker`

Markdown-aware document chunker for RAG knowledge retrieval.

Splits markdown files into overlapping chunks of configurable token size,
respecting header boundaries where possible.

## Classes

### `Chunk`(BaseModel)

A single chunk of a knowledge document.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `content` | `str` | `Field(description='Chunk text content.')` |
| `source_file` | `str` | `Field(description='Source file path (as string for JSON serialization).')` |
| `line_start` | `int` | `Field(ge=1, description='Start line (1-indexed).')` |
| `line_end` | `int` | `Field(ge=1, description='End line (1-indexed).')` |
| `chunk_id` | `str` | `Field(description='Deterministic content hash (hex, 16 chars).')` |
| `token_count` | `int` | `Field(ge=0, description='Approximate token count.')` |

### `Chunker`

Splits markdown content into overlapping chunks.

**Methods:**

#### `__init__`

```python
def __init__(self, target_tokens: int = 512, overlap_tokens: int = 50) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `target_tokens` | `int` |  | 512 |
| `overlap_tokens` | `int` |  | 50 |

#### `chunk_file`

```python
def chunk_file(self, file_path: Path, content: str) -> list[Chunk]:
```

Split *content* into chunks, attributing them to *file_path*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `content` | `str` |  | *required* |

---

*Documentation coverage: 75.0%*


---

# `packages.tapps-core.src.tapps_core.experts.rag_embedder`

Embedding interface and optional sentence-transformers implementation.

The ``sentence-transformers`` and ``numpy`` packages are optional.  When
unavailable, :func:[`create_embedder`](#create-embedder) returns ``None`` and callers should
fall back to keyword-based search.

## Classes

### `Embedder`(ABC)

Abstract base class for text embedding.

**Methods:**

#### `embed`

```python
def embed(self, texts: list[str]) -> list[list[float]]:
```

Embed a batch of texts and return vectors.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `texts` | `list[str]` |  | *required* |

#### `get_embedding_dim`

```python
def get_embedding_dim(self) -> int:
```

Return the dimensionality of embeddings.

#### `get_model_name`

```python
def get_model_name(self) -> str:
```

Return the model identifier.

### `SentenceTransformerEmbedder`(Embedder)

Embedder backed by ``sentence-transformers``.

**Methods:**

#### `__init__`

```python
def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `model_name` | `str` |  | _DEFAULT_MODEL |

#### `embed`

```python
def embed(self, texts: list[str]) -> list[list[float]]:
```

Embed *texts* using the sentence-transformers model.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `texts` | `list[str]` |  | *required* |

#### `get_embedding_dim`

```python
def get_embedding_dim(self) -> int:
```

#### `get_model_name`

```python
def get_model_name(self) -> str:
```

## Functions

### `create_embedder`

```python
def create_embedder(model_name: str | None = None) -> Embedder | None:
```

Factory: return an :class:[`Embedder`](#embedder), or ``None`` if unavailable.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `model_name` | `str \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `SENTENCE_TRANSFORMERS_AVAILABLE` | `` | `_ff.sentence_transformers` |

---

*Documentation coverage: 75.0%*


---

# `packages.tapps-core.src.tapps_core.experts.rag_index`

FAISS-based vector index for RAG knowledge retrieval.

The ``faiss-cpu`` and ``numpy`` packages are optional.  When unavailable,
:class:[`VectorIndex`](#vectorindex) will raise :class:`ImportError` on construction.

## Classes

### `IndexMetadata`(BaseModel)

Metadata stored alongside a FAISS index on disk.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `schema_version` | `str` | `Field(default='1.0', description='Index format version.')` |
| `model_name` | `str` | `Field(description='Embedding model name.')` |
| `embedding_dim` | `int` | `Field(description='Embedding dimensionality.')` |
| `chunk_count` | `int` | `Field(ge=0, description='Number of indexed chunks.')` |
| `chunk_params` | `dict[str, Any]` | `Field(default_factory=dict, description='Chunker parameters used.')` |
| `source_files` | `list[str]` | `Field(default_factory=list, description='Source files included.')` |
| `source_fingerprint` | `str` | `Field(default='', description='Hash of source file set for invalidation.')` |

### `VectorIndex`

FAISS flat-L2 index over document chunks.

**Methods:**

#### `__init__`

```python
def __init__(self, embedder: Embedder | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `embedder` | `Embedder \| None` |  | None |

#### property `chunk_count`

```python
def chunk_count(self) -> int:
```

Number of chunks in the index.

#### `build`

```python
def build(self, chunks: list[Chunk], chunk_params: dict[str, Any] | None = None) -> None:
```

Build the FAISS index from *chunks*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `chunks` | `list[Chunk]` |  | *required* |
| `chunk_params` | `dict[str, Any] \| None` |  | None |

**Raises:**

- ValueError: If no embedder or chunks are provided.

#### `search`

```python
def search(self, query_text: str, top_k: int = 5, similarity_threshold: float = 0.7) -> list[tuple[Chunk, float]]:
```

Search the index for *query_text*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query_text` | `str` |  | *required* |
| `top_k` | `int` |  | 5 |
| `similarity_threshold` | `float` |  | 0.7 |

#### `save`

```python
def save(self, index_dir: Path) -> None:
```

Persist the index to *index_dir*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `index_dir` | `Path` |  | *required* |

#### classmethod `load`

```python
def load(cls, index_dir: Path, embedder: Embedder | None = None) -> VectorIndex:
```

Load a previously saved index from *index_dir*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `index_dir` | `Path` |  | *required* |
| `embedder` | `Embedder \| None` |  | None |

#### `is_valid`

```python
def is_valid(self) -> bool:
```

Check whether the loaded index has valid metadata.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `FAISS_AVAILABLE` | `` | `_ff.faiss` |

---

*Documentation coverage: 90.9%*


---

# `packages.tapps-core.src.tapps_core.experts.rag_warming`

Expert RAG index warming — pre-build vector indices from tech stack.

Maps tech stack (languages, frameworks, libraries, domains) to relevant
expert domains and pre-builds VectorKnowledgeBase indices so the first
tapps_consult_expert call for those domains is fast.

Also supports warming business expert RAG indices from project-local
knowledge directories.

## Functions

### `tech_stack_to_expert_domains`

```python
def tech_stack_to_expert_domains(tech_stack: TechStack) -> list[str]:
```

Map tech stack to relevant expert domain names.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tech_stack` | `TechStack` | Project tech stack from detect_project_profile. | *required* |

**Returns:** Deduplicated list of expert domain names to warm, ordered by
    relevance (domains first, then frameworks, then libraries).

### `warm_expert_rag_indices`

```python
def warm_expert_rag_indices(tech_stack: TechStack, *, max_domains: int = 10, index_base_dir: Path | None = None) -> dict[str, object]:
```

Pre-build VectorKnowledgeBase indices for expert domains relevant to tech stack.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tech_stack` | `TechStack` | Project tech stack. | *required* |
| `max_domains` | `int` | Maximum number of domains to warm. | 10 |
| `index_base_dir` | `Path \| None` | Base directory for per-domain indices. When provided, indices are stored at index_base_dir/{domain_slug}. When None, uses the default package-level location. | None |

**Returns:** Summary dict with warmed, attempted, domains, skipped reason.

### `warm_business_expert_rag_indices`

```python
def warm_business_expert_rag_indices(project_root: Path, *, max_domains: int = 10) -> dict[str, Any]:
```

Pre-build VectorKnowledgeBase indices for registered business experts.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Project root directory (knowledge lives under ``{project_root}/.tapps-mcp/knowledge/``). | *required* |
| `max_domains` | `int` | Maximum number of business domains to warm. | 10 |

**Returns:** Summary dict with ``warmed``, ``skipped``, and ``errors`` lists.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `TECH_STACK_TO_EXPERT_DOMAINS` | `dict[str, list[str]]` | `{'fastapi': ['api-design-integration'], 'flask': ['api-design-integration'], 'django': ['api-design-integration', 'software-architecture'], 'express': ['api-design-integration'], 'aiohttp': ['api-design-integration'], 'react': ['user-experience'], 'vue': ['user-experience'], 'angular': ['user-experience'], 'pytest': ['testing-strategies'], 'jest': ['testing-strategies'], 'unittest': ['testing-strategies'], 'ruff': ['code-quality-analysis'], 'mypy': ['code-quality-analysis'], 'pylint': ['code-quality-analysis'], 'docker': ['cloud-infrastructure', 'development-workflow'], 'kubernetes': ['cloud-infrastructure'], 'terraform': ['cloud-infrastructure'], 'aws': ['cloud-infrastructure'], 'azure': ['cloud-infrastructure'], 'gcp': ['cloud-infrastructure'], 'sqlalchemy': ['database-data-management'], 'postgres': ['database-data-management'], 'redis': ['database-data-management'], 'mongodb': ['database-data-management'], 'prometheus': ['observability-monitoring'], 'grafana': ['observability-monitoring'], 'opentelemetry': ['observability-monitoring'], 'tensorflow': ['ai-frameworks'], 'pytorch': ['ai-frameworks'], 'langchain': ['ai-frameworks'], 'web': ['user-experience', 'api-design-integration'], 'api': ['api-design-integration'], 'testing': ['testing-strategies'], 'database': ['database-data-management'], 'cloud': ['cloud-infrastructure'], 'devops': ['cloud-infrastructure', 'development-workflow'], 'ml': ['ai-frameworks'], 'data': ['database-data-management']}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.registry`

Built-in expert registry — 17-domain expert catalogue + business experts.

Each expert is an immutable ``ExpertConfig`` entry with a primary domain,
knowledge-directory override (where it differs from the domain slug), and
a short description.  The registry is the single source of truth for which
experts ship with TappsMCP.

Business experts can be registered at runtime via
:meth:`ExpertRegistry.register_business_experts`.  Built-in experts always
take precedence in merged lookups.

## Classes

### `ExpertRegistry`

Registry of built-in domain experts and optional business experts.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `TECHNICAL_DOMAINS` | `ClassVar[set[str]]` | `{'security', 'performance-optimization', 'testing-strategies', 'code-quality-analysis', 'software-architecture', 'development-workflow', 'data-privacy-compliance', 'accessibility', 'user-experience', 'documentation-knowledge-management', 'ai-frameworks', 'agent-learning', 'observability-monitoring', 'api-design-integration', 'cloud-infrastructure', 'database-data-management', 'github'}` |
| `BUILTIN_EXPERTS` | `ClassVar[list[ExpertConfig]]` | `[ExpertConfig(expert_id='expert-security', expert_name='Security Expert', primary_domain='security', description='Application security, vulnerability analysis, secure coding practices.'), ExpertConfig(expert_id='expert-performance', expert_name='Performance Expert', primary_domain='performance-optimization', description='Performance profiling, optimisation strategies, bottleneck analysis.', knowledge_dir='performance'), ExpertConfig(expert_id='expert-testing', expert_name='Testing Expert', primary_domain='testing-strategies', description='Test strategy, coverage analysis, testing best practices.', knowledge_dir='testing'), ExpertConfig(expert_id='expert-code-quality', expert_name='Code Quality & Analysis Expert', primary_domain='code-quality-analysis', description='Code quality metrics, static analysis, refactoring guidance.'), ExpertConfig(expert_id='expert-software-architecture', expert_name='Software Architecture Expert', primary_domain='software-architecture', description='System design, architectural patterns, scalability.'), ExpertConfig(expert_id='expert-devops', expert_name='Development Workflow Expert', primary_domain='development-workflow', description='CI/CD, build tooling, developer productivity.'), ExpertConfig(expert_id='expert-data-privacy', expert_name='Data Privacy & Compliance Expert', primary_domain='data-privacy-compliance', description='GDPR, HIPAA, data protection, compliance requirements.'), ExpertConfig(expert_id='expert-accessibility', expert_name='Accessibility Expert', primary_domain='accessibility', description='WCAG compliance, assistive technology, inclusive design.'), ExpertConfig(expert_id='expert-user-experience', expert_name='User Experience Expert', primary_domain='user-experience', description='UX patterns, usability, frontend best practices.'), ExpertConfig(expert_id='expert-documentation', expert_name='Documentation & Knowledge Management Expert', primary_domain='documentation-knowledge-management', description='Technical writing, API docs, knowledge-base management.'), ExpertConfig(expert_id='expert-ai-frameworks', expert_name='AI Agent Framework Expert', primary_domain='ai-frameworks', description='AI/ML frameworks, agent architectures, prompt engineering.'), ExpertConfig(expert_id='expert-agent-learning', expert_name='Agent Learning Best Practices Expert', primary_domain='agent-learning', description='Agent learning patterns, memory systems, adaptive behaviour.'), ExpertConfig(expert_id='expert-observability', expert_name='Observability & Monitoring Expert', primary_domain='observability-monitoring', description='Logging, metrics, tracing, alerting, dashboards.'), ExpertConfig(expert_id='expert-api-design', expert_name='API Design & Integration Expert', primary_domain='api-design-integration', description='REST/GraphQL design, API versioning, integration patterns.'), ExpertConfig(expert_id='expert-cloud-infrastructure', expert_name='Cloud & Infrastructure Expert', primary_domain='cloud-infrastructure', description='AWS/Azure/GCP, Kubernetes, Docker, IaC.'), ExpertConfig(expert_id='expert-database', expert_name='Database & Data Management Expert', primary_domain='database-data-management', description='SQL/NoSQL, schema design, query optimisation, migrations.'), ExpertConfig(expert_id='expert-github', expert_name='GitHub Platform Expert', primary_domain='github', description='GitHub Actions, Issues, PRs, rulesets, Copilot agent integration, and repository governance.')]` |

**Methods:**

#### classmethod `get_all_experts`

```python
def get_all_experts(cls) -> list[ExpertConfig]:
```

Return a copy of all built-in experts.

#### classmethod `get_expert_ids`

```python
def get_expert_ids(cls) -> list[str]:
```

Return a list of all built-in expert IDs.

#### classmethod `get_expert_by_id`

```python
def get_expert_by_id(cls, expert_id: str) -> ExpertConfig | None:
```

Look up an expert by ID.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `expert_id` | `str` |  | *required* |

#### classmethod `get_expert_for_domain`

```python
def get_expert_for_domain(cls, domain: str) -> ExpertConfig | None:
```

Look up the expert whose *primary_domain* matches *domain*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` |  | *required* |

#### classmethod `is_technical_domain`

```python
def is_technical_domain(cls, domain: str) -> bool:
```

Return ``True`` if *domain* is a recognised technical domain.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` |  | *required* |

#### classmethod `get_knowledge_base_path`

```python
def get_knowledge_base_path(cls) -> Path:
```

Return the path to the bundled knowledge-base directory.

#### classmethod `register_business_experts`

```python
def register_business_experts(cls, experts: list[ExpertConfig]) -> None:
```

Register business experts, validating no ID collisions.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `experts` | `list[ExpertConfig]` |  | *required* |

#### classmethod `clear_business_experts`

```python
def clear_business_experts(cls) -> None:
```

Reset business expert state (for testing and re-loading).

#### classmethod `get_all_experts_merged`

```python
def get_all_experts_merged(cls) -> list[ExpertConfig]:
```

Return all experts: built-in first, then business.

#### classmethod `get_expert_for_domain_merged`

```python
def get_expert_for_domain_merged(cls, domain: str) -> ExpertConfig | None:
```

Look up expert by domain, checking built-in first then business.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` |  | *required* |

#### classmethod `get_business_experts`

```python
def get_business_experts(cls) -> list[ExpertConfig]:
```

Return a copy of registered business experts.

#### classmethod `get_business_domains`

```python
def get_business_domains(cls) -> set[str]:
```

Return the set of registered business domain slugs.

#### classmethod `is_business_domain`

```python
def is_business_domain(cls, domain: str) -> bool:
```

Return ``True`` if *domain* is a registered business domain.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `domain` | `str` |  | *required* |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.experts.retrieval_eval`

Retrieval evaluation harness — benchmark queries, metrics, and quality gates.

Provides a standard benchmark query set across domains and measures retrieval
quality: top-k relevance, resolution accuracy, latency, and fallback rate.
Used by CI and manual evaluation to prevent regressions when tuning
ranking, fuzzy matching, or hybrid retrieval.

## Classes

### `BenchmarkQuery`

Decorators: `@dataclass`

A single benchmark query with expected retrieval properties.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `domain` | `str` |  |
| `query` | `str` |  |
| `expected_keywords` | `list[str]` | `field(default_factory=list)` |
| `min_chunks` | `int` | `1` |
| `description` | `str` | `''` |

### `QueryResult`

Decorators: `@dataclass`

Result of evaluating a single benchmark query.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `query` | `BenchmarkQuery` |  |
| `chunks_found` | `int` | `0` |
| `top_score` | `float` | `0.0` |
| `keyword_hits` | `int` | `0` |
| `keyword_total` | `int` | `0` |
| `latency_ms` | `float` | `0.0` |
| `passed` | `bool` | `False` |
| `backend_type` | `str` | `'unknown'` |

### `EvalReport`

Decorators: `@dataclass`

Aggregate evaluation report.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_queries` | `int` | `0` |
| `passed_queries` | `int` | `0` |
| `failed_queries` | `int` | `0` |
| `pass_rate` | `float` | `0.0` |
| `avg_latency_ms` | `float` | `0.0` |
| `p95_latency_ms` | `float` | `0.0` |
| `avg_top_score` | `float` | `0.0` |
| `avg_keyword_coverage` | `float` | `0.0` |
| `fallback_rate` | `float` | `0.0` |
| `results` | `list[QueryResult]` | `field(default_factory=list)` |
| `failures` | `list[str]` | `field(default_factory=list)` |

**Methods:**

#### `to_dict`

```python
def to_dict(self) -> dict[str, Any]:
```

## Functions

### `run_retrieval_eval`

```python
def run_retrieval_eval(queries: list[BenchmarkQuery] | None = None) -> EvalReport:
```

Run the retrieval evaluation harness.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `queries` | `list[BenchmarkQuery] \| None` | Optional override for benchmark queries (defaults to BENCHMARK_QUERIES). | None |

**Returns:** An EvalReport with per-query results and aggregate metrics.

### `check_quality_gates`

```python
def check_quality_gates(report: EvalReport) -> tuple[bool, list[str]]:
```

Check whether the eval report passes quality gates.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `report` | `EvalReport` |  | *required* |

**Returns:** (passed, violations) — True if all gates pass, with list of violation messages.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `BENCHMARK_QUERIES` | `list[BenchmarkQuery]` | `[BenchmarkQuery(domain='security', query='How to prevent SQL injection in Python?', expected_keywords=['sql', 'injection', 'parameterized', 'query'], description='Core security topic — must return relevant chunks'), BenchmarkQuery(domain='security', query='What are OWASP top 10 vulnerabilities?', expected_keywords=['owasp'], description='Well-known security framework'), BenchmarkQuery(domain='testing-strategies', query='How to write pytest fixtures for database tests?', expected_keywords=['pytest', 'fixture'], description='Testing best practice'), BenchmarkQuery(domain='testing-strategies', query='How to configure base URLs and environment variables in tests?', expected_keywords=['url', 'config'], description='Testing KB expansion validation (10.4)'), BenchmarkQuery(domain='api-design-integration', query='How to design RESTful API endpoints?', expected_keywords=['api', 'rest', 'endpoint'], description='API design fundamentals'), BenchmarkQuery(domain='database-data-management', query='What are best practices for database migrations?', expected_keywords=['migration', 'database'], description='Database management topic'), BenchmarkQuery(domain='performance-optimization', query='How to profile and optimize slow queries?', expected_keywords=['profile', 'performance'], description='Performance optimization'), BenchmarkQuery(domain='software-architecture', query='What design patterns work for microservices?', expected_keywords=['pattern', 'microservice'], description='Architecture fundamentals'), BenchmarkQuery(domain='cloud-infrastructure', query='How to write a secure Dockerfile?', expected_keywords=['docker'], description='Infrastructure security'), BenchmarkQuery(domain='code-quality-analysis', query='How to enforce type hints and linting?', expected_keywords=['type', 'lint'], description='Code quality enforcement')]` |
| `QUALITY_GATE_PASS_RATE` | `` | `0.6` |
| `QUALITY_GATE_P95_LATENCY_MS` | `` | `500.0` |
| `QUALITY_GATE_MIN_KEYWORD_COVERAGE` | `` | `0.3` |

---

*Documentation coverage: 90.9%*


---

# `packages.tapps-core.src.tapps_core.experts.vector_rag`

Vector RAG knowledge base with automatic FAISS fallback.

Provides the same interface as :class:`SimpleKnowledgeBase`.  When
``faiss-cpu`` is installed, uses semantic search via embeddings.  When
absent, transparently falls back to keyword-based
:class:`SimpleKnowledgeBase`.  Zero configuration required.

## Classes

### `VectorKnowledgeBase`

Knowledge base with optional vector search and automatic fallback.

**Methods:**

#### `__init__`

```python
def __init__(self, knowledge_dir: Path, domain: str | None = None, *, chunk_size: int = 512, overlap: int = 50, embedding_model: str = 'all-MiniLM-L6-v2', similarity_threshold: float = 0.7, index_dir: Path | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `knowledge_dir` | `Path` |  | *required* |
| `domain` | `str \| None` |  | None |
| `chunk_size` | `int` |  | 512 |
| `overlap` | `int` |  | 50 |
| `embedding_model` | `str` |  | 'all-MiniLM-L6-v2' |
| `similarity_threshold` | `float` |  | 0.7 |
| `index_dir` | `Path \| None` |  | None |

#### property `backend_type`

```python
def backend_type(self) -> str:
```

Return ``"vector"``, ``"simple"``, or ``"pending"``.

#### `search`

```python
def search(self, query: str, max_results: int = 5, context_lines: int = 10, *, relevance_threshold: float = 0.3) -> list[KnowledgeChunk]:
```

Search the knowledge base for *query*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `max_results` | `int` |  | 5 |
| `context_lines` | `int` |  | 10 |
| `relevance_threshold` | `float` |  | 0.3 |

#### `get_context`

```python
def get_context(self, query: str, max_length: int = 2000) -> str:
```

Return formatted context for *query*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `max_length` | `int` |  | 2000 |

#### `get_sources`

```python
def get_sources(self, query: str, max_results: int = 5) -> list[str]:
```

Return source file paths for *query*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `max_results` | `int` |  | 5 |

#### `list_files`

```python
def list_files(self) -> list[str]:
```

Return all loaded knowledge file paths.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 87.5%*


---

# `packages.tapps-core.src.tapps_core.knowledge`

Knowledge & documentation lookup system (Epic 2).

---

*Documentation coverage: 0.0%*


---

# `packages.tapps-core.src.tapps_core.knowledge.cache`

KB cache — file-based documentation cache with TTL and atomic writes.

Stores documentation as markdown files with metadata in JSON sidecars.
Uses ``filelock`` for cross-platform file locking (Windows compatible).

## Classes

### `CacheStats`

Decorators: `@dataclass`

Aggregate cache statistics.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_entries` | `int` | `0` |
| `total_size_bytes` | `int` | `0` |
| `hits` | `int` | `0` |
| `misses` | `int` | `0` |
| `stale_entries` | `int` | `0` |

### `KBCache`

Decorators: `@dataclass`

File-based knowledge base cache.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `cache_dir` | `Path` |  |
| `default_ttl` | `float` | `DEFAULT_TTL_SECONDS` |
| `staleness_policies` | `dict[str, float]` | `field(default_factory=lambda: dict(DEFAULT_STALENESS_POLICIES))` |
| `LOCK_TIMEOUT` | `ClassVar[float]` | `5.0` |

**Methods:**

#### `get`

```python
def get(self, library: str, topic: str = 'overview') -> CacheEntry | None:
```

Retrieve a cache entry, or ``None`` if not found.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library` | `str` |  | *required* |
| `topic` | `str` |  | 'overview' |

#### `put`

```python
def put(self, entry: CacheEntry) -> None:
```

Write or update a cache entry atomically.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `entry` | `CacheEntry` |  | *required* |

#### `has`

```python
def has(self, library: str, topic: str = 'overview') -> bool:
```

Check whether a cache entry exists (does not check staleness).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library` | `str` |  | *required* |
| `topic` | `str` |  | 'overview' |

#### `is_stale`

```python
def is_stale(self, library: str, topic: str = 'overview') -> bool:
```

Check whether a cache entry is stale (past TTL).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library` | `str` |  | *required* |
| `topic` | `str` |  | 'overview' |

#### `remove`

```python
def remove(self, library: str, topic: str = 'overview') -> bool:
```

Remove a cache entry.  Returns True if entry existed.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library` | `str` |  | *required* |
| `topic` | `str` |  | 'overview' |

#### `list_entries`

```python
def list_entries(self) -> list[CacheEntry]:
```

List all cache entries (metadata only, no content).

#### `clear`

```python
def clear(self) -> int:
```

Remove all cache entries.  Returns count of removed entries.

#### property `stats`

```python
def stats(self) -> CacheStats:
```

Return current cache statistics.

#### `evict_lru`

```python
def evict_lru(self, max_mb: int = 100) -> int:
```

Evict least-recently-used entries until cache is under *max_mb*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `max_mb` | `int` |  | 100 |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `DEFAULT_TTL_SECONDS` | `float` | `86400.0` |
| `DEFAULT_STALENESS_POLICIES` | `dict[str, float]` | `{'next': 43200.0, 'react': 43200.0, 'vue': 43200.0, 'svelte': 43200.0, 'python': 172800.0, 'flask': 172800.0, 'django': 172800.0, 'sqlalchemy': 172800.0}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.knowledge.circuit_breaker`

Circuit breaker — fail-fast wrapper for external API calls.

Prevents cascading failures by tracking consecutive failures and
opening the circuit (fast-failing) when the failure threshold is reached.

## Classes

### `CircuitState`(Enum)

Circuit breaker states.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `CLOSED` |  | `'closed'` |
| `OPEN` |  | `'open'` |
| `HALF_OPEN` |  | `'half_open'` |

### `CircuitBreakerOpenError`(Exception)

Raised when circuit is open and call is rejected.

### `CircuitBreakerConfig`

Decorators: `@dataclass`

Configuration for the circuit breaker.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `failure_threshold` | `int` | `3` |
| `success_threshold` | `int` | `2` |
| `timeout_seconds` | `float` | `10.0` |
| `reset_timeout_seconds` | `float` | `30.0` |
| `name` | `str` | `'context7'` |

### `CircuitBreakerStats`

Decorators: `@dataclass`

Runtime statistics for the circuit breaker.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_requests` | `int` | `0` |
| `successful_requests` | `int` | `0` |
| `failed_requests` | `int` | `0` |
| `rejected_requests` | `int` | `0` |
| `consecutive_failures` | `int` | `0` |
| `consecutive_successes` | `int` | `0` |
| `state` | `CircuitState` | `CircuitState.CLOSED` |
| `last_failure_time` | `float | None` | `None` |
| `last_state_change` | `float | None` | `None` |

### `CircuitBreaker`

Async circuit breaker for external API calls.

**Methods:**

#### `__init__`

```python
def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `config` | `CircuitBreakerConfig \| None` |  | None |

#### property `state`

```python
def state(self) -> CircuitState:
```

Current circuit state.

#### property `stats`

```python
def stats(self) -> CircuitBreakerStats:
```

Current statistics.

#### `force_open`

```python
def force_open(self, reason: str = '') -> None:
```

Force the circuit open (e.g., on quota exceeded).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `reason` | `str` |  | '' |

#### `reset`

```python
def reset(self) -> None:
```

Reset to initial closed state.

#### async `call`

```python
async def call(self, func: Callable[..., Any], *args: Any, fallback: Any = None, **kwargs: Any) -> Any:
```

Execute *func* with circuit breaker protection.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `func` | `Callable[..., Any]` | Async callable to execute. *args: Positional arguments for *func*. | *required* |
| `args` | `Any` |  | *required* |
| `fallback` | `Any` | Value to return when circuit is open or call fails. **kwargs: Keyword arguments for *func*. | None |
| `kwargs` | `Any` |  | *required* |

**Returns:** Result of *func* or *fallback*.

**Raises:**

- CircuitBreakerOpenError: If circuit is open and no fallback provided.

## Functions

### `get_context7_circuit_breaker`

```python
def get_context7_circuit_breaker() -> CircuitBreaker:
```

Return the global Context7 circuit breaker singleton.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 92.3%*


---

# `packages.tapps-core.src.tapps_core.knowledge.content_normalizer`

Context7 code-reference quality normalization.

Processes raw Context7 documentation content to:
1. Rank code snippets by completeness + query relevance.
2. Deduplicate similar snippets.
3. Format as compact "reference cards".
4. Enforce per-section token budgets to avoid context overflow.

## Classes

### `CodeSnippet`

Decorators: `@dataclass`

A code snippet extracted from documentation content.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `code` | `str` |  |
| `language` | `str` | `''` |
| `context` | `str` | `''` |
| `score` | `float` | `0.0` |
| `token_count` | `int` | `0` |

### `ReferenceCard`

Decorators: `@dataclass`

Compact reference card for a documentation section.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `title` | `str` |  |
| `snippets` | `list[CodeSnippet]` | `field(default_factory=list)` |
| `summary` | `str` | `''` |
| `token_count` | `int` | `0` |

**Methods:**

#### `to_markdown`

```python
def to_markdown(self) -> str:
```

### `NormalizationResult`

Decorators: `@dataclass`

Result of normalizing Context7 content.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `cards` | `list[ReferenceCard]` | `field(default_factory=list)` |
| `total_snippets` | `int` | `0` |
| `deduped_snippets` | `int` | `0` |
| `total_tokens` | `int` | `0` |
| `budget_applied` | `bool` | `False` |

**Methods:**

#### `to_markdown`

```python
def to_markdown(self) -> str:
```

#### `to_dict`

```python
def to_dict(self) -> dict[str, Any]:
```

## Functions

### `extract_snippets`

```python
def extract_snippets(content: str) -> list[CodeSnippet]:
```

Extract code snippets from markdown content.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `content` | `str` |  | *required* |

### `rank_snippets`

```python
def rank_snippets(snippets: list[CodeSnippet], query: str = '') -> list[CodeSnippet]:
```

Rank snippets by code completeness + query overlap + language fit.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `snippets` | `list[CodeSnippet]` |  | *required* |
| `query` | `str` |  | '' |

### `deduplicate_snippets`

```python
def deduplicate_snippets(snippets: list[CodeSnippet], threshold: float = _DEDUP_THRESHOLD) -> list[CodeSnippet]:
```

Remove near-duplicate snippets using Jaccard similarity.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `snippets` | `list[CodeSnippet]` |  | *required* |
| `threshold` | `float` |  | _DEDUP_THRESHOLD |

### `apply_token_budget`

```python
def apply_token_budget(snippets: list[CodeSnippet], budget: int = _DEFAULT_SECTION_TOKEN_BUDGET) -> list[CodeSnippet]:
```

Keep only snippets that fit within the token budget.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `snippets` | `list[CodeSnippet]` |  | *required* |
| `budget` | `int` |  | _DEFAULT_SECTION_TOKEN_BUDGET |

### `normalize_content`

```python
def normalize_content(content: str, query: str = '', section_token_budget: int = _DEFAULT_SECTION_TOKEN_BUDGET) -> NormalizationResult:
```

Normalise Context7 content into ranked, deduplicated reference cards.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `content` | `str` | Raw documentation content (markdown). | *required* |
| `query` | `str` | The user's query for relevance ranking. | '' |
| `section_token_budget` | `int` | Max tokens per reference card section. | _DEFAULT_SECTION_TOKEN_BUDGET |

**Returns:** NormalizationResult with compact reference cards.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 75.0%*


---

# `packages.tapps-core.src.tapps_core.knowledge.context7_client`

Context7 API client — async HTTP client for documentation lookup.

Endpoints (v2):
  - ``GET /api/v2/search?query={library}`` — resolve library name to ID
  - ``GET /api/v2/docs/{mode}/{library_id}?type=json&topic={topic}`` — fetch docs

Uses ``httpx`` with HTTP/2 and connection pooling.

## Classes

### `Context7Error`(Exception)

Raised when the Context7 API returns an error.

### `Context7Client`

Async HTTP client for the Context7 documentation API.

**Methods:**

#### `__init__`

```python
def __init__(self, api_key: SecretStr | None = None, *, base_url: str = CONTEXT7_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `api_key` | `SecretStr \| None` |  | None |
| `base_url` | `str` |  | CONTEXT7_BASE_URL |
| `timeout` | `float` |  | DEFAULT_TIMEOUT |

#### async `close`

```python
async def close(self) -> None:
```

Close the underlying HTTP client.

#### async `resolve_library`

```python
async def resolve_library(self, query: str) -> list[LibraryMatch]:
```

Resolve a library name query to a list of library matches.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` | Library name or search term. | *required* |

**Returns:** List of ``LibraryMatch`` objects, best match first.

**Raises:**

- Context7Error: On API failure.

#### async `fetch_docs`

```python
async def fetch_docs(self, library_id: str, *, topic: str = 'overview', mode: str = 'code', max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
```

Fetch documentation for a resolved library.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library_id` | `str` | Context7 library ID (e.g., ``"/vercel/next.js"``). | *required* |
| `topic` | `str` | Documentation topic. | 'overview' |
| `mode` | `str` | ``"code"`` for API references, ``"info"`` for conceptual guides. | 'code' |
| `max_tokens` | `int` | Maximum tokens in response. | DEFAULT_MAX_TOKENS |

**Returns:** Documentation content as a markdown string.

**Raises:**

- Context7Error: On API failure or empty response.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `CONTEXT7_BASE_URL` | `` | `'https://context7.com'` |
| `DEFAULT_TIMEOUT` | `` | `10.0` |
| `DEFAULT_MAX_TOKENS` | `` | `5000` |

---

*Documentation coverage: 90.0%*


---

# `packages.tapps-core.src.tapps_core.knowledge.fuzzy_matcher`

Fuzzy matcher v2 — multi-signal library name resolution.

Combines LCS similarity, edit distance, and token overlap for more
accurate library name matching.  Includes confidence bands and "did you
mean" suggestions for ambiguous matches.

No external fuzzy-matching library required.

## Functions

### `lcs_length`

```python
def lcs_length(a: str, b: str) -> int:
```

Compute the length of the Longest Common Subsequence of *a* and *b*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `a` | `str` |  | *required* |
| `b` | `str` |  | *required* |

### `lcs_similarity`

```python
def lcs_similarity(a: str, b: str) -> float:
```

Return a similarity score in [0.0, 1.0] based on LCS ratio.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `a` | `str` |  | *required* |
| `b` | `str` |  | *required* |

### `edit_distance`

```python
def edit_distance(a: str, b: str) -> int:
```

Compute the Levenshtein edit distance between *a* and *b*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `a` | `str` |  | *required* |
| `b` | `str` |  | *required* |

### `edit_distance_similarity`

```python
def edit_distance_similarity(a: str, b: str) -> float:
```

Return a similarity score in [0.0, 1.0] based on edit distance.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `a` | `str` |  | *required* |
| `b` | `str` |  | *required* |

### `token_overlap_score`

```python
def token_overlap_score(a: str, b: str) -> float:
```

Score overlap of tokens (split on hyphens, underscores, spaces).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `a` | `str` |  | *required* |
| `b` | `str` |  | *required* |

### `multi_signal_score`

```python
def multi_signal_score(query: str, candidate: str) -> float:
```

Combine LCS, edit distance, and token overlap into a single score.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `candidate` | `str` |  | *required* |

### `confidence_band`

```python
def confidence_band(score: float) -> str:
```

Classify a match score into a confidence band.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `score` | `float` |  | *required* |

### `resolve_alias`

```python
def resolve_alias(name: str) -> str:
```

Resolve a library alias to its canonical name.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `name` | `str` |  | *required* |

### `fuzzy_match_library`

```python
def fuzzy_match_library(query: str, known_libraries: list[str], *, threshold: float = 0.4, max_results: int = 5, project_libraries: list[str] | None = None) -> list[FuzzyMatch]:
```

Match *query* against *known_libraries* using multi-signal similarity.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` | Library name query string. | *required* |
| `known_libraries` | `list[str]` | List of known library names to match against. | *required* |
| `threshold` | `float` | Minimum similarity score to include. | 0.4 |
| `max_results` | `int` | Maximum number of results. | 5 |
| `project_libraries` | `list[str] \| None` | Libraries from project manifest for priority boost. | None |

**Returns:** Sorted list of FuzzyMatch results (best first).

### `did_you_mean`

```python
def did_you_mean(query: str, known_libraries: list[str], *, threshold: float = 0.3, max_suggestions: int = 3) -> list[str]:
```

Return "did you mean?" suggestions for a low-confidence or failed match.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` | The user's library name query. | *required* |
| `known_libraries` | `list[str]` | All known library names. | *required* |
| `threshold` | `float` | Minimum score for a suggestion. | 0.3 |
| `max_suggestions` | `int` | Maximum number of suggestions to return. | 3 |

**Returns:** List of library name suggestions, best first.

### `fuzzy_match_topic`

```python
def fuzzy_match_topic(query: str, topics: list[str], *, threshold: float = 0.3) -> FuzzyMatch | None:
```

Match *query* against available *topics* for a library.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `query` | `str` |  | *required* |
| `topics` | `list[str]` |  | *required* |
| `threshold` | `float` |  | 0.3 |

### `combined_score`

```python
def combined_score(library_score: float, topic_score: float, *, library_weight: float = 0.6, topic_weight: float = 0.4) -> float:
```

Compute a weighted combined score for library + topic match.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `library_score` | `float` |  | *required* |
| `topic_score` | `float` |  | *required* |
| `library_weight` | `float` |  | 0.6 |
| `topic_weight` | `float` |  | 0.4 |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `CONFIDENCE_HIGH` | `` | `0.85` |
| `CONFIDENCE_MEDIUM` | `` | `0.6` |
| `CONFIDENCE_LOW` | `` | `0.4` |
| `LIBRARY_ALIASES` | `dict[str, str]` | `{'pg': 'postgres', 'postgres': 'postgresql', 'tf': 'tensorflow', 'np': 'numpy', 'pd': 'pandas', 'plt': 'matplotlib', 'sk': 'scikit-learn', 'sklearn': 'scikit-learn', 'fa': 'fastapi', 'dj': 'django', 'bs4': 'beautifulsoup4', 'cv2': 'opencv-python', 'opencv': 'opencv-python', 'jwt': 'pyjwt', 'aio': 'aiohttp', 'boto': 'boto3', 'rx': 'rxpy', 'tz': 'pytz', 'ws': 'websockets'}` |
| `LANGUAGE_HINTS` | `dict[str, str]` | `{'fastapi': 'python', 'django': 'python', 'flask': 'python', 'sqlalchemy': 'python', 'pydantic': 'python', 'pytest': 'python', 'numpy': 'python', 'pandas': 'python', 'tensorflow': 'python', 'pytorch': 'python', 'react': 'javascript', 'next': 'javascript', 'vue': 'javascript', 'svelte': 'javascript', 'express': 'javascript', 'nest': 'typescript', 'angular': 'typescript'}` |

---

*Documentation coverage: 100.0%*


---

# `packages.tapps-core.src.tapps_core.knowledge.import_analyzer`

Analyze Python file imports to detect uncached external libraries.

Used by ``tapps_score_file`` to nudge the LLM toward calling
``tapps_lookup_docs`` for libraries whose docs are not yet cached.

## Functions

### `extract_external_imports`

```python
def extract_external_imports(file_path: Path, project_root: Path) -> list[str]:
```

Parse file AST and return sorted external import names.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` | Path to the Python file to analyze. | *required* |
| `project_root` | `Path` | Project root for detecting local packages. | *required* |

**Returns:** Sorted list of external top-level module names.

### `find_uncached_libraries`

```python
def find_uncached_libraries(external_imports: list[str], cache: KBCache) -> list[str]:
```

Check which external imports are not in the docs cache.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `external_imports` | `list[str]` | List of external module names. | *required* |
| `cache` | `KBCache` | The knowledge base cache to check against. | *required* |

**Returns:** List of module names with no cached documentation.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*

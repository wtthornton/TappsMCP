# `packages.tapps-mcp.src.tapps_mcp.server_analysis_tools`

Analysis and inspection tool handlers for TappsMCP.

Contains: tapps_report, tapps_dead_code, tapps_dependency_scan,
tapps_dependency_graph, tapps_session_notes, tapps_impact_analysis.

Functions are defined at module level (importable for tests) and
registered on the `mcp` instance via [`register`](#register).

All tools in this module are **read-only** (no file modifications) and include
MCP `ToolAnnotations` with `readOnlyHint=True` and `destructiveHint=False`.
`tapps_dependency_scan` additionally has `openWorldHint=True` (network access to vulnerability databases).

---

## Functions

### async `tapps_session_notes`

```python
async def tapps_session_notes(action: str, key: str = '', value: str = '') -> dict[str, Any]:
```

Persist notes across the session to avoid losing context.

Session notes are an **in-memory key-value store** scoped to the current project, with
JSON persistence for crash recovery. Notes are stored under `.tapps-mcp/sessions/` and
automatically recovered from the most recent session file on startup.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `action` | `str` | One of `"save"`, `"get"`, `"list"`, `"clear"`, `"promote"`. | *required* |
| `key` | `str` | Note key (required for save/get/promote). | `''` |
| `value` | `str` | Note value (required for save). For promote, optional tier name (defaults to `"context"`). | `''` |

**Actions:**

| Action | Description | Required params |
|--------|-------------|-----------------|
| `save` | Store or update a note by key. Returns the saved note. | `key`, `value` |
| `get` | Retrieve a single note by key. Returns `found: true/false`. | `key` |
| `list` | Return all notes for the current session. | (none) |
| `clear` | Clear a single note (if `key` provided) or all notes. Returns `cleared_count`. | (optional `key`) |
| `promote` | Promote a session note to the **persistent memory store** (`tapps_memory`). The note is saved with `tier=<value>` (default `"context"`), `scope="session"`, and tagged `"promoted-from-session-notes"`. | `key` |

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | The action that was performed. |
| `note` | `object\|null` | The note object (for save/get). Contains `key`, `value`, `created_at`, `updated_at`. |
| `found` | `bool` | Whether the note was found (get action). |
| `notes` | `list[object]` | All notes (list action). |
| `cleared_count` | `int` | Number of notes cleared (clear action). |
| `promoted` | `bool` | Whether promotion succeeded (promote action). |
| `memory_entry` | `object` | The created memory entry (promote action, on success). |
| `session_id` | `str` | Current session identifier (12-char hex). |
| `session_started` | `str` | ISO timestamp of session start. |
| `note_count` | `int` | Total notes in the session. |
| `migration_hint` | `str` | Always present: `"Use tapps_memory for persistent cross-session storage."` |

---

### async `tapps_impact_analysis`

```python
async def tapps_impact_analysis(file_path: str, change_type: str = 'modified') -> dict[str, Any]:
```

REQUIRED before refactoring or deleting files. Maps the blast radius.

Uses AST-based import graph analysis to identify all files affected by a change,
including direct dependents, transitive dependents, and test files that should be re-run.
Severity is classified based on the total number of affected files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the file being changed. | *required* |
| `change_type` | `str` | One of `"added"`, `"modified"`, `"removed"`. | `'modified'` |

**Severity levels:**

| Severity | Condition |
|----------|-----------|
| `critical` | 10+ affected files |
| `high` | 5-9 affected files |
| `medium` | 2-4 affected files |
| `low` | 0-1 affected files |

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `changed_file` | `str` | The file being changed. |
| `change_type` | `str` | The type of change. |
| `severity` | `str` | Impact severity (`low`, `medium`, `high`, `critical`). |
| `total_affected` | `int` | Total number of affected files. |
| `direct_dependents` | `list[object]` | Files that directly import the changed file. Each has `file_path` and import details. |
| `transitive_dependents` | `list[object]` | Files that import direct dependents. |
| `test_files` | `list[object]` | Test files that should be re-run. |
| `recommendations` | `list[str]` | Actionable suggestions (e.g., "Run affected tests", "Review dependent modules"). |

**Structured output:** Returns `ImpactOutput` via `structuredContent` for machine-parseable consumption, containing `changed_file`, `change_type`, `severity`, `total_affected`, `direct_dependents` (file paths), `test_files` (file paths), and `recommendations`.

---

### async `tapps_report`

```python
async def tapps_report(file_path: str = '', report_format: str = 'json', max_files: int = 20, ctx: Context | None = None) -> dict[str, Any]:
```

Generate a quality report combining scoring and gate results.

Operates in two modes:
- **Single-file mode**: When `file_path` is provided, scores that one file and evaluates its quality gate.
- **Project-wide mode**: When `file_path` is omitted, discovers all `.py` files in the project (excluding `.venv*`, `node_modules`, `dist`, `build`, `__pycache__`, and other generated directories), scores up to `max_files`, and aggregates results.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to a Python file. Omit for project-wide report. | `''` |
| `report_format` | `str` | Output format: `"json"`, `"markdown"`, or `"html"`. | `'json'` |
| `max_files` | `int` | Maximum files to score in project-wide mode. | `20` |

**Progress reporting (project-wide mode):**

- **MCP context notifications**: Emits `ctx.info()` messages as each file is scored (e.g., `"Scored scorer.py: 82/100"`).
- **MCP progress heartbeat**: Reports `ctx.report_progress()` every 5 seconds with `progress/total` counts.
- **Sidecar progress file**: Writes real-time progress to `.tapps-mcp/.report-progress.json` for external consumers (e.g., Claude Code hooks). Contains `status` (`"running"`/`"completed"`/`"error"`), `total`, `completed`, `last_file`, `started_at`, and per-file `results` with scores.

**Response:** Delegates to `project.report.generate_report()` which formats score and gate results according to `report_format`. The report includes per-file scores, category breakdowns, gate pass/fail status, and aggregate statistics.

---

### async `tapps_dead_code`

```python
async def tapps_dead_code(file_path: str = '', min_confidence: int = 80, scope: str = 'file', ctx: Context | None = None) -> dict[str, Any]:
```

Scan a Python file for dead code (unused functions, classes, imports, variables).

Uses **Vulture** for detection. When Vulture is not installed, results are marked `degraded: true` with reduced accuracy.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to scan (required when `scope="file"`). | `''` |
| `min_confidence` | `int` | Minimum confidence threshold (0-100). Clamped to valid range. | `80` |
| `scope` | `str` | Scan scope: `"file"` (single file), `"project"` (all `.py` files), or `"changed"` (git-changed `.py` files only). | `'file'` |

**Configuration (from settings):**

| Setting | Description |
|---------|-------------|
| `dead_code_whitelist_patterns` | List of glob patterns to exclude from dead code detection (e.g., `"test_*"`, `"conftest.py"`). |

**Behavior by scope:**

| Scope | Behavior |
|-------|----------|
| `file` | Scans a single file. `file_path` is required. |
| `project` | Collects all `.py` files in the project (excluding skip dirs), runs multi-file scan with 120-second timeout. |
| `changed` | Collects only git-changed `.py` files, runs multi-file scan with 120-second timeout. |

**Progress reporting** (project/changed scope): Emits `ctx.info()` messages with file count at start and summary at completion.

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `str` | Scanned file or project root path. |
| `scope` | `str` | The scan scope used. |
| `total_findings` | `int` | Total dead code items found. |
| `files_scanned` | `int` | Number of files scanned. |
| `degraded` | `bool` | `true` if Vulture is not installed (AST fallback). |
| `min_confidence` | `int` | The confidence threshold used. |
| `by_type` | `dict[str, list]` | Findings grouped by type (e.g., `"unused-import"`, `"unused-function"`, `"unused-variable"`, `"unused-class"`). Each finding has `name`, `line`, `confidence`, `message`, and (for multi-file) `file_path`. |
| `type_counts` | `dict[str, int]` | Count of findings per type. |
| `summary` | `str` | Human-readable summary (e.g., `"Found 5 dead code items in 3 file(s) (2 unused-import, 3 unused-function)"`). |

---

### async `tapps_dependency_scan`

```python
async def tapps_dependency_scan(project_root: str = '', ctx: Context | None = None) -> dict[str, Any]:
```

Scan project dependencies for known vulnerabilities using pip-audit.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path. Defaults to server's configured root. | `''` |

**Configuration (from settings):**

| Setting | Type | Description |
|---------|------|-------------|
| `dependency_scan_enabled` | `bool` | Master switch. When `False`, returns immediately with `scan_source: "disabled"`. |
| `dependency_scan_source` | `str` | Vulnerability data source for pip-audit. |
| `dependency_scan_severity_threshold` | `str` | Minimum severity to report (e.g., `"low"`, `"medium"`, `"high"`, `"critical"`). |
| `dependency_scan_ignore_ids` | `list[str]` | Vulnerability IDs to ignore (e.g., `["PYSEC-2024-1234"]`). |

**Side effects:**
- **Populates session cache**: On success, stores findings in a session-level cache (`dependency_scan_cache`). This cache is consumed by `tapps_score_file` to apply dependency penalties to quality scores, and by `tapps_dependency_graph` for vulnerability cross-referencing.

**Progress reporting**: Reports `ctx.report_progress()` heartbeat every 5 seconds showing elapsed time during the scan.

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `scanned_packages` | `int` | Number of packages scanned. |
| `vulnerable_packages` | `int` | Number of packages with vulnerabilities. |
| `total_findings` | `int` | Total vulnerability findings. |
| `scan_source` | `str` | Data source used (or `"disabled"` if scanning is off). |
| `by_severity` | `dict[str, list]` | Findings grouped by severity. Each finding has `package`, `installed_version`, `fixed_version`, `vulnerability_id`, and `description` (truncated to 200 chars). |
| `severity_counts` | `dict[str, int]` | Count of findings per severity level. |
| `summary` | `str` | Human-readable summary (e.g., `"Scanned 45 packages: 3 vulnerabilities (1 high, 2 medium)"`). |
| `error` | `str` | Present only if pip-audit encountered an error. |

---

### async `tapps_dependency_graph`

```python
async def tapps_dependency_graph(project_root: str = '', detect_cycles: bool = True, include_coupling: bool = True, ctx: Context | None = None) -> dict[str, Any]:
```

Analyze import dependencies: detect circular imports and measure coupling.

Builds a full import graph of the project, then optionally runs cycle detection and
coupling metrics analysis. Runs synchronously in a thread pool to avoid blocking the
event loop.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Project root path. Defaults to server's configured root. | `''` |
| `detect_cycles` | `bool` | Whether to detect circular dependency cycles. | `True` |
| `include_coupling` | `bool` | Whether to calculate coupling metrics (afferent/efferent). | `True` |

**Progress reporting**: Emits `ctx.info()` messages at each phase: `"Building import graph..."`, cycle detection results, coupling analysis results, and final summary.

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `project_root` | `str` | The analyzed project root. |
| `total_modules` | `int` | Total modules discovered. |
| `total_edges` | `int` | Total import edges in the graph. |

**Cycle detection** (when `detect_cycles=True`):

| Field | Type | Description |
|-------|------|-------------|
| `cycles.total` | `int` | Total circular dependency cycles found. |
| `cycles.runtime_cycles` | `int` | Cycles that affect runtime imports. |
| `cycles.type_checking_cycles` | `int` | Cycles only in `TYPE_CHECKING` blocks. |
| `cycles.details` | `list` | Up to 10 cycle details, each with `modules` (list of module names), `length`, `severity`, and `description`. |
| `cycle_suggestions` | `list[str]` | Fix suggestions for the top 5 cycles (e.g., move imports to `TYPE_CHECKING`, use dependency injection). |

**Coupling metrics** (when `include_coupling=True`):

| Field | Type | Description |
|-------|------|-------------|
| `coupling.total_modules_analysed` | `int` | Modules with coupling data. |
| `coupling.hub_count` | `int` | Modules classified as hubs (high connectivity). |
| `coupling.top_coupled` | `list` | Top 10 modules by coupling, each with `module`, `afferent` (incoming), `efferent` (outgoing), `instability` (0.0-1.0), and `is_hub`. |
| `coupling_suggestions` | `list[str]` | Fix suggestions for the top 5 most coupled modules. |

**Vulnerability cross-referencing**: When `tapps_dependency_scan` has been run in the same session, the graph automatically cross-references external imports with cached vulnerability findings. If vulnerable packages are imported, the response includes:

| Field | Type | Description |
|-------|------|-------------|
| `vulnerability_impact.total_vulnerable_imports` | `int` | Number of imports of vulnerable packages. |
| `vulnerability_impact.most_exposed_modules` | `list[str]` | Up to 10 modules most exposed to vulnerable dependencies. |
| `vulnerability_impact.impacts` | `list` | Up to 10 vulnerability impacts, each with `package`, `vulnerability_id`, `severity`, `importing_modules` (up to 10), and `import_count`. |

---

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register analysis tools on the shared *mcp_instance*.

Registers all six analysis tools with appropriate `ToolAnnotations`:
- `tapps_session_notes`, `tapps_impact_analysis`, `tapps_report`, `tapps_dead_code`, `tapps_dependency_graph`: `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`
- `tapps_dependency_scan`: `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=False`, `openWorldHint=True` (network access)

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` | The shared FastMCP server instance. | *required* |

---

## Internal Helpers

| Helper | Description |
|--------|-------------|
| `_validate_file_path_lazy(file_path)` | Delegates to `server._validate_file_path` for path security validation (sandbox enforcement). |
| `_record_call(tool_name)` | Records tool invocation for checklist tracking. |
| `_record_execution(tool_name, start_ns, ...)` | Records execution metrics (duration, status, score, gate pass/fail). |
| `_with_nudges(tool_name, response)` | Appends contextual nudges (next-step suggestions) to the response. |
| `_get_session_store()` | Lazily creates the `SessionNoteStore` singleton (scoped to project root). |
| `_promote_note_to_memory(note, tier)` | Promotes a session note to persistent memory via `tapps_memory`. |
| `_ReportProgressTracker` | Dataclass managing sidecar progress file writes for `tapps_report`. |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `BoundLogger` | `structlog.get_logger(__name__)` |
| `_ANNOTATIONS_READ_ONLY` | `ToolAnnotations` | `readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False` |
| `_ANNOTATIONS_READ_ONLY_OPEN` | `ToolAnnotations` | `readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True` |
| `_REPORT_PROGRESS_FILE` | `str` | `".tapps-mcp/.report-progress.json"` |

---

*Documentation coverage: 100.0%*

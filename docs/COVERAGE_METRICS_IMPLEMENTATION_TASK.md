# Coverage Metrics Fix — Implementation Task

**Date:** 2026-02-22  
**Source:** TAPPSMCP_COVERAGE_METRICS_RESEARCH.md (HomeIQ)  
**Status:** Implemented

---

## Problem Statement

The TappsMCP dashboard `coverage_metrics` section returns zeros for `files_scored`, `files_gated`, `files_scanned`, `docs_lookup_calls`, and `checklist_calls` even when `tool_calls_*.jsonl` contains valid records with non-null `file_path`.

**Observed:**
- `tool_metrics`: tapps_score_file: 36, tapps_quality_gate: 10, tapps_security_scan: 5
- `coverage_metrics`: files_scored: 0, files_gated: 0, files_scanned: 0

---

## Root Causes

### 1. Data Source Mismatch (Primary)

- `_build_tool_metrics` uses `get_summary_by_tool()` → `_load_from_disk()` → reads JSONL files
- `_build_coverage_metrics` uses `get_recent(limit=500)` → in-memory buffer only (max 100 items)
- When the MCP server restarts or runs in a different process, the buffer is empty while disk has data
- Result: tool_metrics shows correct counts from disk; coverage_metrics shows zeros from empty buffer

### 2. Path Normalization (Secondary — Windows)

- On Windows, same file can appear as:
  - `C:\cursor\HomeIQ\services\weather-api\src\main.py`
  - `c:\cursor\HomeIQ\services\weather-api\src\main.py`
  - `services/weather-api/src/main.py` (relative)
- Without normalization, these count as 3 distinct files in the coverage sets
- Backslash vs forward slash and case differences cause incorrect deduplication

---

## Implementation Plan

### Task 1: Use Disk Data for Coverage Metrics

**File:** `src/tapps_mcp/metrics/execution_metrics.py`

- Add method `get_recent_from_disk(limit: int = 500) -> list[ToolCallMetric]`:
  - Call `_load_from_disk(since=None, until=None)` to load all metrics
  - Sort by `started_at` descending (most recent first)
  - Return the first `limit` items

**File:** `src/tapps_mcp/metrics/dashboard.py`

- In `_build_coverage_metrics`, replace:
  ```python
  recent = self._execution.get_recent(limit=500)
  ```
  with:
  ```python
  recent = self._execution.get_recent_from_disk(limit=500)
  ```

### Task 2: Normalize File Paths for Deduplication

**File:** `src/tapps_mcp/metrics/dashboard.py`

- Add helper `_normalize_file_path(file_path: str, project_root: Path | None) -> str`:
  - Resolve path with `Path(file_path).resolve()` for consistent canonical form
  - On Windows, `Path.resolve()` yields case- and slash-normalized paths
  - Return `str(resolved)` for use as set key
  - Handle invalid paths gracefully (return original or skip)

- In `_build_coverage_metrics`, when building sets:
  - Derive `project_root` from `self._metrics_dir.parent.parent` (structure: project_root/.tapps-mcp/metrics)
  - Use normalized paths as set keys: `{_normalize_file_path(m.file_path, project_root) for m in recent if ... and m.file_path}`

### Task 3: Unit Tests

- Add test for `get_recent_from_disk` with disk-backed metrics (no buffer)
- Add test for coverage metrics with Windows-style absolute paths
- Add test for path normalization deduplication (C:\ vs c:\ vs relative)

---

## Acceptance Criteria

- [x] `coverage_metrics.files_scored` matches count of unique files in tool_calls with `tapps_score_file` and non-null `file_path`
- [x] `coverage_metrics.files_gated` and `files_scanned` correctly populated from disk
- [x] On Windows, path normalization deduplicates `C:\project\foo.py` and relative `foo.py` via `_normalize_file_path`
- [x] Dashboard shows non-zero coverage when JSONL has valid records, even after server restart

## Implemented Changes

- `execution_metrics.py`: Added `get_recent_from_disk(limit)` to load metrics from JSONL files
- `dashboard.py`: `_build_coverage_metrics` now uses `get_recent_from_disk` instead of `get_recent`
- `dashboard.py`: Added `_normalize_file_path()` for Windows case/slash deduplication
- Tests: `test_get_recent_from_disk`, `test_coverage_metrics_from_disk`

---

## References

- TAPPSMCP_COVERAGE_METRICS_RESEARCH.md (HomeIQ)
- `src/tapps_mcp/metrics/dashboard.py` — `_build_coverage_metrics`
- `src/tapps_mcp/metrics/execution_metrics.py` — `get_recent`, `_load_from_disk`

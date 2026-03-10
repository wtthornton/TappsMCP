# Story 75.1: Docker Path Mismatch Resolution

**Epic:** [EPIC-75-DOCKER-PIPELINE-RELIABILITY](../EPIC-75-DOCKER-PIPELINE-RELIABILITY.md)
**Priority:** P1 | **LOE:** 3–4 days | **Recurrence:** 4

## Problem

When TappsMCP runs inside a Docker container (via Docker MCP or `docker run`), `tapps_session_start` resolves `project_root` to `/workspace` — the container's mount point. The host project root (e.g. `C:\cursor\HomeIQ`) is not surfaced. All subsequent tool calls (`tapps_quick_check`, `tapps_validate_changed`, etc.) expect container-relative paths, but automated pipelines generate paths from host-side `git show` or `git diff` output.

This mismatch is silent — no warning, no error, no path mapping hint. Callers must manually translate paths or discover the mismatch through trial and error.

**Observed in:** 4 consecutive sessions across HomeIQ automated bugfix pipeline.

## Root Cause Analysis

1. `tapps_session_start` calls `Path.cwd()` or equivalent to resolve project root — inside Docker this is always the mount target (e.g. `/workspace`).
2. No mechanism exists to pass the host-side root or detect that TappsMCP is running in a container.
3. The Docker MCP proxy doesn't inject host path metadata into tool calls.

## Tasks

- [ ] Add `TAPPS_HOST_ROOT` environment variable support: when set, `tapps_session_start` includes `host_root` in its response alongside `project_root`.
- [ ] Add container detection heuristic (check `/.dockerenv`, `/proc/1/cgroup`, or `TAPPS_DOCKER=1` env var) to `tapps_session_start`.
- [ ] When running in a detected container, emit a `path_mapping` field in session start response: `{"container_root": "/workspace", "host_root": "<from env>", "mapping_available": true/false}`.
- [ ] If `TAPPS_HOST_ROOT` is not set and container is detected, emit a warning in session start output: "Running in container — set TAPPS_HOST_ROOT for accurate path mapping."
- [ ] Add a `translate_path(host_path: str) -> str` utility that converts host paths to container paths using the mapping, for use by callers.
- [ ] Update Docker MCP config templates (`tapps_init` Docker companion) to pass `TAPPS_HOST_ROOT` by default via `-e` flag.
- [ ] Add unit tests: container detection, path mapping, translate_path, env var precedence.
- [ ] Add integration test: session_start in mock container env returns correct mapping.

## Acceptance Criteria

- [ ] `tapps_session_start` response includes `path_mapping` when running in a container.
- [ ] `TAPPS_HOST_ROOT` env var correctly populates `host_root` in mapping.
- [ ] Warning emitted when container detected but `TAPPS_HOST_ROOT` not set.
- [ ] `tapps_init` Docker templates include `TAPPS_HOST_ROOT` by default.
- [ ] Backward compatible — non-Docker runs unaffected.
- [ ] Tests cover all paths: Docker with env, Docker without env, non-Docker.

## Files (likely)

- `packages/tapps-mcp/src/tapps_mcp/server.py` (session_start handler)
- `packages/tapps-core/src/tapps_core/common/utils.py` (container detection, path translation)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (Docker template updates)
- `packages/tapps-mcp/tests/unit/test_server.py`
- `packages/tapps-core/tests/unit/test_common_utils.py`

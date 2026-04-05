# Story 93.4 -- Async and Blocking I/O Correctness

<!-- docsmcp:start:user-story -->

> **As a** user of the MCP server, **I want** async tool handlers to never block the event loop, **so that** concurrent tool calls do not stall each other and tool latency stays predictable under load.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Blocking calls inside `async def` handlers silently stall the asyncio event loop. This story finds every such call site and fixes it, so that MCP tool concurrency actually works.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Audit every `async def` in `packages/*/src/` for synchronous blocking calls. Common offenders: `open(...).read()`, `Path.read_text`, `Path.write_text`, `subprocess.run`, `requests.get`, `time.sleep`, `json.dump` on large files. Replace with async equivalents (`aiofiles`, `asyncio.create_subprocess_exec`, `httpx.AsyncClient`, `asyncio.sleep`) or wrap via `asyncio.to_thread` when an async equivalent is not warranted.

Add a test or lint rule (e.g., a grep-based CI check) that prevents regression.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-mcp/src/tapps_mcp/server*.py`
- `packages/docs-mcp/src/docs_mcp/server*.py`
- `packages/tapps-mcp/src/tapps_mcp/tools/**/*.py`
- `packages/docs-mcp/src/docs_mcp/generators/**/*.py`
- CI config or a test-based guard

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Grep each `async def` body for blocking-call patterns
- [ ] Replace each with async equivalent or `asyncio.to_thread` wrapper
- [ ] Benchmark tool latency before and after to confirm no regression
- [ ] Add guard test that greps for blocking calls inside async handlers
- [ ] Verify MCP concurrency works via a scripted concurrent-call test

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Zero blocking I/O calls in async handlers
- [ ] Guard test prevents regression
- [ ] Tool latency unchanged or improved
- [ ] Concurrent tool calls no longer serialize

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

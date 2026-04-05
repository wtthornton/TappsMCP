# Story 93.5 -- Error Handling and Logging Consistency

<!-- docsmcp:start:user-story -->

> **As a** developer diagnosing a production issue, **I want** narrow exception handling and consistent structured logs, **so that** I can trace what failed without reading stack traces or grep-filtering `print()` noise.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Broad `except Exception:` swallows bugs. Inconsistent logging (print, stdlib logging, structlog) makes debugging slower. This story narrows exception handling and standardizes on structlog everywhere.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Grep for `except Exception` and bare `except:` in `packages/*/src/`. For each, determine the minimum-necessary exception set and narrow the clause. Confirm every error path emits a structlog entry with tool name, file path, and correlation id when available.

Grep for `print(` and `import logging` in `src/`. Replace with `structlog.get_logger()` calls. Keep CLI output (via `typer.echo` or equivalent) only when the function is an entry-point command, not a library function.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/*/src/**/*.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Grep `except Exception` and `except:` in `src/`
- [ ] Narrow each to specific exception types
- [ ] Verify every error path emits a structlog entry with context
- [ ] Grep `print(` and `import logging` in `src/`
- [ ] Convert each to `structlog` (except CLI entry points)
- [ ] Add regression test if any critical error-path log was missing

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Zero bare `except:` clauses in `src/`
- [ ] Every `except Exception` is either narrowed or documented as intentional
- [ ] Zero `print(` calls outside CLI entry points
- [ ] Zero `import logging` in `src/` (structlog only)
- [ ] Error logs include tool/file/correlation context

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

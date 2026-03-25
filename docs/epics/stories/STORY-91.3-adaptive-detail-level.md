# Story 91.3 -- Adaptive Detail Level

<!-- docsmcp:start:user-story -->

> **As a** developer generating epics of varying complexity, **I want** the tool to automatically choose the right level of detail, **so that** simple epics aren't bloated with empty tables and complex epics don't miss critical sections.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the "Adaptive Detail" score rises from 5/10 to 8/10. Currently users must choose between "standard" and "comprehensive" manually. Auto-detection removes this friction and adds a "minimal" style for lightweight epics.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add `style="auto"` as a third option (alongside "standard" and "comprehensive"). When auto is selected:

- **minimal** (new): title, purpose, goal, AC, single story stub, DoD. Used when: 0-1 stories, no risks, no files, no success_metrics.
- **standard**: current default sections. Used when: 2-5 stories, basic input.
- **comprehensive**: all sections including metrics tables. Used when: stories > 5, or risks provided, or files > 3, or success_metrics provided.

Also add "minimal" as an explicit style option.

Detection logic in `_auto_detect_style(config) -> str`:
```python
if len(config.stories) > 5 or config.risks or len(config.files) > 3 or config.success_metrics:
    return "comprehensive"
if len(config.stories) <= 1 and not config.risks and not config.files:
    return "minimal"
return "standard"
```

See [Epic 91](../EPIC-91-epic-generator-quality-gaps.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/generators/epics.py`
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py`
- `packages/docs-mcp/tests/unit/test_epics.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add "minimal" and "auto" to `VALID_STYLES`
- [ ] Implement `_auto_detect_style(config)` method
- [ ] Add minimal rendering path in `generate_with_timing` (title, purpose, goal, AC, stories, DoD)
- [ ] Wire `style="auto"` to call `_auto_detect_style` before rendering
- [ ] Update docstring for style parameter in `server_gen_tools.py`
- [ ] Add unit tests: auto detects minimal, standard, comprehensive correctly

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `style="auto"` with 0 stories produces minimal output
- [ ] `style="auto"` with 3 stories produces standard output
- [ ] `style="auto"` with 6 stories produces comprehensive output
- [ ] `style="minimal"` explicitly produces reduced output
- [ ] Explicit `style="comprehensive"` always produces comprehensive regardless of input

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] All 145+ existing epic tests still pass
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

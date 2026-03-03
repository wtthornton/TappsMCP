# TAPPS Quality Pipeline - Overview

## 5-Stage Workflow

```
Discover --> Research --> Develop --> Validate --> Verify --> DONE
```

| # | Stage | Purpose | Tools |
|---|-------|---------|-------|
| 1 | **Discover** | Understand server capabilities, project context, and recall memory | `tapps_server_info`, `tapps_project_profile`, `tapps_memory` |
| 2 | **Research** | Look up library docs and consult domain experts | `tapps_lookup_docs`, `tapps_consult_expert`, `tapps_list_experts` |
| 3 | **Develop** | Write code with quick feedback loops | `tapps_quick_check`, `tapps_score_file` (quick=True) |
| 4 | **Validate** | Full scoring, quality gate, and security scan | `tapps_score_file`, `tapps_quality_gate`, `tapps_security_scan`, `tapps_quick_check`, `tapps_validate_changed` |
| 5 | **Verify** | Final checklist, save learnings to memory | `tapps_checklist`, `tapps_memory` |

## Stage Flow Rules

1. **Complete each stage before advancing** - exit criteria must be met.
2. **Record findings in TAPPS_HANDOFF.md** - each stage appends its results.
3. **Log actions in TAPPS_RUNLOG.md** - append each tool call and decision.
4. **Only use stage-allowed tools** - other TappsMCP tools are available but stage-specific ones are primary.
5. **Iterate within a stage** - fix issues before advancing (especially Develop and Validate).

## Handoff Format

After completing each stage, append a section to `docs/TAPPS_HANDOFF.md`:

```markdown
## Stage: <name>
**Completed:** <timestamp>
**Tools called:** <list>
**Findings:** <bullet list>
**Decisions:** <bullet list>
**Open questions:** <bullet list (if any)>
```

## Quick Start

1. Call `tapps_server_info` to discover available tools and configuration.
2. Call `tapps_project_profile` to understand the project's tech stack.
3. Follow the 5 stages in order for each task.

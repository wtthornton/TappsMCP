# Stage 1 of 5: Discover

## Objective

Understand the TappsMCP server capabilities and the project's tech stack before writing any code. This stage ensures you know what tools are available and what the project looks like.

## Allowed Tools

- `tapps_session_start` - Combines server info and project context in a single call: server version, available tools, installed checkers, configuration, tech stack, CI, test frameworks, and quality recommendations.
- `tapps_memory` - Recall relevant memories from previous sessions for the current task.

## Constraints

- Do NOT write or modify any code in this stage.
- Do NOT run scoring, gating, or security tools yet.
- Do NOT skip this stage - it provides essential context for all later stages.

## Steps

1. Call `tapps_session_start()` to get server info, installed checkers, and project context in one call.
2. Note which checkers are installed (ruff, mypy, bandit, radon) - this affects scoring accuracy.
3. Review quality recommendations from the session start response.

## Exit Criteria

- [ ] Session started - you know the available tools, installed checkers, tech stack, and quality recommendations.
- [ ] Findings recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Server version and installed checkers
- Project type and tech stack summary
- Quality recommendations that apply to the current task

## Next Stage

**Research** - Look up library documentation for the task at hand.

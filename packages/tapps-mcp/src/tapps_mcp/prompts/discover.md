# Stage 1 of 5: Discover

## Objective

Understand the TappsMCP server capabilities and the project's tech stack before writing any code. This stage ensures you know what tools are available and what the project looks like.

## Allowed Tools

- `tapps_session_start` - Initialize the session (server info, checkers, configuration, memory status).
- `tapps_server_info` - Discover server version, available tools, installed checkers, and configuration.
- `tapps_project_profile` - Detect project type, tech stack, CI, Docker, test frameworks, and get quality recommendations.

## Constraints

- Do NOT write or modify any code in this stage.
- Do NOT run scoring, gating, or security tools yet.
- Do NOT skip this stage - it provides essential context for all later stages.

## Steps

1. Call `tapps_session_start()` to initialize the session and get server info.
2. Call `tapps_project_profile()` to detect the tech stack and get tailored recommendations.
3. Note which checkers are installed (ruff, mypy, bandit, radon) - this affects scoring accuracy.
4. Review quality recommendations from the project profile.

## Exit Criteria

- [ ] Server info retrieved - you know the available tools and installed checkers.
- [ ] Project profile retrieved - you know the tech stack, project type, and recommendations.
- [ ] Findings recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Server version and installed checkers
- Project type and tech stack summary
- Quality recommendations that apply to the current task

## Next Stage

**Research** - Look up library documentation and consult domain experts for the task at hand.

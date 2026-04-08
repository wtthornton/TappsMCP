# Stage 2 of 5: Research

## Objective

Gather domain knowledge and library documentation before writing code. This prevents hallucinated APIs and ensures best practices are followed.

## Allowed Tools

- `tapps_lookup_docs` - Look up current library documentation via Context7. Use before writing code that depends on external libraries.

## Constraints

- Do NOT write or modify code in this stage.
- Do NOT run scoring or gating tools yet.
- Always call `tapps_lookup_docs` before using a library API you are not 100% certain about.

## Steps

1. Identify which libraries the task involves.
2. Call `tapps_lookup_docs(library="<name>", topic="<specific topic>")` for each library.
3. Record all findings - API signatures, patterns, and recommended usage.

## Exit Criteria

- [ ] Library docs retrieved for all external libraries used in the task.
- [ ] Findings and decisions recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Library APIs and patterns to use
- Design decisions made based on research

## Next Stage

**Develop** - Write code with quick scoring feedback loops.

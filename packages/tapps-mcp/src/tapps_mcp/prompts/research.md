# Stage 2 of 5: Research

## Objective

Gather domain knowledge and library documentation before writing code. This prevents hallucinated APIs and ensures best practices are followed.

## Allowed Tools

- `tapps_lookup_docs` - Look up current library documentation via Context7. Use before writing code that depends on external libraries.
- `tapps_consult_expert` - Ask domain-specific questions (security, testing, APIs, databases, etc.). Routes to one of 17 built-in experts.
- `tapps_list_experts` - See which expert domains are available before consulting.

## Constraints

- Do NOT write or modify code in this stage.
- Do NOT run scoring or gating tools yet.
- Always call `tapps_lookup_docs` before using a library API you are not 100% certain about.
- Prefer `tapps_consult_expert` over guessing at best practices.

## Steps

1. Identify which libraries the task involves.
2. Call `tapps_lookup_docs(library="<name>", topic="<specific topic>")` for each library.
3. If the task involves domain-specific decisions (security patterns, testing strategies, API design, etc.), call `tapps_consult_expert(question="<your question>")`; for library-specific guidance, follow up with `tapps_lookup_docs` if suggested.
4. If unsure which expert domain fits, call `tapps_list_experts()` first.
5. Record all findings - API signatures, patterns, expert recommendations.

## Exit Criteria

- [ ] Library docs retrieved for all external libraries used in the task.
- [ ] Domain expert consulted for any non-trivial design decisions.
- [ ] Findings and decisions recorded in TAPPS_HANDOFF.md.

## Handoff

Record in `docs/TAPPS_HANDOFF.md`:
- Library APIs and patterns to use
- Expert recommendations and confidence levels
- Design decisions made based on research

## Next Stage

**Develop** - Write code with quick scoring feedback loops.

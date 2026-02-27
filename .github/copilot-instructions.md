# TappsMCP Quality Tools

This project uses TappsMCP for code quality analysis. When TappsMCP is
available as an MCP server (configured in `.vscode/mcp.json`), use the
following tools to maintain code quality throughout development.

## Key Tools

- `tapps_session_start` — Initialize a TappsMCP session at the start of
  each work session. Call this first.
- `tapps_quick_check` — Run a quick quality check on a single file after
  editing. Returns score and top issues.
- `tapps_score_file` — Get a detailed 7-category quality score for any file.
- `tapps_quality_gate` — Run a pass/fail quality gate against a configurable
  preset (standard, strict, or framework).
- `tapps_security_scan` — Run Bandit + secret detection on a Python file.
- `tapps_validate_changed` — Validate all changed files against the quality
  gate. Call this before declaring work complete.
- `tapps_lookup_docs` — Fetch current library documentation to avoid
  hallucinated APIs.
- `tapps_consult_expert` — Consult a domain expert (security, performance,
  architecture, testing, and more) for guidance.
- `tapps_research` — Combined expert + docs lookup in one call.
- `tapps_impact_analysis` — Analyze file dependencies before refactoring.
- `tapps_dead_code` — Find unused functions, classes, imports, and variables.
- `tapps_dependency_scan` — Check dependencies for known vulnerabilities.
- `tapps_dependency_graph` — Build import graph and detect circular imports.
- `tapps_checklist` — Verify all required quality steps were completed.

## Workflow

1. Start a session: call `tapps_session_start`
2. Before using a library API: call `tapps_lookup_docs`
3. After editing Python files: call `tapps_quick_check` on changed files
4. Before creating a PR or declaring work complete: call
   `tapps_validate_changed`, then `tapps_checklist`
5. For domain-specific guidance: call `tapps_consult_expert` with the
   relevant domain

## Quality Scoring Categories

TappsMCP scores code across 7 categories (0-100 each):
complexity, security, maintainability, test_coverage, performance,
structure, and devex (developer experience).

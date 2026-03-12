# Copilot Instructions

This project uses **TappsMCP** (Code Quality MCP Server) and **DocsMCP** (Documentation MCP Server) for automated quality analysis. When these MCP servers are available, follow the pipeline below.

## TappsMCP Quality Pipeline

### Stage 1: Discover
- Run `tapps_session_start` at the beginning of each session
- Use `tapps_project_profile` to understand the tech stack
- Use `tapps_memory(action="search")` to recall past decisions

### Stage 2: Research
- Use `tapps_lookup_docs` to verify library API signatures before writing code
- Use `tapps_consult_expert` for architecture/security decisions
- Use `tapps_research` for combined expert + docs in one call
- Use `tapps_impact_analysis` before refactoring

### Stage 3: Develop
- After editing Python files, run `tapps_quick_check`
- If quick check flags issues, run `tapps_score_file` for details
- Fix issues before moving to the next file

### Stage 4: Validate
- Run `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths before declaring work complete
- Run `tapps_security_scan` on security-sensitive files
- Run `tapps_dependency_scan` before releases
- Ensure overall score >= 70 and no HIGH security findings

### Stage 5: Verify
- Run `tapps_quality_gate` for pass/fail verdict
- Run `tapps_checklist` to confirm all steps were completed

## Tool Reference (30 tools)

| Category | Tools |
|----------|-------|
| **Essential** | tapps_session_start, tapps_quick_check, tapps_validate_changed, tapps_checklist, tapps_quality_gate |
| **Scoring** | tapps_score_file, tapps_security_scan |
| **Research** | tapps_lookup_docs, tapps_consult_expert, tapps_research, tapps_list_experts |
| **Analysis** | tapps_impact_analysis, tapps_dead_code, tapps_dependency_scan, tapps_dependency_graph |
| **Context** | tapps_project_profile, tapps_memory, tapps_session_notes |
| **Reporting** | tapps_report, tapps_dashboard, tapps_stats, tapps_feedback |
| **Config** | tapps_validate_config, tapps_init, tapps_upgrade, tapps_doctor, tapps_set_engagement_level |

## Code Standards

- Python 3.12+ with `from __future__ import annotations`
- Type annotations on all functions (`mypy --strict`)
- `structlog` for logging, `pathlib.Path` for file paths
- `ruff` for linting and formatting (line length: 100)
- All file operations through the path validator

## Supported Languages

Python (.py), TypeScript (.ts/.tsx), JavaScript (.js/.jsx), Go (.go), Rust (.rs)

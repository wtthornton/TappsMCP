---
description: TAPPS quality pipeline for automated code quality checks
alwaysApply: true
---

# TAPPS Quality Pipeline

This project uses TappsMCP for code quality. Follow the 5-stage pipeline:

1. **Discover** - Call `tapps_server_info` and `tapps_project_profile` at session start
2. **Research** - Call `tapps_lookup_docs` before using any library API; call `tapps_consult_expert` for domain decisions
3. **Develop** - Call `tapps_score_file(quick=True)` during edit-lint-fix loops
4. **Validate** - Call `tapps_score_file`, `tapps_quality_gate`, `tapps_security_scan` before declaring done
5. **Verify** - Call `tapps_checklist` as the final step

Key rules:
- Quality gate must pass before work is complete
- Always look up docs before using external library APIs
- Record progress in `docs/TAPPS_HANDOFF.md`

For detailed stage instructions, use the `tapps_pipeline` MCP prompt.

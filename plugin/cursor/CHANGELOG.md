# Changelog

## [1.1.0] — 2026-06-22

### Added

- **`tapps-refactor` skill** — function-level refactor workflow (call graph, diff impact)
- **Doc-orchestration skills** — `tapps-docs-refresh`, `tapps-docs-bootstrap`, `tapps-docs-finish-task`, `tapps-docs-report`, `tapps-docs-validate`, `tapps-docs-generate`
- **Doc agents** — `tapps-docs-reviewer`, `tapps-docs-validator`
- **`tapps-review-fixer` agent** — parallel review-fix-validate pipeline

### Changed

- Expanded `tapps-tool-reference` and `tapps-finish-task` with call-graph guidance
- Updated README with current skill/agent inventory and install deep link
- Plugin version tracks tapps-mcp **3.12.46**

## [1.0.0] — 2026-02-22

### Added

- Initial release of TappsMCP Quality Tools for Cursor
- Code quality scoring across 7 categories
- Security scanning via Bandit + secret detection
- Configurable quality gates
- Core skills, agents, rules, and Cursor hooks bundle

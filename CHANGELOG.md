# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-02-09

### Fixed
- Path traversal prevention in MCP resource handler (regex whitelist + resolve boundary check)
- Thread safety for `CallTracker` shared state in checklist module
- Thread safety for singleton patterns (circuit breaker, vector RAG, session notes)
- `asyncio.CancelledError` propagation in circuit breaker (no longer swallowed by generic except)
- PII detection now flags single SSN occurrences (was requiring 2+)
- Credential redaction handles multi-group regex patterns correctly
- Negative variance guard in Pearson correlation (floating-point safety)
- Silent exception logging upgraded from debug to warning in report generation
- Shell injection prevention in npm wrapper (`shell: false` on non-Windows)
- TOCTOU race condition removed from symlink check in path validator
- Unreachable `except BaseException` narrowed to `except OSError` in session notes
- Async subprocess runner catches `OSError` alongside `FileNotFoundError`
- Lookup engine properly awaits cancelled background tasks on shutdown

### Added
- `SECURITY.md` with vulnerability reporting process, response timeline, and scope
- `LICENSE` file (MIT)
- JSONL rotation (`rotate()`) for outcome tracker and expert metrics
- Overall safety timeout on `asyncio.gather` in parallel tool execution
- Docker OCI vendor label and writable state volume
- CI concurrency group with cancel-in-progress
- Error handler for npm wrapper child process spawn failures

### Changed
- `format` parameter renamed to `output_format` in `tapps_dashboard` to avoid shadowing builtin
- Tool enumeration catch narrowed from `Exception` to `AttributeError` with full fallback list
- RAG safety regex improved: `role_manipulation` pattern accepts "an" article; added `malicious`/`jailbroken` keywords
- Cache hit counter update moved inside file lock for atomicity

## [0.1.0] - 2026-02-09

### Added
- Initial release of TappsMCP
- Code scoring across 7 quality categories (complexity, security, maintainability, test coverage, performance, structure, devex)
- Security scanning with Bandit integration and secret detection
- Quality gates with configurable presets (standard, strict, framework)
- Documentation lookup via Context7 with fuzzy matching and local cache
- Config validation for Dockerfile, docker-compose, WebSocket, MQTT, InfluxDB
- 16 domain experts with RAG-backed answers and confidence scoring
- Project profiling: tech stack detection, type classification
- Session notes for persisting decisions across AI sessions
- Impact analysis via AST-based import graph
- Quality reports in JSON, Markdown, and HTML
- Adaptive scoring and expert weight adjustment
- TAPPS 5-stage pipeline orchestration (discover, research, develop, validate, verify)
- Metrics dashboard with execution tracking, alerts, and trends
- User feedback collection for continuous improvement
- Path safety: all file operations restricted to configurable project root
- Docker support with Streamable HTTP transport
- CI/CD with GitHub Actions (Windows, Linux, macOS x Python 3.12, 3.13)

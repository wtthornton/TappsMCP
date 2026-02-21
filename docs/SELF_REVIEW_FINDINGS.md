# TappsMCP Self-Review: Code Review Using Its Own Tools

**Date:** 2026-02-21
**Version:** 0.2.1
**Reviewer:** TappsMCP (reviewing itself via its own MCP tools)

## Methodology

The full TappsMCP tool suite was run against its own codebase:

- `tapps_session_start` — project profiling (Python library, pytest, fastapi detected)
- `tapps_score_file` — 20 key source files scored across 7 categories
- `tapps_security_scan` — 7 security-sensitive modules scanned
- `tapps_quality_gate` — 8 critical files evaluated against `standard` preset (70+ threshold)
- `tapps_validate_changed` — batch validation (10 files, max cap)
- `tapps_consult_expert` — 4 domain consultations (architecture, security, quality, testing)
- `tapps_dashboard` — full metrics dashboard (809 historical tool calls)
- `tapps_checklist` — workflow completeness verification
- `pytest` — 1658 tests passed, 7 skipped, 0 failures

## Quality Gate Results

| File | Score | Gate | Key Issues |
|------|-------|------|------------|
| `pipeline/init.py` | 63.35 | FAIL | CC=30, 2 security issues |
| `scoring/scorer.py` | 67.24 | FAIL | CC=13, MI=23, nested loops |
| `server.py` | 68.78 | FAIL | MI=16, 1884 lines, CC=15 |
| `project/impact_analyzer.py` | 70.90 | PASS | CC=23, MI borderline |
| `metrics/dashboard.py` | 70.98 | PASS | CC=17, MI=low |
| `adaptive/weight_distributor.py` | 73.02 | PASS | test_coverage=0 |
| `gates/evaluator.py` | 74.30 | PASS | CC=26, nested loops |
| `knowledge/cache.py` | 76.97 | PASS | nested loops |
| `config/settings.py` | 77.84 | PASS | test_coverage=0 |
| `experts/engine.py` | 78.33 | PASS | CC=17 |
| `adaptive/scoring_engine.py` | 79.24 | PASS | OK |
| `tools/ruff.py` | 81.21 | PASS | OK |
| `security/security_scanner.py` | 82.48 | PASS | CC=13 |
| `metrics/collector.py` | 84.31 | PASS | OK |
| `project/profiler.py` | 84.40 | PASS | OK |

**3 of 15 scored files fail the standard quality gate.**

## Dashboard Metrics (7-day window, 809 calls)

- **Gate pass rate:** 82.9%
- **Average score:** 85.61
- **Success rate:** 98.4%
- **`tapps_lookup_docs` success rate:** 50% (26 calls)
- **`tapps_report` avg duration:** 84.6s
- **`tapps_quality_gate` avg duration:** 8.9s

## Expert Consultation Quality

| Domain | Confidence | Chunks | Quality Assessment |
|--------|-----------|--------|-------------------|
| software-architecture | 50% | 5 | Returned Docker Compose content for MCP architecture question |
| security | 63% | 5 | Generic threat modeling, not MCP-specific |
| code-quality-analysis | 61% | 4 | Reasonable but generic metrics guidance |
| testing-strategies | 30% | 0 | No relevant knowledge found |

## High-Value Enhancements (Ranked by Impact)

### 1. server.py Fails Its Own Quality Gate (Critical)
The main server file scores 68.78 against a 70.0 threshold. MI=16 (very low) and
1884 lines make this the lowest-maintainability file in the project.

**Recommendation:** Split into `server_core.py`, `server_scoring_tools.py`,
`server_pipeline_tools.py`, `server_metrics_tools.py`.

### 2. Feedback Loop Is Disconnected (High)
`tapps_feedback` records data to `feedback.jsonl` but nothing reads it.
`AdaptiveScoringEngine` uses `CodeOutcome`, not feedback records.
The "adaptive learning" pipeline has a gap between data collection and weight adjustment.

**Recommendation:** Wire `FeedbackTracker.get_by_tool()` into the adaptive engine
so negative feedback on specific tools or categories influences weight recalibration.

### 3. Checklist State Is Not Persisted (High)
`CallTracker` uses module-level state that resets between sessions.
The checklist reported all tools as "missing" even after calling them,
because the Python process was restarted between calls.

**Recommendation:** Persist call records to session JSON files (`.tapps-mcp/sessions/`).

### 4. Expert RAG Relevance Is Poor (High)
Architecture and testing consultations returned irrelevant or empty results.
Keyword-based chunk matching produces low-relevance results for specific questions.

**Recommendation:** Implement BM25/TF-IDF scoring. Add relevance threshold
(reject chunks with score < 0.3). Expand knowledge base with MCP-specific content.

### 5. validate_changed Caps at 10 Files (Medium)
Only ~8% of source files get validated in a batch run. The cap is too low
for medium-sized projects.

**Recommendation:** Use `score_file_quick` for batch validation with a 50-file cap.
Reserve full scoring for files flagged by quick check.

### 6. pipeline/init.py Has CC=30 (Medium)
`bootstrap_pipeline()` is the most complex function in the codebase.
11 boolean parameters contribute to branch explosion.

**Recommendation:** Extract parameters into `BootstrapConfig` dataclass.
Split into `_verify_server()`, `_create_templates()`, `_warm_caches()`.

### 7. Scoring Weights Need Empirical Calibration (Medium)
15% gap between avg score (85.6) and gate pass rate (82.9%) suggests
weight calibration issues. `MIN_OUTCOMES_FOR_ADJUSTMENT = 10` means
adaptive weights rarely activate.

**Recommendation:** Ship calibrated default weights. Add `tapps_calibrate` tool.
Lower minimum outcomes threshold.

### 8. tapps_lookup_docs Has 50% Success Rate (Medium)
A blocking requirement tool fails half the time. Without Context7 API key,
it degrades completely with poor error visibility.

**Recommendation:** Ship pre-built cache for top-50 Python libraries.
Use expert knowledge base as fallback. Improve no-API-key messaging.

### 9. Quick Check vs Full Gate Score Inconsistency (Medium)
`tapps_quick_check` reports 100% pass rate; `tapps_quality_gate` shows 80%.
Ruff-only scoring misses complexity and maintainability issues entirely.

**Recommendation:** Add AST-based complexity heuristic to quick check (no subprocess needed).

### 10. tapps_report Performance (Medium)
Avg 84.6s, P95 30.2s — too slow for interactive sessions.

**Recommendation:** Use `score_file_quick` with `asyncio.gather`. Add `max_files` parameter.
Cache recent scores for unchanged files.

### 11. Missing Tests for Foundational Modules (Low)
`config/settings.py` and `adaptive/weight_distributor.py` have no test files.

### 12. Bandit False Positives in secret_scanner.py (Low)
Severity label strings `'high'`, `'medium'`, `'low'` trigger B105 false positives.

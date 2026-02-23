# TappsMCP Full Service Review Tracking

## Review Date: 2026-02-22

## Batch Organization (by priority)

### Batch 1: Server + Entry Points (Critical)
- server.py, server_helpers.py, server_scoring_tools.py, server_pipeline_tools.py, server_metrics_tools.py
- cli.py, __init__.py, diagnostics.py

### Batch 2: Security + Config (Critical)
- security/path_validator.py, security/io_guardrails.py, security/governance.py
- security/api_keys.py, security/secret_scanner.py, security/security_scanner.py
- config/settings.py

### Batch 3: Scoring + Gates + Tools (Core)
- scoring/models.py, scoring/constants.py, scoring/scorer.py
- gates/models.py, gates/evaluator.py
- tools/subprocess_utils.py, tools/subprocess_runner.py, tools/tool_detection.py
- tools/ruff.py, tools/ruff_direct.py, tools/mypy.py, tools/bandit.py
- tools/radon.py, tools/radon_direct.py, tools/parallel.py, tools/checklist.py
- tools/batch_validator.py

### Batch 4: Knowledge + Validators
- knowledge/models.py, knowledge/cache.py, knowledge/fuzzy_matcher.py
- knowledge/context7_client.py, knowledge/rag_safety.py, knowledge/lookup.py
- knowledge/circuit_breaker.py, knowledge/library_detector.py
- knowledge/warming.py, knowledge/import_analyzer.py, knowledge/content_normalizer.py
- validators/base.py, validators/dockerfile.py, validators/docker_compose.py
- validators/websocket.py, validators/mqtt.py, validators/influxdb.py

### Batch 5: Experts
- experts/models.py, experts/registry.py, experts/domain_utils.py
- experts/domain_detector.py, experts/rag.py, experts/confidence.py
- experts/engine.py, experts/rag_chunker.py, experts/rag_embedder.py
- experts/rag_index.py, experts/vector_rag.py, experts/knowledge_freshness.py
- experts/knowledge_validator.py, experts/knowledge_ingestion.py
- experts/adaptive_domain_detector.py, experts/hot_rank.py
- experts/rag_warming.py, experts/retrieval_eval.py

### Batch 6: Project + Pipeline + Distribution
- project/models.py, project/ast_parser.py, project/tech_stack.py
- project/type_detector.py, project/profiler.py, project/session_notes.py
- project/impact_analyzer.py, project/report.py
- pipeline/models.py, pipeline/handoff.py, pipeline/init.py
- pipeline/agents_md.py, pipeline/platform_generators.py
- distribution/setup_generator.py, distribution/doctor.py

### Batch 7: Adaptive + Metrics + Common + Prompts
- adaptive/models.py, adaptive/protocols.py, adaptive/persistence.py
- adaptive/scoring_engine.py, adaptive/scoring_wrapper.py
- adaptive/voting_engine.py, adaptive/weight_distributor.py
- metrics/collector.py, metrics/execution_metrics.py, metrics/outcome_tracker.py
- metrics/expert_metrics.py, metrics/confidence_metrics.py, metrics/rag_metrics.py
- metrics/consultation_logger.py, metrics/expert_observability.py
- metrics/business_metrics.py, metrics/quality_aggregator.py
- metrics/alerts.py, metrics/trends.py, metrics/visualizer.py
- metrics/dashboard.py, metrics/otel_export.py, metrics/feedback.py
- common/exceptions.py, common/logging.py, common/models.py
- common/nudges.py, common/elicitation.py, common/utils.py
- prompts/prompt_loader.py

## Status
- [x] Batch 1: Complete - 6/8 files score 100, 2 files had issues (fixed)
- [x] Batch 2: Complete - 7/7 files score 100, only false-positive Bandit B105 findings
- [x] Batch 3: Complete - 17/17 files score 100, only expected subprocess Bandit warnings
- [x] Batch 4: Complete - 17/17 files score 100, no issues
- [x] Batch 5: Complete - 18/18 files score 100, 1 low-severity B110 (expected)
- [x] Batch 6: Complete - 14/15 files score 100, 1 file had issues (fixed)
- [x] Batch 7: Complete - 29/30 files score 100, 1 file had issue (fixed)

## Issues Found & Fixed

### 1. server_pipeline_tools.py (score 80 -> 100)
- **RUF002 x4**: EN DASH characters in docstrings (lines 236, 239, 259, 260)
- **Fix**: Replaced Unicode EN DASH with plain hyphen-minus

### 2. pipeline/init.py (score 75 -> 100)
- **RUF002**: EN DASH in docstring (line 130)
- **E501**: Line too long at 106 chars (line 196)
- **Fix**: Replaced EN DASH, split long string across lines

### 3. server.py (score 85 -> 100)
- **PLR2004**: Magic value `0.3` in comparison (line 429)
- **S110/B110**: Silent try-except-pass (line 439)
- **PLR0911**: Too many return statements in `_library_to_domain` (line 98)
- **Fix**: Extracted `_EXPERT_FALLBACK_MIN_CONFIDENCE` constant, added `logger.debug()` call, refactored to dict-based lookup

### 4. adaptive/persistence.py (score 95 -> 100)
- **SIM103**: Simplifiable if/return pattern (line 239)
- **Fix**: Collapsed to single `return` expression

## Non-actionable Findings (by design)
- **B404/B603/B607** in subprocess wrapper files (subprocess_runner.py, ruff_direct.py, batch_validator.py, pipeline/init.py) - expected for tool runner architecture
- **B105** false positives in governance.py, secret_scanner.py, persistence.py, outcome_tracker.py - regex patterns and string literals misidentified as passwords
- **B110** in domain_utils.py, server.py (pre-fix) - intentional silent error handling for best-effort fallbacks

## Complexity Advisories (informational, no score impact)
High (CC >= 16): impact_analyzer.py (23), evaluator.py (20), parallel.py (19), docker_compose.py (19), execution_metrics.py (19), lookup.py (18), ast_parser.py (17), init.py (16)
Moderate (CC 11-15): scorer.py (13), mypy.py (13), engine.py (13), setup_generator.py (13), dashboard.py (13), rag_safety.py (12), import_analyzer.py (12), content_normalizer.py (12), influxdb.py (15), agents_md.py (11), vector_rag.py (11), rag_warming.py (11), server_pipeline_tools.py (11)

## Final Validation
- All 4 fixed files: score 100, quality gate PASS, 0 lint issues
- Full test suite: 1955 passed, 10 skipped
- TAPPS checklist: COMPLETE (no missing items)

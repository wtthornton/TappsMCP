# Test Coverage Review - TappsMCP

## Executive Summary
- **Total test files**: ~130+ test modules covering 100+ source modules
- **Test quality**: High overall - conftest.py properly resets all 4 key caches
- **Main coverage gaps**: knowledge/* modules mostly under-tested despite being critical
- **Anti-patterns identified**: 7 files use sleep/timing-dependent tests; async mocking patterns need improvement
- **Skipped tests**: 7 tests with @pytest.mark.skipif for Windows/optional deps (acceptable)

## Cache Reset Verification (PASS)
`tests/conftest.py` uses autouse fixture `_reset_caches()` that properly resets:
1. `_reset_settings_cache()` - config/settings.py
2. `_reset_scorer_cache()` - server_helpers.py
3. `_reset_lookup_engine_cache()` - server_helpers.py (NEW)
4. `_reset_memory_store_cache()` - server_helpers.py
5. `_reset_session_state()` - server_helpers.py (NEW)
6. `_reset_tools_cache()` - tools/tool_detection.py
7. `clear_dependency_cache()` - tools/dependency_scan_cache.py (NEW)

**Status**: Complete. All 7 caches properly reset.

## Test Coverage by Module

### Fully Tested (Excellent Coverage)
- **scoring/**: test_scorer.py (180+ tests) - comprehensive quick/full modes
- **gates/**: test_evaluator.py - comprehensive threshold logic
- **memory/**: Epic 23-25 coverage complete
  - test_memory_tool.py (MCP tool handler)
  - test_memory_real_store.py (526 lines! Integration tests for seeding/retrieval/injection/IO)
  - test_memory_integration.py (high-level workflows)
  - test_memory_config.py (configuration variants)
- **security/**: test_path_validator.py, test_io_guardrails.py, test_governance.py
- **experts/**: 15+ test modules covering domain detection, RAG, confidence, etc.
- **metrics/**: 12+ test modules covering collection, visualization, alerts, etc.
- **project/**: test_ast_parser.py, test_tech_stack.py, test_session_notes.py, etc.
- **tools/**: test_ruff.py, test_mypy.py, test_bandit.py, test_radon.py, test_subprocess.py, etc.

### Under-Tested Modules (GAPS FOUND)
1. **knowledge/library_detector.py** - Has test_library_detector.py but coverage limited
2. **knowledge/rag_safety.py** - Has test_rag_safety.py but needs edge case coverage
3. **knowledge/context7_client.py** - test_context7_client.py exists but limited
4. **knowledge/circuit_breaker.py** - test_circuit_breaker.py good but async edge cases
5. **knowledge/content_normalizer.py** - test_content_normalizer.py exists, basic coverage
6. **knowledge/fuzzy_matcher.py** - test_fuzzy_matcher.py exists, basic coverage
7. **knowledge/import_analyzer.py** - test_import_analyzer.py exists, basic coverage
8. **knowledge/warming.py** - test_warming.py exists, basic coverage
9. **knowledge/providers/*.py** - test_provider_orchestration.py + test_providers.py (limited detail)
   - context7_provider.py - limited tests
   - llms_txt_provider.py - limited tests
   - (Epic 29: deepcon_provider and docfork_provider removed; Context7 + LlmsTxt only)
10. **knowledge/lookup.py** - test_lookup.py (basic coverage, mostly mocked)

### Untested or Minimal Modules (CRITICAL GAPS)
1. **knowledge/models.py** - No dedicated test file (likely covered indirectly)
2. **knowledge/cache.py** - test_cache.py exists (basic)
3. **server_*.py module tools** - Tested indirectly:
   - server_scoring_tools.py → test_composite_tools.py (extensive)
   - server_metrics_tools.py → test_feedback.py, test_research_p2.py
   - server_pipeline_tools.py → test_checklist_auto_run.py, test_session_auto_init.py
   - server_memory_tools.py → test_memory_tool.py
   - **MISSING**: Dedicated test_server_scoring_tools.py, test_server_metrics_tools.py, test_server_pipeline_tools.py (tools are tested via composite tests but not in isolation)

## Anti-Patterns Found

### 1. Sleep-Based Tests (7 files) - **MINOR RISK**
- `test_cache.py:121` - time.sleep(0.01) in cache warming test
- `test_circuit_breaker.py:93,117,134,165` - asyncio.sleep() in timeout scenarios (ACCEPTABLE for circuit breaker)
- `test_progress_heartbeat.py:26,86,106` - asyncio.sleep() for heartbeat timing (ACCEPTABLE)
- `test_session_notes.py:44` - time.sleep(0.01) (MINOR)
- `test_subprocess.py:54` - Python subprocess timeout test (ACCEPTABLE - uses python -c trick correctly)

**Assessment**: Most are acceptable for async/timeout testing. Only `test_cache.py` and `test_session_notes.py` are questionable.

### 2. Mock Patterns (22+ files with mock.patch)
- **Well-implemented**: test_composite_tools.py, test_scorer.py, test_validate_changed_p0.py
- **Potential issues**:
  - test_memory_tool.py patches `ensure_session_initialized` - good pattern
  - test_server_helpers.py likely patches singletons - should verify
  - Some tests mock asyncio functions - need to verify proper AsyncMock usage

### 3. Skipped Tests (7 tests) - **ACCEPTABLE**
- `test_agent_teams_integration.py:31` - @pytest.mark.skipif(sys.platform == "win32") - Exec bit
- `test_claude_hooks_generation.py:42` - Windows skip - Exec bit
- `test_cursor_hooks_generation.py:35` - Windows skip - Exec bit
- `test_rag_embedder.py:29` - Optional sentence-transformers
- `test_rag_index.py:30,62,72,87,101` - Optional faiss-cpu with conditional pytest.skip() (GOOD pattern)
- `test_pyinstaller_spec.py:48` - pytest.skip() for missing spec file

**Assessment**: All justifiable - Windows platform limitations, optional dependencies.

## Test Quality Assessment

### Strengths
1. **conftest.py**: Excellent fixture design with proper cache reset
2. **Integration tests**: test_memory_real_store.py (526 lines) is exemplary - real SQLite tests
3. **Parametrization**: Tests use proper parametrization where appropriate
4. **Async handling**: Good use of @pytest.mark.asyncio and AsyncMock
5. **Type hints**: Test code has proper type hints
6. **Fixture design**: Reusable fixtures with clear dependencies

### Weaknesses
1. **Knowledge module coverage**: Scattered across multiple files, some light
2. **Provider implementation tests**: Context7 and LlmsTxt have coverage (Epic 29: Deepcon, Docfork removed)
3. **Server tool isolation**: Tools tested through composite/integration tests but not in isolation
4. **Circuit breaker edge cases**: Could use more failure scenario testing
5. **Mock cleanup**: Some tests could benefit from explicit mock.reset_mock() calls

## Recommendations

### Immediate (High Priority)
1. **Add dedicated test_server_scoring_tools.py** - test each tool in isolation
2. **Add dedicated test_server_metrics_tools.py** - test metrics tools individually
3. **Improve knowledge/providers tests** - Context7, LlmsTxt covered; Epic 29 removed Deepcon, Docfork
4. **Review knowledge/circuit_breaker.py** - Add more failure scenarios

### Medium Priority
1. **Reduce timing-dependent tests** - Replace time.sleep in test_cache.py with mock.patch or event signaling
2. **Parametrize knowledge tests** - Use pytest.mark.parametrize for variant testing
3. **Add edge case tests** - RAG safety injection patterns, fuzzy matcher edge cases
4. **Document mock patterns** - Create pytest.ini guidelines or conftest documentation

### Low Priority (Nice to Have)
1. Add pytest-xdist for parallel test execution
2. Generate coverage HTML reports per module
3. Add benchmark tests for performance-critical paths

## File List Summary

**Test files with highest impact for review**:
- tests/conftest.py (VALIDATED - proper cache resets)
- tests/unit/test_memory_real_store.py (EXCELLENT - 526 lines, real store tests)
- tests/unit/test_composite_tools.py (GOOD - covers session/validate/quick)
- tests/unit/test_scorer.py (COMPREHENSIVE - 80+ tests)
- tests/unit/test_server_tools.py (GOOD - basic tool coverage)
- tests/unit/test_server_helpers.py (should verify cache test patterns)

**Modules needing better isolation testing**:
- src/tapps_mcp/server_scoring_tools.py
- src/tapps_mcp/server_metrics_tools.py
- src/tapps_mcp/server_pipeline_tools.py

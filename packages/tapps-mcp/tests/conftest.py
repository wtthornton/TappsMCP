"""Shared test fixtures for TappsMCP.

Ensures test isolation by resetting module-level caches between tests.

Cache reset registry
--------------------
Every module-level singleton or cached value that persists across function
calls must be reset here.  When adding a new cache:

1. Create a ``_reset_*()`` function in the source module.
2. Import and call it in ``_reset_caches()`` below.
3. Verify isolation by running the new tests twice in a row.

Current resets (11 total):
  - settings              — ``tapps_core.config.settings._reset_settings_cache``
  - feature_flags         — ``tapps_core.config.feature_flags.feature_flags.reset``
  - scorer           — ``tapps_mcp.server_helpers._reset_scorer_cache``
  - lookup_engine    — ``tapps_mcp.server_helpers._reset_lookup_engine_cache``
  - memory_store     — ``tapps_mcp.server_helpers._reset_memory_store_cache``
  - hive_store       — ``tapps_mcp.server_helpers._reset_hive_store_cache``
  - session_state    — ``tapps_mcp.server_helpers._reset_session_state``
  - tools_detection  — ``tapps_mcp.tools.tool_detection._reset_tools_cache``
  - session_gc_flag  — ``tapps_mcp.server_pipeline_tools._reset_session_gc_flag``
  - dependency_cache — ``tapps_mcp.tools.dependency_scan_cache.clear_dependency_cache``
  - quick_check_recurring — ``tapps_mcp.quick_check_recurring._reset_recurring_quick_check_state``
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset all module-level singletons after each test.

    Caches populate normally during each test and are cleared in teardown,
    ensuring test isolation.  See module docstring for the full registry.
    """
    yield

    # -- tapps-core caches --
    from tapps_core.config.feature_flags import feature_flags
    from tapps_core.config.settings import _reset_settings_cache

    _reset_settings_cache()
    feature_flags.reset()

    # -- tapps-mcp caches --
    from tapps_mcp.quick_check_recurring import _reset_recurring_quick_check_state
    from tapps_mcp.server_helpers import (
        _reset_hive_store_cache,
        _reset_lookup_engine_cache,
        _reset_memory_store_cache,
        _reset_scorer_cache,
        _reset_session_state,
    )
    from tapps_mcp.server_pipeline_tools import _reset_session_gc_flag
    from tapps_mcp.tools.dependency_scan_cache import clear_dependency_cache
    from tapps_mcp.tools.tool_detection import _reset_tools_cache

    _reset_scorer_cache()
    _reset_lookup_engine_cache()
    _reset_memory_store_cache()
    _reset_hive_store_cache()
    _reset_session_state()
    _reset_tools_cache()
    _reset_session_gc_flag()
    clear_dependency_cache()
    _reset_recurring_quick_check_state()

    # content_hash_cache is a module-level OrderedDict; must be cleared so
    # a cached result for "x = 1\n" (or any other small file) from one test
    # cannot produce a spurious cache hit in a later test that uses the same
    # file content with a different preset or expectation.
    from tapps_mcp.tools.content_hash_cache import clear as _clear_content_cache

    _clear_content_cache()

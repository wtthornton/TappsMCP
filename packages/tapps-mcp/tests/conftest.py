"""Shared test fixtures for TappsMCP.

Ensures test isolation by resetting module-level caches between tests.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset all module-level singletons after each test.

    Caches populate normally during each test and are cleared in teardown,
    ensuring test isolation when caching is active in:

    - ``load_settings()`` (config/settings.py)
    - ``_get_scorer()`` (server_helpers.py)
    - ``detect_installed_tools()`` (tools/tool_detection.py)
    """
    yield

    from tapps_core.config.settings import _reset_settings_cache
    from tapps_mcp.server_helpers import (
        _reset_lookup_engine_cache,
        _reset_memory_store_cache,
        _reset_scorer_cache,
        _reset_session_state,
    )
    from tapps_mcp.tools.dependency_scan_cache import clear_dependency_cache
    from tapps_mcp.tools.tool_detection import _reset_tools_cache

    _reset_settings_cache()
    _reset_scorer_cache()
    _reset_lookup_engine_cache()
    _reset_memory_store_cache()
    _reset_session_state()
    _reset_tools_cache()
    clear_dependency_cache()

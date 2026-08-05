"""Shared test fixtures for tapps-core.

Ensures test isolation by resetting module-level caches between tests.

Current resets (3 total):
  - settings              — ``tapps_core.config.settings._reset_settings_cache``
  - feature_flags         — ``tapps_core.config.feature_flags.feature_flags.reset``
  - memory_project_id     — ``tapps_mcp.memory_project_id.uninstall_memory_project_id_patch``
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset all module-level singletons after each test."""
    yield

    from tapps_core.config.feature_flags import feature_flags
    from tapps_core.config.settings import _reset_settings_cache

    _reset_settings_cache()
    feature_flags.reset()

    # tapps-core's fleet-RPC tests install the TAP-5442 patch on
    # server_memory_tools._params_project_id, which production never undoes.
    # Restore it so the mutation cannot outlive the test that made it and
    # change results for whatever runs next. tapps-mcp is an optional import
    # here: tapps-core is installable without it.
    try:
        from tapps_mcp.memory_project_id import uninstall_memory_project_id_patch
    except ImportError:
        return
    uninstall_memory_project_id_patch()

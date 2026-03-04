"""Shared test fixtures for tapps-core.

Ensures test isolation by resetting module-level caches between tests.

Cache reset registry
--------------------
Every module-level singleton or cached value that persists across function
calls must be reset here.  When adding a new cache:

1. Create a ``_reset_*()`` or ``reset()`` method in the source module.
2. Import and call it in ``_reset_caches()`` below.
3. Verify isolation by running the new tests twice in a row.

Current resets (3 total):
  - settings         — ``tapps_core.config.settings._reset_settings_cache``
  - feature_flags    — ``tapps_core.config.feature_flags.feature_flags.reset``
  - business_experts — ``tapps_core.experts.registry.ExpertRegistry.clear_business_experts``
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

    from tapps_core.config.feature_flags import feature_flags
    from tapps_core.config.settings import _reset_settings_cache
    from tapps_core.experts.registry import ExpertRegistry

    _reset_settings_cache()
    feature_flags.reset()
    ExpertRegistry.clear_business_experts()

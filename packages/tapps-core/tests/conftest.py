"""Shared test fixtures for tapps-core.

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
    """
    yield

    from tapps_core.config.settings import _reset_settings_cache

    _reset_settings_cache()

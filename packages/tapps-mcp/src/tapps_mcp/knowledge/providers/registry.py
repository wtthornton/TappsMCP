"""Backward-compatible re-export."""
from __future__ import annotations

from tapps_core.knowledge.providers.registry import (
    _FAILURE_THRESHOLD as _FAILURE_THRESHOLD,
)
from tapps_core.knowledge.providers.registry import (
    _RECOVERY_SECONDS as _RECOVERY_SECONDS,
)
from tapps_core.knowledge.providers.registry import ProviderRegistry as ProviderRegistry
from tapps_core.knowledge.providers.registry import _ProviderState as _ProviderState

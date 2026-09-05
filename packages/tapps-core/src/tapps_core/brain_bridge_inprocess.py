"""In-process :class:`BrainBridge` wrapping a local ``tapps_brain.AgentBrain``.

Split out of ``brain_bridge.py`` (TAP-6736); further split into
``brain_bridge_inprocess_core.py`` (circuit breaker / write queue / lifecycle)
and ``brain_bridge_inprocess_ops.py`` (AgentBrain-delegating read/write/
maintenance methods) to clear the quality gate. No behavior change: this
module only composes the two mixins.
"""

from __future__ import annotations

from tapps_core.brain_bridge_inprocess_core import _InProcessCoreMixin
from tapps_core.brain_bridge_inprocess_ops import _InProcessOpsMixin


class BrainBridge(_InProcessOpsMixin, _InProcessCoreMixin):
    """Async-safe wrapper over :class:`tapps_brain.AgentBrain`.

    Provides read and write operations against the tapps-brain v3 Postgres
    backend with built-in resilience:

    - ``asyncio.to_thread`` for every sync call
    - Circuit breaker (opens after 3 failures, resets after 30 s)
    - Exponential-backoff retry (3 attempts, base 0.5 s, max 8 s, +-10 % jitter)
    - Offline write queue (cap 100; drained asynchronously after circuit resets)

    Composed from :class:`_InProcessOpsMixin` (read/write/maintenance methods)
    and :class:`_InProcessCoreMixin` (circuit breaker, retry wrapper, write
    queue, lifecycle) — see the module docstring (TAP-6736).
    """

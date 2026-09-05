"""Root conftest: pin process-wide env before any test can import torch or the brain.

tapps-brain (a workspace dependency of tapps-core) pulls in
sentence-transformers -> torch. Torch sizes its OpenMP intra-op pool to the
machine's core count *per process*, so under pytest-xdist every worker spins
up its own full-width pool: N workers x nproc threads oversubscribes the box
(observed: 4 workers x 20-thread pools -> ~80 compute threads on 20 cores,
load average ~60). The caps must be exported before torch is first imported,
and this root conftest is the only hook that precedes every test module in
every documented invocation (root run, per-package runs,
scripts/run-regression.sh). ``setdefault`` keeps explicit caller overrides.

The same reasoning applies to ``TAPPS_METRICS_STORAGE`` (TAP-5841).
``metrics_storage_mode()`` defaults to ``dual``, so
``ToolCallMetricsCollector._load_from_disk`` builds a real ``HttpBrainBridge``
from the repo's own ``.tapps-mcp.yaml`` and issues live HTTP to
``localhost:8080`` -- a health probe plus ``query_events`` MCP POSTs -- on
every metrics read. Any test that generates a dashboard with default sections
therefore does real network I/O against whatever tapps-brain the developer
happens to be running. Under xdist all workers hit that one service at once,
each request bounded only by the bridge's 30s client timeout, so two stalled
round-trips exceed pytest-timeout's 60s and the test dies blocked in
``selectors.py``. Which tests collide depends on the pytest-randomly seed and
the xdist work split, which is exactly why the failure looked order-dependent.
Six test modules already pinned ``local`` in their own autouse fixtures;
``local`` short-circuits ``should_read_metrics_from_brain()`` so the bridge is
never built. Pinning it here makes that hermeticity suite-wide instead of
per-module. ``setdefault`` still lets a caller export ``dual``/``brain``
deliberately, and ``monkeypatch.delenv`` still restores the production default
for the tests that assert on it.

TAP-6592: the same reasoning applies to ``HF_HUB_OFFLINE``/``TRANSFORMERS_OFFLINE``.
Any test that constructs a real ``tapps_brain.store.MemoryStore`` directly
(bypassing tapps-mcp's own settings, where semantic search defaults to
disabled) inherits that pinned dependency's own default of embedding saved
content via sentence-transformers -- which downloads its model from
HuggingFace Hub on a cache miss. Under the new root socket guard
(packages/tapps-mcp/tests/conftest.py) that dial fails loudly instead of
silently succeeding-if-cached/hanging-if-not; offline mode makes
huggingface_hub short-circuit before attempting the connection at all, so
MemoryStore's embedding step degrades gracefully instead of ever touching a
socket. ``setdefault`` still lets a caller export ``0`` deliberately for a
test that genuinely wants to exercise the live download path.
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

os.environ.setdefault("TAPPS_METRICS_STORAGE", "local")

for _var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
    os.environ.setdefault(_var, "1")

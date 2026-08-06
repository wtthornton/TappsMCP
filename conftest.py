"""Root conftest: cap native thread pools before any test can import torch.

tapps-brain (a workspace dependency of tapps-core) pulls in
sentence-transformers -> torch. Torch sizes its OpenMP intra-op pool to the
machine's core count *per process*, so under pytest-xdist every worker spins
up its own full-width pool: N workers x nproc threads oversubscribes the box
(observed: 4 workers x 20-thread pools -> ~80 compute threads on 20 cores,
load average ~60). The caps must be exported before torch is first imported,
and this root conftest is the only hook that precedes every test module in
every documented invocation (root run, per-package runs,
scripts/run-regression.sh). ``setdefault`` keeps explicit caller overrides.
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

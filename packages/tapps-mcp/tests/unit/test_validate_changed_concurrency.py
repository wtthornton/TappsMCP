"""TAP-5965 — tapps_validate_changed must not wedge under concurrency.

Root cause covered here: ``heavy_cpu()`` is a process-wide, non-reentrant
semaphore (limit 2).  ``_validate_single_file`` holds a slot while it calls
``CodeScorer.score_file``, which acquires a *second* slot for its category
build.  With ``_VALIDATE_CONCURRENCY == 2`` every slot ends up held by an
outer waiter that can only progress by acquiring an inner slot, so the batch
deadlocks — and the explicit-``file_paths`` gather had no wall-clock bound,
so the MCP caller hung forever instead of getting a verdict.

TAP-7785 — phase instrumentation and the 60s-vs-20s discrepancy
-----------------------------------------------------------------
``pytest-timeout`` (``pyproject.toml``'s ``timeout = 60``) runs with
``timeout_func_only`` at its default of ``False``. Reading
``pytest_timeout.pytest_runtest_protocol``: when ``func_only`` is ``False``
the plugin arms a *single* SIGALRM before the item's *setup* phase and only
disarms it after the item's *teardown* phase completes — one 60s budget
shared across setup + call + teardown. This file's own
``_BOTH_RETURN_BOUND_S = 20.0`` only bounds the ``asyncio.wait_for`` inside
the *call* phase. The two numbers are not measuring the same span, so a
20s-vs-60s "inversion" does not require any defect in the code under test:
if wall-clock is consumed *outside* the call phase, the 60s ceiling can be
reached with the 20s inner bound never having had a chance to start.

That is not hypothetical, but the specific causal story is narrower than the
evidence supports: under sufficient CPU contention, *some* session-scoped
import triggered from ``tests/conftest.py`` can exceed the 60s item ceiling
during **setup**, not inside our async batch. *Which* import pays that cost
varies across runs — observed culprits include the
``sentence_transformers -> sklearn -> scipy.stats`` chain via
``_inject_in_memory_private_backend``'s lazy ``from tapps_brain import
store``, pydantic model-schema generation via
``_clear_test_singleton_caches``, and a ``tapps_mcp.server`` import via
``_isolate_checklist_session`` — listed here as examples, not as the sole
cause. Because ``addopts`` runs tests under ``-p randomly`` with a fresh
per-run seed, and pytest-xdist's worker assignment also varies, *which* test
in *which* worker pays whichever cold-import cost is non-deterministic
across CI runs — consistent with "one run errored, an identical re-run
passed." This is a real, reproducible loaded-runner effect class, not a
returning TAP-5965 deadlock: the failure sits entirely outside this file's
own fixtures and outside the awaited gather. (A specific number such as
"200 processes against 20 cores reliably reproduces this" is not committed
here — it was not reproducible via the same culprit across independent
attempts, so it is not restated as a reliable result.)

The instrumentation below cannot reach into ``tests/conftest.py`` (out of
this issue's permitted paths), so it cannot bound *that* import. What it can
do, and does, is remove the ambiguity for *this file's own* phases: a
durable, uncaptured phase log records entry/exit of this file's setup,
call sub-steps, and teardown, so a future timeout can be checked against the
log to see whether execution ever reached this file's own fixture or async
batch at all. If the log is empty or stops before ``setup:start``, the block
was upstream of this file (load / another fixture's import), matching what
was measured here. If the log stops between ``call:awaiting_gather`` and
``call:gather_returned``, that is the TAP-5965 deadlock signature.

TAP-7785 round 2 — a second, independently real inversion mechanism
-----------------------------------------------------------------
The paragraph above documents one way the 20s inner bound can fail to fire
before the 60s outer ceiling: the time is spent *outside* the call phase
(setup-time import), so the inner ``asyncio.wait_for`` never even starts.
There is a second, distinct way, verified by direct injection: a
*synchronous* ``time.sleep(65)`` placed inside the mocked ``run_all_tools``
stand-in that the awaited ``asyncio.gather`` calls does not trip
``asyncio.wait_for(..., timeout=20)`` at 20s. It blocks the single-threaded
event loop, so no callback — including ``wait_for``'s own scheduled
cancellation — can run until pytest-timeout's SIGALRM interrupts the sleep
near the 60s item ceiling; the observed phase log for that run was
``call:start`` (t=0.001s) -> ``call:awaiting_gather`` (t=0.012s) -> [57s gap
with no further phase recorded] -> ``call:gather_returned`` (t=57.39s). This
is event-loop starvation by synchronous code inside the awaited path, not a
setup-time import stall.

So there are (at least) two distinct ways the 20s inner bound can fail to
fire before the 60s outer ceiling:

1. the time is spent **outside** the call phase, so the inner bound never
   starts (the setup-import case above); and
2. the time is spent **inside** the call phase but in **synchronous** code
   that starves the event loop, so the inner bound cannot be scheduled to
   fire (this case).

The phase log distinguishes them: mechanism 1 leaves the log empty or
stopping before ``setup:start``; mechanism 2 leaves a gap between
``call:awaiting_gather`` and ``call:gather_returned`` — the same signature
this docstring already calls the TAP-5965 deadlock shape. **A gap there does
not by itself prove a deadlock** — a long synchronous call in the awaited
path produces the identical signature. Distinguishing the two requires
inspecting *what* ran during the gap (a real async wedge on the heavy-cpu
semaphore vs. a blocking call that starves the loop), not just that a gap
exists.

TAP-7785 round 2 — timeout margin for this file's own runtime
-----------------------------------------------------------------
Measured uncontended, 5 runs of this file alone (wall-clock, includes
interpreter/pytest startup):
5.06s, 5.13s, 5.19s, 5.24s, 12.73s -> min=5.06s, median=5.19s, max=12.73s.
Margin against the 60s pytest-timeout ceiling: 60 / 12.73 ~= 4.7x at the
observed max.

This file's own runtime is nowhere near the 60s ceiling, so the ceiling is
not binding on this file's work: every timeout this docstring documents was
consumed *upstream* of this file, in session-scoped fixture imports that
this issue's permitted paths cannot reach (``tests/conftest.py``). The
correct justification for leaving ``timeout = 60`` unchanged is therefore
that the binding risk is not this file's runtime — raising the ceiling would
mask an upstream cost rather than fix it, and this file does not need a
larger budget to pass reliably on its own.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import tapps_validate_changed
from tapps_mcp.tools import content_hash_cache as _chc
from tapps_mcp.tools import event_loop_guard as guard
from tapps_mcp.tools.parallel import ParallelResults

# Wall-clock ceiling for the two-root acceptance run. Real scoring is stubbed
# at the subprocess boundary, so a healthy run is sub-second; anything near
# this bound means the batch is wedged.
_BOTH_RETURN_BOUND_S = 20.0

# Each of this fixture's own teardown steps is trivial (dict.clear() / setting
# a module global to None) with no I/O — a real hang there would be a new,
# distinct defect, not TAP-5965 recurring. Bound each step so that a genuine
# regression fails fast with a named step instead of riding the shared 60s
# item-level pytest-timeout ceiling to an unattributed error.
_TEARDOWN_STEP_BOUND_S = 2.0


def _phase_log_path() -> Path:
    """Durable, uncaptured per-process phase log for this test file.

    Written as plain file I/O (not ``print``) because pytest's default
    capture closes/reopens stdout per test, and pytest-timeout's SIGALRM
    handler (the ``signal`` method used here) only dumps *other* threads'
    stacks, never the main thread's own current frame — so a phase recorded
    via ``print`` can be lost, and the one frame most useful for diagnosing
    a stuck main thread is exactly the one pytest-timeout does not show.
    """
    return Path(tempfile.gettempdir()) / f"tap7785_phase_log_{os.getpid()}.log"


def _record_phase(phase: str) -> None:
    with _phase_log_path().open("a", encoding="utf-8") as f:
        f.write(f"{time.monotonic():.3f} {phase}\n")


def _read_phases() -> list[str]:
    path = _phase_log_path()
    if not path.exists():
        return []
    return [
        line.split(" ", 1)[1].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="session", autouse=True)
def _reset_phase_log() -> None:
    """Start this worker's phase log clean, once per session.

    Guards against stale entries from an earlier pytest invocation that
    happened to reuse this OS pid.
    """
    _phase_log_path().unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clear_state() -> Any:
    _record_phase("setup:start")
    t0 = time.monotonic()
    _chc.clear()
    guard.reset_heavy_cpu_semaphore_for_tests()
    dt = time.monotonic() - t0
    assert dt < _TEARDOWN_STEP_BOUND_S, (
        f"setup:clear_state took {dt:.2f}s (bound {_TEARDOWN_STEP_BOUND_S}s) "
        "— content_hash_cache.clear()/reset_heavy_cpu_semaphore_for_tests() "
        "do no I/O and must be near-instant; this is a new defect, not load."
    )
    _record_phase("setup:done")
    yield
    _record_phase("teardown:start")
    t0 = time.monotonic()
    _chc.clear()
    dt = time.monotonic() - t0
    assert dt < _TEARDOWN_STEP_BOUND_S, (
        f"teardown:content_hash_cache.clear() took {dt:.2f}s "
        f"(bound {_TEARDOWN_STEP_BOUND_S}s) — this call does no I/O."
    )
    _record_phase("teardown:cache_cleared")
    t0 = time.monotonic()
    guard.reset_heavy_cpu_semaphore_for_tests()
    dt = time.monotonic() - t0
    assert dt < _TEARDOWN_STEP_BOUND_S, (
        f"teardown:reset_heavy_cpu_semaphore_for_tests() took {dt:.2f}s "
        f"(bound {_TEARDOWN_STEP_BOUND_S}s) — this call does no I/O."
    )
    _record_phase("teardown:semaphore_reset")


def _make_root(tmp_path: Path, name: str, n_files: int) -> tuple[Path, list[str]]:
    root = tmp_path / name
    root.mkdir()
    names = []
    for i in range(n_files):
        (root / f"mod{i}.py").write_text(f"def f{i}(x: int) -> int:\n    return x + {i}\n")
        names.append(f"mod{i}.py")
    return root, names


def _settings_for(root: Path) -> Any:
    settings = MagicMock()
    settings.project_root = root
    settings.tool_timeout = 30
    settings.dependency_scan_enabled = False
    settings.quality_preset = "standard"
    settings.validate_changed.judges = []
    settings.validate_changed.missing_file_paths_mode = "off"
    settings.memory.recall_on_validate = False
    settings.model_copy.return_value = settings
    return settings


async def _no_subprocess_tools(*_args: Any, **_kwargs: Any) -> ParallelResults:
    """Stand in for the ruff/mypy/bandit/radon fan-out.

    Keeps ``CodeScorer.score_file`` — and therefore its nested ``heavy_cpu()``
    acquisition — on the real code path while removing subprocess latency.
    """
    return ParallelResults()


@pytest.mark.asyncio
async def test_two_concurrent_roots_full_mode_both_return(tmp_path: Path) -> None:
    """Two concurrent full-mode calls from distinct roots must both return."""
    _record_phase("call:start")
    root_a, files_a = _make_root(tmp_path, "repo_a", 2)
    root_b, files_b = _make_root(tmp_path, "repo_b", 2)

    # Pin the guard to its shipped limit so the test reproduces the field
    # geometry (2 heavy slots vs 2 concurrent files per call) regardless of
    # TAPPS_MCP_HEAVY_CPU_LIMIT in the developer's environment.
    with (
        patch.object(guard, "_LIMIT", 2),
        patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            side_effect=_no_subprocess_tools,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            side_effect=lambda *a, **k: _settings_for(root_a),
        ),
    ):
        guard.reset_heavy_cpu_semaphore_for_tests()
        loop = asyncio.get_running_loop()
        started = loop.time()
        _record_phase("call:awaiting_gather")
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    tapps_validate_changed(
                        file_paths=",".join(files_a),
                        project_root=str(root_a),
                        quick=False,
                        include_security=False,
                    ),
                    tapps_validate_changed(
                        file_paths=",".join(files_b),
                        project_root=str(root_b),
                        quick=False,
                        include_security=False,
                    ),
                ),
                timeout=_BOTH_RETURN_BOUND_S,
            )
        finally:
            # Recorded even on the wait_for-timeout path: it is the marker
            # that distinguishes "the gather itself returned/raised" from
            # "the main thread never got scheduled to notice the deadline" —
            # the latter is what a genuine TAP-5965-style wedge looks like.
            _record_phase("call:gather_returned")
        elapsed = loop.time() - started

    assert elapsed < _BOTH_RETURN_BOUND_S
    for result in results:
        assert result["tool"] == "tapps_validate_changed"
        data = result["data"]
        assert data.get("timed_out") is not True
        assert data["files_validated"] == 2
    _record_phase("call:done")

    # Positive control: a healthy run must still name every phase it passed
    # through, not only a failing one — otherwise the instrumentation would
    # only ever fire on the failure path it exists to diagnose.
    phases = _read_phases()
    for expected in (
        "setup:start",
        "setup:done",
        "call:start",
        "call:awaiting_gather",
        "call:gather_returned",
        "call:done",
    ):
        assert expected in phases, f"phase log missing {expected!r}: {phases}"


@pytest.mark.asyncio
async def test_explicit_paths_batch_is_wall_clock_bounded(tmp_path: Path) -> None:
    """A stuck file yields a structured timeout envelope, never a hang."""
    files = []
    for i in range(2):
        p = tmp_path / f"stuck{i}.py"
        p.write_text(f"x = {i}\n", encoding="utf-8")
        files.append(p)

    async def never_returns(path: Path, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    with (
        patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_settings_for(tmp_path),
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._discover_changed_files",
            return_value=files,
        ),
        patch(
            "tapps_mcp.server_pipeline_tools._validate_single_file",
            side_effect=never_returns,
        ),
        patch(
            "tapps_mcp.tools.validate_changed_orchestrator._EXPLICIT_PATHS_BUDGET_S",
            0.25,
        ),
    ):
        result = await asyncio.wait_for(
            tapps_validate_changed(
                file_paths=",".join(str(p) for p in files),
                include_impact=False,
            ),
            timeout=30,
        )

    data = result["data"]
    assert data["timed_out"] is True
    assert data["code"] == "validate_changed_timeout"
    assert data["files_remaining"] == 2
    assert data["all_gates_passed"] is False

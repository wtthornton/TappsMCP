"""Regression: an async command timeout must be bounded even with grandchildren.

`tapps-mcp validate-changed --full` hung for 44+ minutes on `pip-audit` despite
`timeout=30`, and never logged `command_timeout_async`. Two compounding causes:

* ``proc.kill()`` signals only the direct child, so processes it spawned kept the
  inherited stdout/stderr write-ends open;
* ``asyncio.wait_for`` cancels ``communicate()`` and then *awaits* that
  cancellation, which cannot finish while those pipes are held — so the
  ``except TimeoutError`` handler was never reached at all.

These tests spawn a child that leaves a long-lived grandchild holding the pipes,
which is the shape that reproduced it.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

from tapps_mcp.tools.subprocess_runner import run_command_async

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process-group kill is POSIX-only")

# Child spawns a detached grandchild that holds the inherited pipes, then sleeps.
# Killing only the child would leave the grandchild keeping communicate() open.
_SPAWNS_GRANDCHILD = (
    "import subprocess,time,sys;"
    "subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)']);"
    "time.sleep(300)"
)


@pytest.mark.asyncio
async def test_timeout_is_bounded_when_child_leaves_a_grandchild() -> None:
    start = time.monotonic()
    result = await run_command_async([sys.executable, "-c", _SPAWNS_GRANDCHILD], timeout=2)
    elapsed = time.monotonic() - start

    assert result.timed_out is True
    assert result.returncode == -1
    assert "Timed out after 2s" in result.stderr
    # Generous ceiling: the point is bounded-vs-unbounded, not precision.
    assert elapsed < 30, f"timeout path took {elapsed:.1f}s — the hang is back"


@pytest.mark.asyncio
async def test_grandchild_is_killed_not_left_running() -> None:
    """The whole tree must die; a survivor is a leak and re-opens the hang."""
    marker = "tapps-timeout-regression-marker"
    script = (
        "import subprocess,time,sys;"
        f"subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)#{marker}']);"
        "time.sleep(300)"
    )
    await run_command_async([sys.executable, "-c", script], timeout=2)
    await asyncio.sleep(0.5)

    check = await asyncio.create_subprocess_exec(
        "pgrep", "-f", marker, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await check.communicate()
    survivors = [line for line in out.decode().split() if line.strip()]
    assert not survivors, f"grandchild survived the timeout kill: {survivors}"


@pytest.mark.asyncio
async def test_simple_child_still_times_out_correctly() -> None:
    start = time.monotonic()
    result = await run_command_async(
        [sys.executable, "-c", "import time;time.sleep(300)"], timeout=2
    )
    assert result.timed_out is True
    assert time.monotonic() - start < 30


@pytest.mark.asyncio
async def test_fast_command_is_unaffected() -> None:
    result = await run_command_async([sys.executable, "-c", "print('ok')"], timeout=30)
    assert result.timed_out is False
    assert result.returncode == 0
    assert result.stdout == "ok"


@pytest.mark.asyncio
async def test_nonzero_exit_is_reported_not_treated_as_timeout() -> None:
    result = await run_command_async([sys.executable, "-c", "import sys;sys.exit(3)"], timeout=30)
    assert result.timed_out is False
    assert result.returncode == 3


@pytest.mark.asyncio
async def test_stderr_is_captured() -> None:
    result = await run_command_async(
        [sys.executable, "-c", "import sys;sys.stderr.write('boom')"], timeout=30
    )
    assert "boom" in result.stderr
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_stdin_is_still_delivered() -> None:
    result = await run_command_async(
        [sys.executable, "-c", "import sys;print(sys.stdin.read().strip())"],
        timeout=30,
        stdin_data="hello",
    )
    assert result.stdout == "hello"

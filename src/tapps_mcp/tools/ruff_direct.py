"""Direct ruff execution - synchronous subprocess in thread pool.

Uses ``subprocess.run`` instead of ``asyncio.create_subprocess_exec``
for more reliable execution in MCP server async contexts.  Ruff does
not expose a Python library API (it is a Rust binary), so subprocess
is the only option - but synchronous execution via ``asyncio.to_thread``
avoids the async subprocess issues that can cause silent failures.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

import structlog

from tapps_mcp.tools.ruff import parse_ruff_json

if TYPE_CHECKING:
    from tapps_mcp.scoring.models import LintIssue

logger = structlog.get_logger(__name__)


def _run_ruff_sync(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
) -> list[LintIssue]:
    """Run ``ruff check --output-format=json`` synchronously.

    Uses ``subprocess.run`` for reliable, blocking execution.
    """
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError:
        logger.debug("ruff_direct_not_found")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("ruff_direct_timeout", file=file_path, timeout=timeout)
        return []

    if not result.stdout.strip():
        return []
    return parse_ruff_json(result.stdout)


async def run_ruff_check_direct(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
) -> list[LintIssue]:
    """Async wrapper that runs ruff synchronously in a thread pool.

    More reliable than ``asyncio.create_subprocess_exec`` in MCP async
    contexts where async subprocess can silently fail.
    """
    return await asyncio.to_thread(
        _run_ruff_sync, file_path, cwd=cwd, timeout=timeout,
    )

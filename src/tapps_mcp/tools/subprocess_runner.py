"""Centralised subprocess execution.

All external tool invocations (ruff, mypy, bandit, radon) should go
through ``run_command`` / ``run_command_async`` so that timeout handling,
logging, and Windows shim wrapping are applied consistently.
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess

import structlog

from tapps_mcp.tools.subprocess_utils import CommandResult, wrap_windows_cmd_shim

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT: int = 60


def run_command(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    stdin_data: str | None = None,
) -> CommandResult:
    """Run an external command synchronously.

    The command is automatically wrapped for Windows ``.cmd`` shims.

    Args:
        cmd: Command and arguments.
        cwd: Working directory.
        timeout: Timeout in seconds.
        env: Environment variable overrides.
        stdin_data: Data to pipe to stdin.

    Returns:
        ``CommandResult`` with return code, stdout, stderr.
    """
    cmd = wrap_windows_cmd_shim(cmd)
    logger.debug("run_command", cmd=cmd, cwd=cwd, timeout=timeout)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            input=stdin_data,
        )
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            command=cmd,
        )
    except subprocess.TimeoutExpired:
        logger.warning("command_timeout", cmd=cmd, timeout=timeout)
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Timed out after {timeout}s",
            command=cmd,
            timed_out=True,
        )
    except FileNotFoundError:
        logger.error("command_not_found", cmd=cmd[0] if cmd else "<empty>")
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0] if cmd else '<empty>'}",
            command=cmd,
        )


async def run_command_async(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    stdin_data: str | None = None,
) -> CommandResult:
    """Run an external command asynchronously via ``asyncio.create_subprocess_exec``.

    Args:
        cmd: Command and arguments.
        cwd: Working directory.
        timeout: Timeout in seconds.
        env: Environment variable overrides.
        stdin_data: Data to pipe to stdin.

    Returns:
        ``CommandResult`` with return code, stdout, stderr.
    """
    cmd = wrap_windows_cmd_shim(cmd)
    logger.debug("run_command_async", cmd=cmd, cwd=cwd, timeout=timeout)

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(
                input=stdin_data.encode() if stdin_data else None,
            ),
            timeout=timeout,
        )
        return CommandResult(
            returncode=proc.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace").strip() if stdout_bytes else "",
            stderr=stderr_bytes.decode("utf-8", errors="replace").strip() if stderr_bytes else "",
            command=cmd,
        )
    except TimeoutError:
        logger.warning("command_timeout_async", cmd=cmd, timeout=timeout)
        with contextlib.suppress(Exception):
            if proc is not None:
                proc.kill()
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Timed out after {timeout}s",
            command=cmd,
            timed_out=True,
        )
    except (FileNotFoundError, OSError) as exc:
        logger.error("command_not_found_async", cmd=cmd[0] if cmd else "<empty>", error=str(exc))
        return CommandResult(
            returncode=-1,
            stdout="",
            stderr=f"Command error: {exc}",
            command=cmd,
        )

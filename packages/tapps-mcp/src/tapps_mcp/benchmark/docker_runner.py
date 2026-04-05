"""Docker container management for benchmark evaluation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tapps_mcp.benchmark.models import BenchmarkInstance

logger = structlog.get_logger()

__all__ = ["DockerNotAvailableError", "DockerRunner", "TestResult"]


@dataclass(frozen=True)
class TestResult:
    """Result of running tests in a Docker container."""

    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0


class DockerNotAvailableError(Exception):
    """Docker SDK not installed or daemon not running."""


class DockerRunner:
    """Manages Docker containers for benchmark evaluation.

    Uses the Docker SDK for Python to create isolated sandbox containers,
    apply patches, run test suites, and clean up resources. Containers are
    created with network isolation and memory limits for safety.
    """

    def __init__(self, timeout: int = 300) -> None:
        self._timeout = timeout
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize Docker client.

        Raises:
            DockerNotAvailableError: If the Docker SDK is not installed or
                the Docker daemon is unreachable.
        """
        if self._client is not None:
            return self._client
        try:
            import docker  # type: ignore[import-untyped]

            self._client = docker.from_env()
            # Test connectivity
            self._client.ping()
            return self._client
        except ImportError as exc:
            msg = (
                "Docker SDK for Python is required for benchmark "
                "evaluation. Install with: uv add docker"
            )
            raise DockerNotAvailableError(msg) from exc
        except Exception as exc:
            if isinstance(exc, DockerNotAvailableError):
                raise
            msg = f"Docker daemon not available: {exc}"
            raise DockerNotAvailableError(msg) from exc

    async def prepare_container(
        self,
        instance: BenchmarkInstance,
        work_dir: str | None = None,
    ) -> str:
        """Pull/build image and create a container.

        Args:
            instance: Benchmark instance with Docker image and setup commands.
            work_dir: Optional working directory override inside the container.

        Returns:
            The container ID as a string.
        """
        client = self._get_client()
        image = instance.docker_image or "python:3.12-slim"
        effective_workdir = work_dir or "/workspace"

        # Pull image
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, client.images.pull, image)
        except Exception:
            logger.warning("docker_pull_failed", image=image)

        # Create container with working directory
        container = await loop.run_in_executor(
            None,
            lambda: client.containers.create(
                image,
                command="sleep infinity",
                detach=True,
                working_dir=effective_workdir,
                mem_limit="512m",
                network_mode="none",
            ),
        )

        # Start container
        await loop.run_in_executor(None, container.start)

        # Run setup commands
        for cmd in instance.setup_commands:
            await self._exec_in_container(container.id, cmd)

        logger.info(
            "container_prepared",
            container_id=container.short_id,
            image=image,
        )
        return str(container.id)

    async def apply_patch(self, container_id: str, patch: str) -> bool:
        """Apply a unified diff patch to the repo in the container.

        Args:
            container_id: Docker container ID.
            patch: Unified diff content.

        Returns:
            True if the patch was applied successfully, False otherwise.
        """
        client = self._get_client()
        container = client.containers.get(container_id)

        try:
            escaped = patch.replace("'", "'\\''")
            exit_code, output = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: container.exec_run(
                    [
                        "sh",
                        "-c",
                        f"echo '{escaped}' | patch -p1 --no-backup-if-mismatch",
                    ],
                    workdir="/workspace",
                ),
            )
            if exit_code != 0:
                logger.warning(
                    "patch_apply_failed",
                    exit_code=exit_code,
                    output=output.decode(errors="replace")[:500],
                )
                return False
            return True
        except Exception as exc:
            logger.error("patch_apply_error", error=str(exc))
            return False

    async def run_tests(
        self,
        container_id: str,
        commands: list[str],
        timeout: int | None = None,
    ) -> TestResult:
        """Execute test commands in the container.

        Args:
            container_id: Docker container ID.
            commands: Shell commands to execute sequentially.
            timeout: Per-command timeout in seconds (defaults to
                constructor timeout).

        Returns:
            Aggregated test result with stdout/stderr and timing.
        """
        effective_timeout = timeout or self._timeout
        client = self._get_client()
        container = client.containers.get(container_id)

        all_stdout: list[str] = []
        all_stderr: list[str] = []
        all_passed = True
        start = time.monotonic()

        for cmd in commands:
            try:
                exit_code, output = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda c=cmd: container.exec_run(  # type: ignore[misc]
                            ["sh", "-c", c],
                            workdir="/workspace",
                        ),
                    ),
                    timeout=effective_timeout,
                )
                decoded = output.decode(errors="replace")
                all_stdout.append(decoded)
                if exit_code != 0:
                    all_passed = False
                    all_stderr.append(f"Command '{cmd}' failed (exit {exit_code})")
            except TimeoutError:
                all_passed = False
                all_stderr.append(f"Command '{cmd}' timed out after {effective_timeout}s")
                break
            except Exception as exc:
                all_passed = False
                all_stderr.append(f"Command '{cmd}' error: {exc}")

        duration_ms = int((time.monotonic() - start) * 1000)

        return TestResult(
            passed=all_passed,
            stdout="\n".join(all_stdout),
            stderr="\n".join(all_stderr),
            duration_ms=duration_ms,
        )

    async def cleanup(self, container_id: str) -> None:
        """Remove container and associated volumes.

        Args:
            container_id: Docker container ID to remove.
        """
        try:
            client = self._get_client()
            container = client.containers.get(container_id)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: container.remove(force=True, v=True),
            )
            logger.debug(
                "container_cleaned",
                container_id=container_id[:12],
            )
        except Exception as exc:
            logger.warning("container_cleanup_failed", error=str(exc))

    async def _exec_in_container(self, container_id: str, cmd: str) -> tuple[int, str]:
        """Execute a command in a container.

        Args:
            container_id: Docker container ID.
            cmd: Shell command to execute.

        Returns:
            Tuple of (exit_code, decoded_output).
        """
        client = self._get_client()
        container = client.containers.get(container_id)
        exit_code, output = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: container.exec_run(["sh", "-c", cmd], workdir="/workspace"),
        )
        return exit_code, output.decode(errors="replace")

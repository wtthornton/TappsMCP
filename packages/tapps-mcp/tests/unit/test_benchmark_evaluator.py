"""Unit tests for Evaluator, EvaluatorBackend, and DockerRunner (Epic 30, Story 4)."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.benchmark.docker_runner import (
    DockerNotAvailableError,
    DockerRunner,
    TestResult,
)
from tapps_mcp.benchmark.evaluator import Evaluator, EvaluatorBackend
from tapps_mcp.benchmark.mock_evaluator import MockEvaluator
from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkInstance,
    BenchmarkResult,
    ContextMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, Any] = {
    "instance_id": "test-001",
    "repo": "owner/repo",
    "problem_description": "Fix the bug.",
    "clean_pr_patch": "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n",
    "test_commands": ["pytest tests/"],
    "test_file_names": ["tests/test_foo.py"],
    "test_file_contents": {"tests/test_foo.py": "def test(): pass"},
    "docker_image": "python:3.12-slim",
}


def _make_instance(**overrides: Any) -> BenchmarkInstance:
    """Build a BenchmarkInstance with sensible defaults."""
    fields: dict[str, Any] = {**_REQUIRED_FIELDS, **overrides}
    return BenchmarkInstance(**fields)


def _make_config(**overrides: Any) -> BenchmarkConfig:
    """Build a BenchmarkConfig with sensible defaults."""
    defaults: dict[str, Any] = {
        "context_mode": ContextMode.NONE,
        "engagement_level": "medium",
        "workers": 4,
    }
    defaults.update(overrides)
    return BenchmarkConfig(**defaults)


# ---------------------------------------------------------------------------
# TestResult dataclass tests
# ---------------------------------------------------------------------------


class TestTestResult:
    """Tests for the TestResult dataclass."""

    def test_creation_with_defaults(self) -> None:
        """TestResult can be created with only the required field."""
        result = TestResult(passed=True)
        assert result.passed is True
        assert result.total_tests == 0
        assert result.passed_tests == 0
        assert result.failed_tests == 0
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.duration_ms == 0

    def test_creation_with_all_fields(self) -> None:
        """TestResult accepts all optional fields."""
        result = TestResult(
            passed=False,
            total_tests=10,
            passed_tests=7,
            failed_tests=3,
            stdout="test output",
            stderr="error output",
            duration_ms=1500,
        )
        assert result.passed is False
        assert result.total_tests == 10
        assert result.passed_tests == 7
        assert result.failed_tests == 3
        assert result.stdout == "test output"
        assert result.stderr == "error output"
        assert result.duration_ms == 1500

    def test_frozen_dataclass(self) -> None:
        """TestResult is frozen (immutable)."""
        result = TestResult(passed=True)
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DockerRunner tests
# ---------------------------------------------------------------------------


class TestDockerRunnerNotInstalled:
    """Tests for DockerRunner when docker SDK is unavailable."""

    def test_raises_when_docker_not_installed(self) -> None:
        """DockerNotAvailableError raised when docker import fails."""
        runner = DockerRunner()

        with (
            patch.dict(sys.modules, {"docker": None}),
            pytest.raises(DockerNotAvailableError, match="Docker SDK"),
        ):
            runner._get_client()

    def test_raises_when_daemon_unreachable(self) -> None:
        """DockerNotAvailableError raised when daemon ping fails."""
        runner = DockerRunner()
        mock_docker = types.ModuleType("docker")
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("refused")
        mock_docker.from_env = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]

        with (
            patch.dict(sys.modules, {"docker": mock_docker}),
            pytest.raises(DockerNotAvailableError, match="Docker daemon"),
        ):
            runner._get_client()

    def test_client_cached_after_success(self) -> None:
        """Successful client initialization is cached."""
        runner = DockerRunner()
        mock_docker = types.ModuleType("docker")
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.from_env = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"docker": mock_docker}):
            client1 = runner._get_client()
            client2 = runner._get_client()

        assert client1 is client2
        # from_env should only be called once
        mock_docker.from_env.assert_called_once()  # type: ignore[attr-defined]

    def test_custom_timeout(self) -> None:
        """DockerRunner stores custom timeout."""
        runner = DockerRunner(timeout=600)
        assert runner._timeout == 600


class TestDockerRunnerErrorMessage:
    """Tests for DockerNotAvailableError messaging."""

    def test_error_message_contains_install_hint(self) -> None:
        """Error message includes installation instructions."""
        runner = DockerRunner()

        with patch.dict(sys.modules, {"docker": None}):
            try:
                runner._get_client()
            except DockerNotAvailableError as exc:
                assert "uv add docker" in str(exc)
            else:
                pytest.fail("Expected DockerNotAvailableError")


# ---------------------------------------------------------------------------
# Evaluator with MockEvaluator backend
# ---------------------------------------------------------------------------


class TestEvaluatorWithBackend:
    """Tests for Evaluator using MockEvaluator as backend."""

    async def test_evaluate_instance_delegates_to_backend(self) -> None:
        """Evaluator delegates to backend for instance evaluation."""
        config = _make_config()
        backend = MockEvaluator(outcomes={("eval-001", ContextMode.NONE): True})
        evaluator = Evaluator(config=config, backend=backend)
        instance = _make_instance(instance_id="eval-001")

        result = await evaluator.evaluate_instance(instance, ContextMode.NONE)

        assert result.resolved is True
        assert result.instance_id == "eval-001"
        assert result.context_mode is ContextMode.NONE
        assert result.engagement_level == "medium"
        assert backend.call_count == 1

    async def test_evaluate_instance_passes_engagement_level(
        self,
    ) -> None:
        """Backend receives the config engagement level."""
        config = _make_config(engagement_level="high")
        backend = MockEvaluator()
        evaluator = Evaluator(config=config, backend=backend)
        instance = _make_instance()

        result = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)

        assert result.engagement_level == "high"


class TestEvaluatorNoBackend:
    """Tests for Evaluator without a backend."""

    async def test_returns_unresolved_with_error(self) -> None:
        """Without a backend, returns unresolved result with error."""
        config = _make_config()
        evaluator = Evaluator(config=config, backend=None)
        instance = _make_instance(instance_id="no-backend-001")

        result = await evaluator.evaluate_instance(instance, ContextMode.NONE)

        assert result.resolved is False
        assert result.error == "No evaluation backend configured"
        assert result.instance_id == "no-backend-001"
        assert result.context_mode is ContextMode.NONE


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------


class TestEvaluatorBatch:
    """Tests for batch evaluation."""

    async def test_batch_returns_all_results(self) -> None:
        """Batch evaluation returns one result per instance."""
        config = _make_config(workers=2)
        backend = MockEvaluator(seed=42)
        evaluator = Evaluator(config=config, backend=backend)
        instances = [_make_instance(instance_id=f"batch-{i}") for i in range(5)]

        results = await evaluator.evaluate_batch(instances, ContextMode.NONE)

        assert len(results) == 5
        assert all(isinstance(r, BenchmarkResult) for r in results)
        ids = {r.instance_id for r in results}
        assert ids == {f"batch-{i}" for i in range(5)}

    async def test_batch_respects_parallelism(self) -> None:
        """Workers setting limits concurrency."""
        config = _make_config(workers=2)

        # Track concurrent calls
        max_concurrent = 0
        current_concurrent = 0
        call_lock = __import__("asyncio").Lock()

        class TrackingBackend:
            """Backend that tracks concurrent execution."""

            async def evaluate_instance(
                self,
                instance: BenchmarkInstance,
                context_mode: ContextMode,
                engagement_level: str,
            ) -> BenchmarkResult:
                nonlocal max_concurrent, current_concurrent
                async with call_lock:
                    current_concurrent += 1
                    max_concurrent = max(max_concurrent, current_concurrent)

                await __import__("asyncio").sleep(0.01)

                async with call_lock:
                    current_concurrent -= 1

                return BenchmarkResult(
                    instance_id=instance.instance_id,
                    context_mode=context_mode,
                    engagement_level=engagement_level,
                    resolved=True,
                )

        evaluator = Evaluator(config=config, backend=TrackingBackend())
        instances = [_make_instance(instance_id=f"par-{i}") for i in range(6)]

        results = await evaluator.evaluate_batch(instances, ContextMode.NONE)

        assert len(results) == 6
        # Semaphore should limit to 2 concurrent
        assert max_concurrent <= 2

    async def test_batch_handles_errors(self) -> None:
        """Individual failures produce error results, not crashes."""
        config = _make_config()
        call_count = 0

        class FailingBackend:
            """Backend that fails on the second call."""

            async def evaluate_instance(
                self,
                instance: BenchmarkInstance,
                context_mode: ContextMode,
                engagement_level: str,
            ) -> BenchmarkResult:
                nonlocal call_count
                call_count += 1
                if instance.instance_id == "fail-1":
                    msg = "Simulated failure"
                    raise RuntimeError(msg)
                return BenchmarkResult(
                    instance_id=instance.instance_id,
                    context_mode=context_mode,
                    engagement_level=engagement_level,
                    resolved=True,
                )

        evaluator = Evaluator(config=config, backend=FailingBackend())
        instances = [_make_instance(instance_id=f"fail-{i}") for i in range(3)]

        results = await evaluator.evaluate_batch(instances, ContextMode.NONE)

        assert len(results) == 3
        # Instance fail-1 should have error, others resolved
        error_results = [r for r in results if r.error is not None]
        resolved_results = [r for r in results if r.resolved is True]
        assert len(error_results) == 1
        assert "Simulated failure" in error_results[0].error  # type: ignore[operator]
        assert len(resolved_results) == 2

    async def test_batch_progress_callback(self) -> None:
        """Progress callback is called with correct counts."""
        config = _make_config(workers=1)
        backend = MockEvaluator(seed=42)
        evaluator = Evaluator(config=config, backend=backend)
        instances = [_make_instance(instance_id=f"prog-{i}") for i in range(3)]

        progress_calls: list[tuple[int, int]] = []

        def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        await evaluator.evaluate_batch(instances, ContextMode.NONE, progress_callback=on_progress)

        # Should be called once per instance
        assert len(progress_calls) == 3
        # All calls should have total=3
        assert all(total == 3 for _, total in progress_calls)
        # Completed values should include 1, 2, 3 (order may vary
        # with parallelism, but workers=1 ensures sequential)
        completed_values = sorted(c for c, _ in progress_calls)
        assert completed_values == [1, 2, 3]


# ---------------------------------------------------------------------------
# All-conditions evaluation
# ---------------------------------------------------------------------------


class TestEvaluatorAllConditions:
    """Tests for evaluate_all_conditions."""

    async def test_all_mode_evaluates_three_modes(self) -> None:
        """ContextMode.ALL evaluates NONE, TAPPS, and HUMAN."""
        config = _make_config(context_mode=ContextMode.ALL)
        backend = MockEvaluator(seed=42)
        evaluator = Evaluator(config=config, backend=backend)
        instances = [_make_instance(instance_id=f"all-{i}") for i in range(2)]

        results = await evaluator.evaluate_all_conditions(instances)

        assert set(results.keys()) == {
            ContextMode.NONE,
            ContextMode.TAPPS,
            ContextMode.HUMAN,
        }
        for mode_results in results.values():
            assert len(mode_results) == 2

    async def test_single_mode_evaluates_only_that_mode(
        self,
    ) -> None:
        """Non-ALL mode evaluates only the specified mode."""
        config = _make_config(context_mode=ContextMode.TAPPS)
        backend = MockEvaluator(seed=42)
        evaluator = Evaluator(config=config, backend=backend)
        instances = [_make_instance(instance_id="single-001")]

        results = await evaluator.evaluate_all_conditions(instances)

        assert list(results.keys()) == [ContextMode.TAPPS]
        assert len(results[ContextMode.TAPPS]) == 1
        assert results[ContextMode.TAPPS][0].instance_id == "single-001"

    async def test_all_mode_result_modes_match_keys(self) -> None:
        """Each result has a context_mode matching its dict key."""
        config = _make_config(context_mode=ContextMode.ALL)
        backend = MockEvaluator(seed=42)
        evaluator = Evaluator(config=config, backend=backend)
        instances = [_make_instance(instance_id="match-001")]

        results = await evaluator.evaluate_all_conditions(instances)

        for mode, mode_results in results.items():
            for result in mode_results:
                assert result.context_mode is mode


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestEvaluatorBackendProtocol:
    """Tests for EvaluatorBackend protocol compliance."""

    def test_mock_evaluator_satisfies_protocol(self) -> None:
        """MockEvaluator is a structural match for EvaluatorBackend."""
        backend: EvaluatorBackend = MockEvaluator()
        # If this assignment type-checks and runs, the protocol is
        # satisfied structurally.
        assert hasattr(backend, "evaluate_instance")

    def test_custom_backend_satisfies_protocol(self) -> None:
        """A custom class with the right signature satisfies the protocol."""

        class CustomBackend:
            async def evaluate_instance(
                self,
                instance: BenchmarkInstance,
                context_mode: ContextMode,
                engagement_level: str,
            ) -> BenchmarkResult:
                return BenchmarkResult(
                    instance_id=instance.instance_id,
                    context_mode=context_mode,
                    engagement_level=engagement_level,
                    resolved=True,
                )

        backend: EvaluatorBackend = CustomBackend()
        assert hasattr(backend, "evaluate_instance")


# ---------------------------------------------------------------------------
# Evaluator property access
# ---------------------------------------------------------------------------


class TestEvaluatorProperties:
    """Tests for Evaluator property accessors."""

    def test_injector_property(self) -> None:
        """Evaluator exposes its ContextInjector via property."""
        config = _make_config(engagement_level="high")
        evaluator = Evaluator(config=config)
        injector = evaluator.injector
        assert injector is not None
        assert injector._engagement_level == "high"

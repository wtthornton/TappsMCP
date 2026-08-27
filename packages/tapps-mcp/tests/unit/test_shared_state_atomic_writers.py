"""VAL-16 / TAP-6081: shared-state writers must never publish a torn file.

Every writer covered here persists JSON (or a single id line) to a path that
other threads and other processes read concurrently. Before TAP-6081 they used
a bare ``Path.write_text``, which truncates the target and then streams bytes
in — a reader landing mid-write sees a prefix. The corruption was observed live
in WebStoreDNA's ``tool-versions.json``, and is reachable inside a single
``tapps_validate_changed`` call (``_VALIDATE_CONCURRENCY`` worker threads all
missing the ``detect_installed_tools`` cache at once).

The probe: N writer threads publish payloads of deliberately different lengths
to one path while a reader thread reads it as fast as it can. Every read that
sees the file at all must parse. Length variation is what makes the assertion
meaningful — same-length payloads can mask truncation because a torn read of a
constant-shape file may still happen to parse.

All state is under ``tmp_path``; nothing here touches the live repo's
``.tapps-mcp/`` or any sibling checkout.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tapps_core.agent_identity import _write_uuid
from tapps_core.brain_bridge import _write_tools_warm_cache
from tapps_core.common.models import InstalledTool
from tapps_core.metrics.confidence_metrics import ConfidenceMetric, ConfidenceMetricsTracker
from tapps_core.metrics.rag_metrics import RAGMetricsTracker, RAGQueryMetric
from tapps_mcp.project.profile_cache import save_cached_profile_summary
from tapps_mcp.tools import tool_detection

if TYPE_CHECKING:
    from collections.abc import Callable

_WRITER_THREADS = 8
_WRITES_PER_THREAD = 30

# Payload sizes chosen so consecutive publishes differ by kilobytes: a stale
# tail left by a truncating writer then shows up as trailing garbage.
_PAYLOAD_SCALE = (1, 60, 3, 250, 12, 900)


def _payload_len(seq: int) -> int:
    """Number of records the *seq*-th write should serialize."""
    return _PAYLOAD_SCALE[seq % len(_PAYLOAD_SCALE)]


# --- one writer factory per shared-state writer under test -------------------


def _setup_tool_detection(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    target = root / ".tapps-mcp" / "tool-versions.json"
    monkeypatch.setattr(tool_detection, "_get_disk_cache_path", lambda: target)

    def write(seq: int) -> None:
        tools = [
            InstalledTool(name=f"tool-{i}", version=f"1.0.{i}", available=True)
            for i in range(_payload_len(seq))
        ]
        tool_detection._write_disk_cache(tools)

    return target, write


def _setup_brain_warm_cache(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    target = root / ".tapps-mcp-cache" / "brain-tools.json"

    def write(seq: int) -> None:
        _write_tools_warm_cache(
            target, frozenset(f"tapps_tool_{i}" for i in range(_payload_len(seq)))
        )

    return target, write


def _setup_profile_cache(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    target = root / ".tapps-mcp" / "profile-cache.json"

    def write(seq: int) -> None:
        profile = {f"key_{i}": "v" * 40 for i in range(_payload_len(seq))}
        save_cached_profile_summary(root, f"fp-{seq}", profile)

    return target, write


def _setup_confidence_metrics(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    tracker = ConfidenceMetricsTracker(root / "metrics")
    target = root / "metrics" / "confidence_metrics.json"
    template = ConfidenceMetric(
        domain="security", confidence=0.75, threshold=0.6, meets_threshold=True
    )

    def write(seq: int) -> None:
        tracker._save([template] * _payload_len(seq))

    return target, write


def _setup_rag_metrics(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    tracker = RAGMetricsTracker(root / "metrics")
    target = root / "metrics" / "rag_metrics.json"
    template = RAGQueryMetric(query="q" * 40, domain="testing", latency_ms=1.5, num_results=3)

    def write(seq: int) -> None:
        tracker._save([template] * _payload_len(seq))

    return target, write


def _setup_agent_id(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Callable[[int], None]]:
    """``agent.id`` is create-if-absent, so every write after the first is a no-op."""
    target = root / ".tapps-mcp" / "agent.id"

    def write(seq: int) -> None:
        _write_uuid(target, f"{seq:032x}")

    return target, write


def _parse_json(raw: str) -> None:
    json.loads(raw)


def _parse_agent_id(raw: str) -> None:
    stripped = raw.strip()
    assert len(stripped) == 32, f"torn agent.id: {stripped!r}"
    int(stripped, 16)


_CASES = {
    "tool_detection._write_disk_cache": (_setup_tool_detection, _parse_json),
    "brain_bridge._write_tools_warm_cache": (_setup_brain_warm_cache, _parse_json),
    "profile_cache.save_cached_profile_summary": (_setup_profile_cache, _parse_json),
    "confidence_metrics.ConfidenceMetricsTracker._save": (_setup_confidence_metrics, _parse_json),
    "rag_metrics.RAGMetricsTracker._save": (_setup_rag_metrics, _parse_json),
    "agent_identity._write_uuid": (_setup_agent_id, _parse_agent_id),
}


@pytest.mark.parametrize("writer_name", sorted(_CASES))
def test_concurrent_writers_never_publish_a_torn_file(
    writer_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TAP-6081 acceptance 2: every intermediate read of the target parses."""
    setup, parse = _CASES[writer_name]
    root = tmp_path / "proj"
    root.mkdir()
    target, write = setup(root, monkeypatch)
    target.parent.mkdir(parents=True, exist_ok=True)

    stop = threading.Event()
    failures: list[str] = []
    reads = [0]

    def reader() -> None:
        while not stop.is_set():
            try:
                raw = target.read_text(encoding="utf-8")
            except OSError:
                continue  # not published yet
            if not raw:
                continue
            reads[0] += 1
            try:
                parse(raw)
            except (AssertionError, ValueError) as exc:
                failures.append(f"torn read after {reads[0]} reads: {exc} :: {raw[:120]!r}")
                return

    def writer(offset: int) -> None:
        for i in range(_WRITES_PER_THREAD):
            write(offset + i)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    writers = [
        threading.Thread(target=writer, args=(t * _WRITES_PER_THREAD,))
        for t in range(_WRITER_THREADS)
    ]
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join(timeout=60)
    stop.set()
    reader_thread.join(timeout=10)

    assert not failures, f"{writer_name}: {failures[0]}"
    assert reads[0] > 0, f"{writer_name}: reader never observed a published file"
    parse(target.read_text(encoding="utf-8"))


# --- observability: corruption and write failures stop being silent ----------


class _LogRecorder:
    """Minimal structlog stand-in that records ``(level, event, kwargs)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def _record(self, level: str) -> Callable[..., None]:
        def log(event: str, **kwargs: object) -> None:
            self.calls.append((level, event, kwargs))

        return log

    def __getattr__(self, level: str) -> Callable[..., None]:
        return self._record(level)

    def events(self, level: str) -> list[str]:
        return [event for lvl, event, _ in self.calls if lvl == level]


def test_unparseable_tool_cache_logs_at_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TAP-6081 acceptance 3: a present-but-corrupt cache file is visible once."""
    target = tmp_path / ".tapps-mcp" / "tool-versions.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"timestamp_epoch": 1, "tools": [{"name": "ru', encoding="utf-8")
    monkeypatch.setattr(tool_detection, "_get_disk_cache_path", lambda: target)
    recorder = _LogRecorder()
    monkeypatch.setattr(tool_detection, "_logger", recorder)

    assert tool_detection._read_disk_cache() is None
    assert "disk_cache_corrupt" in recorder.events("warning"), (
        f"expected a WARNING for the torn cache, got {recorder.calls}"
    )


def test_absent_tool_cache_stays_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An ordinary miss must not be promoted to WARNING — only corruption is."""
    target = tmp_path / ".tapps-mcp" / "tool-versions.json"
    monkeypatch.setattr(tool_detection, "_get_disk_cache_path", lambda: target)
    recorder = _LogRecorder()
    monkeypatch.setattr(tool_detection, "_logger", recorder)

    assert tool_detection._read_disk_cache() is None
    assert recorder.events("warning") == []


def test_warm_cache_write_failure_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TAP-6081 acceptance 4: the bare ``except Exception: pass`` now reports."""
    from tapps_core import brain_bridge

    recorder = _LogRecorder()
    monkeypatch.setattr(brain_bridge, "logger", recorder)
    # A path whose parent is an existing *file* — mkdir raises NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")

    brain_bridge._write_tools_warm_cache(blocker / "sub" / "tools.json", frozenset({"a"}))

    assert "tools_warm_cache_write_failed" in recorder.events("warning"), (
        f"warm-cache write failure was swallowed: {recorder.calls}"
    )

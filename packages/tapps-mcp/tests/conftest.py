"""Shared test fixtures for TappsMCP.

Ensures test isolation by resetting module-level caches between tests.

Cache reset registry
--------------------
Every module-level singleton or cached value that persists across function
calls must be reset here.  When adding a new cache:

1. Create a ``_reset_*()`` function in the source module.
2. Import and call it in ``_reset_caches()`` below.
3. Verify isolation by running the new tests twice in a row.

Current resets (13 total):
  - settings              — ``tapps_core.config.settings._reset_settings_cache``
  - feature_flags         — ``tapps_core.config.feature_flags.feature_flags.reset``
  - scorer           — ``tapps_mcp.server_helpers._reset_scorer_cache``
  - lookup_engine    — ``tapps_mcp.server_helpers._reset_lookup_engine_cache``
  - memory_store     — ``tapps_mcp.server_helpers._reset_memory_store_cache``
  - hive_store       — ``tapps_mcp.server_helpers._reset_hive_store_cache``
  - session_state    — ``tapps_mcp.server_helpers._reset_session_state``
  - tools_detection  — ``tapps_mcp.tools.tool_detection._reset_tools_cache``
  - session_gc_flag  — ``tapps_mcp.server_pipeline_tools._reset_session_gc_flag``
  - background_tasks — ``tapps_mcp.server_pipeline_tools._reset_background_tasks``
  - dependency_cache — ``tapps_mcp.tools.dependency_scan_cache.clear_dependency_cache``
  - quick_check_recurring — ``tapps_mcp.quick_check_recurring._reset_recurring_quick_check_state``
  - memory_project_id     — ``tapps_mcp.memory_project_id.uninstall_memory_project_id_patch``
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
import threading
from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# In-memory PrivateBackend for unit tests (tapps-brain v3 / ADR-007)
# ---------------------------------------------------------------------------
#
# tapps-brain v3 removed SQLite; MemoryStore now requires a Postgres backend.
# Unit tests that don't need real Postgres use this dict-backed stand-in that
# satisfies the PrivateBackend protocol.  Integration tests that need real
# Postgres set TAPPS_BRAIN_DATABASE_URL and bypass this fixture.
#
# The backend registry is shared per-project-root so that tests that create
# multiple MemoryStore instances against the same directory see consistent data.
# The registry is cleared between tests by the autouse fixture below.

_inmemory_backend_registry: dict[str, InMemoryPrivateBackend] = {}

_AUDIT_ROW_KEYS = ("action", "key", "timestamp", "event_type")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _search_tokens(text: str) -> set[str]:
    """Lowercase word tokens, approximating plainto_tsquery's tokenizer."""
    return set(_WORD_RE.findall(text.lower()))


def _entry_matches(entry: Any, q_words: set[str]) -> bool:
    """True when *entry*'s value or key shares a token with *q_words*."""
    return bool(
        q_words & _search_tokens(entry.value)
        or q_words & _search_tokens(entry.key.replace("-", " "))
    )


def _filter_by_created_at(entries: list[Any], *, since: str | None, until: str | None) -> list[Any]:
    """Restrict *entries* to the inclusive ``created_at`` window."""
    if since is not None:
        entries = [e for e in entries if getattr(e, "created_at", "") >= since]
    if until is not None:
        entries = [e for e in entries if getattr(e, "created_at", "") <= until]
    return entries


def _audit_row(rec: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw audit record into the query_audit result shape."""
    return {
        "timestamp": str(rec.get("timestamp", "")),
        "event_type": str(rec.get("event_type") or rec.get("action", "")),
        "key": str(rec.get("key", "")),
        "details": {k: v for k, v in rec.items() if k not in _AUDIT_ROW_KEYS},
    }


def _audit_row_matches(
    row: dict[str, Any],
    *,
    key: str | None,
    event_type: str | None,
    since: str | None,
    until: str | None,
) -> bool:
    """True when *row* satisfies every supplied query_audit filter."""
    if key is not None and row["key"] != key:
        return False
    if event_type is not None and row["event_type"] != event_type:
        return False
    if since is not None and row["timestamp"] < since:
        return False
    return not (until is not None and row["timestamp"] > until)


class InMemoryPrivateBackend:
    """Dict-backed PrivateBackend for unit tests — never used in production."""

    def __init__(self, project_id: str = "test", agent_id: str = "test") -> None:
        self._project_id = project_id
        self._agent_id = agent_id
        self._entries: dict[str, Any] = {}
        self._relations: list[dict[str, Any]] = []
        self._gc_archive: list[dict[str, Any]] = []
        self._gc_archive_bytes: int = 0
        self._lock = threading.Lock()
        self._db_path = Path("/dev/null")
        self._store_dir = Path("/dev/null").parent
        self._tmp_audit_dir: str = tempfile.mkdtemp(prefix="tapps_test_audit_")
        self._audit_path = Path(self._tmp_audit_dir) / "audit.jsonl"
        self._audit_path.touch()
        self._cm = None
        self._feedback_events: list[Any] = []

    @property
    def store_dir(self) -> Path:
        return self._store_dir

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def audit_path(self) -> Path:
        return self._audit_path

    @property
    def encryption_key(self) -> str | None:
        return None

    def save(self, entry: Any) -> None:
        with self._lock:
            self._entries[entry.key] = entry

    def load_all(self, *, limit: int | None = None) -> list[Any]:
        with self._lock:
            entries = list(self._entries.values())
        if limit is not None:
            return entries[:limit]
        return entries

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def search(self, query: str, **kwargs: Any) -> list[Any]:
        """Word-level FTS approximation matching plainto_tsquery token behaviour."""
        if not query.strip():
            return []
        q_words = _search_tokens(query)
        with self._lock:
            results = [e for e in self._entries.values() if _entry_matches(e, q_words)]
        return _filter_by_created_at(results, since=kwargs.get("since"), until=kwargs.get("until"))

    def list_relations(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._relations)

    def count_relations(self) -> int:
        with self._lock:
            return len(self._relations)

    def save_relations(self, key: str, relations: list[Any]) -> int:
        with self._lock:
            for rel in relations:
                self._relations.append(
                    {
                        "subject": getattr(rel, "subject", ""),
                        "predicate": getattr(rel, "predicate", ""),
                        "object_entity": getattr(rel, "object_entity", ""),
                        "source_entry_keys": list(
                            dict.fromkeys([*getattr(rel, "source_entry_keys", []), key])
                        ),
                        "confidence": float(getattr(rel, "confidence", 0.8)),
                        "created_at": "1970-01-01T00:00:00+00:00",
                    }
                )
            return len(relations)

    def load_relations(self, key: str) -> list[dict[str, Any]]:
        with self._lock:
            return [r for r in self._relations if key in r["source_entry_keys"]]

    def delete_relations(self, key: str) -> int:
        with self._lock:
            before = len(self._relations)
            self._relations = [
                r for r in self._relations if key not in r.get("source_entry_keys", [])
            ]
            return before - len(self._relations)

    def get_schema_version(self) -> int:
        return 1

    def knn_search(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        return []

    def vector_row_count(self) -> int:
        return 0

    def append_audit(
        self,
        action: str,
        key: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        from datetime import UTC, datetime

        record: dict[str, Any] = {
            "action": action,
            "key": key,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if extra:
            record.update(extra)
        with self._lock:
            try:
                with self._audit_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, default=str) + "\n")
            except OSError:
                pass

    def archive_entry(self, entry: Any) -> int:
        try:
            payload = entry.model_dump()
            line = json.dumps(payload, default=str)
            byte_count = len(line.encode("utf-8"))
            with self._lock:
                from datetime import UTC, datetime

                self._gc_archive.append(
                    {
                        "key": entry.key,
                        "archived_at": datetime.now(UTC).isoformat(),
                        "byte_count": byte_count,
                        "payload": payload,
                    }
                )
                self._gc_archive_bytes += byte_count
            return byte_count
        except Exception:
            return 0

    def list_archive(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._gc_archive))[:limit]

    def total_archive_bytes(self) -> int:
        with self._lock:
            return self._gc_archive_bytes

    def _read_audit_records(self) -> list[dict[str, Any]]:
        """Parse the audit log into records, skipping blank and malformed lines."""
        try:
            lines = self._audit_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        records: list[dict[str, Any]] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return records

    def query_audit(
        self,
        *,
        key: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for rec in self._read_audit_records():
            row = _audit_row(rec)
            if not _audit_row_matches(
                row, key=key, event_type=event_type, since=since, until=until
            ):
                continue
            results.append(row)
            if len(results) >= limit:
                break
        return results

    def flywheel_meta_set(self, key: str, value: str) -> None:
        with self._lock:
            if not hasattr(self, "_flywheel_meta"):
                self._flywheel_meta: dict[str, str] = {}
            self._flywheel_meta[key] = value

    def flywheel_meta_get(self, key: str) -> str | None:
        with self._lock:
            return getattr(self, "_flywheel_meta", {}).get(key)

    def close(self) -> None:
        if self._tmp_audit_dir is not None:
            shutil.rmtree(self._tmp_audit_dir, ignore_errors=True)
            self._tmp_audit_dir = None  # type: ignore[assignment]


def _make_test_bridge(store: Any) -> Any:
    """Build a real :class:`BrainBridge` wrapping a fake AgentBrain over *store*.

    The fake brain provides only the attributes BrainBridge touches: ``.store``,
    ``.hive`` (None for unit tests), ``.recall``, and ``.close``. This lets the
    handlers exercise the real BrainBridge code path (circuit breaker, retry,
    asyncio.to_thread) against the in-memory store from
    :class:`InMemoryPrivateBackend`.

    Used by the autouse fixture below; tests that need a custom store can call
    this helper directly and patch ``_get_brain_bridge`` themselves.
    """
    from types import SimpleNamespace

    from tapps_core.brain_bridge import BrainBridge

    fake_brain = SimpleNamespace(
        store=store,
        hive=None,
        recall=lambda query, max_results=10: [],
        close=lambda: None,
    )
    return BrainBridge(fake_brain)


@pytest.fixture(autouse=True)
def _tolerate_brain_auth_failure_in_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Force ``memory.tolerate_brain_auth_failure=true`` for every unit test.

    Production sets the default to False so that ``tapps_session_start`` returns
    a hard ``brain_auth_failed`` error when the bridge has no auth token (TAP-1082).
    That's the right default for real users — silent degradation hides
    misconfiguration. But unit tests don't run a real brain and don't set the
    auth token, so ~13 ``test_server_pipeline_tools`` /
    ``test_composite_tools`` ``TestTappsSessionStart::*`` tests would always
    fail on a bare master checkout.

    Setting the env var here keeps the production default intact while letting
    the tests exercise the soft-degraded path they were originally written
    against. Tests that specifically verify the hard-error branch can opt out
    by overriding this fixture or unsetting the env var inside the test.
    """
    monkeypatch.setenv("TAPPS_MCP_MEMORY_TOLERATE_BRAIN_AUTH_FAILURE", "true")
    yield


@pytest.fixture(autouse=True)
def _inject_test_brain_bridge(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Patch ``_get_brain_bridge`` to wrap whatever store ``_get_memory_store`` returns.

    Production code requires ``TAPPS_BRAIN_DATABASE_URL`` for the bridge.  Unit
    tests don't set that env var; instead they patch ``_get_memory_store`` to
    return an in-memory MemoryStore.  This autouse fixture mirrors that pattern
    for the bridge: each call to ``_get_brain_bridge`` builds a fresh
    :class:`BrainBridge` over the current ``_get_memory_store()`` result.

    Looks up ``_get_memory_store`` dynamically from ``server_memory_tools`` so
    that test fixtures which patch only that alias (e.g. ``mock_store``) are
    honored.  Falls back to a fresh in-memory MemoryStore when no patch is in
    place.

    EPIC-95.3 / TAP-412: handlers now delegate to BrainBridge instead of using
    MemoryStore directly, so test infrastructure must wire up both.
    """
    from tapps_mcp import server_helpers, server_memory_tools

    original_get_memory_store = server_helpers._get_memory_store

    def _resolve_store() -> Any:
        # Honour test patches on ``server_memory_tools._get_memory_store``.
        # When unpatched, the alias still points at the original
        # ``server_helpers`` function — and calling that would loop back into
        # ``_get_brain_bridge`` (also patched here), causing infinite
        # recursion. Detect that case and bail to None.
        getter = server_memory_tools._get_memory_store
        if getter is original_get_memory_store:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _bridge_from_store() -> Any:
        store = _resolve_store()
        if store is None:
            return None
        return _make_test_bridge(store)

    monkeypatch.setattr("tapps_mcp.server_memory_tools._get_brain_bridge", _bridge_from_store)
    # TAP-5841: the canonical accessor must be patched too. Unpatched, it calls
    # the real ``load_settings()`` -- which reads this repo's own
    # ``.tapps-mcp.yaml`` and its ``brain_http_url: http://localhost:8080`` --
    # and hands back a live ``HttpBrainBridge`` no matter what settings the test
    # mocked. ``tapps_session_start`` reaches it through
    # ``session_start_helpers``, so every session-start unit test opened real
    # sockets to whatever tapps-brain the developer happened to be running. With
    # 20 xdist workers on one brain those round trips stall past pytest-timeout's
    # 60s and die blocked in ``selectors.py``, which is the order-dependent hang
    # TAP-5841 describes. ``_resolve_store`` already short-circuits to ``None``
    # when ``_get_memory_store`` is unpatched, so wiring the canonical name to
    # the same factory cannot re-enter the recursion described above.
    # Tests marked ``real_brain_bridge`` are *about* this accessor and mock the
    # wire themselves, so they keep the production function.
    if request.node.get_closest_marker("real_brain_bridge") is None:
        monkeypatch.setattr("tapps_mcp.server_helpers._get_brain_bridge", _bridge_from_store)
    yield


@pytest.fixture(autouse=True)
def _inject_in_memory_private_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Inject InMemoryPrivateBackend into MemoryStore when no Postgres DSN is set.

    tapps-brain v3 (ADR-007) removed SQLite; MemoryStore raises ValueError when
    constructed without a Postgres private_backend.  This fixture patches
    MemoryStore.__init__ so unit tests that don't supply a backend or DSN get an
    in-memory dict-backed stand-in instead.

    Tests that want to verify the hard-fail behaviour set
    TAPPS_BRAIN_TEST_NO_INMEMORY_BACKEND=1 to bypass this fixture.
    """
    import os

    from tapps_brain import store as _store_mod

    if not os.environ.get("TAPPS_BRAIN_TEST_NO_INMEMORY_BACKEND"):
        monkeypatch.delenv("TAPPS_BRAIN_DATABASE_URL", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_HIVE_DSN", raising=False)
        monkeypatch.delenv("TAPPS_BRAIN_PROJECT", raising=False)

    _original_init = _store_mod.MemoryStore.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        if (
            kwargs.get("private_backend") is None
            and not os.environ.get("TAPPS_BRAIN_DATABASE_URL")
            and not os.environ.get("TAPPS_BRAIN_HIVE_DSN")
            and not os.environ.get("TAPPS_BRAIN_TEST_NO_INMEMORY_BACKEND")
        ):
            project_root = args[0] if args else kwargs.get("project_root")
            reg_key = str(project_root) if project_root is not None else "__default__"
            if reg_key not in _inmemory_backend_registry:
                _inmemory_backend_registry[reg_key] = InMemoryPrivateBackend()
            kwargs["private_backend"] = _inmemory_backend_registry[reg_key]
        _original_init(self, *args, **kwargs)

    monkeypatch.setattr(_store_mod.MemoryStore, "__init__", _patched_init)
    yield
    # close() is already total: rmtree(ignore_errors=True) cannot raise and the
    # None guard makes a second call a no-op, so the try/except that used to
    # wrap this only hid real teardown breakage (bandit B110).
    for _backend in list(_inmemory_backend_registry.values()):
        _backend.close()
    _inmemory_backend_registry.clear()


@pytest.fixture(autouse=True)
def _skip_real_memory_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip BGE ``encode()`` in MemoryStore unit tests.

    Real embedding calls flake under pytest-xdist torch/CPU contention and can
    exceed the 60s timeout when auto-consolidation chains multiple saves.
    """
    from tapps_brain.store import MemoryStore

    def _no_embed(_self: MemoryStore, _key: str, _value: str, entry: Any) -> Any:
        return entry

    monkeypatch.setattr(MemoryStore, "_embed_entry", _no_embed)


@pytest.fixture(autouse=True)
def _reset_mcp_memory_mode() -> Generator[None, None, None]:
    """Reset tapps_memory slim/off routing before and after each test.

    Importing ``tapps_mcp.server`` registers ``tapps_memory`` and sets
    ``_MCP_MEMORY_MODE = "slim"`` at collection time; without this reset,
    refused-envelope tests see slim dispatch instead.
    """
    import tapps_mcp.server_memory_tools as _smt

    _smt._MCP_MEMORY_MODE = "off"
    yield
    _smt._MCP_MEMORY_MODE = "off"


@pytest.fixture()
def no_session_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the on-disk session sentinel so tests get full session_start payloads."""
    from tapps_mcp.server_pipeline_tools import _reset_session_start_cache
    from tapps_mcp.tools import session_start_core as ssc

    monkeypatch.setattr(ssc, "read_session_sentinel", lambda *_a, **_k: None)
    _reset_session_start_cache()


def _clear_test_singleton_caches() -> None:
    """Reset module-level singletons (see module docstring for registry)."""
    from tapps_core.config.feature_flags import feature_flags
    from tapps_core.config.settings import _reset_settings_cache

    _reset_settings_cache()
    feature_flags.reset()

    from tapps_mcp.quick_check_recurring import _reset_recurring_quick_check_state
    from tapps_mcp.server_helpers import (
        _reset_brain_bridge_cache,
        _reset_hive_store_cache,
        _reset_lookup_engine_cache,
        _reset_memory_store_cache,
        _reset_scorer_cache,
        _reset_session_state,
    )
    from tapps_mcp.server_pipeline_tools import (
        _reset_background_tasks,
        _reset_session_gc_flag,
        _reset_session_start_cache,
        _reset_state_lock,
    )
    from tapps_mcp.tools.dependency_scan_cache import clear_dependency_cache
    from tapps_mcp.tools.event_loop_guard import reset_heavy_cpu_semaphore_for_tests
    from tapps_mcp.tools.tool_detection import _reset_tools_cache

    _reset_scorer_cache()
    _reset_lookup_engine_cache()
    _reset_memory_store_cache()
    _reset_brain_bridge_cache()
    _reset_hive_store_cache()
    _reset_session_state()
    _reset_tools_cache()
    _reset_session_gc_flag()
    _reset_session_start_cache()
    _reset_background_tasks()
    # TAP-5841: both of these are process-wide asyncio primitives that outlive
    # the per-test event loop. Left alone, one loop teardown while a slot or the
    # lock is held poisons every later test in the process — the serial suite
    # then dies in ``EpollSelector.select(timeout=-1)`` on whichever test the
    # shuffle put next, which is the order-dependent hang.
    _reset_state_lock()
    reset_heavy_cpu_semaphore_for_tests()
    clear_dependency_cache()
    _reset_recurring_quick_check_state()

    from tapps_mcp.tools.content_hash_cache import clear as _clear_content_cache

    _clear_content_cache()

    from tapps_mcp.project.test_linker_cache import _reset_test_edges_stats

    _reset_test_edges_stats()

    # TAP-5442 replaces server_memory_tools._params_project_id globally the
    # first time a brain bridge is built, and production never undoes it. Left
    # installed, it leaks the settings-tenant fallback into every later test in
    # the process and makes results depend on collection order.
    from tapps_mcp.memory_project_id import uninstall_memory_project_id_patch

    uninstall_memory_project_id_patch()


def _iter_failed_sub_results(
    node: Any,
    path: str = "data",
    allow: tuple[str, ...] = (),
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(path, payload)`` for every nested dict that reports failure."""
    if isinstance(node, dict):
        # A key named in ``allow`` is not read as a failure signal on this node,
        # and is not descended into — one meaning of "skip this key", applied at
        # both ends. Without the first half a payload whose failure marker sits
        # at the root of ``data`` is unreachable by ``allow`` (TAP-5659).
        looks_failed = ("error" not in allow and bool(node.get("error"))) or (
            "success" not in allow and node.get("success") is False
        )
        if looks_failed and not node.get("skipped"):
            yield path, node
        for key, value in node.items():
            if key in allow:
                continue
            yield from _iter_failed_sub_results(value, f"{path}.{key}", allow)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_failed_sub_results(value, f"{path}[{index}]", allow)


def assert_envelope_consistent(
    response: dict[str, Any],
    *,
    allow: tuple[str, ...] = (),
) -> None:
    """Fail if a response claims plain success over a nested failure (TAP-5656).

    A tool may legitimately continue past a best-effort dependency, but it must
    say so — either ``success: false`` or ``degraded: true``. Reporting an
    unqualified success while a nested sub-result carries an error is the
    "envelope lie" that shipped two defects to a consuming project: the caller
    reads the top level and believes work happened that never did.

    ``allow`` names data keys to skip, for genuinely informational payloads
    that embed failure-shaped records (a report *about* failures, say). A named
    key is skipped both as a subtree to walk and as a failure signal on the node
    that carries it, so ``allow=("error",)`` also covers a marker sitting at the
    root of ``data`` where there is no parent key to name.
    ``skipped`` sub-results are not failures — that flag means never attempted.

    The static counterpart is ``scripts/check-response-envelope.py``; the lint
    catches the shape at authoring time, this catches the behaviour at runtime.
    """
    if response.get("success") is not True or response.get("degraded") is True:
        return

    failures = list(_iter_failed_sub_results(response.get("data"), allow=allow))
    if not failures:
        return

    rendered = "\n".join(f"  {path}: {payload!r}" for path, payload in failures)
    tool = response.get("tool", "<unknown tool>")
    raise AssertionError(
        f"{tool} reported plain success while nested sub-results report failure.\n"
        f"{rendered}\n"
        "Pass degraded=True (or success=False) so the caller can see it."
    )


@pytest.fixture
def envelope_consistent() -> Callable[..., None]:
    """The :func:`assert_envelope_consistent` invariant, as a fixture."""
    return assert_envelope_consistent


@pytest.fixture
def envelope_guard(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Assert the envelope invariant on every response a test actually builds.

    The chokepoint is ``success_response`` — every tool envelope in this package
    is constructed there. The fixture records each envelope as it is built and
    checks it at teardown, *not* at construction: handlers routinely mutate the
    returned dict afterwards (setting ``degraded``, merging sub-results), and the
    recorded reference is that same dict, so teardown sees the final shape the
    caller would receive.

    Most tool modules bind the helper with ``from tapps_mcp.server_helpers import
    success_response``, which copies the reference into their own namespace at
    import time — patching ``server_helpers`` alone would miss every one of them.
    So the binding sites are discovered from ``sys.modules`` rather than listed:
    a hand-maintained list silently goes stale and the guard degrades to a no-op.
    Modules imported lazily *after* the patch is installed re-bind the spy, so
    they are covered too.

    Opt a suite in with ``pytestmark = pytest.mark.usefixtures("envelope_guard")``
    rather than making it autouse: it only means anything for tests that drive a
    real tool handler, and a blanket patch would fire inside the tests that
    exercise ``success_response`` itself.

    A suite whose tool legitimately returns failure-shaped records inside a
    success payload names those keys with ``@pytest.mark.envelope_allow(...)``;
    every use carries a justification comment at the mark.
    """
    import sys

    from tapps_mcp import server_helpers

    allow: tuple[str, ...] = ()
    for mark in request.node.iter_markers("envelope_allow"):
        allow += tuple(mark.args)

    built: list[dict[str, Any]] = []
    original = server_helpers.success_response

    def _spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        response = original(*args, **kwargs)
        built.append(response)
        return response

    targets = [
        module
        for name, module in list(sys.modules.items())
        if name.startswith(("tapps_mcp", "tapps_core", "docs_mcp"))
        and getattr(module, "success_response", None) is original
    ]

    with contextlib.ExitStack() as stack:
        for module in targets:
            stack.enter_context(patch.object(module, "success_response", _spy))
        yield

    # A module imported lazily *during* the test bound the spy itself, so the
    # ExitStack knows nothing about it. Left alone it would keep appending to
    # this fixture's dead list for the rest of the session.
    for module in list(sys.modules.values()):
        if getattr(module, "success_response", None) is _spy:
            module.success_response = original

    for response in built:
        assert_envelope_consistent(response, allow=allow)


@pytest.fixture
def no_repo_wide_scans() -> Generator[None, None, None]:
    """Keep ``tapps_checklist`` callers off the full-repo git and AST scans.

    ``tapps_checklist`` runs ``check_tdd_stages`` by default, whose
    compile-time-RED check ``ast.parse()``s every Python file under the project
    source roots. With ``project_root`` pointing at the real repository that is
    slow enough to blow the 60s per-test timeout on a CI runner — it failed
    three ``TestTappsChecklist`` tests that assert nothing about TDD stages.

    Opt-in rather than autouse on purpose: ``test_checklist.py`` imports
    ``check_tdd_stages`` inside each test, so an unconditional patch here would
    silently hollow out the tests that exercise it for real. Apply with
    ``pytestmark = pytest.mark.usefixtures("no_repo_wide_scans")``.

    Deliberately does NOT stub ``compute_gaps``: it is also repo-wide, but
    ``test_contract_finish_gate.py`` asserts on the gaps it returns, so a
    blanket stub here hollows those tests out rather than speeding them up.
    """
    tdd_stub = MagicMock()
    tdd_stub.model_dump.return_value = {"passed": True, "checks": []}
    with (
        patch(
            "tapps_mcp.tools.checklist.check_tdd_stages",
            AsyncMock(return_value=tdd_stub),
        ),
        patch(
            "tapps_mcp.tools.checklist._get_git_context",
            AsyncMock(return_value=None),
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _isolate_checklist_session(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Point ``CallTracker`` at a per-test file instead of the real repo ledger.

    ``server._record_call`` lazily calls ``CallTracker.set_persist_path`` on the
    project's ``.tapps-mcp/sessions/checklist_calls.jsonl``, and that setter
    *clears in-memory records and reloads from disk*. Two things followed:

    - Tests that ``CallTracker.record(...)`` then call ``tapps_checklist`` had
      their records wiped by the first ``_record_call``, so assertions read the
      developer's real session instead. Whichever test ran first flipped
      ``persist_configured``, which is why the failures were order-dependent
      (``test_with_calls`` and ``test_checklist_tracks_session`` passed in a
      full run and failed standalone).
    - Test runs appended into that real ledger, corrupting live telemetry.

    Autouse because any test touching a recorded tool inherits both problems.
    """
    from tapps_mcp import server as _server
    from tapps_mcp.tools.checklist import CallTracker

    prev_path = CallTracker._persist_path
    prev_session = CallTracker._active_session_id
    prev_configured = _server._checklist_state["persist_configured"]

    session_dir = tmp_path_factory.mktemp("checklist_session")
    CallTracker.set_persist_path(session_dir / "checklist_calls.jsonl")
    _server._checklist_state["persist_configured"] = True
    try:
        yield
    finally:
        _server._checklist_state["persist_configured"] = prev_configured
        if prev_path is not None:
            CallTracker.set_persist_path(prev_path)
        else:
            CallTracker._persist_path = None
            CallTracker._calls.clear()
        CallTracker._active_session_id = prev_session


@pytest.fixture(autouse=True)
def _no_install_drift() -> Generator[None, None, None]:
    """Decouple ``upgrade_pipeline`` tests from the machine's deployed CLIs.

    ``check_install_drift`` compares the in-process package version against the
    binaries under ``~/.tapps-mcp/current``, and ``upgrade_pipeline`` refuses to
    run when they disagree. That made 77 upgrade tests fail the moment the
    version was bumped, until the developer happened to run ``deploy-local`` —
    machine state deciding whether the suite passes.

    Drift detection is not what these tests are for, so it reports "clean" by
    default. Tests that *do* exercise drift (``test_install_drift.py``,
    ``test_upgrade_integration.py``) patch the same target themselves, and an
    explicit inner patch takes precedence over this one.
    """
    from tapps_core.common.models import InstallDriftDiagnostic

    clean = InstallDriftDiagnostic(
        drift_detected=False,
        entries=[],
        local_install_warning=False,
        remediation_hint="",
    )
    with patch("tapps_mcp.diagnostics.check_install_drift", return_value=clean):
        yield


_METRICS_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIVE_METRICS_DIR = _METRICS_REPO_ROOT / ".tapps-mcp" / "metrics"


def _snapshot_live_metrics_dir() -> dict[str, tuple[int, int]]:
    """Map filename -> (size, mtime_ns) for every file in the live metrics dir."""
    if not _LIVE_METRICS_DIR.is_dir():
        return {}
    return {
        entry.name: (entry.stat().st_size, entry.stat().st_mtime_ns)
        for entry in _LIVE_METRICS_DIR.iterdir()
        if entry.is_file()
    }


@pytest.fixture(autouse=True)
def _isolate_metrics_hub(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Generator[None, None, None]:
    """VAL-TAP-6639: pin every test's metrics hub to a tmp_path instance, and
    fail the test loudly if anything still reaches the live metrics dir.

    ``_record_execution`` (server.py) and the umbrella handlers in
    server_metrics_tools.py / server_analysis_tools.py all resolve the hub
    via ``tapps_mcp.server._get_metrics_hub`` (looked up by name at call
    time, even where it's re-imported locally) -- patching that one seam
    covers every caller. ``MetricsHub`` (tapps_core/metrics/collector.py)
    takes its directory only via constructor arg, with no env/config
    injection point, so patching the accessor (rather than adding a new
    injection seam to MetricsHub itself) is the smallest correct fix.

    That patch is a redirect, not a guarantee: any other path to the live
    ``.tapps-mcp/metrics/`` dir (a module that builds its own MetricsHub,
    a future accessor, a subprocess) would leak unobserved. So this fixture
    also snapshots the live directory's file set + (size, mtime_ns) before
    and after each test and ``pytest.fail``s on any difference, naming the
    test's node id and the changed files -- the isolation proves itself
    instead of relying on an external md5 check to catch drift.
    """
    from tapps_core.metrics.collector import MetricsHub

    before = _snapshot_live_metrics_dir()
    hub = MetricsHub(tmp_path / "metrics-hub")
    with patch("tapps_mcp.server._get_metrics_hub", return_value=hub):
        yield
    after = _snapshot_live_metrics_dir()
    if after != before:
        changed = sorted(set(before) | set(after))
        changed = [name for name in changed if before.get(name) != after.get(name)]
        pytest.fail(
            f"{request.node.nodeid} leaked to live metrics dir "
            f"{_LIVE_METRICS_DIR}: changed files {changed}"
        )


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset module-level singletons before and after each test."""
    _clear_test_singleton_caches()
    yield
    _clear_test_singleton_caches()

"""Shared test fixtures for TappsMCP.

Ensures test isolation by resetting module-level caches between tests.

Cache reset registry
--------------------
Every module-level singleton or cached value that persists across function
calls must be reset here.  When adding a new cache:

1. Create a ``_reset_*()`` function in the source module.
2. Import and call it in ``_reset_caches()`` below.
3. Verify isolation by running the new tests twice in a row.

Current resets (11 total):
  - settings              — ``tapps_core.config.settings._reset_settings_cache``
  - feature_flags         — ``tapps_core.config.feature_flags.feature_flags.reset``
  - scorer           — ``tapps_mcp.server_helpers._reset_scorer_cache``
  - lookup_engine    — ``tapps_mcp.server_helpers._reset_lookup_engine_cache``
  - memory_store     — ``tapps_mcp.server_helpers._reset_memory_store_cache``
  - hive_store       — ``tapps_mcp.server_helpers._reset_hive_store_cache``
  - session_state    — ``tapps_mcp.server_helpers._reset_session_state``
  - tools_detection  — ``tapps_mcp.tools.tool_detection._reset_tools_cache``
  - session_gc_flag  — ``tapps_mcp.server_pipeline_tools._reset_session_gc_flag``
  - dependency_cache — ``tapps_mcp.tools.dependency_scan_cache.clear_dependency_cache``
  - quick_check_recurring — ``tapps_mcp.quick_check_recurring._reset_recurring_quick_check_state``
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

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

    def load_all(self) -> list[Any]:
        with self._lock:
            return list(self._entries.values())

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def search(self, query: str, **kwargs: Any) -> list[Any]:
        """Word-level FTS approximation matching plainto_tsquery token behaviour."""
        import re

        def _tokens(text: str) -> set[str]:
            return set(re.findall(r"[a-z0-9]+", text.lower()))

        since: str | None = kwargs.get("since")
        until: str | None = kwargs.get("until")

        if not query.strip():
            return []
        q_words = _tokens(query)
        with self._lock:
            results = [
                e
                for e in self._entries.values()
                if q_words & _tokens(e.value) or q_words & _tokens(e.key.replace("-", " "))
            ]

        if since is not None:
            results = [e for e in results if getattr(e, "created_at", "") >= since]
        if until is not None:
            results = [e for e in results if getattr(e, "created_at", "") <= until]
        return results

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
                with open(self._audit_path, "a", encoding="utf-8") as fh:
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
        try:
            lines = self._audit_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_type = str(rec.get("event_type") or rec.get("action", ""))
            rec_key = str(rec.get("key", ""))
            ts = str(rec.get("timestamp", ""))
            details = {
                k: v
                for k, v in rec.items()
                if k not in ("action", "key", "timestamp", "event_type")
            }

            if key is not None and rec_key != key:
                continue
            if event_type is not None and ev_type != event_type:
                continue
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue

            results.append(
                {"timestamp": ts, "event_type": ev_type, "key": rec_key, "details": details}
            )
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
def _inject_test_brain_bridge(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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

    # Only patch the alias used by the handler module, not the canonical name
    # in server_helpers. Patching both creates the recursion described above.
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools._get_brain_bridge", _bridge_from_store
    )
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
    for _backend in list(_inmemory_backend_registry.values()):
        try:
            _backend.close()
        except Exception:
            pass
    _inmemory_backend_registry.clear()


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset all module-level singletons after each test.

    Caches populate normally during each test and are cleared in teardown,
    ensuring test isolation.  See module docstring for the full registry.
    """
    yield

    # -- tapps-core caches --
    from tapps_core.config.feature_flags import feature_flags
    from tapps_core.config.settings import _reset_settings_cache

    _reset_settings_cache()
    feature_flags.reset()

    # -- tapps-mcp caches --
    from tapps_mcp.quick_check_recurring import _reset_recurring_quick_check_state
    from tapps_mcp.server_helpers import (
        _reset_hive_store_cache,
        _reset_lookup_engine_cache,
        _reset_memory_store_cache,
        _reset_scorer_cache,
        _reset_session_state,
    )
    from tapps_mcp.server_pipeline_tools import _reset_session_gc_flag
    from tapps_mcp.tools.dependency_scan_cache import clear_dependency_cache
    from tapps_mcp.tools.tool_detection import _reset_tools_cache

    _reset_scorer_cache()
    _reset_lookup_engine_cache()
    _reset_memory_store_cache()
    _reset_hive_store_cache()
    _reset_session_state()
    _reset_tools_cache()
    _reset_session_gc_flag()
    clear_dependency_cache()
    _reset_recurring_quick_check_state()

    # content_hash_cache is a module-level OrderedDict; must be cleared so
    # a cached result for "x = 1\n" (or any other small file) from one test
    # cannot produce a spurious cache hit in a later test that uses the same
    # file content with a different preset or expectation.
    from tapps_mcp.tools.content_hash_cache import clear as _clear_content_cache

    _clear_content_cache()

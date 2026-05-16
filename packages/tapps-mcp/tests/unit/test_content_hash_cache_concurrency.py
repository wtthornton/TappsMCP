"""TAP-1797: content_hash_cache must be safe under concurrent thread access.

The cache is hit from `asyncio.to_thread` workers when tools like
``tapps_validate_changed`` batch many files. Without a lock, concurrent
`move_to_end` / `popitem` / `__setitem__` raised
``RuntimeError: OrderedDict mutated during iteration`` and dropped entries.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from tapps_mcp.tools import content_hash_cache as chc


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    chc.clear()


def test_concurrent_get_set_does_not_raise() -> None:
    """20 worker threads, 5000 ops each — no RuntimeError, no exceptions."""
    errors: list[BaseException] = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(5000):
                sha = f"{worker_id:02d}-{i % 200:04d}"
                chc.set(chc.KIND_QUICK_CHECK, sha, {"worker": worker_id, "i": i})
                chc.get(chc.KIND_QUICK_CHECK, sha)
        except BaseException as exc:  # pragma: no cover — recorded for assertion
            errors.append(exc)
            raise

    threads = [threading.Thread(target=worker, args=(wid,)) for wid in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent workers raised: {errors!r}"


def test_concurrent_writes_stay_bounded_at_max_entries() -> None:
    """LRU bound must hold under contention — total size <= _MAX_ENTRIES."""
    # Use a small per-test ceiling by writing more than _MAX_ENTRIES distinct
    # keys; the eviction loop in `set` must keep size at the ceiling.
    cap = chc._MAX_ENTRIES  # noqa: SLF001 — test peers at module constant
    total_writes = cap * 2

    def writer(start: int) -> None:
        for i in range(start, start + total_writes // 20):
            chc.set(chc.KIND_SCORE, f"sha-{i:08d}", {"i": i})

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(writer, w * (total_writes // 20)) for w in range(20)]
        for f in as_completed(futures):
            f.result()  # surface any exception

    assert chc.size() <= cap, f"cache exceeded cap: {chc.size()} > {cap}"


def test_stats_counters_are_consistent_after_contention() -> None:
    """Stats are atomic with the get/set body; sets should equal write count."""
    writes_per_worker = 500
    workers = 20

    def writer(worker_id: int) -> None:
        for i in range(writes_per_worker):
            chc.set(chc.KIND_SECURITY, f"w{worker_id}-{i}", {"x": i})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(writer, w) for w in range(workers)]
        for f in as_completed(futures):
            f.result()

    assert chc.stats()["sets"] == workers * writes_per_worker


def test_concurrent_iteration_via_size_is_safe() -> None:
    """size() (and any future stats reader) must not race with writers."""
    stop = threading.Event()

    def writer() -> None:
        i = 0
        while not stop.is_set():
            chc.set(chc.KIND_GATE, f"k-{i % 1000}", {"i": i})
            i += 1

    def reader() -> None:
        while not stop.is_set():
            _ = chc.size()
            _ = chc.stats()

    threads = [
        *[threading.Thread(target=writer) for _ in range(5)],
        *[threading.Thread(target=reader) for _ in range(5)],
    ]
    for t in threads:
        t.start()
    # Let them race for a short window then stop.
    threading.Event().wait(0.5)
    stop.set()
    for t in threads:
        t.join()

    # If we got here without error, the lock is sufficient.
    assert chc.size() <= chc._MAX_ENTRIES  # noqa: SLF001

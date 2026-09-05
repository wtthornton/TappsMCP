"""Tests for the SHA-256 content-hash cache (STORY-101.1)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.gates.models import GateResult, GateThresholds
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.security.security_scanner import SecurityScanResult
from tapps_mcp.server_scoring_tools import tapps_quick_check
from tapps_mcp.tools import content_hash_cache as cache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


def test_content_hash_is_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text("x = 1\n")
    h1 = cache.content_hash(p)
    h2 = cache.content_hash(p)
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_differs_across_content(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("x = 2\n")
    assert cache.content_hash(a) != cache.content_hash(b)


def test_set_and_get_roundtrip() -> None:
    cache.set(cache.KIND_SCORE, "abc", {"score": 85})
    assert cache.get(cache.KIND_SCORE, "abc") == {"score": 85}
    assert cache.stats()["hits"] == 1
    assert cache.stats()["sets"] == 1


def test_get_miss_returns_none_and_increments_miss_counter() -> None:
    assert cache.get(cache.KIND_SCORE, "nope") is None
    assert cache.stats()["misses"] == 1


def test_different_kinds_are_isolated() -> None:
    cache.set(cache.KIND_SCORE, "h", {"score": 80})
    cache.set(cache.KIND_GATE, "h", {"passed": True})
    assert cache.get(cache.KIND_SCORE, "h") == {"score": 80}
    assert cache.get(cache.KIND_GATE, "h") == {"passed": True}


def test_ttl_expires_entry() -> None:
    cache.set(cache.KIND_SCORE, "h", {"score": 80})
    # Bump monotonic clock forward past ttl via patch.
    real = time.monotonic()
    with patch("tapps_mcp.tools.content_hash_cache.time.monotonic", return_value=real + 10_000):
        assert cache.get(cache.KIND_SCORE, "h", ttl=1.0) is None
    assert cache.size() == 0


def test_eviction_when_over_capacity() -> None:
    with patch("tapps_mcp.tools.content_hash_cache._MAX_ENTRIES", 3):
        cache.set(cache.KIND_SCORE, "a", {"v": 1})
        cache.set(cache.KIND_SCORE, "b", {"v": 2})
        cache.set(cache.KIND_SCORE, "c", {"v": 3})
        cache.set(cache.KIND_SCORE, "d", {"v": 4})  # triggers eviction of "a"
    assert cache.get(cache.KIND_SCORE, "a") is None
    assert cache.get(cache.KIND_SCORE, "d") == {"v": 4}
    assert cache.stats()["evictions"] >= 1


def test_clear_resets_stats_and_entries() -> None:
    cache.set(cache.KIND_SCORE, "h", {"v": 1})
    cache.get(cache.KIND_SCORE, "h")
    cache.clear()
    assert cache.size() == 0
    assert cache.stats() == {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}


def test_content_hash_ignores_path(tmp_path: Path) -> None:
    """The raw content hash is path-insensitive — it hashes bytes only."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("same\n")
    b.write_text("same\n")
    assert cache.content_hash(a) == cache.content_hash(b)


def test_result_key_separates_identical_content_at_different_paths(tmp_path: Path) -> None:
    """TAP-5401 regression: byte-identical files must NOT share a cache entry.

    ``devex``, ``structure`` and ``test_coverage`` are pure functions of
    directory context, so the same bytes legitimately score differently at
    different depths. A content-only key served the first file's score — and
    its ``file_path`` — for the second.
    """
    shallow = tmp_path / "mod.py"
    deep_dir = tmp_path / "domains" / "billing" / "service" / "src"
    deep_dir.mkdir(parents=True)
    deep = deep_dir / "mod.py"
    shallow.write_text("x = 1\n")
    deep.write_text("x = 1\n")

    assert cache.content_hash(shallow) == cache.content_hash(deep)

    k_shallow = cache.result_key(shallow, preset="standard")
    k_deep = cache.result_key(deep, preset="standard")
    assert k_shallow != k_deep

    cache.set(cache.KIND_QUICK_CHECK, k_shallow, {"overall_score": 82.97, "devex": 10})
    assert cache.get(cache.KIND_QUICK_CHECK, k_deep) is None


def test_result_key_separates_presets(tmp_path: Path) -> None:
    """A `standard` verdict must not be served to a `strict` call."""
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    assert cache.result_key(f, preset="standard") != cache.result_key(f, preset="strict")


def test_result_key_stable_for_same_file_and_preset(tmp_path: Path) -> None:
    """Unchanged file + same preset still hits — the cache must remain useful."""
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    key = cache.result_key(f, preset="standard")
    cache.set(cache.KIND_QUICK_CHECK, key, {"overall_score": 91.0})
    assert cache.get(cache.KIND_QUICK_CHECK, cache.result_key(f, preset="standard")) == {
        "overall_score": 91.0
    }


def _make_project(tmp_path: Path) -> tuple[Path, Path]:
    """A tiny project: ``pkg/auth.py`` with an empty ``tests/`` dir. Returns
    ``(source_file, tests_dir)``."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    source = pkg / "auth.py"
    source.write_text("x = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    return source, tests_dir


def test_result_key_changes_when_sibling_test_file_is_added(tmp_path: Path) -> None:
    """TAP-6608: adding a name-matched test file must change the effective
    cache key, forcing a rescore without waiting for TTL expiry -- the
    test_coverage category depends on this state and cannot see it from
    content + path alone."""
    source, tests_dir = _make_project(tmp_path)

    key_before = cache.result_key(source, preset="standard")
    cache.set(cache.KIND_QUICK_CHECK, key_before, {"overall_score": 55.0})
    assert cache.get(cache.KIND_QUICK_CHECK, key_before) is not None

    (tests_dir / "test_auth.py").write_text("def test_x(): pass\n", encoding="utf-8")
    key_after = cache.result_key(source, preset="standard")

    assert key_after != key_before
    assert cache.get(cache.KIND_QUICK_CHECK, key_after) is None


def test_result_key_changes_when_sibling_test_file_is_removed(tmp_path: Path) -> None:
    """Negative-direction control: removing the sibling must also bust the key,
    proving the signal tracks live state rather than a one-way ratchet."""
    source, tests_dir = _make_project(tmp_path)
    test_file = tests_dir / "test_auth.py"
    test_file.write_text("def test_x(): pass\n", encoding="utf-8")

    key_with_sibling = cache.result_key(source, preset="standard")
    test_file.unlink()
    key_without_sibling = cache.result_key(source, preset="standard")

    assert key_with_sibling != key_without_sibling


async def test_quick_check_degraded_reflects_ruff_and_survives_cache_hit(
    tmp_path: Path,
) -> None:
    """TAP-6608: degraded must reflect ruff (not only bandit) and survive a cache hit --
    old code reported ``not sec_result.bandit_available`` alone and the cache-hit path
    never passed ``degraded=`` at all, so a replay of a degraded run read as clean."""
    f = tmp_path / "ruff_down.py"
    f.write_text("x = 1\n", encoding="utf-8")
    score = ScoreResult(
        file_path=str(f),
        overall_score=60.0,
        categories={"linting": CategoryScore(name="linting", score=8.0, weight=1.0)},
        degraded=True,
        missing_tools=["ruff"],
    )
    gate = GateResult(passed=True, failures=[], thresholds=GateThresholds())
    sec = SecurityScanResult(passed=True, total_issues=0, bandit_available=True)
    scorer_mock = MagicMock(language="python", score_file_quick_enriched=lambda *a, **kw: score)

    _record_call = patch("tapps_mcp.server._record_call", side_effect=lambda *a, **kw: None)
    _record_exec = patch("tapps_mcp.server._record_execution", side_effect=lambda *a, **kw: None)
    _with_nudges = patch(
        "tapps_mcp.server._with_nudges", side_effect=lambda _t, resp, _c: resp
    )
    with (
        _record_call,
        _record_exec,
        _with_nudges,
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized", new_callable=AsyncMock
        ),
        patch("tapps_mcp.server._validate_file_path", return_value=f),
        patch("tapps_mcp.server_scoring_tools._get_scorer_for_file", return_value=scorer_mock),
        patch("tapps_mcp.server_scoring_tools.load_settings") as mock_settings,
        patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
        patch("tapps_mcp.security.security_scanner.run_security_scan", return_value=sec),
    ):
        mock_settings.return_value = MagicMock(project_root=tmp_path, tool_timeout=30)
        first = await tapps_quick_check(str(f))
        second = await tapps_quick_check(str(f))

    assert first["degraded"] is True and first["data"].get("cache_hit") is not True
    assert second["data"].get("cache_hit") is True and second["degraded"] is True


def test_cache_hit_key_used_by_quick_check_wiring(tmp_path: Path) -> None:
    """Prove the KIND_QUICK_CHECK kind is the one server_scoring_tools uses.

    Integration through tapps_quick_check requires a real project_root for
    path validation; that is covered in test_server_scoring_tools. Here we
    just pin the kind constant so the wiring cannot silently drift.
    """
    assert cache.KIND_QUICK_CHECK == "quick_check"
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    h = cache.result_key(f, preset="standard")
    cache.set(cache.KIND_QUICK_CHECK, h, {"score": 90})
    assert cache.get(cache.KIND_QUICK_CHECK, h) == {"score": 90}

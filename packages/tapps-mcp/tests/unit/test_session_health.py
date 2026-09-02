"""TAP-6900 / TAP-6901: session-start freshness and build-skew probes."""

from __future__ import annotations

import math
import time

import pytest

from tapps_mcp.tools.session_health import (
    _MARKER_EPOCH_MAX_S,
    DEFAULT_STALE_MEMO_S,
    attach_session_health,
    collect_build_skew,
    collect_session_start_health,
    prepend_session_health_warnings,
    read_marker_epoch,
    session_health_warnings,
    stale_memo_threshold_s,
)


def _write_marker(root, epoch: float) -> None:
    sidecar = root / ".tapps-mcp"
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / ".session-start-marker").write_text(str(int(epoch)), encoding="utf-8")


# --------------------------------------------------------------------------
# marker reading
# --------------------------------------------------------------------------


def test_read_marker_epoch_prefers_content_over_mtime(tmp_path):
    """Content is authoritative: a touched file must not read as a fresh bootstrap."""
    _write_marker(tmp_path, 1_000_000)
    marker = tmp_path / ".tapps-mcp" / ".session-start-marker"
    # mtime is "now", content says 1970-01-12. Content wins.
    marker.touch()
    assert read_marker_epoch(tmp_path) == pytest.approx(1_000_000)


def test_read_marker_epoch_absent_returns_none(tmp_path):
    assert read_marker_epoch(tmp_path) is None


def test_read_marker_epoch_falls_back_to_mtime_on_garbage(tmp_path):
    sidecar = tmp_path / ".tapps-mcp"
    sidecar.mkdir()
    marker = sidecar / ".session-start-marker"
    marker.write_text("not-an-epoch", encoding="utf-8")
    got = read_marker_epoch(tmp_path)
    assert got is not None
    assert got == pytest.approx(marker.stat().st_mtime)


_LEGAL_VERDICTS = {"never_bootstrapped", "fresh", "memoized", "stale_memo", "stale_marker"}


@pytest.mark.parametrize(
    "marker_content",
    ["nan", "inf", "-inf", "1e400", "99999999999999999999"],
)
def test_hostile_marker_values_are_rejected_not_raised(tmp_path, marker_content):
    """VAL-06: non-finite and out-of-range marker content must not reach
    datetime.fromtimestamp or otherwise take the probe down."""
    _write_marker(tmp_path, 0)  # placeholder so the sidecar dir exists
    marker = tmp_path / ".tapps-mcp" / ".session-start-marker"
    marker.write_text(marker_content, encoding="utf-8")

    got = read_marker_epoch(tmp_path)
    assert got is None or (math.isfinite(got) and 0.0 <= got <= _MARKER_EPOCH_MAX_S)

    block = collect_session_start_health(tmp_path, memo_present=False)
    assert block["verdict"] in _LEGAL_VERDICTS


def test_hostile_marker_test_accepts_a_known_good_value(tmp_path):
    """Validates the instrument above: a guard that rejects everything would
    also pass the hostile-value cases and be a false green."""
    now = time.time()
    _write_marker(tmp_path, now - 5)

    got = read_marker_epoch(tmp_path)
    assert got is not None
    assert got == pytest.approx(now - 5, abs=1)

    block = collect_session_start_health(tmp_path, memo_present=False, now=now)
    assert block["verdict"] == "fresh"


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------


def test_no_marker_reports_never_bootstrapped(tmp_path):
    block = collect_session_start_health(tmp_path, memo_present=False)
    assert block["verdict"] == "never_bootstrapped"
    assert block["bootstrap_within_this_process"] is False
    assert block["marker_age_s"] is None
    assert "force=True" in block["warning"]


def test_fresh_bootstrap_without_memo_is_fresh(tmp_path):
    now = time.time()
    _write_marker(tmp_path, now - 5)
    block = collect_session_start_health(tmp_path, memo_present=False, now=now)
    assert block["verdict"] == "fresh"
    assert "warning" not in block
    assert block["marker_age_s"] == 5


def test_recent_memo_is_reported_but_not_warned(tmp_path):
    now = time.time()
    _write_marker(tmp_path, now - 10)
    block = collect_session_start_health(tmp_path, memo_present=True, now=now)
    assert block["verdict"] == "memoized"
    assert block["memo_hit_pending"] is True
    assert "warning" not in block


def test_stale_memo_warns_and_names_the_age(tmp_path):
    """The defect this ships for: a memo standing in for a long-dead session."""
    now = time.time()
    age = DEFAULT_STALE_MEMO_S + 1_000
    _write_marker(tmp_path, now - age)
    block = collect_session_start_health(tmp_path, memo_present=True, now=now)
    assert block["verdict"] == "stale_memo"
    assert block["marker_age_s"] == age
    assert str(age) in block["warning"]
    assert "checklist_session_id" in block["warning"]


def test_old_marker_without_memo_is_not_a_stale_memo(tmp_path):
    """VAL-03: age alone is not `stale_memo` — it takes a pending memo hit.

    But it is also not silently `fresh`: an ancient marker with no memo must
    surface as `stale_marker`, and the verdict must never contradict its own
    reported age.
    """
    now = time.time()
    _write_marker(tmp_path, now - (DEFAULT_STALE_MEMO_S + 1_000))
    block = collect_session_start_health(tmp_path, memo_present=False, now=now)
    assert block["verdict"] == "stale_marker"
    assert block["verdict"] != "stale_memo"
    assert block["marker_age_s"] > block["stale_after_s"]
    assert str(block["marker_age_s"]) in block["warning"]


def test_recent_marker_without_memo_is_still_fresh(tmp_path):
    """VAL-04 (negative control): a fix that always returns `stale_marker`
    would also pass VAL-03, so a recent marker must still report `fresh`."""
    now = time.time()
    _write_marker(tmp_path, now - 5)
    block = collect_session_start_health(tmp_path, memo_present=False, now=now)
    assert block["verdict"] == "fresh"
    assert "warning" not in block
    assert block["marker_age_s"] <= block["stale_after_s"]


@pytest.mark.parametrize(
    "age_s",
    [
        0,
        1,
        DEFAULT_STALE_MEMO_S - 1,
        DEFAULT_STALE_MEMO_S,
        DEFAULT_STALE_MEMO_S + 1,
        DEFAULT_STALE_MEMO_S * 10,
    ],
)
def test_fresh_verdict_never_contradicts_marker_age(tmp_path, age_s):
    """Invariant: whatever the age, `verdict == "fresh"` implies the marker is
    within the threshold. The bug this defends against is exactly a `fresh`
    verdict sitting beside a marker_age_s that exceeds stale_after_s."""
    now = time.time()
    _write_marker(tmp_path, now - age_s)
    block = collect_session_start_health(tmp_path, memo_present=False, now=now)
    if block["verdict"] == "fresh":
        assert block["marker_age_s"] <= block["stale_after_s"]


def test_marker_older_than_process_is_not_within_this_process(tmp_path):
    now = time.time()
    _write_marker(tmp_path, now - 86_400)
    block = collect_session_start_health(tmp_path, memo_present=True, now=now)
    # This process cannot have been up for a day in a test run.
    assert block["bootstrap_within_this_process"] is False


# --------------------------------------------------------------------------
# threshold override
# --------------------------------------------------------------------------


def test_threshold_default_and_override(monkeypatch):
    monkeypatch.delenv("TAPPS_MCP_SESSION_STALE_S", raising=False)
    assert stale_memo_threshold_s() == DEFAULT_STALE_MEMO_S
    monkeypatch.setenv("TAPPS_MCP_SESSION_STALE_S", "30")
    assert stale_memo_threshold_s() == 30


@pytest.mark.parametrize("bad", ["", "nope", "0", "-5"])
def test_threshold_rejects_unusable_values(monkeypatch, bad):
    monkeypatch.setenv("TAPPS_MCP_SESSION_STALE_S", bad)
    assert stale_memo_threshold_s() == DEFAULT_STALE_MEMO_S


def test_threshold_override_changes_the_verdict(tmp_path, monkeypatch):
    now = time.time()
    _write_marker(tmp_path, now - 60)
    monkeypatch.setenv("TAPPS_MCP_SESSION_STALE_S", "30")
    block = collect_session_start_health(tmp_path, memo_present=True, now=now)
    assert block["verdict"] == "stale_memo"
    assert block["stale_after_s"] == 30


# --------------------------------------------------------------------------
# build skew
# --------------------------------------------------------------------------


def test_build_skew_matched_is_not_skew():
    """Negative control: the normal case must stay quiet."""
    block = collect_build_skew()
    assert block["running_version"] == block["installed_version"]
    assert block["skew"] is False
    assert "warning" not in block


def test_build_skew_detected_names_both_versions(monkeypatch):
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "9.9.9")
    block = collect_build_skew()
    assert block["skew"] is True
    assert block["installed_version"] == "9.9.9"
    assert "9.9.9" in block["warning"]
    assert block["running_version"] in block["warning"]
    assert "Restart" in block["warning"]


def test_build_skew_unreadable_metadata_is_reported_not_raised(monkeypatch):
    import importlib.metadata

    def _boom(_name):
        raise importlib.metadata.PackageNotFoundError("tapps-mcp")

    monkeypatch.setattr(importlib.metadata, "version", _boom)
    block = collect_build_skew()
    assert block["installed_version"] is None
    assert block["skew"] is False
    assert "note" in block


# --------------------------------------------------------------------------
# attach_session_health — the wiring tapps_doctor actually calls
# --------------------------------------------------------------------------


def test_attach_populates_both_blocks(tmp_path):
    result: dict = {}
    attach_session_health(result, tmp_path, {})
    assert set(result) == {"session_start", "build_skew"}
    assert result["session_start"]["verdict"] == "never_bootstrapped"


def test_attach_matches_memo_key_for_this_root_only(tmp_path):
    """Per-root isolation: another root's memo must not read as this root's."""
    _write_marker(tmp_path, time.time())
    other: dict = {}
    attach_session_health(other, tmp_path, {("sid", True, "/somewhere/else"): {}})
    assert other["session_start"]["memo_hit_pending"] is False

    mine: dict = {}
    attach_session_health(mine, tmp_path, {("sid", True, str(tmp_path.resolve())): {}})
    assert mine["session_start"]["memo_hit_pending"] is True


def test_attach_tolerates_a_malformed_memo_key(tmp_path):
    """A cache holding an unexpected key shape must not take the doctor down."""
    result: dict = {}
    attach_session_health(result, tmp_path, {"not-a-tuple": {}, ("a", "b"): {}})
    assert "error" not in result["session_start"]
    assert result["session_start"]["memo_hit_pending"] is False


def test_attach_records_probe_failure_rather_than_omitting_the_block(tmp_path):
    """An absent block would read as healthy; an error field cannot."""

    class Hostile:
        def __iter__(self):
            raise RuntimeError("cache exploded")

    result: dict = {}
    attach_session_health(result, tmp_path, Hostile())
    assert "cache exploded" in result["session_start"]["error"]
    assert "build_skew" in result


def test_warnings_put_build_skew_before_session_start(monkeypatch):
    """Skew invalidates every other reading, so it must lead."""
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", lambda _n: "9.9.9")
    result = {
        "build_skew": collect_build_skew(),
        "session_start": {"warning": "session warning"},
    }
    warnings = session_health_warnings(result)
    assert len(warnings) == 2
    assert "9.9.9" in warnings[0]
    assert warnings[1] == "session warning"


def test_warnings_empty_when_healthy(tmp_path):
    result: dict = {}
    _write_marker(tmp_path, time.time())
    attach_session_health(result, tmp_path, {})
    assert session_health_warnings(result) == []


def test_prepend_pushes_skew_to_the_front(monkeypatch):
    """Each prepend goes to the front, so skew must be prepended last."""
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", lambda _n: "9.9.9")
    result = {
        "build_skew": collect_build_skew(),
        "session_start": {"warning": "session warning"},
    }
    resp: dict = {"data": {"next_steps": ["existing"]}}

    def prepend(target, text):
        target["data"]["next_steps"].insert(0, text)

    prepend_session_health_warnings(resp, result, prepend)
    steps = resp["data"]["next_steps"]
    assert "9.9.9" in steps[0]
    assert steps[1] == "session warning"
    assert steps[2] == "existing"


def test_prepend_is_a_noop_when_healthy(tmp_path):
    result: dict = {}
    _write_marker(tmp_path, time.time())
    attach_session_health(result, tmp_path, {})
    resp: dict = {"data": {"next_steps": ["existing"]}}
    prepend_session_health_warnings(resp, result, lambda t, x: t["data"]["next_steps"].insert(0, x))
    assert resp["data"]["next_steps"] == ["existing"]

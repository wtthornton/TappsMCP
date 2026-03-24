"""M4.2: recurring tapps_quick_check gate failures -> procedural memory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tapps_core.config.settings import MemorySettings, TappsMCPSettings
from tapps_mcp.gates.models import GateFailure
from tapps_mcp.quick_check_recurring import (
    _reset_recurring_quick_check_state,
    record_quick_check_recurring,
)


def _fail_overall(msg: str = "Overall 10.0 < 70.0") -> list[GateFailure]:
    return [
        GateFailure(
            category="overall",
            actual=10.0,
            threshold=70.0,
            message=msg,
            weight=1.0,
        )
    ]


def test_feature_off_returns_empty() -> None:
    _reset_recurring_quick_check_state()
    tmp = Path("/tmp/proj")
    f = tmp / "a.py"
    settings = TappsMCPSettings(
        project_root=tmp,
        memory=MemorySettings(track_recurring_quick_check=False),
    )
    out = record_quick_check_recurring(settings, f, False, _fail_overall())
    assert out == {}


@patch("tapps_mcp.server_helpers._get_memory_store")
def test_three_failures_triggers_save(mock_get_store: MagicMock, tmp_path: Path) -> None:
    _reset_recurring_quick_check_state()
    store = MagicMock()
    store.get.return_value = None
    store.save.return_value = object()
    mock_get_store.return_value = store

    f = tmp_path / "x.py"
    f.write_text("x = 1\n", encoding="utf-8")
    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            track_recurring_quick_check=True,
            recurring_quick_check_threshold=3,
        ),
    )
    failures = _fail_overall()

    assert record_quick_check_recurring(settings, f, False, failures) == {}
    assert record_quick_check_recurring(settings, f, False, failures) == {}
    out = record_quick_check_recurring(settings, f, False, failures)

    assert "recurring_quality_memory_events" in out
    ev = out["recurring_quality_memory_events"]
    assert len(ev) == 1
    assert ev[0]["action"] == "saved"
    store.save.assert_called_once()
    kwargs = store.save.call_args.kwargs
    assert kwargs["tier"] == "procedural"
    assert kwargs["source"] == "agent"
    assert "auto-captured" in kwargs["tags"]


@patch("tapps_mcp.server_helpers._get_memory_store")
def test_fourth_cycle_reinforces(mock_get_store: MagicMock, tmp_path: Path) -> None:
    _reset_recurring_quick_check_state()
    store = MagicMock()
    store.get.return_value = None
    store.save.return_value = object()
    mock_get_store.return_value = store

    f = tmp_path / "y.py"
    f.write_text("y = 2\n", encoding="utf-8")
    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            track_recurring_quick_check=True,
            recurring_quick_check_threshold=3,
        ),
    )
    failures = _fail_overall()

    for _ in range(3):
        record_quick_check_recurring(settings, f, False, failures)
    store.save.reset_mock()
    store.get.return_value = MagicMock()

    for _ in range(2):
        record_quick_check_recurring(settings, f, False, failures)
    out = record_quick_check_recurring(settings, f, False, failures)

    assert out["recurring_quality_memory_events"][0]["action"] == "reinforced"
    store.reinforce.assert_called_once()
    store.save.assert_not_called()


def test_gate_pass_clears_streak(tmp_path: Path) -> None:
    _reset_recurring_quick_check_state()
    f = tmp_path / "z.py"
    f.write_text("z = 3\n", encoding="utf-8")
    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(
            track_recurring_quick_check=True,
            recurring_quick_check_threshold=3,
        ),
    )
    failures = _fail_overall()
    record_quick_check_recurring(settings, f, False, failures)
    record_quick_check_recurring(settings, f, False, failures)
    record_quick_check_recurring(settings, f, True, [])
    with patch("tapps_mcp.server_helpers._get_memory_store") as mock_gs:
        store = MagicMock()
        store.get.return_value = None
        store.save.return_value = object()
        mock_gs.return_value = store
        record_quick_check_recurring(settings, f, False, failures)
        record_quick_check_recurring(settings, f, False, failures)
        out = record_quick_check_recurring(settings, f, False, failures)
        assert out["recurring_quality_memory_events"][0]["action"] == "saved"
        store.save.assert_called_once()

"""CLI/MCP parity for the doctor's session_start and build_skew blocks (F3).

The defect: both blocks were attached by the ``tapps_doctor`` MCP caller, so
``tapps-mcp doctor`` — the command a human actually runs — never emitted them.
``run_doctor`` does not call ``run_doctor_structured``; they are siblings over
``_collect_checks``, which is why the CLI had no seam to inherit them through.

These tests are the net that would have caught it: they assert both surfaces
carry the same block names, that the CLI prints them literally, and that the
process-relative fields never claim server identity on the CLI.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.doctor_runner import (
    collect_session_health_blocks,
    run_doctor,
    run_doctor_structured,
)
from tapps_mcp.tools.session_health import (
    PROBE_ROLE_CLI,
    PROBE_ROLE_SERVER,
    SESSION_HEALTH_BLOCK_KEYS,
)


def _write_marker(root: Path, epoch: float) -> None:
    sidecar = root / ".tapps-mcp"
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / ".session-start-marker").write_text(str(int(epoch)), encoding="utf-8")


def _cli_output(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """Run the CLI report against *root* and return what a human would see."""
    with (
        patch("tapps_mcp.distribution.doctor.Path.home", return_value=root),
        patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
    ):
        run_doctor(project_root=str(root), quick=True)
    return capsys.readouterr().out


# ---------------------------------------------------------------------------
# VAL-05: the CLI surface emits both blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("block_key", SESSION_HEALTH_BLOCK_KEYS)
def test_cli_doctor_emits_every_session_health_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], block_key: str
) -> None:
    """VAL-05: `tapps-mcp doctor` prints the literal block keys, so the CLI and
    the MCP payload can be grepped for the same names."""
    _write_marker(tmp_path, time.time())
    assert block_key in _cli_output(tmp_path, capsys)


def test_cli_doctor_renders_the_verdict_and_the_skew(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Printing the key alone would satisfy the grep without carrying the
    reading, so assert a field from each block reaches the human output."""
    _write_marker(tmp_path, time.time())
    out = _cli_output(tmp_path, capsys)
    assert "verdict=fresh" in out
    assert "running_version=" in out


def test_cli_doctor_prints_the_session_start_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The block's whole point is the warning; a rendering that drops it would
    still pass the key-presence checks above."""
    out = _cli_output(tmp_path, capsys)  # no marker written -> never_bootstrapped
    assert "verdict=never_bootstrapped" in out
    assert "tapps_session_start(force=True)" in out


@pytest.mark.parametrize("block_key", SESSION_HEALTH_BLOCK_KEYS)
def test_structured_doctor_emits_every_session_health_block(tmp_path: Path, block_key: str) -> None:
    result = run_doctor_structured(project_root=str(tmp_path), quick=True)
    assert block_key in result


# ---------------------------------------------------------------------------
# parity: the two surfaces cannot drift apart again
# ---------------------------------------------------------------------------


def test_both_surfaces_report_the_same_block_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The test that would have caught F3: every block in the MCP payload must
    appear in the CLI report, and vice versa."""
    _write_marker(tmp_path, time.time())
    structured = run_doctor_structured(
        project_root=str(tmp_path),
        quick=True,
        memo_cache={},
        probe_role=PROBE_ROLE_SERVER,
    )
    mcp_blocks = {k for k in SESSION_HEALTH_BLOCK_KEYS if k in structured}
    out = _cli_output(tmp_path, capsys)
    cli_blocks = {k for k in SESSION_HEALTH_BLOCK_KEYS if k in out}

    assert mcp_blocks == cli_blocks == set(SESSION_HEALTH_BLOCK_KEYS)


def test_both_surfaces_report_the_same_fields_within_each_block(tmp_path: Path) -> None:
    """Block-name parity is not enough: the fields inside must match too, or a
    reader of one surface learns something the other never says."""
    _write_marker(tmp_path, time.time())
    cli = collect_session_health_blocks(tmp_path, memo_cache=None, probe_role=PROBE_ROLE_CLI)
    server = collect_session_health_blocks(tmp_path, memo_cache={}, probe_role=PROBE_ROLE_SERVER)
    for key in SESSION_HEALTH_BLOCK_KEYS:
        assert set(cli[key]) == set(server[key]), key


def test_cli_render_covers_every_declared_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The renderer iterates SESSION_HEALTH_BLOCK_KEYS rather than a hand-kept
    list, so a block added to the shared helper reaches the CLI unedited."""
    _write_marker(tmp_path, time.time())
    out = _cli_output(tmp_path, capsys)
    blocks = collect_session_health_blocks(tmp_path, memo_cache=None, probe_role=PROBE_ROLE_CLI)
    assert set(blocks) == set(SESSION_HEALTH_BLOCK_KEYS)
    for key in blocks:
        assert key in out


# ---------------------------------------------------------------------------
# the naming trap: no server claim on the CLI surface
# ---------------------------------------------------------------------------


def test_cli_never_prints_a_server_uptime(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`server_process_uptime_s` on the CLI would report the age of a process
    that started milliseconds ago under a name asserting it is the server."""
    _write_marker(tmp_path, time.time())
    out = _cli_output(tmp_path, capsys)
    assert "server_process_uptime_s" not in out
    assert "server_process_started" not in out
    assert f"probe_process_role={PROBE_ROLE_CLI}" in out
    assert f"probe_process_role={PROBE_ROLE_SERVER}" not in out


def test_cli_does_not_claim_to_know_the_servers_memo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI runs in its own process and cannot inspect the server's memo, so
    it reports the field as unknown rather than as a negative finding."""
    _write_marker(tmp_path, time.time())
    out = _cli_output(tmp_path, capsys)
    assert "memo_hit_pending=None" in out
    assert "memo_hit_pending=False" not in out


def test_structured_default_role_is_the_cli_one(tmp_path: Path) -> None:
    """Only the long-lived server may call itself one, and it says so
    explicitly; every other caller of the structured runner under-claims."""
    result = run_doctor_structured(project_root=str(tmp_path), quick=True)
    assert result["session_start"]["probe_process_role"] == PROBE_ROLE_CLI
    assert result["session_start"]["memo_hit_pending"] is None


def test_structured_server_role_is_carried_through(tmp_path: Path) -> None:
    """Negative control: the server's explicit claim must still reach the
    payload, or the rename would have simply deleted the distinction."""
    _write_marker(tmp_path, time.time())
    root_key = str(tmp_path.resolve())
    result = run_doctor_structured(
        project_root=str(tmp_path),
        quick=True,
        memo_cache={("sid", True, root_key): {}},
        probe_role=PROBE_ROLE_SERVER,
    )
    assert result["session_start"]["probe_process_role"] == PROBE_ROLE_SERVER
    assert result["session_start"]["memo_hit_pending"] is True


# ---------------------------------------------------------------------------
# the MCP tool keeps its warning prepend
# ---------------------------------------------------------------------------


def test_mcp_doctor_still_prepends_the_session_health_warning(tmp_path: Path) -> None:
    """Moving the attach into run_doctor_structured must not cost the MCP tool
    its warning prepend: an unbootstrapped root has to lead the next steps."""
    from tapps_mcp.server_pipeline_tools import tapps_doctor

    with patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings:
        mock_settings.return_value.project_root = tmp_path
        resp = tapps_doctor(project_root=str(tmp_path), quick=True)

    block = resp["data"]["session_start"]
    assert block["verdict"] == "never_bootstrapped"
    assert block["probe_process_role"] == PROBE_ROLE_SERVER
    assert resp["data"]["next_steps"][0] == block["warning"]


def test_mcp_doctor_leads_with_build_skew_when_both_warn(tmp_path: Path) -> None:
    """Ordering is load-bearing: a skew invalidates every other reading, so it
    must still outrank the session-start warning after the rewiring."""
    import importlib.metadata

    from tapps_mcp.server_pipeline_tools import tapps_doctor

    with (
        patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
        patch.object(importlib.metadata, "version", lambda _n: "9.9.9"),
    ):
        mock_settings.return_value.project_root = tmp_path
        resp = tapps_doctor(project_root=str(tmp_path), quick=True)

    steps = resp["data"]["next_steps"]
    assert "9.9.9" in steps[0]
    assert steps[1] == resp["data"]["session_start"]["warning"]

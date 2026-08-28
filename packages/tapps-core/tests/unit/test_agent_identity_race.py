"""``_write_uuid`` atomic create-if-absent primitive (TAP-5893 / TAP-6081).

``get_stable_agent_id`` no longer mints or persists a uuid at all (Ruling 9,
TAP-6701 — see ``test_agent_identity.py``), so the multi-process race probes
this file previously ran against it (concurrent first-callers converging on
one persisted id, read-only-FS fallback) no longer apply: there is nothing
left to race over. ``_write_uuid`` itself survives as a generic atomic
create-if-absent primitive — it is independently exercised by
``test_shared_state_atomic_writers.py``'s TAP-6081 torn-write suite — so its
own create-only-once contract stays pinned here.
"""

from __future__ import annotations

from pathlib import Path

from tapps_core.agent_identity import _write_uuid


def test_write_uuid_reports_loss_instead_of_clobbering(tmp_path: Path) -> None:
    """``_write_uuid`` creates only when absent and never overwrites a winner."""
    path = tmp_path / ".tapps-mcp" / "agent.id"

    assert _write_uuid(path, "a" * 32) is True
    assert _write_uuid(path, "b" * 32) is False
    assert path.read_text(encoding="utf-8").strip() == "a" * 32

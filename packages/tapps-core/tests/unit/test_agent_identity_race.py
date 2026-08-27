"""First-run agent-id race regression (TAP-5893).

``get_stable_agent_id`` used to read ``.tapps-mcp/agent.id`` and, on a miss,
mint-and-write unconditionally. N concurrent first-callers against one fresh
root therefore each persisted their own UUID: the last writer won on disk while
every loser kept an id that no longer matched the file. These tests pin the
atomic create-if-absent behaviour and the read-only-FS fallback that it must
not regress.

The multi-process probe uses a ``multiprocessing.Barrier`` so all workers are
released into the read-then-create window simultaneously; a thread-only probe
would not exercise the cross-process ``O_EXCL`` guarantee.
"""

from __future__ import annotations

import errno
import multiprocessing as mp
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tapps_core.agent_identity import _write_uuid, get_stable_agent_id
from tapps_core.config.settings import TappsMCPSettings

if TYPE_CHECKING:
    from collections.abc import Callable

_WORKERS = 6
_FRESH_ROOTS = 12
_ID_REL = Path(".tapps-mcp") / "agent.id"


def _make_settings(project_root: Path) -> TappsMCPSettings:
    settings = TappsMCPSettings(project_root=project_root)
    settings.memory.project_id = "tapps-mcp"
    return settings


def _worker(root_str: str, barrier: object, out: object) -> None:
    """Resolve the agent id for *root_str* the instant every sibling is ready."""
    import os as _os

    _os.environ.pop("CLAUDE_AGENT_ID", None)
    barrier.wait()  # type: ignore[attr-defined]
    out.put(get_stable_agent_id(_make_settings(Path(root_str))))  # type: ignore[attr-defined]


def _run_barrier_probe(root: Path, workers: int = _WORKERS) -> list[str]:
    """Return the agent ids produced by *workers* simultaneous first-callers."""
    ctx = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    barrier = ctx.Barrier(workers)
    queue: mp.Queue[str] = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(str(root), barrier, queue)) for _ in range(workers)]
    for proc in procs:
        proc.start()
    ids = [queue.get(timeout=30) for _ in range(workers)]
    for proc in procs:
        proc.join(timeout=30)
        assert proc.exitcode == 0, f"worker exited {proc.exitcode}"
    return ids


@pytest.mark.parametrize("run", range(_FRESH_ROOTS))
def test_concurrent_first_callers_converge_on_one_persisted_id(tmp_path: Path, run: int) -> None:
    """TAP-5893 acceptance 1: N racing first-callers agree with each other and disk."""
    root = tmp_path / f"fresh-{run}"
    root.mkdir()

    ids = _run_barrier_probe(root)

    persisted = (root / _ID_REL).read_text(encoding="utf-8").strip()
    assert len(persisted) == 32, f"expected a 32-char uuid hex, got {persisted!r}"
    assert len(set(ids)) == 1, f"divergent agent ids across first-callers: {sorted(set(ids))}"
    assert ids[0].endswith(persisted[:8]), (
        f"returned id {ids[0]!r} does not match persisted uuid {persisted!r}"
    )


def test_write_uuid_reports_loss_instead_of_clobbering(tmp_path: Path) -> None:
    """``_write_uuid`` creates only when absent and never overwrites a winner."""
    path = tmp_path / ".tapps-mcp" / "agent.id"

    assert _write_uuid(path, "a" * 32) is True
    assert _write_uuid(path, "b" * 32) is False
    assert path.read_text(encoding="utf-8").strip() == "a" * 32


def test_loser_reuses_the_winners_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that loses the create race returns the persisted id, not its own."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    root = tmp_path / "proj"
    root.mkdir()
    winner_uuid = "c" * 32

    real_write = _write_uuid

    def _write_after_a_winner_appeared(path: Path, value: str) -> bool:
        # Simulate another process creating the file inside our read/create gap.
        real_write(path, winner_uuid)
        return real_write(path, value)

    monkeypatch.setattr("tapps_core.agent_identity._write_uuid", _write_after_a_winner_appeared)

    agent_id = get_stable_agent_id(_make_settings(root))

    assert (root / _ID_REL).read_text(encoding="utf-8").strip() == winner_uuid
    assert agent_id.endswith(winner_uuid[:8])


@pytest.mark.parametrize("err", [errno.EACCES, errno.EPERM])
def test_readonly_fs_falls_back_to_non_persisted_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, err: int
) -> None:
    """TAP-5893 acceptance 2: EACCES/EPERM yields a valid id and no exception."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    root = tmp_path / "proj"
    root.mkdir()

    real_open = __import__("os").open

    def _deny(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(path).endswith("agent.id"):
            raise OSError(err, "denied")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("tapps_core.agent_identity.os.open", _deny)

    agent_id = get_stable_agent_id(_make_settings(root))

    assert not (root / _ID_REL).exists(), "nothing should persist on a read-only FS"
    assert agent_id.startswith("tapps-mcp-")
    assert len(agent_id.rsplit("-", 1)[1]) == 8


def test_readonly_parent_dir_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``mkdir`` denial (read-only root) also degrades to a non-persisted id."""
    monkeypatch.delenv("CLAUDE_AGENT_ID", raising=False)
    root = tmp_path / "proj"
    root.mkdir()

    real_mkdir: Callable[..., None] = Path.mkdir

    def _deny(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == ".tapps-mcp":
            raise OSError(errno.EPERM, "read-only file system")
        real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", _deny)

    agent_id = get_stable_agent_id(_make_settings(root))

    assert agent_id.startswith("tapps-mcp-")
    assert len(agent_id.rsplit("-", 1)[1]) == 8

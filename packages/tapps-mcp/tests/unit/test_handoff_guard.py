"""Ownership guard, archive/prune and atomic promote for handoff writes (TAP-6871)."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.handoff_guard import (
    ARCHIVE_KEEP,
    HandoffOwnerConflictError,
    guarded_write,
    handoff_archive_dir,
)
from tapps_mcp.tools.handoff_schema import handoff_path

pytestmark = pytest.mark.usefixtures("envelope_guard")


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _handoff(title: str, *, program: str | None = None, age_hours: float = 0.5) -> str:
    """A lint-clean handoff body with a stated title and optional program."""
    updated = datetime.now(UTC) - timedelta(hours=age_hours)
    program_line = f"**Program:** {program}\n" if program else ""
    return (
        f"# {title}\n"
        f"{program_line}"
        f"**Updated:** {_iso(updated)}\n"
        "**Linear P0:** TAP-6871\n"
        "\n"
        "## Done\n"
        f"- {title} did a thing\n"
        "\n"
        "## Open\n"
        "- none\n"
        "\n"
        "## Next (P0)\n"
        "- keep going\n"
        "\n"
        "## Success criterion\n"
        "- the guard fires\n"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_incumbent(root: Path, markdown: str) -> Path:
    path = handoff_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


class TestOwnershipGuard:
    def test_warn_mode_writes_and_reports_conflict(self, tmp_path: Path) -> None:
        previous = _handoff("Program A", program="alpha")
        incumbent = _seed_incumbent(tmp_path, previous)
        incoming = _handoff("Program B", program="beta")

        result = guarded_write(tmp_path, incoming, mode="warn")

        assert result.path.read_text(encoding="utf-8") == incoming
        assert result.conflict is not None
        assert result.conflict["foreign"] is True
        assert result.conflict["previous"]["title"] == "Program A"
        # The parsed ``**Program:**`` is what decided this, not the title
        # (TAP-6872) — so the payload must carry the value, not just the key.
        assert result.conflict["previous"]["program"] == "alpha"
        archived_to = Path(result.conflict["archived_to"])
        assert archived_to.is_file()
        assert archived_to.parent == handoff_archive_dir(tmp_path)
        assert archived_to.read_text(encoding="utf-8") == previous
        assert incumbent.read_text(encoding="utf-8") == incoming

    def test_block_mode_leaves_incumbent_byte_identical(self, tmp_path: Path) -> None:
        previous = _handoff("Program A", program="alpha")
        incumbent = _seed_incumbent(tmp_path, previous)
        before = _sha256(incumbent)

        with pytest.raises(HandoffOwnerConflictError) as exc_info:
            guarded_write(tmp_path, _handoff("Program B", program="beta"), mode="block")

        after = _sha256(incumbent)
        assert before == after
        assert incumbent.read_text(encoding="utf-8") == previous
        envelope = exc_info.value.envelope
        assert envelope["code"] == "handoff_owner_conflict"
        assert "Program A" in envelope["hint"]
        assert "slot=" in envelope["hint"]
        # block refuses before it touches anything: no archive is written either.
        assert not handoff_archive_dir(tmp_path).exists()

    def test_force_overrides_block_and_archives(self, tmp_path: Path) -> None:
        previous = _handoff("Program A", program="alpha")
        _seed_incumbent(tmp_path, previous)
        incoming = _handoff("Program B", program="beta")

        result = guarded_write(tmp_path, incoming, mode="block", force=True)

        assert result.path.read_text(encoding="utf-8") == incoming
        assert result.conflict is not None
        assert result.conflict["foreign"] is True
        assert result.conflict["forced"] is True
        archived_to = Path(result.conflict["archived_to"])
        assert archived_to.read_text(encoding="utf-8") == previous

    def test_archive_prune_keeps_exactly_twenty(self, tmp_path: Path) -> None:
        archive_dir = handoff_archive_dir(tmp_path)
        archive_dir.mkdir(parents=True, exist_ok=True)
        stale = []
        for index in range(25):
            path = archive_dir / f"20260101T0000{index:02d}Z-default.md"
            path.write_text(f"stale {index}\n", encoding="utf-8")
            stale.append(path)
        _seed_incumbent(tmp_path, _handoff("Program A", program="alpha"))

        guarded_write(tmp_path, _handoff("Program B", program="beta"), mode="warn")

        remaining = sorted(archive_dir.glob("*.md"))
        assert len(remaining) == ARCHIVE_KEEP == 20
        # The newest survive; the oldest five are gone.
        assert all(not path.exists() for path in stale[:6])
        assert all(path.exists() for path in stale[6:])

    def test_promote_failure_leaves_incumbent_byte_identical(self, tmp_path: Path) -> None:
        previous = _handoff("Program A", program="alpha")
        incumbent = _seed_incumbent(tmp_path, previous)
        before = _sha256(incumbent)
        real_replace = os.replace
        calls: list[tuple[str, str]] = []

        def flaky_replace(
            src: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            dst: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            **kwargs: int | None,
        ) -> None:
            calls.append((str(src), str(dst)))
            if len(calls) == 2:
                raise OSError("simulated promote failure")
            real_replace(src, dst, **kwargs)

        with patch("os.replace", side_effect=flaky_replace):
            with pytest.raises(OSError, match="simulated promote failure"):
                guarded_write(tmp_path, _handoff("Program B", program="beta"), mode="warn")

        # The temp file was created in the target's own directory.
        assert Path(calls[1][0]).parent == incumbent.parent
        assert incumbent.is_file()
        assert _sha256(incumbent) == before
        assert incumbent.read_text(encoding="utf-8") == previous
        leftovers = [
            path for path in incumbent.parent.iterdir() if path.is_file() and path != incumbent
        ]
        assert leftovers == []


class TestGuardNegativeControls:
    def test_identical_program_is_not_foreign(self, tmp_path: Path) -> None:
        _seed_incumbent(tmp_path, _handoff("Program A", program="alpha"))
        incoming = _handoff("Program A", program="alpha")

        result = guarded_write(tmp_path, incoming, mode="block")

        assert result.conflict is not None
        assert result.conflict["foreign"] is False
        assert result.path.read_text(encoding="utf-8") == incoming
        # Archive is unconditional even when there is no conflict.
        assert Path(result.conflict["archived_to"]).is_file()

    def test_previous_older_than_window_is_not_foreign(self, tmp_path: Path) -> None:
        _seed_incumbent(tmp_path, _handoff("Program A", program="alpha", age_hours=48))
        incoming = _handoff("Program B", program="beta")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] is False
        assert result.path.read_text(encoding="utf-8") == incoming

    def test_unparseable_previous_reports_unknown_and_does_not_block(self, tmp_path: Path) -> None:
        _seed_incumbent(tmp_path, "no heading, no program, no timestamp\n")
        incoming = _handoff("Program B", program="beta")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] == "unknown"
        assert result.path.read_text(encoding="utf-8") == incoming
        archived_to = Path(result.conflict["archived_to"])
        assert archived_to.read_text(encoding="utf-8") == ("no heading, no program, no timestamp\n")


class TestProgramIsTheIdentity:
    """TAP-6872: ``**Program:**`` decides ownership, and the title never does.

    Before the header parsed, ``classify_foreign`` fell through to a raw string
    compare of the H1 heading. Every test here pins a case where the heading and
    the program disagree, which is exactly where that fallback answered wrong.
    """

    def test_different_programs_sharing_one_title_are_foreign(self, tmp_path: Path) -> None:
        # The false negative the title compare shipped: a generic heading is a
        # plausible convention, and under it two unrelated programs read as one.
        _seed_incumbent(tmp_path, _handoff("Session handoff", program="alpha"))
        incoming = _handoff("Session handoff", program="beta")

        result = guarded_write(tmp_path, incoming, mode="warn")

        assert result.conflict is not None
        assert result.conflict["foreign"] is True
        assert result.conflict["previous"]["program"] == "alpha"

    def test_different_programs_sharing_one_title_block(self, tmp_path: Path) -> None:
        # The consequence of the case above: under ``block`` the write that the
        # whole effort exists to refuse was being silently permitted.
        incumbent = _seed_incumbent(tmp_path, _handoff("Session handoff", program="alpha"))
        before = _sha256(incumbent)

        with pytest.raises(HandoffOwnerConflictError) as exc_info:
            guarded_write(tmp_path, _handoff("Session handoff", program="beta"), mode="block")

        assert _sha256(incumbent) == before
        assert "alpha" in exc_info.value.envelope["hint"]

    def test_same_program_under_different_titles_is_not_foreign(self, tmp_path: Path) -> None:
        # The matching false positive: one program that puts a round number in
        # its heading tripped a conflict against itself.
        _seed_incumbent(tmp_path, _handoff("Handoff slots — round 1", program="alpha"))
        incoming = _handoff("Handoff slots — round 2", program="alpha")

        result = guarded_write(tmp_path, incoming, mode="block")

        assert result.conflict is not None
        assert result.conflict["foreign"] is False


class TestHeaderAbsentIsUnknownNotATitleCompare:
    """Backcompat: a handoff written before TAP-6872 carries no ``**Program:**``.

    Its ownership is unprovable, so it reports ``"unknown"`` — archived, never
    blocked. ``"unknown"`` and "the titles happened to match" are different
    answers, and collapsing them is the gap the title fallback created.
    """

    def test_legacy_incumbent_with_a_different_title_is_unknown_not_foreign(
        self, tmp_path: Path
    ) -> None:
        _seed_incumbent(tmp_path, _handoff("Program A"))
        incoming = _handoff("Program B", program="beta")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] == "unknown"
        assert result.path.read_text(encoding="utf-8") == incoming
        assert Path(result.conflict["archived_to"]).is_file()

    def test_legacy_incumbent_with_a_matching_title_is_unknown_not_no_conflict(
        self, tmp_path: Path
    ) -> None:
        previous = _handoff("Session handoff")
        _seed_incumbent(tmp_path, previous)
        incoming = _handoff("Session handoff", program="beta")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] == "unknown"
        assert Path(result.conflict["archived_to"]).read_text(encoding="utf-8") == previous

    def test_legacy_incoming_against_a_stated_incumbent_is_unknown(self, tmp_path: Path) -> None:
        # The other direction: a repo that has not adopted the header yet must
        # not be blocked out of a handoff path a stated program now owns.
        _seed_incumbent(tmp_path, _handoff("Program A", program="alpha"))
        incoming = _handoff("Program B")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] == "unknown"
        assert result.path.read_text(encoding="utf-8") == incoming

    def test_neither_side_states_a_program_is_unknown(self, tmp_path: Path) -> None:
        # Two legacy repos: the pre-TAP-6872 fleet. Unprovable either way, so
        # reported and archived, and never a refusal.
        _seed_incumbent(tmp_path, _handoff("Program A"))
        incoming = _handoff("Program B")

        result = guarded_write(tmp_path, incoming, mode="block", window_hours=12)

        assert result.conflict is not None
        assert result.conflict["foreign"] == "unknown"
        assert result.path.read_text(encoding="utf-8") == incoming


class TestGuardModeSetting:
    def test_conflict_mode_defaults_to_warn(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        settings = TappsMCPSettings()
        assert settings.handoff_conflict_mode == "warn"
        assert settings.handoff_conflict_window_hours == 12

    def test_off_mode_archives_without_signalling(self, tmp_path: Path) -> None:
        previous = _handoff("Program A", program="alpha")
        _seed_incumbent(tmp_path, previous)

        result = guarded_write(tmp_path, _handoff("Program B", program="beta"), mode="off")

        assert result.conflict is None
        archives = list(handoff_archive_dir(tmp_path).glob("*.md"))
        assert len(archives) == 1
        assert archives[0].read_text(encoding="utf-8") == previous


class TestWriteHandoffIntegration:
    @pytest.mark.asyncio
    async def test_write_handoff_surfaces_conflict(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.handoff_write import write_handoff

        _seed_incumbent(tmp_path, _handoff("Program A", program="alpha"))
        incoming = _handoff("Program B", program="beta")

        with patch(
            "tapps_mcp.tools.handoff_write.mirror_handoff_to_brain",
            new_callable=AsyncMock,
            return_value={"success": True, "key": "session-handoff"},
        ):
            result = await write_handoff(tmp_path, incoming, conflict_mode="warn")

        assert result.conflict is not None
        assert result.conflict["foreign"] is True
        assert Path(result.conflict["archived_to"]).is_file()

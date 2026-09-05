"""The surfaces that expose slots to their users (TAP-6874).

Every mechanism under test here already existed and was proved in isolation by
TAP-6870/6871/6872/6873. What was missing was a caller: ``handoff_path`` had a
``slot`` parameter nothing on the write path passed, ``handoff_memory_key`` had
no caller at all, and the guard's ``force`` was reachable only from Python. So
each test in this file drives the mechanism *through the surface an agent
actually touches* — the read side, the MCP tool, the CLI, or the emitted skill
body — never by calling the mechanism directly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from tapps_mcp.tools.handoff_guard import conflict_advisory, handoff_archive_dir
from tapps_mcp.tools.handoff_schema import (
    handoff_memory_key,
    handoff_path,
    list_handoffs,
    load_and_lint_handoff,
)


def _handoff(program: str, *, updated: datetime | None = None, p0: str = "TAP-6874") -> str:
    stamp = (updated or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""\
# Session handoff
**Program:** {program}
**Updated:** {stamp}
**Linear P0:** {p0}

## Done
- wired {program} to its surface

## Open
- none

## Next (P0)
- run the surfaces suite

## Success criterion
- the surface reaches the mechanism
"""


def _seed(project_root: Path, slot: str | None, markdown: str) -> Path:
    path = handoff_path(project_root, slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


class _BrainHolder:
    """The one attribute ``BrainBridge`` reaches for on an in-process brain.

    Constructing a full ``AgentBrain`` loads the real embedding model, which
    costs seconds and a network fetch; the bridge only ever touches ``.store``.
    """

    def __init__(self, store: Any) -> None:
        self.store = store


class TestTheReadSideSeesSlots:
    """``load_and_lint_handoff`` and ``list_handoffs`` — spec §2.3."""

    def test_load_reads_the_slot_it_was_given(self, tmp_path: Path) -> None:
        _seed(tmp_path, None, _handoff("default-program"))
        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub"))

        doc, lint = load_and_lint_handoff(tmp_path, slot="ceg-hub")

        assert doc is not None
        assert doc.program == "ceg-hub"
        assert lint.ok

    def test_load_without_a_slot_still_reads_the_default_file(self, tmp_path: Path) -> None:
        """The ~35 repos that never pass a slot must see no change."""
        _seed(tmp_path, None, _handoff("default-program"))
        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub"))

        doc, _ = load_and_lint_handoff(tmp_path)

        assert doc is not None
        assert doc.program == "default-program"

    def test_list_covers_the_default_file_and_every_slot(self, tmp_path: Path) -> None:
        _seed(tmp_path, None, _handoff("default-program"))
        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub"))
        _seed(tmp_path, "merch-imagery", _handoff("merch-imagery"))

        rows = list_handoffs(tmp_path)

        assert {row["slot"] for row in rows} == {None, "ceg-hub", "merch-imagery"}
        assert {row["program"] for row in rows} == {
            "default-program",
            "ceg-hub",
            "merch-imagery",
        }

    def test_list_never_enumerates_the_archive(self, tmp_path: Path) -> None:
        """The archive holds superseded handoffs; offering one as live is the bug.

        The archive lives *inside* the slot directory (``handoffs/archive/``),
        so a recursive walk picks it up. It has to be excluded deliberately.
        """
        _seed(tmp_path, None, _handoff("default-program"))
        archive = handoff_archive_dir(tmp_path)
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "20260901T120000.000000Z-default.md").write_text(
            _handoff("archived-program"), encoding="utf-8"
        )

        rows = list_handoffs(tmp_path)

        assert [row["slot"] for row in rows] == [None]
        assert all("archive" not in row["path"] for row in rows)

    def test_list_sorts_by_updated_descending(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        _seed(tmp_path, "oldest", _handoff("oldest", updated=now - timedelta(hours=6)))
        _seed(tmp_path, "newest", _handoff("newest", updated=now))
        _seed(tmp_path, "middle", _handoff("middle", updated=now - timedelta(hours=3)))

        rows = list_handoffs(tmp_path)

        assert [row["slot"] for row in rows] == ["newest", "middle", "oldest"]

    def test_list_reports_age_and_linear_p0(self, tmp_path: Path) -> None:
        _seed(
            tmp_path,
            "ceg-hub",
            _handoff("ceg-hub", updated=datetime.now(UTC) - timedelta(hours=2), p0="TAP-1234"),
        )

        (row,) = list_handoffs(tmp_path)

        assert row["linear_p0"] == "TAP-1234"
        assert row["age_hours"] == pytest.approx(2.0, abs=0.2)

    def test_list_is_empty_when_nothing_was_ever_written(self, tmp_path: Path) -> None:
        assert list_handoffs(tmp_path) == []


@pytest.mark.live_network
class TestTheSlotReachesTheBrainKey:
    """Inherited findings 1 and 2, proved together over one real save.

    TAP-6592: ``_store`` constructs a real ``tapps_brain.store.MemoryStore``
    directly. That external, pinned dependency's own default embeds saved
    content via sentence-transformers on ``.save()``, downloading its model
    from HuggingFace Hub on a cache miss -- out of this repo's boundary to
    fix (tapps-brain is a pinned external package). Marked live_network
    rather than silently broken by the new root guard.

    Finding 1: ``handoff_memory_key`` had no caller — the write path handed the
    bare constant to the mirror, so no slotted handoff could reach the brain
    under its own key. Finding 2: the mirror passed ``details_json=``, which is
    not a field of the pinned brain's ``MemoryEntry`` and not a parameter of
    ``MemoryStore.save`` — so the in-process mirror raised before storing
    anything at all.

    Both are asserted by reading the key back **out of a real store**, not by
    inspecting the arguments of a mocked mirror: a mock accepts a kwarg the
    pinned brain refuses.
    """

    @staticmethod
    def _store(tmp_path: Path) -> Any:
        from tapps_brain.store import MemoryStore

        return MemoryStore(tmp_path / "brain")

    @staticmethod
    def _patched_bridge(store: Any) -> Any:
        from tapps_core.brain_bridge import BrainBridge

        return patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            return_value=BrainBridge(_BrainHolder(store)),
        )

    @pytest.mark.asyncio
    async def test_a_slotted_write_stores_the_row_under_the_slotted_key(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.tools.handoff_write import write_handoff

        store = self._store(tmp_path)
        markdown = _handoff("ceg-hub")

        with self._patched_bridge(store):
            result = await write_handoff(tmp_path, markdown, slot="ceg-hub")

        assert result.file_path == str(tmp_path / ".tapps-mcp" / "handoffs" / "ceg-hub.md")
        assert result.brain_mirror is not None
        assert result.brain_mirror["success"] is True

        row = store.get(handoff_memory_key("ceg-hub"))
        assert row is not None
        assert row.key == "session-handoff.ceg-hub"
        assert row.value == markdown
        assert store.get("session-handoff") is None

    @pytest.mark.asyncio
    async def test_an_unslotted_write_still_stores_the_bare_key(self, tmp_path: Path) -> None:
        """Negative control: the default key is byte-identical to today's."""
        from tapps_mcp.tools.handoff_write import write_handoff

        store = self._store(tmp_path)

        with self._patched_bridge(store):
            await write_handoff(tmp_path, _handoff("default-program"))

        row = store.get("session-handoff")
        assert row is not None
        assert row.key == "session-handoff"


class TestTheToolSurfaceAcceptsSlotOwnerAndForce:
    """Scope item 3 — where ``force`` finally gets wired."""

    @staticmethod
    def _block_mode_root(tmp_path: Path) -> Path:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "handoff_conflict_mode: block\n", encoding="utf-8"
        )
        return tmp_path

    @staticmethod
    async def _save(root: Path, markdown: str, **kwargs: Any) -> dict[str, Any]:
        from tapps_mcp import server_pipeline_tools as spt

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = root
            return await spt.tapps_handoff_save(markdown, mirror_brain=False, **kwargs)

    @pytest.mark.asyncio
    async def test_slot_routes_the_write_under_handoffs(self, tmp_path: Path) -> None:
        result = await self._save(tmp_path, _handoff("ceg-hub"), slot="ceg-hub")

        assert result["success"] is True
        assert result["data"]["file_path"] == str(
            tmp_path / ".tapps-mcp" / "handoffs" / "ceg-hub.md"
        )

    @pytest.mark.asyncio
    async def test_an_invalid_slot_is_refused_before_any_path_is_written(
        self, tmp_path: Path
    ) -> None:
        result = await self._save(tmp_path, _handoff("x"), slot="../escape")

        assert result["success"] is False
        assert result["error"]["code"] == "invalid_handoff_slot"
        assert not (tmp_path / ".tapps-mcp").exists()

    @pytest.mark.asyncio
    async def test_block_mode_refuses_a_foreign_overwrite(self, tmp_path: Path) -> None:
        root = self._block_mode_root(tmp_path)
        incumbent = _handoff("program-a")
        path = _seed(root, None, incumbent)

        result = await self._save(root, _handoff("program-b"))

        assert result["success"] is False
        assert result["error"]["code"] == "handoff_owner_conflict"
        assert path.read_text(encoding="utf-8") == incumbent

    @pytest.mark.asyncio
    async def test_force_overrides_the_block_and_archives_first(self, tmp_path: Path) -> None:
        """Spec line 99: ``force=true`` overrides the refusal *and archives first*."""
        root = self._block_mode_root(tmp_path)
        incumbent = _handoff("program-a")
        path = _seed(root, None, incumbent)
        incoming = _handoff("program-b")

        result = await self._save(root, incoming, force=True)

        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == incoming
        conflict = result["data"]["conflict"]
        assert conflict["forced"] is True
        assert conflict["foreign"] is True
        archived = Path(conflict["archived_to"])
        assert archived.read_text(encoding="utf-8") == incumbent

    @pytest.mark.asyncio
    async def test_owner_overrides_the_program_header_for_ownership(self, tmp_path: Path) -> None:
        """``owner`` states the identity when the body's header does not (spec §2.2).

        Same body both times; only ``owner`` differs, and only that makes the
        second write a foreign overwrite.
        """
        root = self._block_mode_root(tmp_path)
        body = _handoff("shared-title").replace("**Program:** shared-title\n", "")
        _seed(root, None, _handoff("program-a"))

        result = await self._save(root, body, owner="program-b")

        assert result["success"] is False
        assert result["error"]["code"] == "handoff_owner_conflict"

    @pytest.mark.asyncio
    async def test_matching_owner_is_not_a_conflict(self, tmp_path: Path) -> None:
        """Negative control for ``owner``: same stated identity, no refusal."""
        root = self._block_mode_root(tmp_path)
        body = _handoff("shared-title").replace("**Program:** shared-title\n", "")
        _seed(root, None, _handoff("program-a"))

        result = await self._save(root, body, owner="program-a")

        assert result["success"] is True


class TestTheConflictSignalReachesTheAgent:
    """Warn mode writes *and reports* — the report has to leave Python.

    ``block`` mode refuses through the gateway envelope, which is loud by
    construction. ``warn`` — the default, and the mode the ~35 consuming repos
    run — completes the write and hands the displacement back in the response.
    Embedding it as an unclassified sub-result is the TAP-5656 shape: a caller
    reading only the top level sees a plain success over somebody else's
    archived handoff.
    """

    @staticmethod
    async def _save(root: Path, markdown: str, **kwargs: Any) -> dict[str, Any]:
        return await TestTheToolSurfaceAcceptsSlotOwnerAndForce._save(root, markdown, **kwargs)

    @pytest.mark.asyncio
    async def test_a_warn_mode_overwrite_surfaces_through_the_envelope(
        self, tmp_path: Path
    ) -> None:
        incumbent = _handoff("program-a")
        _seed(tmp_path, None, incumbent)

        result = await self._save(tmp_path, _handoff("program-b"))

        assert result["success"] is True
        # The raw payload keeps every field it had — the classification is
        # additive, never a replacement for the record.
        conflict = result["data"]["conflict"]
        assert conflict["foreign"] is True
        assert conflict["mode"] == "warn"
        assert conflict["previous"]["program"] == "program-a"
        assert Path(conflict["archived_to"]).read_text(encoding="utf-8") == incumbent
        # And the envelope itself now says so, at the top level and in prose.
        assert result["data"]["conflict_status"] == "overwritten"
        assert result["degraded"] is True
        assert any("program-a" in w for w in result["data"]["warnings"])

    @pytest.mark.asyncio
    async def test_a_clean_write_is_classified_clear_and_not_degraded(self, tmp_path: Path) -> None:
        """Negative control: nothing displaced, nothing to warn about."""
        result = await self._save(tmp_path, _handoff("program-a"))

        assert result["data"]["conflict_status"] == "clear"
        assert "degraded" not in result
        assert "warnings" not in result["data"]

    @pytest.mark.asyncio
    async def test_an_unownable_recent_incumbent_is_advised_and_degrades(
        self, tmp_path: Path
    ) -> None:
        """A header-less incumbent updated inside the conflict window (TAP-7008).

        ``classify_foreign`` still answers ``"unknown"`` — the header really
        is missing, so this is not a named displacement — but "somebody wrote
        this a moment ago" and "this is TAP-6872's dated legacy population"
        are not the same event. Only the window tells them apart, and this
        one is inside it: it gets an advisory, and the advisory is a warning
        like any other, so the envelope degrades.
        """
        legacy = _handoff("program-a").replace("**Program:** program-a\n", "")
        _seed(tmp_path, None, legacy)

        result = await self._save(tmp_path, _handoff("program-b"))

        assert result["data"]["conflict"]["foreign"] == "unknown"
        assert result["data"]["conflict_status"] == "unknown"
        assert result["degraded"] is True
        assert any("unestablished ownership" in w for w in result["data"]["warnings"])

    @pytest.mark.asyncio
    async def test_a_stale_unownable_incumbent_is_reported_but_does_not_degrade(
        self, tmp_path: Path
    ) -> None:
        """Every handoff written before TAP-6872 lacks the header.

        ``classify_foreign`` answers ``"unknown"`` for those and never blocks
        them; degrading on it would make the ordinary re-handoff in every
        legacy repo read as a displacement. This is TAP-6872's population —
        dated, and outside the conflict window — and it must stay the negative
        control: still classified ``"unknown"``, still silent, still
        undegraded, no matter what the recent-unknown case above does.
        """
        stale = datetime.now(UTC) - timedelta(hours=13)
        legacy = _handoff("program-a", updated=stale).replace("**Program:** program-a\n", "")
        _seed(tmp_path, None, legacy)

        result = await self._save(tmp_path, _handoff("program-b"))

        assert result["data"]["conflict"]["foreign"] == "unknown"
        assert result["data"]["conflict_status"] == "unknown"
        assert "degraded" not in result
        assert "warnings" not in result["data"]

    @pytest.mark.asyncio
    async def test_an_undated_unknown_incumbent_is_advised(self, tmp_path: Path) -> None:
        """No ``**Program:**`` header *and* no ``**Updated:**`` line.

        The window test in :func:`~tapps_mcp.tools.handoff_guard._unknown_advisory`
        cannot be applied to an incumbent it cannot date, and "cannot be shown
        to be stale" is not the same claim as "shown to be stale". Refuse to
        guess: this one gets the advisory, same as a recent one would.
        """
        legacy = """\
# Session handoff
**Linear P0:** TAP-6874

## Done
- legacy write, pre-header and pre-timestamp

## Open
- none

## Next (P0)
- run the surfaces suite

## Success criterion
- the surface reaches the mechanism
"""
        _seed(tmp_path, None, legacy)

        result = await self._save(tmp_path, _handoff("program-b"))

        assert result["data"]["conflict"]["foreign"] == "unknown"
        assert result["data"]["conflict"]["previous"]["updated"] is None
        assert result["data"]["conflict_status"] == "unknown"
        assert result["degraded"] is True
        assert any("unestablished ownership" in w for w in result["data"]["warnings"])

    def test_an_unparseable_updated_value_is_advised_not_raised(self) -> None:
        """``previous.updated`` that is not a parseable timestamp (TAP-7008 regression).

        The MCP save path drives a mocked write result in
        ``test_handoff_write.py``, so ``updated`` can arrive as something
        that is not even a string (a ``MagicMock``, in that suite). A value
        that fails to parse cannot be shown to be stale any more than a
        missing one can, so it must take the same branch as ``None`` — the
        advisory — rather than propagating a ``TypeError``/``ValueError``
        out of ``strptime``.
        """
        payload = {
            "foreign": "unknown",
            "previous": {"updated": MagicMock()},
            "archived_to": None,
        }

        status, warnings, next_steps = conflict_advisory(payload)

        assert status == "unknown"
        assert any("unestablished ownership" in w for w in warnings)
        assert next_steps


class TestTheCliSurface:
    """Scope item 4 — ``--slot`` on write, and a new ``handoff list``."""

    @staticmethod
    def _payload(output: str, opener: str) -> Any:
        """Parse the JSON document out of mixed CLI output.

        ``structlog`` writes its debug lines to the same stream, so the JSON is
        the tail of the output rather than the whole of it.
        """
        return json.loads(output[output.index(opener) :])

    def test_write_accepts_a_slot(self, tmp_path: Path) -> None:
        from tapps_mcp.cli_handoff import handoff_write

        result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(tmp_path), "--slot", "ceg-hub", "--no-brain-mirror"],
            input=_handoff("ceg-hub"),
        )

        assert result.exit_code == 0, result.output
        payload = self._payload(result.output, "{")
        assert payload["file_path"] == str(tmp_path / ".tapps-mcp" / "handoffs" / "ceg-hub.md")

    def test_list_renders_every_handoff(self, tmp_path: Path) -> None:
        from tapps_mcp.cli_handoff import handoff_list

        _seed(tmp_path, None, _handoff("default-program"))
        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub"))

        result = CliRunner().invoke(handoff_list, ["--project-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        rows = self._payload(result.output, "[")
        assert {row["slot"] for row in rows} == {None, "ceg-hub"}

    def test_list_is_registered_on_the_group(self) -> None:
        from tapps_mcp.cli_handoff import handoff_group

        result = CliRunner().invoke(handoff_group, ["--help"])

        assert result.exit_code == 0
        assert "list" in result.output


class TestTheSlotReachesTheSessionEnd:
    """The third half of a slotted write — ``load_and_lint_handoff(slot=)``.

    ``write_handoff`` routes the file and the brain row by slot, then ran
    ``session_end`` against whatever program owned the *default* handoff. The
    read-side ``slot`` argument had no production caller at all, so the
    retrieval query for a slotted session was keyed off an unrelated program.
    These drive the real entry point, never ``load_and_lint_handoff`` directly.
    """

    @pytest.mark.asyncio
    async def test_a_slotted_write_searches_on_its_own_handoff(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.handoff_write import write_handoff

        _seed(tmp_path, None, _handoff("default-program", p0="TAP-0000"))

        result = await write_handoff(
            tmp_path,
            _handoff("ceg-hub", p0="TAP-6874"),
            slot="ceg-hub",
            mirror_brain=False,
            run_session_end=True,
        )

        assert result.session_end is not None
        assert result.session_end["session_search_query"] == "TAP-6874"

    @pytest.mark.asyncio
    async def test_an_unslotted_write_still_searches_on_the_default_handoff(
        self, tmp_path: Path
    ) -> None:
        """Negative control: the ~35 repos that never pass a slot see no change."""
        from tapps_mcp.tools.handoff_write import write_handoff

        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub", p0="TAP-6874"))

        result = await write_handoff(
            tmp_path,
            _handoff("default-program", p0="TAP-0000"),
            mirror_brain=False,
            run_session_end=True,
        )

        assert result.session_end is not None
        assert result.session_end["session_search_query"] == "TAP-0000"


class TestOneEnumerationSite:
    """Scope item 2 — three consumers, one ``list_handoffs``."""

    _SRC = Path(__file__).resolve().parents[2] / "src" / "tapps_mcp"

    @pytest.mark.parametrize(
        "module",
        ["cli_handoff.py", "tools/fleet_audit.py"],
    )
    def test_each_consumer_imports_the_enumeration_site(self, module: str) -> None:
        assert "list_handoffs" in (self._SRC / module).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "module",
        ["cli_handoff.py", "tools/fleet_audit.py"],
    )
    def test_no_consumer_enumerates_for_itself(self, module: str) -> None:
        """A second glob is the restatement SG-2 and SG-2b spent two lanes removing."""
        text = (self._SRC / module).read_text(encoding="utf-8")
        assert '.md"' not in text
        assert "'.md'" not in text

    def test_fleet_audit_reports_every_live_slot(self, tmp_path: Path) -> None:
        """Behavioural counterpart to the two source-text assertions above.

        Those prove ``list_handoffs`` is *named* in the consumer; they cannot
        prove it is *called*. Returning a constant ``[]`` from the slots row
        left them both green, which is how the wiring stayed unpinned.
        """
        from tapps_mcp.tools.fleet_audit import audit_project_root

        (tmp_path / ".tapps-mcp.yaml").write_text("", encoding="utf-8")
        _seed(tmp_path, None, _handoff("default-program"))
        _seed(tmp_path, "ceg-hub", _handoff("ceg-hub"))
        _seed(tmp_path, "merch-imagery", _handoff("merch-imagery"))

        row = audit_project_root(
            tmp_path,
            since=datetime.now(UTC) - timedelta(days=1),
            include_brain=False,
        )

        assert sorted(row["handoff"]["slots"]) == ["ceg-hub", "merch-imagery"]
        # The default file is a handoff but not a slot; it is reported by
        # ``path``/``exists`` and must not be smuggled into the slot list.
        assert row["handoff"]["exists"] is True
        assert None not in row["handoff"]["slots"]

    def test_fleet_audit_reports_no_slots_when_only_the_default_exists(
        self, tmp_path: Path
    ) -> None:
        """Negative control — an empty row must mean 'none', not 'never looked'."""
        from tapps_mcp.tools.fleet_audit import audit_project_root

        (tmp_path / ".tapps-mcp.yaml").write_text("", encoding="utf-8")
        _seed(tmp_path, None, _handoff("default-program"))

        row = audit_project_root(
            tmp_path,
            since=datetime.now(UTC) - timedelta(days=1),
            include_brain=False,
        )

        assert row["handoff"]["slots"] == []
        assert row["handoff"]["exists"] is True


class TestTheEmittedSkillBodyTeachesSlots:
    """VAL-5 — assert on the emitted template text, never a live model run."""

    @staticmethod
    def _body(host: str, name: str) -> str:
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS

        return (CLAUDE_SKILLS if host == "claude" else CURSOR_SKILLS)[name]

    def test_continue_session_argument_hint_offers_a_slot(self) -> None:
        """Claude-host frontmatter only; the Cursor variant carries no hint field."""
        body = self._body("claude", "tapps-continue-session")
        hint = next(line for line in body.splitlines() if line.startswith("argument-hint:"))

        assert "[slot]" in hint

    @pytest.mark.parametrize("host", ["claude", "cursor"])
    def test_step_two_lists_and_asks_when_more_than_one_handoff_exists(self, host: str) -> None:
        body = self._body(host, "tapps-continue-session")

        assert "tapps-mcp handoff list" in body
        assert "never silently pick" in body.lower()
        assert "exactly one" in body.lower()

    @pytest.mark.parametrize("host", ["claude", "cursor"])
    def test_the_ground_truth_gate_still_runs(self, host: str) -> None:
        """Step 3 is unchanged and still reached — spec §2.3, last sentence."""
        body = self._body(host, "tapps-continue-session")

        assert "3. **Ground-truth gate (run before emitting anything).**" in body
        assert "**Commit drift.**" in body

    @pytest.mark.parametrize("host", ["claude", "cursor"])
    def test_the_handoff_row_names_slot_as_the_destination_selector(self, host: str) -> None:
        """Scope item 5 — ``--file`` is the *input*, never the destination."""
        body = self._body(host, "tapps-handoff-session")
        row = next(line for line in body.splitlines() if "CLI atomic" in line)

        assert "--slot" in row
        assert "slot=" in body

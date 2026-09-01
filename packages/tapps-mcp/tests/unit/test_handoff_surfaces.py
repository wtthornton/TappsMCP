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
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.tools.handoff_guard import handoff_archive_dir
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


class TestTheSlotReachesTheBrainKey:
    """Inherited findings 1 and 2, proved together over one real save.

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

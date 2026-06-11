"""Tests for session handoff schema parsing and lint (TAP-3573)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tapps_mcp.tools.handoff_schema import (
    lint_handoff,
    load_and_lint_handoff,
    parse_handoff_markdown,
)

_VALID_HANDOFF = """\
# Session handoff
**Updated:** 2026-06-11T12:00:00Z
**Linear P0:** TAP-3571

## Done
- Shipped metrics fix

## Open
- none

## Next (P0)
- Continue Wave 2 handoff hardening

## Blockers
- none

## Verify
- uv run pytest

## Success criterion
- Doctor passes handoff lint
"""

_MISSING_P0 = """\
# Session handoff
**Updated:** 2026-06-11T12:00:00Z

## Done
- Partial work

## Open
- Finish doctor linter

## Next (P0)
- none

## Success criterion
- MET
"""

_STALE_HANDOFF = """\
# Session handoff
**Updated:** 2026-01-01T00:00:00Z

## Open
- stale task

## Next (P0)
- refresh handoff
"""


class TestHandoffSchemaParse:
    def test_parse_valid_handoff(self) -> None:
        doc = parse_handoff_markdown(_VALID_HANDOFF)
        assert doc.linear_p0 == "TAP-3571"
        assert doc.done == ["Shipped metrics fix"]
        assert doc.next_p0 == ["Continue Wave 2 handoff hardening"]

    def test_lint_passes_valid(self) -> None:
        doc = parse_handoff_markdown(_VALID_HANDOFF)
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert result.ok
        assert not result.warnings

    def test_lint_fails_open_without_p0(self) -> None:
        doc = parse_handoff_markdown(_MISSING_P0)
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert not result.ok
        assert any("Next (P0)" in err for err in result.errors)

    def test_lint_warns_met_with_open(self) -> None:
        text = _MISSING_P0.replace("## Next (P0)\n- none\n", "## Next (P0)\n- do the thing\n")
        doc = parse_handoff_markdown(text)
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert result.ok
        assert any("MET" in w for w in result.warnings)

    def test_lint_warns_stale_updated(self) -> None:
        doc = parse_handoff_markdown(_STALE_HANDOFF)
        result = lint_handoff(
            doc,
            now=datetime(2026, 6, 11, tzinfo=UTC),
            stale_days=7,
        )
        assert result.ok
        assert any("older than" in w for w in result.warnings)


class TestHandoffSchemaDoctorIntegration:
    def test_load_and_lint_missing_file(self, tmp_path: Path) -> None:
        doc, lint = load_and_lint_handoff(tmp_path)
        assert doc is None
        assert lint.ok

    def test_load_and_lint_bad_handoff_on_disk(self, tmp_path: Path) -> None:
        handoff = tmp_path / ".tapps-mcp" / "session-handoff.md"
        handoff.parent.mkdir(parents=True)
        handoff.write_text(_MISSING_P0, encoding="utf-8")
        doc, lint = load_and_lint_handoff(tmp_path)
        assert doc is not None
        assert not lint.ok

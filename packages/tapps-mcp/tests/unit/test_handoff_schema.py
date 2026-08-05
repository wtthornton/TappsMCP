"""Tests for session handoff schema parsing and lint (TAP-3573)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tapps_mcp.tools.handoff_schema import (
    _brain_max_value_length,
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
        assert any("Next" in err for err in result.errors)

    def test_parse_next_heading_with_suffix(self) -> None:
        """TAP-5362: suffixed Next headings still populate next_p0."""
        text = _VALID_HANDOFF.replace(
            "## Next (P0)\n- Continue Wave 2 handoff hardening\n",
            "## Next (P0 -> Production)\n- Ship the release cut\n",
        )
        doc = parse_handoff_markdown(text)
        assert doc.next_p0 == ["Ship the release cut"]
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert result.ok

    def test_lint_quotes_unrecognized_next_like_header(self) -> None:
        """TAP-5362: near-miss headers are quoted when next_p0 is empty."""
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-06-11T12:00:00Z\n\n"
            "## Open\n"
            "- Finish doctor linter\n\n"
            "## Upcoming (P0)\n"
            "- do the thing\n"
        )
        doc = parse_handoff_markdown(text)
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert not result.ok
        assert any("unrecognized" in err and "Upcoming (P0)" in err for err in result.errors)

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

    def test_lint_warns_when_body_exceeds_brain_value_cap(self) -> None:
        """Warn while the draft can still be shortened, not after the mirror fails.

        The handoff template naturally produces bodies past the brain's
        per-value cap; without this the first sign of trouble was a
        bad_request buried in the save response's brain_mirror key.
        """
        cap = _brain_max_value_length()
        padding = "\n".join(f"- filler line {i}" for i in range(cap // 8))
        doc = parse_handoff_markdown(_VALID_HANDOFF.replace("- Shipped metrics fix", padding))
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))

        assert result.ok, "oversize body is advisory, not a blocking error"
        assert any(str(cap) in w and "value cap" in w for w in result.warnings)

    def test_lint_does_not_warn_for_normal_sized_handoff(self) -> None:
        doc = parse_handoff_markdown(_VALID_HANDOFF)
        result = lint_handoff(doc, now=datetime(2026, 6, 11, tzinfo=UTC))
        assert not any("value cap" in w for w in result.warnings)


class TestBulletTokenizer:
    """TAP-5669: numbered lists, bold markup, and prose paragraphs.

    One character-class ``lstrip("-* ")`` produced three defects: numbered
    items were invisible (so the P0 gate compared two empty lists and never
    fired), bold bullets lost their opening ``**``, and bold paragraphs
    counted as bullets.
    """

    def test_numbered_dot_items_populate_sections(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Open\n1. TAP-5618 still in progress.\n2. Second open item.\n\n"
            "## Next (P0)\n1. Split the megafiles.\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.open_items == ["TAP-5618 still in progress.", "Second open item."]
        assert doc.next_p0 == ["Split the megafiles."]

    def test_numbered_paren_and_two_digit_items(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Verify\n"
            + "\n".join(f"{i}. check number {i}" for i in range(1, 11))
            + "\n\n## Done\n1) paren marker item\n"
        )
        doc = parse_handoff_markdown(text)
        assert len(doc.verify) == 10
        assert doc.verify[9] == "check number 10"
        assert doc.done == ["paren marker item"]

    def test_bold_leading_bullet_survives_verbatim(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Open\n- **TAP-5618** (In Progress) — epic.\n- *emphasis* leading item\n\n"
            "## Next (P0)\n1. **Commit** the scaffolding refresh.\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.open_items == [
            "**TAP-5618** (In Progress) — epic.",
            "*emphasis* leading item",
        ]
        assert doc.next_p0 == ["**Commit** the scaffolding refresh."]

    def test_bold_paragraph_is_not_a_bullet(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Done\n**v3.12.65 released** - first cut since v3.12.29.\n\nPlain prose line.\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.done == []

    def test_numbered_placeholders_still_filtered(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Blockers\n1. none\n\n"
            "## Done\n- ...\n2. tbd\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.blockers == []
        assert doc.done == []

    def test_gate_fires_on_numbered_open_without_next(self) -> None:
        """The silent-pass case: all-numbered handoff, Open populated, Next empty."""
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Open\n1. TAP-5618 still in progress.\n\n"
            "## Next (P0)\n1. none\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.open_items, "numbered Open items must be visible to the gate"
        result = lint_handoff(doc, now=datetime(2026, 8, 5, tzinfo=UTC))
        assert not result.ok
        assert any("Next" in err for err in result.errors)

    def test_gate_quiet_on_mixed_bullet_open_numbered_next(self) -> None:
        """The false-positive case: bulleted Open plus numbered Next (P0)."""
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Open\n- TAP-5618 still in progress.\n\n"
            "## Next (P0)\n1. Split the megafiles.\n"
        )
        doc = parse_handoff_markdown(text)
        result = lint_handoff(doc, now=datetime(2026, 8, 5, tzinfo=UTC))
        assert result.ok
        assert doc.next_p0 == ["Split the megafiles."]

    def test_plus_marker_and_indented_bullets(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Verify\n+ plus marker item\n  - indented bullet\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.verify == ["plus marker item", "indented bullet"]

    def test_marker_without_trailing_space_is_not_a_bullet(self) -> None:
        text = (
            "# Session handoff\n"
            "**Updated:** 2026-08-05T12:00:00Z\n\n"
            "## Done\n-dash-glued word\n*star-glued word\n"
        )
        doc = parse_handoff_markdown(text)
        assert doc.done == []


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


class TestMetClaimFalsePositives:
    """The MET warning must not trip on substrings or conditional phrasing."""

    def _doc(self, criterion: str):
        from tapps_mcp.tools.handoff_schema import parse_handoff_markdown

        return parse_handoff_markdown(
            "# Session handoff\n"
            "**Updated:** 2026-07-10T00:00:00Z\n\n"
            "## Open\n- something in flight\n\n"
            "## Next (P0)\n- do the thing\n\n"
            "## Success criterion\n"
            f"- {criterion}\n"
        )

    def test_geometry_substring_does_not_warn(self) -> None:
        from tapps_mcp.tools.handoff_schema import lint_handoff

        doc = self._doc("pawvlov3 ships a gate-passing .glb (geometry >= 0.65)")
        assert not any("MET" in w for w in lint_handoff(doc).warnings)

    def test_metrics_substring_does_not_warn(self) -> None:
        from tapps_mcp.tools.handoff_schema import lint_handoff

        doc = self._doc("dashboard metrics land in the report")
        assert not any("MET" in w for w in lint_handoff(doc).warnings)

    def test_conditional_is_met_when_does_not_warn(self) -> None:
        from tapps_mcp.tools.handoff_schema import lint_handoff

        doc = self._doc("criterion is met when the full suite passes")
        assert not any("MET" in w for w in lint_handoff(doc).warnings)

    def test_bare_met_claim_still_warns(self) -> None:
        from tapps_mcp.tools.handoff_schema import lint_handoff

        doc = self._doc("MET")
        assert any("MET" in w for w in lint_handoff(doc).warnings)

    def test_criterion_is_met_claim_still_warns(self) -> None:
        from tapps_mcp.tools.handoff_schema import lint_handoff

        doc = self._doc("success criterion is met.")
        assert any("MET" in w for w in lint_handoff(doc).warnings)

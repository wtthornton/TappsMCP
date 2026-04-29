"""Tests for the marker-wrapped TAPPS obligations block (TAP-970).

Covers the four cases the ticket calls out:
(a) fresh project with no CLAUDE.md
(b) legacy unmarked TAPPS section — auto-wraps as a one-time migration
(c) marked block with stale obligations — refresh between markers
(d) customized lines both inside and outside the markers — outside survives
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.tapps_obligations_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    install_or_refresh,
    wrap_with_markers,
)


_NEW_OBLIGATIONS = (
    "# TAPPS Quality Pipeline\n\n"
    "## Recommended Tool Call Obligations\n\n"
    "Call tapps_session_start() first.\n"
    "Call tapps_quick_check() after every Python edit.\n"
)


class TestWrapWithMarkers:
    def test_emits_begin_and_end_markers(self) -> None:
        wrapped = wrap_with_markers(_NEW_OBLIGATIONS, version="3.4.0")
        assert wrapped.startswith("<!-- BEGIN: tapps-obligations v3.4.0 -->\n")
        assert wrapped.endswith(MARKER_END)

    def test_preserves_obligation_body_verbatim(self) -> None:
        wrapped = wrap_with_markers(_NEW_OBLIGATIONS, version="9.9.9")
        assert _NEW_OBLIGATIONS.strip() in wrapped


class TestFreshProject:
    def test_creates_claude_md_with_markered_block(self, tmp_path: Path) -> None:
        claude_md = tmp_path / "CLAUDE.md"
        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS, version="3.4.0")
        assert action == "created"
        body = claude_md.read_text(encoding="utf-8")
        assert "<!-- BEGIN: tapps-obligations v3.4.0 -->" in body
        assert MARKER_END in body
        assert "tapps_session_start()" in body


class TestLegacyUnmarkedSection:
    def test_auto_wraps_existing_tapps_section(self, tmp_path: Path) -> None:
        legacy = (
            "# Project notes\n\n"
            "Some preamble that must survive.\n\n"
            "# TAPPS Quality Pipeline\n\n"
            "Old obligation prose that predates markers.\n\n"
            "# Other section\n\n"
            "Custom content the user added below TAPPS.\n"
        )
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(legacy, encoding="utf-8")

        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS)
        assert action == "migrated"
        result = claude_md.read_text(encoding="utf-8")
        assert MARKER_BEGIN_PREFIX in result
        assert MARKER_END in result
        # Pre-TAPPS content survives.
        assert "Some preamble that must survive." in result
        # Custom section AFTER TAPPS survives.
        assert "Custom content the user added below TAPPS." in result
        # Old prose was replaced by the new marker block.
        assert "Old obligation prose that predates markers." not in result


class TestMarkedBlockRefresh:
    def test_refresh_replaces_only_marker_region(self, tmp_path: Path) -> None:
        stale = (
            "# Project notes\n\n"
            "Custom intro.\n\n"
            + wrap_with_markers("# TAPPS Quality Pipeline\n\nold body", version="2.0.0")
            + "\n\n## Custom user appendix\n\nLines the user wrote.\n"
        )
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(stale, encoding="utf-8")

        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS, version="3.4.0")
        assert action == "refreshed"
        result = claude_md.read_text(encoding="utf-8")
        assert "<!-- BEGIN: tapps-obligations v3.4.0 -->" in result
        assert "<!-- BEGIN: tapps-obligations v2.0.0 -->" not in result
        assert "old body" not in result
        # Content outside the markers survives.
        assert "Custom intro." in result
        assert "## Custom user appendix" in result
        assert "Lines the user wrote." in result

    def test_unchanged_when_block_matches(self, tmp_path: Path) -> None:
        markered = wrap_with_markers(_NEW_OBLIGATIONS, version="3.4.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(f"# preamble\n\n{markered}\n", encoding="utf-8")
        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS, version="3.4.0")
        assert action == "unchanged"


class TestCustomLinesSurviveRoundTrip:
    def test_custom_lines_outside_markers_preserved(self, tmp_path: Path) -> None:
        custom_above = "# My project rules\n\nCRITICAL: do not commit on Fridays.\n\n"
        custom_below = "\n\n## My deployment notes\n\nDeploy via `make ship`.\n"
        markered = wrap_with_markers("# TAPPS Quality Pipeline\n\nv1 body", version="1.0.0")
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(custom_above + markered + custom_below, encoding="utf-8")

        # First refresh.
        install_or_refresh(claude_md, _NEW_OBLIGATIONS, version="3.4.0")
        body = claude_md.read_text(encoding="utf-8")
        assert "CRITICAL: do not commit on Fridays." in body
        assert "Deploy via `make ship`." in body
        assert "v1 body" not in body

        # Second refresh (idempotency).
        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS, version="3.4.0")
        assert action == "unchanged"
        final = claude_md.read_text(encoding="utf-8")
        assert "CRITICAL: do not commit on Fridays." in final
        assert "Deploy via `make ship`." in final


class TestAppendsWhenNoTappsContent:
    def test_appends_block_to_existing_unrelated_claude_md(self, tmp_path: Path) -> None:
        existing = "# My CLAUDE.md\n\nProject-specific notes only.\n"
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(existing, encoding="utf-8")
        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS)
        assert action == "appended"
        result = claude_md.read_text(encoding="utf-8")
        assert "Project-specific notes only." in result
        assert MARKER_BEGIN_PREFIX in result


class TestDryRun:
    def test_dry_run_reports_action_without_writing(self, tmp_path: Path) -> None:
        claude_md = tmp_path / "CLAUDE.md"
        action = install_or_refresh(claude_md, _NEW_OBLIGATIONS, dry_run=True)
        assert action == "created"
        assert not claude_md.exists()

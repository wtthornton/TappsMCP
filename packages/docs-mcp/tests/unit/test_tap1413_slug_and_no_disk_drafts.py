"""TAP-1413 — slug sanitiser + no-disk-draft default for epic/story generators.

Two regressions:

1. The inline filename slug in ``docs_generate_epic`` / ``docs_generate_story``
   only replaced spaces, so titles containing ``:``, ``;``, ``/``, or ``.``
   produced filenames like ``EPIC-x:-leaves-.md-drafts.md`` (and a stray
   subdirectory when ``/`` appeared).
2. Both tools defaulted to writing the body to disk, leaving ``.md`` drafts
   around even though Linear is the canonical store.

These tests fail without the TAP-1413 fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from docs_mcp.server_helpers import safe_slug
from tests.helpers import make_settings as _make_settings

# ---------------------------------------------------------------------------
# safe_slug — pure unit tests
# ---------------------------------------------------------------------------


class TestSafeSlug:
    def test_strips_colons_semicolons_slashes_and_dots(self) -> None:
        result = safe_slug(
            "docs_generate epic/story leaves .md drafts on disk; "
            "filename slug allows colons"
        )
        for forbidden in ("/", ":", ";", "."):
            assert forbidden not in result, f"slug retained {forbidden!r}: {result!r}"
        # Single path segment, lowercase, hyphen-separated.
        assert " " not in result
        assert result == result.lower()
        assert "/" not in result

    def test_collapses_runs_of_specials(self) -> None:
        # Multiple consecutive specials must collapse to a single hyphen.
        result = safe_slug("a:::b///c...d   e")
        assert result == "a-b-c-d-e"

    def test_strips_leading_and_trailing_hyphens(self) -> None:
        assert safe_slug(":::leading and trailing///") == "leading-and-trailing"

    def test_unicode_is_normalised_to_ascii(self) -> None:
        # Diacritics fold to ASCII; non-mappable codepoints drop entirely.
        assert safe_slug("naïve café") == "naive-cafe"
        # Pure CJK has no ASCII fold — slug becomes empty after stripping.
        assert safe_slug("日本語") == ""

    def test_caps_length(self) -> None:
        result = safe_slug("a" * 500, max_length=60)
        assert len(result) == 60

    def test_does_not_end_with_hyphen_after_truncation(self) -> None:
        # After truncating mid-run the trailing hyphen must be stripped.
        result = safe_slug("a" * 59 + "-extra", max_length=60)
        assert not result.endswith("-")

    def test_empty_input_returns_empty(self) -> None:
        assert safe_slug("") == ""
        assert safe_slug("   ") == ""
        assert safe_slug(":/.;") == ""


# ---------------------------------------------------------------------------
# docs_generate_epic / docs_generate_story — default no-disk-draft behavior
# ---------------------------------------------------------------------------


class TestGenerateEpicDefaultsToNoDiskWrite:
    @staticmethod
    async def _call(**kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_epic

        return await docs_generate_epic(**kwargs)

    @pytest.mark.asyncio
    async def test_default_does_not_write_draft_to_disk(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="An Epic with: tricky/chars; in.title",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        # Default behavior is no disk write — content must be inline.
        assert "written_to" not in result["data"], (
            "Epic generator wrote a .md draft when write_to_disk defaulted "
            "to False — TAP-1413 regression"
        )
        assert "content" in result["data"]
        # No EPIC-*.md files anywhere under the project root.
        leftovers = list(tmp_path.rglob("EPIC-*.md"))
        assert leftovers == [], f"unexpected drafts on disk: {leftovers}"

    @pytest.mark.asyncio
    async def test_uses_safe_slug_for_default_path_when_number_is_zero(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title=(
                    "docs_generate epic/story leaves .md drafts on disk; "
                    "filename slug allows colons"
                ),
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        op = result["data"]["output_path"]
        # Path = "docs/epics/EPIC-<slug>.md" — exactly three segments.
        parts = op.split("/")
        assert parts[:2] == ["docs", "epics"]
        assert len(parts) == 3, f"unexpected subdirectory in path: {op}"
        assert parts[2].startswith("EPIC-")
        assert parts[2].endswith(".md")
        slug_segment = parts[2][len("EPIC-") : -len(".md")]
        for forbidden in (":", ";"):
            assert forbidden not in slug_segment, slug_segment

    @pytest.mark.asyncio
    async def test_write_to_disk_true_still_works(self, tmp_path: Path) -> None:
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="Explicit Write Epic",
                number=999,
                project_root=str(tmp_path),
                write_to_disk=True,
            )

        assert result["success"] is True
        assert "written_to" in result["data"]
        assert (tmp_path / result["data"]["written_to"]).is_file()


class TestGenerateStoryDefaultsToNoDiskWrite:
    @staticmethod
    async def _call(**kwargs: Any) -> dict[str, Any]:
        from docs_mcp.server_gen_tools import docs_generate_story

        return await docs_generate_story(**kwargs)

    @pytest.mark.asyncio
    async def test_default_does_not_write_draft_to_disk(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="foo.py: leaves drafts on disk",
                files="foo.py:1-10",
                acceptance_criteria="don't write disk drafts",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        assert "written_to" not in result["data"], (
            "Story generator wrote a .md draft when write_to_disk defaulted "
            "to False — TAP-1413 regression"
        )
        leftovers = list(tmp_path.rglob("STORY-*.md"))
        assert leftovers == [], f"unexpected drafts on disk: {leftovers}"

    @pytest.mark.asyncio
    async def test_uses_safe_slug_for_default_path_when_numbers_unset(
        self, tmp_path: Path
    ) -> None:
        with patch(
            "docs_mcp.server_gen_tools._get_settings",
            return_value=_make_settings(tmp_path),
        ):
            result = await self._call(
                title="foo.py: tricky/chars; in.title",
                files="foo.py:1-10",
                acceptance_criteria="works",
                project_root=str(tmp_path),
            )

        assert result["success"] is True
        op = result["data"]["output_path"]
        parts = op.split("/")
        assert parts[:3] == ["docs", "epics", "stories"]
        # No subdirectory smuggled in via the title's "/" character.
        assert len(parts) == 4, f"unexpected subdirectory in path: {op}"
        assert parts[3].startswith("STORY-")
        slug_segment = parts[3][len("STORY-") : -len(".md")]
        for forbidden in (":", ";", "/"):
            assert forbidden not in slug_segment, slug_segment

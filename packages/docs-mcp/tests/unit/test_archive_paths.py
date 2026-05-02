"""Regression tests for archive_paths exclusion (TAP-1278).

Verifies that the four validators (style, cross_refs, links, diataxis)
honor the archive_paths setting at file-discovery time, surface
excluded_paths_count, and remain inclusive when archive_paths is empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.validators._scan_filters import matches_any_pattern
from docs_mcp.validators.cross_ref import CrossRefValidator
from docs_mcp.validators.diataxis import DiataxisValidator
from docs_mcp.validators.link_checker import LinkChecker
from docs_mcp.validators.style import StyleChecker


def _make_repo(tmp_path: Path) -> Path:
    """Build a tiny doc tree: 2 live files, 2 archived files."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "archive").mkdir()
    (tmp_path / "docs" / "GUIDE.md").write_text(
        "# Guide\n\nUse the API to do things.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "REFERENCE.md").write_text(
        "# Reference\n\n## Parameters\n\n- name: str\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "archive" / "OLD_PRD.md").write_text(
        "# Old PRD\n\n"
        + "This sentence will be utilized to leverage some jargon. " * 30
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "archive" / "OLD_API.md").write_text(
        "# Old API\n\n[broken](does_not_exist.md)\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path)


def test_matches_any_pattern_basic() -> None:
    assert matches_any_pattern("docs/archive/foo.md", ["docs/archive/**"])
    assert matches_any_pattern("packages/x/archive/foo.md", ["**/archive/**"])
    assert not matches_any_pattern("docs/GUIDE.md", ["docs/archive/**", "**/archive/**"])
    assert not matches_any_pattern("docs/archive/foo.md", [])
    assert not matches_any_pattern("", ["**/archive/**"])


def test_style_excludes_archive_by_default(repo: Path) -> None:
    checker = StyleChecker()
    archive = ["docs/archive/**", "**/archive/**"]

    excluded = checker.check_project(repo, archive_paths=archive)
    included = checker.check_project(repo, archive_paths=[])

    assert excluded.excluded_paths_count == 2
    assert excluded.total_files == 2
    assert included.excluded_paths_count == 0
    assert included.total_files == 4
    paths = {f.file_path for f in excluded.files}
    assert all("archive" not in p for p in paths)


def test_cross_refs_excludes_archive(repo: Path) -> None:
    validator = CrossRefValidator()
    archive = ["docs/archive/**", "**/archive/**"]

    excluded = validator.validate(repo, archive_paths=archive)
    included = validator.validate(repo, archive_paths=[])

    assert excluded.excluded_paths_count == 2
    assert excluded.broken_count == 0
    assert included.broken_count >= 1


def test_links_excludes_archive(repo: Path) -> None:
    checker = LinkChecker()
    archive = ["docs/archive/**", "**/archive/**"]

    excluded = checker.check(repo, archive_paths=archive)
    included = checker.check(repo, archive_paths=[])

    assert excluded.excluded_paths_count == 2
    assert len(excluded.broken_links) == 0
    assert any("archive" in b.source_file for b in included.broken_links)


def test_diataxis_excludes_archive(repo: Path) -> None:
    validator = DiataxisValidator()
    archive = ["docs/archive/**", "**/archive/**"]

    excluded = validator.validate(repo, archive_paths=archive)
    included = validator.validate(repo, archive_paths=[])

    assert excluded.excluded_paths_count == 2
    assert excluded.total_scanned == 2
    assert included.excluded_paths_count == 0
    assert included.total_scanned == 4


def test_archive_paths_empty_includes_everything(repo: Path) -> None:
    """When archive_paths=[], no filtering happens (backward-compatible)."""
    style = StyleChecker().check_project(repo, archive_paths=None)
    cross = CrossRefValidator().validate(repo, archive_paths=None)
    links = LinkChecker().check(repo, archive_paths=None)
    diataxis = DiataxisValidator().validate(repo, archive_paths=None)

    for r in (style, cross, links, diataxis):
        assert r.excluded_paths_count == 0

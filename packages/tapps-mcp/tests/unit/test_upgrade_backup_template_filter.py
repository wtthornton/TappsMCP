"""TAP-7433: ``_TEMPLATE_DIRS`` collection in ``collect_upgrade_targets`` must
filter to genuine template artifacts, mirroring how the adjacent ``_RULE_DIRS``
loop filters with ``.glob("*.md")`` / ``.glob("*.mdc")`` in the same function.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.upgrade_backup import (
    collect_upgrade_targets,
    create_pre_upgrade_backup,
)


def test_non_template_file_in_templates_dir_is_not_collected(tmp_path: Path) -> None:
    """A stray non-template file dropped in docs/templates/ must not be swept
    into the upgrade backup target list."""
    templates_dir = tmp_path / "docs" / "templates"
    templates_dir.mkdir(parents=True)
    (templates_dir / "one-pager.html").write_text("<html></html>", encoding="utf-8")
    junk = templates_dir / "notes.png"
    junk.write_bytes(b"\x89PNG\r\n")

    targets = collect_upgrade_targets(tmp_path)

    assert junk not in targets, (
        f"non-template file {junk} was collected as an upgrade backup target: {targets}"
    )


def test_genuine_template_file_is_still_collected(tmp_path: Path) -> None:
    """The real .html template artifact in docs/templates/ must survive the
    filter — this is the population the collected count below counts:
    genuine .html templates under docs/templates/."""
    templates_dir = tmp_path / "docs" / "templates"
    templates_dir.mkdir(parents=True)
    one_pager = templates_dir / "one-pager.html"
    one_pager.write_text("<html></html>", encoding="utf-8")
    (templates_dir / "junk.tmp").write_text("scratch", encoding="utf-8")

    targets = collect_upgrade_targets(tmp_path)
    template_targets = [t for t in targets if t.is_relative_to(templates_dir)]

    assert one_pager in targets
    assert len(template_targets) == 1, (
        f"expected exactly 1 genuine .html template under {templates_dir}, "
        f"got {len(template_targets)}: {template_targets}"
    )


def test_directory_named_html_under_templates_is_not_collected_and_backup_succeeds(
    tmp_path: Path,
) -> None:
    """A directory whose name happens to match the ``*.html`` glob (e.g. a
    ``partials.html/`` dir) must not be swept into the backup target list --
    ``Path.glob`` matches directories too, and ``shutil.copy2`` raises
    ``IsADirectoryError`` on one, aborting the whole upgrade."""
    templates_dir = tmp_path / "docs" / "templates"
    templates_dir.mkdir(parents=True)
    one_pager = templates_dir / "one-pager.html"
    one_pager.write_text("<html></html>", encoding="utf-8")
    weird_dir = templates_dir / "partials.html"
    weird_dir.mkdir()
    (weird_dir / "inner.txt").write_text("not a template", encoding="utf-8")

    targets = collect_upgrade_targets(tmp_path)
    template_targets = [t for t in targets if t.is_relative_to(templates_dir)]

    assert one_pager in targets
    assert weird_dir not in targets
    assert template_targets == [one_pager]

    result: dict[str, object] = {"errors": []}
    assert create_pre_upgrade_backup(tmp_path, result) is True
    assert result["errors"] == []

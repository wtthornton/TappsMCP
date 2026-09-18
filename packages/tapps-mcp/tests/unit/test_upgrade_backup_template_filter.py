"""TAP-7433: ``_TEMPLATE_DIRS`` collection in ``collect_upgrade_targets`` must
filter to genuine template artifacts, mirroring how the adjacent ``_RULE_DIRS``
loop filters with ``.glob("*.md")`` / ``.glob("*.mdc")`` in the same function.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.upgrade_backup import collect_upgrade_targets


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

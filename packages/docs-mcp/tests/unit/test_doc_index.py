"""Regression tests for docs_generate_doc_index (TAP-1276).

Covers two bug shapes from the v3.7.0 audit:

1. Sub-package writes producing path-doubled refs (e.g.
   ``packages/docs-mcp/docs/docs/INSTALLATION.md``).
2. Bare-filename ``output_path`` falling through to the legacy code path
   that emitted project-root-relative links from inside a nested directory.

Both are guarded by computing link targets via absolute-path arithmetic
against the resolved on-disk parent of the index file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from docs_mcp.generators.doc_index import DocIndexGenerator


def _build_subpackage_tree(tmp_path: Path) -> Path:
    """Mirror the sub-package shape from the bug report.

    tmp_path/
      README.md
      docs/
        INSTALLATION.md
        CONTRIBUTING.md
    """
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "INSTALLATION.md").write_text("# Install\n", encoding="utf-8")
    (docs / "CONTRIBUTING.md").write_text("# Contribute\n", encoding="utf-8")
    return tmp_path


def _broken_targets(content: str, index_dir: Path) -> list[str]:
    """Return any link targets in *content* that don't resolve from *index_dir*."""
    broken: list[str] = []
    for line in content.splitlines():
        m = re.search(r"\]\(([^)]+)\)", line)
        if not m:
            continue
        target = m.group(1)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (index_dir / target).resolve().exists():
            broken.append(target)
    return broken


@pytest.fixture
def subpackage(tmp_path: Path) -> Path:
    return _build_subpackage_tree(tmp_path)


def test_subpackage_with_docs_prefixed_output_emits_no_doubled_refs(
    subpackage: Path,
) -> None:
    """output_path='docs/INDEX.md' from a sub-package root must produce
    links resolvable from the index's actual on-disk parent (docs/)."""
    gen = DocIndexGenerator()
    result = gen.generate(subpackage, output_path="docs/INDEX.md")
    index_dir = (subpackage / "docs").resolve()

    bad = _broken_targets(result.content, index_dir)
    assert not bad, f"expected no broken refs, got: {bad}"
    # Specifically: no link should literally contain "docs/docs/"
    assert "docs/docs/" not in result.content


def test_bare_filename_output_path_resolves_correctly(subpackage: Path) -> None:
    """A bare filename like 'INDEX.md' was the legacy doubling shape.
    Should now resolve relative to project root, not produce broken refs."""
    gen = DocIndexGenerator()
    result = gen.generate(subpackage, output_path="INDEX.md")
    index_dir = subpackage.resolve()

    bad = _broken_targets(result.content, index_dir)
    assert not bad, f"expected no broken refs, got: {bad}"


def test_workspace_root_index_has_no_broken_refs(tmp_path: Path) -> None:
    """A typical workspace-root run with output_path='docs/INDEX.md'
    should emit links resolvable from docs/."""
    (tmp_path / "README.md").write_text("# r\n", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("# c\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("# a\n", encoding="utf-8")
    sub = docs / "guides"
    sub.mkdir()
    (sub / "QUICKSTART.md").write_text("# q\n", encoding="utf-8")

    gen = DocIndexGenerator()
    result = gen.generate(tmp_path, output_path="docs/INDEX.md")
    bad = _broken_targets(result.content, (tmp_path / "docs").resolve())
    assert not bad, f"workspace-root broken refs: {bad}"


def test_entries_deduped_by_path(tmp_path: Path) -> None:
    """A doc reachable via both root iterdir and recursive scan must not
    appear twice."""
    (tmp_path / "README.md").write_text("# r\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "GUIDE.md").write_text("# g\n", encoding="utf-8")

    gen = DocIndexGenerator()
    result = gen.generate(tmp_path, output_path="docs/INDEX.md")

    paths = [e.path for e in result.entries]
    assert len(paths) == len(set(paths)), f"duplicates in entries: {paths}"
    # Rendered content should not list any link twice either
    link_lines = [
        line for line in result.content.splitlines() if re.search(r"\]\([^)]+\)", line)
    ]
    assert len(link_lines) == len(set(link_lines))

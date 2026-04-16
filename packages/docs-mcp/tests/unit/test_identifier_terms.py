"""Tests for Python identifier term extraction (Epic 84.3)."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.validators.identifier_terms import collect_identifier_terms


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_empty_project(tmp_path: Path) -> None:
    assert collect_identifier_terms(tmp_path) == []


def test_collect_class_and_camel_parts(tmp_path: Path) -> None:
    _write(
        tmp_path / "mod.py",
        "class ZephyrBridgeWidget:\n    pass\n",
    )
    terms = collect_identifier_terms(tmp_path, max_files=10, max_terms=50)
    assert "ZephyrBridgeWidget" in terms
    assert "Zephyr" in terms
    assert "Bridge" in terms
    assert "Widget" in terms


def test_collect_long_def_name(tmp_path: Path) -> None:
    _write(
        tmp_path / "a.py",
        "def load_widget_registry():\n    pass\n",
    )
    terms = collect_identifier_terms(tmp_path, max_files=10, max_terms=20)
    assert "load_widget_registry" in terms


def test_skips_test_def_and_short_names(tmp_path: Path) -> None:
    _write(
        tmp_path / "t.py",
        "def test_foo():\n    pass\ndef run():\n    pass\nclass TestHelper:\n    pass\n",
    )
    terms = collect_identifier_terms(tmp_path, max_files=10, max_terms=50)
    assert "test_foo" not in terms
    assert "run" not in terms
    assert "TestHelper" in terms


def test_respects_max_terms(tmp_path: Path) -> None:
    lines = "\n".join(f"class ClassName{i:03d}:\n    pass\n" for i in range(30))
    _write(tmp_path / "many.py", lines)
    terms = collect_identifier_terms(tmp_path, max_files=5, max_terms=5)
    assert len(terms) == 5


def test_skips_venv_path(tmp_path: Path) -> None:
    _write(tmp_path / ".venv" / "lib" / "x.py", "class VenvSpam:\n    pass\n")
    _write(tmp_path / "good.py", "class GoodClass:\n    pass\n")
    terms = collect_identifier_terms(tmp_path, max_files=20, max_terms=20)
    assert "GoodClass" in terms
    assert "VenvSpam" not in terms

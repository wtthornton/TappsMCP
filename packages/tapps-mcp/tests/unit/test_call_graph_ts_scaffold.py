"""Tests for the TypeScript language-dispatch scaffold (TAP-4537).

Covers the S1 plumbing only: the ``language`` tag on ``SymbolRecord``, its
backward-compatible round-trip through ``index_from_dict``, and the suffix →
analyzer dispatch (Python → real ``analyze_file``, ``.ts``/``.tsx`` → placeholder).
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph import (
    _analyzer_for,
    _ts_file_to_module,
)
from tapps_mcp.project.call_graph_analyze import analyze_file
from tapps_mcp.project.call_graph_analyze_ts import analyze_file_ts
from tapps_mcp.project.call_graph_cache import index_from_dict, index_to_dict
from tapps_mcp.project.call_graph_types import (
    INDEX_VERSION,
    CallGraphIndex,
    SymbolRecord,
)


class TestSymbolLanguageTag:
    def test_default_language_is_python(self) -> None:
        rec = SymbolRecord(
            qualified_name="pkg.mod.fn",
            module="pkg.mod",
            file_path="pkg/mod.py",
            line=1,
            kind="function",
        )
        assert rec.language == "python"

    def test_language_round_trips_through_index_from_dict(self) -> None:
        index = CallGraphIndex(
            symbols=[
                SymbolRecord(
                    qualified_name="pkg.mod.fn",
                    module="pkg.mod",
                    file_path="pkg/mod.py",
                    line=1,
                    kind="function",
                    language="typescript",
                )
            ],
            fingerprint="deadbeef",
        )
        restored = index_from_dict(index_to_dict(index))
        assert restored.symbols[0].language == "typescript"

    def test_v2_cache_without_language_still_deserializes(self) -> None:
        # A stale v2 payload predates the ``language`` field; index_from_dict
        # must still construct a SymbolRecord (language defaults to "python").
        legacy = {
            "version": 2,
            "fingerprint": "old",
            "project_root": "/repo",
            "symbols": [
                {
                    "qualified_name": "pkg.mod.fn",
                    "module": "pkg.mod",
                    "file_path": "pkg/mod.py",
                    "line": 3,
                    "kind": "function",
                }
            ],
            "edges": [],
            "resolution_gaps": [],
            "parse_failures": [],
        }
        restored = index_from_dict(legacy)
        assert restored.version == 2  # stale — triggers rebuild via version mismatch
        assert restored.version != INDEX_VERSION
        assert restored.symbols[0].language == "python"


class TestSuffixDispatch:
    def test_py_routes_to_analyze_file(self) -> None:
        assert _analyzer_for(".py") is analyze_file

    def test_ts_routes_to_ts_analyzer(self) -> None:
        assert _analyzer_for(".ts") is analyze_file_ts

    def test_tsx_routes_to_ts_analyzer(self) -> None:
        assert _analyzer_for(".tsx") is analyze_file_ts

    def test_unknown_suffix_has_no_analyzer(self) -> None:
        assert _analyzer_for(".rb") is None


class TestTsFileToModule:
    def test_strips_src_prefix_and_suffix(self, tmp_path: Path) -> None:
        f = tmp_path / "src" / "components" / "Widget.ts"
        assert _ts_file_to_module(f, tmp_path) == "components/Widget"

    def test_tsx_suffix_dropped(self, tmp_path: Path) -> None:
        f = tmp_path / "src" / "App.tsx"
        assert _ts_file_to_module(f, tmp_path) == "App"

    def test_no_src_prefix_kept_verbatim(self, tmp_path: Path) -> None:
        f = tmp_path / "lib" / "util.ts"
        assert _ts_file_to_module(f, tmp_path) == "lib/util"

    def test_path_outside_root_returns_empty(self, tmp_path: Path) -> None:
        assert _ts_file_to_module(Path("/elsewhere/x.ts"), tmp_path) == ""

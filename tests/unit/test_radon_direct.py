"""Tests for tools.radon_direct — direct radon library analysis."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.tools.radon_direct import cc_direct, is_available, mi_direct


@pytest.fixture(autouse=True)
def _mock_radon_modules():
    """Inject mock radon modules into sys.modules for tests.

    radon may not be installed in the test venv; we inject mocks
    so that ``from radon.complexity import cc_visit`` works inside
    ``cc_direct`` when ``is_available`` is patched True.
    """
    radon_mod = types.ModuleType("radon")
    radon_complexity = types.ModuleType("radon.complexity")
    radon_metrics = types.ModuleType("radon.metrics")

    # Default implementations (overridden per-test via patch)
    radon_complexity.cc_visit = MagicMock(return_value=[])  # type: ignore[attr-defined]
    radon_complexity.SCORE = ["A", "A", "A", "B", "B", "C", "C", "D", "E", "F"]  # type: ignore[attr-defined]
    radon_metrics.mi_visit = MagicMock(return_value=50.0)  # type: ignore[attr-defined]

    originals = {
        "radon": sys.modules.get("radon"),
        "radon.complexity": sys.modules.get("radon.complexity"),
        "radon.metrics": sys.modules.get("radon.metrics"),
    }
    sys.modules["radon"] = radon_mod
    sys.modules["radon.complexity"] = radon_complexity
    sys.modules["radon.metrics"] = radon_metrics

    yield

    # Restore originals
    for key, val in originals.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val


class TestIsAvailable:
    def test_returns_bool(self):
        import tapps_mcp.tools.radon_direct as mod

        mod._RADON_AVAILABLE = None  # reset cache
        result = is_available()
        assert isinstance(result, bool)

    def test_caches_result(self):
        import tapps_mcp.tools.radon_direct as mod

        mod._RADON_AVAILABLE = None
        first = is_available()
        second = is_available()
        assert first == second

    @patch("importlib.util.find_spec", return_value=None)
    def test_returns_false_when_not_importable(self, _mock):
        import tapps_mcp.tools.radon_direct as mod

        mod._RADON_AVAILABLE = None
        assert is_available() is False


class TestCcDirect:
    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=False)
    def test_returns_empty_when_unavailable(self, _mock):
        assert cc_direct("test.py") == []

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source", return_value=None)
    def test_returns_empty_on_read_failure(self, _mock_read, _mock_avail):
        assert cc_direct("missing.py") == []

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source")
    def test_returns_entries_for_valid_code(self, mock_read, _mock_avail):
        mock_read.return_value = "def foo():\n    if True:\n        pass\n"
        mock_block = MagicMock()
        mock_block.name = "foo"
        mock_block.letter = "F"
        mock_block.complexity = 2
        mock_block.lineno = 1
        mock_block.endline = 3
        with (
            patch("radon.complexity.cc_visit", return_value=[mock_block]),
            patch("radon.complexity.SCORE", ["A", "A", "A", "B", "B"]),
        ):
            entries = cc_direct("test.py")
            assert isinstance(entries, list)
            assert len(entries) >= 1
            assert entries[0]["name"] == "foo"
            assert "complexity" in entries[0]

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source")
    def test_handles_syntax_error(self, mock_read, _mock_avail):
        mock_read.return_value = "def foo(\n"
        with patch("radon.complexity.cc_visit", side_effect=SyntaxError("bad")):
            result = cc_direct("bad.py")
            # Should return empty list on parse error, not raise
            assert isinstance(result, list)

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source")
    def test_entry_structure(self, mock_read, _mock_avail):
        mock_read.return_value = "def simple():\n    return 1\n"
        mock_block = MagicMock()
        mock_block.name = "simple"
        mock_block.letter = "F"
        mock_block.complexity = 1
        mock_block.lineno = 1
        mock_block.endline = 2
        with (
            patch("radon.complexity.cc_visit", return_value=[mock_block]),
            patch("radon.complexity.SCORE", ["A", "A", "A", "B", "B"]),
        ):
            entries = cc_direct("test.py")
            assert len(entries) >= 1
            for entry in entries:
                assert "name" in entry
                assert "complexity" in entry
                assert "type" in entry
                assert "lineno" in entry


class TestMiDirect:
    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=False)
    def test_returns_default_when_unavailable(self, _mock):
        assert mi_direct("test.py") == 50.0

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source", return_value=None)
    def test_returns_default_on_read_failure(self, _mock_read, _mock_avail):
        assert mi_direct("missing.py") == 50.0

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source")
    def test_returns_float_for_valid_code(self, mock_read, _mock_avail):
        mock_read.return_value = (
            '"""Module docstring."""\n\n'
            "def foo():\n"
            '    """Function docstring."""\n'
            "    return 1\n"
        )
        mi = mi_direct("test.py")
        assert isinstance(mi, float)
        assert 0.0 <= mi <= 100.0

    @patch("tapps_mcp.tools.radon_direct.is_available", return_value=True)
    @patch("tapps_mcp.tools.radon_direct._read_source")
    def test_handles_empty_file(self, mock_read, _mock_avail):
        mock_read.return_value = ""
        mi = mi_direct("empty.py")
        assert isinstance(mi, float)


class TestReadSource:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        from tapps_mcp.tools.radon_direct import _read_source

        content = _read_source(str(f))
        assert content == "x = 1\n"

    def test_returns_none_for_missing_file(self):
        from tapps_mcp.tools.radon_direct import _read_source

        assert _read_source("/nonexistent/path/file.py") is None

"""Tests for docs_mcp.validators.drift — drift detection."""

from __future__ import annotations

import os
import time
from pathlib import Path

from unittest.mock import MagicMock, patch

from docs_mcp.validators.drift import (
    DriftDetector,
    DriftItem,
    DriftReport,
    _build_doc_token_mtime_map,
    _build_doc_word_set,
    _find_doc_files,
    _find_python_files,
    _get_files_changed_since,
    _get_relevant_doc_mtime,
    _iso_from_mtime,
    _matches_any_pattern,
    _name_covered_by_prose,
    _name_covered_by_word_set,
    _qualify,
    _tokenize_name,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestDriftItemModel:
    """Test DriftItem Pydantic model."""

    def test_defaults(self) -> None:
        item = DriftItem(file_path="src/app.py", drift_type="added_undocumented")
        assert item.severity == "warning"
        assert item.description == ""
        assert item.code_last_modified == ""
        assert item.doc_last_modified == ""

    def test_full_construction(self) -> None:
        item = DriftItem(
            file_path="src/app.py",
            drift_type="modified_undocumented",
            severity="error",
            description="Public names not found in docs: run",
            code_last_modified="2026-03-01T12:00:00",
            doc_last_modified="2026-02-01T12:00:00",
        )
        assert item.drift_type == "modified_undocumented"
        assert item.severity == "error"

    def test_symbols_field_default_empty(self) -> None:
        item = DriftItem(file_path="src/app.py", drift_type="added_undocumented")
        assert item.symbols == []

    def test_symbols_field_stored(self) -> None:
        item = DriftItem(
            file_path="src/app.py",
            drift_type="added_undocumented",
            symbols=["foo", "bar", "baz"],
        )
        assert item.symbols == ["foo", "bar", "baz"]


class TestDriftReportModel:
    """Test DriftReport Pydantic model."""

    def test_defaults(self) -> None:
        report = DriftReport()
        assert report.total_items == 0
        assert report.items == []
        assert report.drift_score == 0.0
        assert report.drift_fraction == 0.0
        assert report.checked_files == 0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_iso_from_mtime(self) -> None:
        # Use a known timestamp
        ts = 1709290800.0  # 2024-03-01 in some timezone
        result = _iso_from_mtime(ts)
        assert "T" in result
        assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ
        assert result.endswith("Z")

    def test_find_python_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "mod.py").write_text("y = 2", encoding="utf-8")
        # Should skip __pycache__
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("z = 3", encoding="utf-8")

        files = _find_python_files(tmp_path)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "mod.py" in names
        assert "cached.py" not in names

    def test_find_python_files_nonexistent(self) -> None:
        result = _find_python_files(Path("/nonexistent/path"))
        assert result == []

    def test_find_doc_files_default(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide", encoding="utf-8")

        files = _find_doc_files(tmp_path)
        names = {f.name for f in files}
        assert "README.md" in names
        assert "guide.md" in names

    def test_find_doc_files_specific_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "api.md").write_text("# API", encoding="utf-8")

        files = _find_doc_files(tmp_path, doc_dirs=["docs"])
        names = {f.name for f in files}
        assert "api.md" in names
        # Root-level README should NOT be included when dirs are specified
        assert "README.md" not in names


class TestTokenizer:
    """Test the fuzzy name tokenizer."""

    def test_pascal_case_with_digits(self) -> None:
        tokens = _tokenize_name("BM25Scorer")
        # Full name + long-enough component words, case-insensitive variants
        assert "BM25Scorer" in tokens
        assert "bm25scorer" in tokens
        assert "BM25" in tokens
        assert "bm25" in tokens
        assert "Scorer" in tokens
        assert "scorer" in tokens

    def test_snake_case(self) -> None:
        tokens = _tokenize_name("get_user_id")
        assert "get_user_id" in tokens
        # "user" is 4 chars, kept; "get" and "id" are <4, dropped
        assert "user" in tokens
        assert "get" not in tokens
        assert "id" not in tokens

    def test_short_tokens_dropped(self) -> None:
        """TypeVar's 'T' component must not be considered a fuzzy match."""
        tokens = _tokenize_name("TypeVar")
        # The letter "T" must never appear as a match candidate — it would match
        # any stray capital T in prose.
        assert "T" not in tokens
        assert "Type" in tokens  # 4 chars, kept

    def test_single_char_name_still_present_but_not_matchable(self) -> None:
        # The full name is always included in the token set, but the downstream
        # matcher filters on length >= 4, so a 1-char name still won't match prose.
        tokens = _tokenize_name("X")
        assert "X" in tokens

    def test_flashrank_reranker(self) -> None:
        tokens = _tokenize_name("FlashRankReranker")
        assert "FlashRankReranker" in tokens
        assert "Flash" in tokens
        assert "Rank" in tokens
        assert "Reranker" in tokens


class TestNameCoveredByProse:
    """Test the prose-coverage fuzzy matcher."""

    def test_full_name_match(self) -> None:
        assert _name_covered_by_prose("BM25Scorer", "uses bm25scorer for ranking") is True

    def test_token_match(self) -> None:
        # "scorer" is a long-enough token of BM25Scorer
        assert _name_covered_by_prose("BM25Scorer", "our scorer is fast") is True

    def test_case_insensitive(self) -> None:
        assert _name_covered_by_prose("BM25Scorer", "the SCORER class") is True

    def test_no_match(self) -> None:
        assert _name_covered_by_prose("BM25Scorer", "unrelated prose") is False

    def test_empty_prose(self) -> None:
        assert _name_covered_by_prose("foo", "") is False

    def test_short_token_not_matched(self) -> None:
        # "id" is too short — the prose contains a stray "id" but we must not match.
        assert _name_covered_by_prose("id", "we need id") is False


class TestQualifyAndIgnorePatterns:
    """Test qualified-name building and glob matching."""

    def test_qualify_module(self) -> None:
        # src/ prefix is stripped so ignore_patterns work on logical package names.
        assert _qualify("src/pkg/mod.py", "Foo") == "pkg.mod.Foo"

    def test_qualify_init(self) -> None:
        assert _qualify("src/pkg/__init__.py", "Foo") == "pkg.Foo"

    def test_qualify_windows_slashes(self) -> None:
        assert _qualify("src\\pkg\\mod.py", "Foo") == "pkg.mod.Foo"

    def test_qualify_lib_prefix_stripped(self) -> None:
        assert _qualify("lib/pkg/mod.py", "Bar") == "pkg.mod.Bar"

    def test_qualify_no_prefix(self) -> None:
        # Paths without src/ or lib/ are unchanged.
        assert _qualify("mypkg/cli.py", "run") == "mypkg.cli.run"

    def test_matches_qualified_glob(self) -> None:
        assert _matches_any_pattern("mypkg.cli.main", ["mypkg.cli.*"]) is True

    def test_matches_bare_tail_glob(self) -> None:
        # Tail-based match so "_*" works even against fully-qualified names.
        assert _matches_any_pattern("mypkg.cli._private", ["_*"]) is True

    def test_no_match(self) -> None:
        assert _matches_any_pattern("mypkg.api.public", ["mypkg.cli.*"]) is False

    def test_src_layout_ignore_pattern_works(self, tmp_path: Path) -> None:
        """ignore_patterns on logical names must suppress src-layout symbols."""
        src = tmp_path / "src" / "mypkg"
        src.mkdir(parents=True)
        (src / "cli.py").write_text(
            "def subcommand_one() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        # Without ignore: drift detected.
        assert DriftDetector().check(tmp_path).total_items == 1
        # With logical package pattern (no src. prefix): suppressed.
        report = DriftDetector().check(tmp_path, ignore_patterns=["mypkg.cli.*"])
        assert report.total_items == 0


# ---------------------------------------------------------------------------
# Inverted word-set tests
# ---------------------------------------------------------------------------


class TestDocWordSet:
    """Test the inverted doc-word-set builder and O(1) coverage checker."""

    def test_build_empty(self, tmp_path: Path) -> None:
        ws = _build_doc_word_set([])
        assert ws == frozenset()

    def test_build_reads_all_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("hello world", encoding="utf-8")
        (tmp_path / "b.md").write_text("scorer reranker", encoding="utf-8")
        ws = _build_doc_word_set([tmp_path / "a.md", tmp_path / "b.md"])
        assert "hello" in ws
        assert "scorer" in ws

    def test_build_lowercased(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("SCORER PaymentProcessor", encoding="utf-8")
        ws = _build_doc_word_set([tmp_path / "a.md"])
        assert "scorer" in ws
        assert "paymentprocessor" in ws
        assert "SCORER" not in ws

    def test_build_skips_unreadable(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.md"
        ws = _build_doc_word_set([missing])
        assert ws == frozenset()

    def test_covered_by_word_set(self) -> None:
        ws = frozenset({"scorer", "reranker", "processor"})
        assert _name_covered_by_word_set("BM25Scorer", ws) is True
        assert _name_covered_by_word_set("FlashRankReranker", ws) is True
        assert _name_covered_by_word_set("UnrelatedThing", ws) is False

    def test_not_covered_empty_set(self) -> None:
        assert _name_covered_by_word_set("BM25Scorer", frozenset()) is False

    def test_short_token_not_matched(self) -> None:
        ws = frozenset({"id", "go"})
        assert _name_covered_by_word_set("id", ws) is False


class TestDocTokenMtimeMap:
    """Test the per-file token mtime map and relevant-mtime helper."""

    def test_build_empty(self) -> None:
        result = _build_doc_token_mtime_map([])
        assert result == {}

    def test_build_records_mtime(self, tmp_path: Path) -> None:
        fp = tmp_path / "doc.md"
        fp.write_text("scorer processor", encoding="utf-8")
        result = _build_doc_token_mtime_map([fp])
        assert "scorer" in result
        assert result["scorer"] == fp.stat().st_mtime

    def test_build_uses_max_mtime_for_shared_word(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("scorer", encoding="utf-8")
        b.write_text("scorer reranker", encoding="utf-8")
        import os
        os.utime(a, (1_000_000, 1_000_000))
        os.utime(b, (2_000_000, 2_000_000))
        result = _build_doc_token_mtime_map([a, b])
        assert result["scorer"] == 2_000_000.0
        assert result["reranker"] == 2_000_000.0

    def test_get_relevant_doc_mtime_finds_best(self) -> None:
        tmap = {"scorer": 1_500_000.0, "processor": 1_200_000.0}
        mtime = _get_relevant_doc_mtime(["BM25Scorer", "PaymentProcessor"], tmap)
        assert mtime == 1_500_000.0

    def test_get_relevant_doc_mtime_zero_when_no_match(self) -> None:
        tmap = {"unrelated": 9_999_999.0}
        assert _get_relevant_doc_mtime(["BM25Scorer"], tmap) == 0.0

    def test_per_file_mtime_reduces_false_positive_errors(
        self, tmp_path: Path
    ) -> None:
        """Touching an unrelated doc should not escalate severity for code with
        unrelated public names."""
        import os
        # Code file with an unrelated public name.
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\ndef zzzz_unrelated_func() -> None:\n    pass\n',
            encoding="utf-8",
        )
        # An unrelated doc touched very recently.
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n\nsome other content here.\n", encoding="utf-8")
        os.utime(readme, (2_000_000, 2_000_000))  # "future" doc
        # Make code file older than the doc.
        os.utime(tmp_path / "app.py", (1_000_000, 1_000_000))

        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 1
        # "zzzz_unrelated_func" is not mentioned in README, so no relevant doc mtime
        # → falls back to global doc_mtime → code (1M) < doc (2M) → severity=warning, not error
        assert report.items[0].severity == "warning"


class TestSinceFilter:
    """Test git-based incremental drift filtering via the `since` parameter."""

    def test_get_files_changed_since_ref(self, tmp_path: Path) -> None:
        """Successful git diff result returns the changed paths."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/app.py\nsrc/utils.py\n"
        with patch("docs_mcp.validators.drift.subprocess.run", return_value=mock_result):
            paths = _get_files_changed_since(tmp_path, "HEAD~1")
        assert paths == {"src/app.py", "src/utils.py"}

    def test_get_files_changed_since_falls_back_to_log(self, tmp_path: Path) -> None:
        """When git diff returns nothing, git log --since is tried."""
        diff_result = MagicMock()
        diff_result.returncode = 0
        diff_result.stdout = ""  # empty → try date fallback
        log_result = MagicMock()
        log_result.returncode = 0
        log_result.stdout = "src/changed.py\n\n"
        with patch(
            "docs_mcp.validators.drift.subprocess.run",
            side_effect=[diff_result, log_result],
        ):
            paths = _get_files_changed_since(tmp_path, "2026-04-01")
        assert paths == {"src/changed.py"}

    def test_get_files_changed_since_empty_on_error(self, tmp_path: Path) -> None:
        """Returns empty set when git is unavailable."""
        with patch("docs_mcp.validators.drift.subprocess.run", side_effect=FileNotFoundError):
            paths = _get_files_changed_since(tmp_path, "HEAD~1")
        assert paths == set()

    def test_detector_since_filters_to_changed_files(self, tmp_path: Path) -> None:
        """When `since` returns specific files, only those files are analyzed."""
        (tmp_path / "changed.py").write_text(
            '"""Mod."""\n\ndef changed_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "unchanged.py").write_text(
            '"""Mod."""\n\ndef unchanged_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        with patch(
            "docs_mcp.validators.drift._get_files_changed_since",
            return_value={"changed.py"},
        ):
            report = DriftDetector().check(
                tmp_path, since="HEAD~1", docstring_coverage_counts=False
            )

        assert report.checked_files == 1
        assert report.total_items == 1
        assert report.items[0].file_path == "changed.py"

    def test_detector_since_empty_result_scans_all(self, tmp_path: Path) -> None:
        """When git returns no changed files, all files are scanned."""
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\ndef some_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        with patch(
            "docs_mcp.validators.drift._get_files_changed_since",
            return_value=set(),
        ):
            report = DriftDetector().check(
                tmp_path, since="HEAD~1", docstring_coverage_counts=False
            )

        assert report.checked_files == 1  # fell back to scanning all


# ---------------------------------------------------------------------------
# DriftDetector tests
# ---------------------------------------------------------------------------


class TestDriftDetector:
    """Test DriftDetector.check()."""

    def test_empty_project(self, tmp_path: Path) -> None:
        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items == 0
        assert report.checked_files == 0
        assert report.drift_score == 0.0
        assert report.drift_fraction == 0.0

    def test_nonexistent_root(self) -> None:
        detector = DriftDetector()
        report = detector.check(Path("/nonexistent/path"))
        assert report.total_items == 0
        assert report.checked_files == 0

    def test_no_drift_when_docs_cover_api(self, tmp_path: Path) -> None:
        """When docs mention all public names, no drift should be detected."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""App module."""\n\ndef execute_job() -> None:\n    """Run the app."""\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nThe `execute_job` function starts the app.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items == 0
        # 0-100 scale — no drift means 0.
        assert report.drift_score == 0.0

    def test_drift_detected_for_undocumented_api(self, tmp_path: Path) -> None:
        """When public names are not in docs, drift should be detected."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""App module."""\n\n'
            "def calculate_total() -> float:\n"
            '    """Calculate total."""\n'
            "    return 0.0\n\n"
            "class PaymentProcessor:\n"
            '    """Process payments."""\n'
            "    pass\n",
            encoding="utf-8",
        )
        # README doesn't mention these names
        (tmp_path / "README.md").write_text(
            "# Project\n\nThis is a project.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items > 0
        # 0-100 scale: a drifted file in a single-file project scores 100.
        assert report.drift_score > 0.0
        assert report.drift_score <= 100.0
        assert 0.0 < report.drift_fraction <= 1.0
        assert report.checked_files > 0

    def test_drift_with_no_docs(self, tmp_path: Path) -> None:
        """When there are no doc files, all public APIs are undocumented."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""Module."""\n\ndef hello() -> str:\n    return "hi"\n',
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items > 0

    def test_empty_python_files_skipped(self, tmp_path: Path) -> None:
        """Empty Python files should not contribute to drift."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.checked_files == 0

    def test_drift_score_capped_at_100(self, tmp_path: Path) -> None:
        """Drift score should never exceed 100 on the new 0-100 scale."""
        # Create multiple source files with undocumented APIs
        src = tmp_path / "src"
        src.mkdir()
        for i in range(5):
            (src / f"mod{i}.py").write_text(
                f'"""Module {i}."""\n\ndef func_{i}() -> None:\n    pass\n',
                encoding="utf-8",
            )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.drift_score <= 100.0
        assert report.drift_fraction <= 1.0

    def test_drift_score_is_100_when_all_files_drift(self, tmp_path: Path) -> None:
        """Every checked file flagged => drift_score == 100.0."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text(
            '"""A."""\n\ndef opaque_symbol_one() -> None:\n    pass\n',
            encoding="utf-8",
        )
        (src / "b.py").write_text(
            '"""B."""\n\ndef opaque_symbol_two() -> None:\n    pass\n',
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.drift_score == 100.0
        assert report.drift_fraction == 1.0

    def test_severity_error_when_code_newer(self, tmp_path: Path) -> None:
        """When code is newer than docs, severity should be 'error'."""
        # Create doc file first
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n\nOld content.\n", encoding="utf-8")
        # Set doc mtime to past
        old_time = time.time() - 86400 * 30  # 30 days ago
        os.utime(readme, (old_time, old_time))

        # Create code file (will have current mtime)
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\ndef brand_new_capability() -> None:\n    pass\n',
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.items, "Expected drift items when code is newer than docs"
        # At least one item should have error severity
        severities = {item.severity for item in report.items}
        assert "error" in severities

    def test_source_files_pre_filter_limits_scan(self, tmp_path: Path) -> None:
        """source_files pre-filter should scope analysis to matching files only."""
        (tmp_path / "included.py").write_text(
            '"""Mod."""\n\ndef included_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "excluded.py").write_text(
            '"""Mod."""\n\ndef excluded_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        report = DriftDetector().check(
            tmp_path,
            source_files=["included.py"],
            docstring_coverage_counts=False,
        )
        assert report.checked_files == 1
        assert report.total_items == 1
        assert report.items[0].file_path == "included.py"

    def test_source_files_pre_filter_tail_match(self, tmp_path: Path) -> None:
        """Partial path suffix like 'mod.py' should match 'src/pkg/mod.py'."""
        src = tmp_path / "src" / "pkg"
        src.mkdir(parents=True)
        (src / "mod.py").write_text(
            '"""Mod."""\n\ndef deep_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (src / "other.py").write_text(
            '"""Other."""\n\ndef other_func() -> None:\n    pass\n', encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        report = DriftDetector().check(
            tmp_path,
            source_files=["mod.py"],
            docstring_coverage_counts=False,
        )
        assert report.checked_files == 1
        assert report.items[0].file_path.endswith("mod.py")

    def test_symbols_populated_on_drift_item(self, tmp_path: Path) -> None:
        """DriftItem.symbols must contain the full undocumented name list."""
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\n'
            "def alpha_func() -> None:\n    pass\n"
            "def beta_func() -> None:\n    pass\n"
            "def gamma_func() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 1
        item = report.items[0]
        assert set(item.symbols) == {"alpha_func", "beta_func", "gamma_func"}

    def test_symbols_not_truncated_beyond_five(self, tmp_path: Path) -> None:
        """symbols must include all names even when > 5 (description truncates to 5)."""
        funcs = "\n".join(
            f"def func_{i}() -> None:\n    pass" for i in range(8)
        )
        (tmp_path / "app.py").write_text(f'"""Mod."""\n\n{funcs}\n', encoding="utf-8")
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 1
        item = report.items[0]
        assert len(item.symbols) == 8
        assert "(+3 more)" in item.description  # description is still truncated

    def test_doc_dirs_filter(self, tmp_path: Path) -> None:
        """doc_dirs parameter should restrict which docs are searched."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""Module."""\n\ndef special_capability() -> None:\n    pass\n',
            encoding="utf-8",
        )

        # Root README mentions the function
        (tmp_path / "README.md").write_text(
            "# Project\n\nUse special_capability to do things.\n",
            encoding="utf-8",
        )

        # docs/ directory does NOT mention it
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "# Guide\n\nGeneral usage.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()

        # When searching all docs, no drift (README mentions it)
        report_all = detector.check(tmp_path)
        # Strict-mode check: docstring coverage is disabled so only prose counts.
        report_all_strict = detector.check(tmp_path, docstring_coverage_counts=False)
        assert report_all.total_items == 0
        assert report_all_strict.total_items == 0

        # When restricting to docs/ only, drift detected
        report_docs = detector.check(tmp_path, doc_dirs=["docs"])
        assert report_docs.total_items > 0


# ---------------------------------------------------------------------------
# New behavior: fuzzy matching, docstring coverage, ignore patterns
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    """Verify fuzzy / partial / case-insensitive matching on real source."""

    def test_camel_case_token_covered(self, tmp_path: Path) -> None:
        """Prose mentioning 'scorer' covers a ``BM25Scorer`` class."""
        (tmp_path / "app.py").write_text(
            "class BM25Scorer:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nOur scorer ranks results.\n",
            encoding="utf-8",
        )
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_snake_case_token_covered(self, tmp_path: Path) -> None:
        """Prose mentioning 'user' covers ``get_user_id``."""
        (tmp_path / "app.py").write_text(
            "def get_user_id() -> int:\n    return 0\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nReturns the user identifier.\n",
            encoding="utf-8",
        )
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            "class Reranker:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nWe use a RERANKER to re-order hits.\n",
            encoding="utf-8",
        )
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_short_name_still_flagged_when_absent(self, tmp_path: Path) -> None:
        """A 3-char public name with no matching prose should still drift."""
        (tmp_path / "app.py").write_text(
            "def foo() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 1


class TestDocstringCoverage:
    """Verify that module / class / function docstrings can cover symbol names."""

    def test_module_docstring_covers(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            '"""Module providing flashrank_reranker utilities."""\n\n'
            "class FlashRankReranker:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_class_docstring_covers(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\nclass PaymentProcessor:\n'
            '    """PaymentProcessor handles payments."""\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_function_docstring_covers(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\ndef calculate_invoice_total() -> float:\n'
            '    """calculate_invoice_total returns the total."""\n    return 0.0\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_strict_mode_ignores_docstrings(self, tmp_path: Path) -> None:
        """docstring_coverage_counts=False disables self-coverage."""
        (tmp_path / "app.py").write_text(
            '"""Mod."""\n\nclass PaymentProcessor:\n'
            '    """PaymentProcessor handles payments."""\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 1


class TestIgnorePatterns:
    """Verify the ignore_patterns kwarg and the 'defaults' sentinel."""

    def test_explicit_pattern_suppresses(self, tmp_path: Path) -> None:
        """A symbol matched by an ignore pattern never drifts."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cli.py").write_text(
            "def subcommand_one() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        # Without ignore: drift detected.
        assert DriftDetector().check(tmp_path).total_items == 1
        # With ignore: suppressed.
        report = DriftDetector().check(
            tmp_path,
            ignore_patterns=["mypkg.cli.*"],
        )
        assert report.total_items == 0

    def test_defaults_sentinel_suppresses_test_symbols(self, tmp_path: Path) -> None:
        """``ignore_patterns='defaults'`` hides ``test_*``-style names."""
        (tmp_path / "app.py").write_text(
            "def test_helper() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        # Off by default: drift detected.
        assert DriftDetector().check(tmp_path).total_items == 1
        # Opt in to defaults: suppressed.
        report = DriftDetector().check(tmp_path, ignore_patterns="defaults")
        assert report.total_items == 0

    def test_defaults_not_applied_implicitly(self, tmp_path: Path) -> None:
        """Backwards compat: ``ignore_patterns=None`` means no patterns applied."""
        (tmp_path / "app.py").write_text(
            "def test_helper() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path)
        assert report.total_items == 1


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------


class TestPublicConstants:
    """Verify that public module-level constants are included in drift detection."""

    def test_public_constant_detected_as_drifted(self, tmp_path: Path) -> None:
        """An all-caps constant not mentioned in docs should be flagged."""
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\nMAX_RETRIES: int = 3\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 1
        assert "MAX_RETRIES" in report.items[0].symbols

    def test_public_constant_covered_in_docs(self, tmp_path: Path) -> None:
        """A constant whose name appears in docs should not drift."""
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\nDEFAULT_TIMEOUT: int = 30\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nSet DEFAULT_TIMEOUT to control the timeout.\n",
            encoding="utf-8",
        )
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 0

    def test_test_constant_suppressed_by_defaults(self, tmp_path: Path) -> None:
        """TEST_* constants are suppressed when ignore_patterns='defaults'."""
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\nTEST_TIMEOUT: int = 5\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        # Without defaults: still flagged
        assert DriftDetector().check(tmp_path, docstring_coverage_counts=False).total_items == 1
        # With defaults: suppressed by TEST_* pattern
        report = DriftDetector().check(
            tmp_path,
            docstring_coverage_counts=False,
            ignore_patterns="defaults",
        )
        assert report.total_items == 0

    def test_fixture_constant_suppressed_by_defaults(self, tmp_path: Path) -> None:
        """*_FIXTURE constants are suppressed when ignore_patterns='defaults'."""
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\nUSER_FIXTURE: dict = {}\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        assert DriftDetector().check(tmp_path, docstring_coverage_counts=False).total_items == 1
        report = DriftDetector().check(
            tmp_path,
            docstring_coverage_counts=False,
            ignore_patterns="defaults",
        )
        assert report.total_items == 0

    def test_private_constant_not_detected(self, tmp_path: Path) -> None:
        """Constants starting with _ are private and should not drift."""
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\n_INTERNAL_LIMIT: int = 100\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        report = DriftDetector().check(tmp_path, docstring_coverage_counts=False)
        assert report.total_items == 0


# ---------------------------------------------------------------------------
# Score scale
# ---------------------------------------------------------------------------


class TestScoreScale:
    """Verify drift_score is 0-100 and drift_fraction preserves the raw ratio."""

    def test_partial_drift_score(self, tmp_path: Path) -> None:
        """Half of files drift -> drift_score == 50.0."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "documented.py").write_text(
            '"""Mod."""\n\ndef documented_feature() -> None:\n'
            '    """documented_feature is available."""\n    pass\n',
            encoding="utf-8",
        )
        (src / "undocumented.py").write_text(
            '"""Mod."""\n\ndef hidden_capability() -> None:\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee documented_feature.\n",
            encoding="utf-8",
        )

        report = DriftDetector().check(tmp_path)
        assert report.checked_files == 2
        assert report.total_items == 1
        assert report.drift_score == 50.0
        assert report.drift_fraction == 0.5

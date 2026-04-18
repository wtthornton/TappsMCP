"""Tests for docs_mcp.validators._scan_filters."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.validators._scan_filters import (
    BASELINE_EXCLUDE_DIRS,
    load_gitignore_patterns,
    should_exclude,
)

# ---------------------------------------------------------------------------
# load_gitignore_patterns
# ---------------------------------------------------------------------------


class TestLoadGitignorePatterns:
    """Test gitignore file loading."""

    def test_no_gitignore_returns_empty(self, tmp_path: Path) -> None:
        assert load_gitignore_patterns(tmp_path) == []

    def test_reads_patterns(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text(
            "*.log\n.venv-release-smoke/\nbuild\n",
            encoding="utf-8",
        )
        patterns = load_gitignore_patterns(tmp_path)
        assert "*.log" in patterns
        assert ".venv-release-smoke/" in patterns
        assert "build" in patterns

    def test_skips_blank_lines_and_comments(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text(
            "# comment\n\n*.log\n  \n# another\nfoo/\n",
            encoding="utf-8",
        )
        patterns = load_gitignore_patterns(tmp_path)
        assert patterns == ["*.log", "foo/"]

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text(
            "  *.tmp  \n\t.cache/\t\n",
            encoding="utf-8",
        )
        patterns = load_gitignore_patterns(tmp_path)
        assert patterns == ["*.tmp", ".cache/"]

    def test_negation_patterns_are_skipped(self, tmp_path: Path) -> None:
        """Negation (!) is not supported and should be dropped.

        Documented module-level non-support -- this test pins that
        contract so accidental "partial" support doesn't sneak in.
        """
        (tmp_path / ".gitignore").write_text(
            "*.log\n!keep.log\nbuild/\n",
            encoding="utf-8",
        )
        patterns = load_gitignore_patterns(tmp_path)
        assert "*.log" in patterns
        assert "build/" in patterns
        assert not any(p.startswith("!") for p in patterns)

    def test_gitignore_is_directory_returns_empty(self, tmp_path: Path) -> None:
        """If .gitignore is somehow a directory, return empty rather than error."""
        (tmp_path / ".gitignore").mkdir()
        assert load_gitignore_patterns(tmp_path) == []


# ---------------------------------------------------------------------------
# should_exclude -- baseline
# ---------------------------------------------------------------------------


class TestBaselineExclude:
    """Baseline dirs are always excluded regardless of other args."""

    def test_empty_rel_path_not_excluded(self) -> None:
        assert should_exclude("", [], []) is False
        assert should_exclude(".", [], []) is False

    def test_git_dir_excluded(self) -> None:
        assert should_exclude(".git/HEAD", [], []) is True
        assert should_exclude(".git", [], []) is True

    def test_venv_excluded(self) -> None:
        assert should_exclude(".venv/lib/x.py", [], []) is True
        assert should_exclude("venv/bin/python", [], []) is True

    def test_venv_glob_baseline(self) -> None:
        """``.venv-*`` baseline pattern catches release-smoke dirs."""
        assert should_exclude(".venv-release-smoke/lib/x.md", [], []) is True
        assert should_exclude(".venv-py312", [], []) is True

    def test_build_and_dist(self) -> None:
        assert should_exclude("build/out.txt", [], []) is True
        assert should_exclude("dist/wheel.whl", [], []) is True

    def test_cache_dirs(self) -> None:
        assert should_exclude("__pycache__/x.pyc", [], []) is True
        assert should_exclude(".mypy_cache/x", [], []) is True
        assert should_exclude(".pytest_cache/x", [], []) is True
        assert should_exclude(".ruff_cache/x", [], []) is True

    def test_node_modules(self) -> None:
        assert should_exclude("node_modules/foo/package.json", [], []) is True

    def test_nested_baseline_match(self) -> None:
        """Baseline match works even when name appears deep in the path."""
        assert should_exclude("packages/x/.venv/y.md", [], []) is True
        assert should_exclude("packages/x/node_modules/y", [], []) is True

    def test_normal_path_not_excluded(self) -> None:
        assert should_exclude("src/app.py", [], []) is False
        assert should_exclude("README.md", [], []) is False
        assert should_exclude("docs/guide.md", [], []) is False

    def test_all_baseline_names_listed(self) -> None:
        """Smoke test that the documented list matches the constant."""
        expected = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".venv-*",
            "dist",
            "build",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".eggs",
        }
        assert set(BASELINE_EXCLUDE_DIRS) == expected


# ---------------------------------------------------------------------------
# should_exclude -- pattern matching
# ---------------------------------------------------------------------------


class TestPatternMatching:
    """Gitignore-style pattern matching."""

    def test_simple_segment_match(self) -> None:
        assert should_exclude("foo/bar.md", ["foo"], []) is True
        assert should_exclude("pkg/foo/bar.md", ["foo"], []) is True
        assert should_exclude("baz/bar.md", ["foo"], []) is False

    def test_glob_segment_match(self) -> None:
        assert should_exclude("foo.log", ["*.log"], []) is True
        assert should_exclude("nested/foo.log", ["*.log"], []) is True
        assert should_exclude("foo.txt", ["*.log"], []) is False

    def test_trailing_slash_dir_only(self) -> None:
        """``foo/`` matches the dir AND everything beneath it."""
        assert should_exclude(".venv-release-smoke", [".venv-release-smoke/"], []) is True
        assert (
            should_exclude(
                ".venv-release-smoke/lib/x.md",
                [".venv-release-smoke/"],
                [],
            )
            is True
        )

    def test_leading_slash_anchored(self) -> None:
        """``/foo`` matches only at the root."""
        assert should_exclude("build", ["/build"], []) is True
        # An anchored pattern should still match nested children when
        # directory semantics apply.
        assert should_exclude("build/out.txt", ["/build/"], []) is True

    def test_leading_slash_does_not_match_nested(self) -> None:
        """``/foo`` should NOT match ``pkg/foo`` (anchoring)."""
        # Note baseline 'build' would match anyway -- use a custom name.
        assert should_exclude("pkg/special", ["/special"], []) is False
        assert should_exclude("special", ["/special"], []) is True

    def test_multi_segment_glob(self) -> None:
        assert should_exclude("vendored/pkg/x.md", ["vendored/**/*"], []) is True
        assert should_exclude("vendored/x.md", ["vendored/**/*"], []) is True

    def test_extra_exclude_applied(self) -> None:
        assert should_exclude("custom/x.md", [], ["custom/**"]) is True
        assert should_exclude("custom", [], ["custom/"]) is True

    def test_extra_combined_with_gitignore(self) -> None:
        """gitignore patterns + extras are both applied."""
        assert should_exclude("a/x.md", ["a/"], ["b/**"]) is True
        assert should_exclude("b/x.md", ["a/"], ["b/**"]) is True
        assert should_exclude("c/x.md", ["a/"], ["b/**"]) is False

    def test_empty_pattern_is_noop(self) -> None:
        assert should_exclude("src/app.py", [""], [""]) is False

    def test_windows_style_separator_normalized(self) -> None:
        """Backslash paths (Windows callers) are normalized to forward slashes."""
        assert should_exclude(".venv\\lib\\x.md", [], []) is True
        assert should_exclude("vendored\\pkg\\x", [], ["vendored/**"]) is True

    def test_gitignore_venv_smoke_scenario(self) -> None:
        """Regression: original bug scenario (.venv-release-smoke)."""
        patterns = [".venv-release-smoke/"]
        assert (
            should_exclude(
                ".venv-release-smoke/lib/README.md",
                patterns,
                [],
            )
            is True
        )
        assert (
            should_exclude(
                ".venv-release-smoke/site-packages/foo/README.md",
                patterns,
                [],
            )
            is True
        )
        assert should_exclude("README.md", patterns, []) is False

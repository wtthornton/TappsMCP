"""Unit tests for the language detector module.

Epic 56: Non-Python Language Scoring
Story 56.2: Language Detection & Routing
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.scoring.language_detector import (
    EXTENSION_TO_LANGUAGE,
    SUPPORTED_LANGUAGES,
    detect_language,
    get_canonical_language,
    get_languages_for_extensions,
    get_scorer,
    get_scorer_for_language,
    get_supported_extensions,
    is_language_supported,
)
from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.scoring.scorer_base import ScorerBase
from tapps_mcp.scoring.scorer_go import GoScorer
from tapps_mcp.scoring.scorer_rust import RustScorer
from tapps_mcp.scoring.scorer_typescript import TypeScriptScorer


class TestDetectLanguage:
    """Tests for detect_language function."""

    def test_detect_python(self) -> None:
        """Should detect Python files."""
        assert detect_language(Path("main.py")) == "python"
        assert detect_language(Path("types.pyi")) == "python"
        assert detect_language(Path("src/module/file.py")) == "python"

    def test_detect_typescript(self) -> None:
        """Should detect TypeScript files."""
        assert detect_language(Path("app.ts")) == "typescript"
        assert detect_language(Path("component.tsx")) == "typescript"

    def test_detect_javascript(self) -> None:
        """Should detect JavaScript files."""
        assert detect_language(Path("script.js")) == "javascript"
        assert detect_language(Path("component.jsx")) == "javascript"
        assert detect_language(Path("module.mjs")) == "javascript"
        assert detect_language(Path("config.cjs")) == "javascript"

    def test_detect_go(self) -> None:
        """Should detect Go files."""
        assert detect_language(Path("main.go")) == "go"
        assert detect_language(Path("server/handler.go")) == "go"

    def test_detect_rust(self) -> None:
        """Should detect Rust files."""
        assert detect_language(Path("lib.rs")) == "rust"
        assert detect_language(Path("src/main.rs")) == "rust"

    def test_detect_unknown(self) -> None:
        """Should return None for unknown extensions."""
        assert detect_language(Path("data.json")) is None
        assert detect_language(Path("style.css")) is None
        assert detect_language(Path("README.md")) is None
        assert detect_language(Path("config.yaml")) is None

    def test_detect_case_insensitive(self) -> None:
        """Should be case-insensitive."""
        assert detect_language(Path("file.PY")) == "python"
        assert detect_language(Path("file.Py")) == "python"
        assert detect_language(Path("file.TS")) == "typescript"
        assert detect_language(Path("file.Go")) == "go"
        assert detect_language(Path("file.RS")) == "rust"

    def test_detect_with_string_path(self) -> None:
        """Should accept string paths."""
        assert detect_language("main.py") == "python"
        assert detect_language("app.ts") == "typescript"


class TestGetCanonicalLanguage:
    """Tests for get_canonical_language function."""

    def test_javascript_alias(self) -> None:
        """JavaScript should alias to typescript."""
        assert get_canonical_language("javascript") == "typescript"

    def test_no_alias(self) -> None:
        """Languages without aliases should return themselves."""
        assert get_canonical_language("python") == "python"
        assert get_canonical_language("typescript") == "typescript"
        assert get_canonical_language("go") == "go"
        assert get_canonical_language("rust") == "rust"

    def test_unknown_language(self) -> None:
        """Unknown languages should return themselves."""
        assert get_canonical_language("java") == "java"
        assert get_canonical_language("ruby") == "ruby"


class TestIsLanguageSupported:
    """Tests for is_language_supported function."""

    def test_supported_languages(self) -> None:
        """Should return True for supported languages."""
        assert is_language_supported("python") is True
        assert is_language_supported("typescript") is True
        assert is_language_supported("go") is True
        assert is_language_supported("rust") is True

    def test_javascript_via_alias(self) -> None:
        """JavaScript should be supported via typescript alias."""
        assert is_language_supported("javascript") is True

    def test_unsupported_languages(self) -> None:
        """Should return False for unsupported languages."""
        assert is_language_supported("java") is False
        assert is_language_supported("ruby") is False
        assert is_language_supported("c++") is False


class TestGetScorer:
    """Tests for get_scorer function."""

    def test_get_python_scorer(self) -> None:
        """Should return CodeScorer for Python files."""
        scorer = get_scorer(Path("main.py"))
        assert scorer is not None
        assert isinstance(scorer, CodeScorer)
        assert scorer.language == "python"

    def test_get_typescript_scorer(self) -> None:
        """Should return TypeScriptScorer for TypeScript files."""
        scorer = get_scorer(Path("app.ts"))
        assert scorer is not None
        assert isinstance(scorer, TypeScriptScorer)
        assert scorer.language == "typescript"

    def test_get_typescript_scorer_for_tsx(self) -> None:
        """Should return TypeScriptScorer for TSX files."""
        scorer = get_scorer(Path("component.tsx"))
        assert scorer is not None
        assert isinstance(scorer, TypeScriptScorer)

    def test_get_typescript_scorer_for_javascript(self) -> None:
        """Should return TypeScriptScorer for JavaScript files (via alias)."""
        scorer = get_scorer(Path("script.js"))
        assert scorer is not None
        assert isinstance(scorer, TypeScriptScorer)

    def test_get_go_scorer(self) -> None:
        """Should return GoScorer for Go files."""
        scorer = get_scorer(Path("main.go"))
        assert scorer is not None
        assert isinstance(scorer, GoScorer)
        assert scorer.language == "go"

    def test_get_rust_scorer(self) -> None:
        """Should return RustScorer for Rust files."""
        scorer = get_scorer(Path("lib.rs"))
        assert scorer is not None
        assert isinstance(scorer, RustScorer)
        assert scorer.language == "rust"

    def test_get_scorer_unknown(self) -> None:
        """Should return None for unknown file types."""
        assert get_scorer(Path("data.json")) is None
        assert get_scorer(Path("style.css")) is None

    def test_get_scorer_with_string(self) -> None:
        """Should accept string paths."""
        scorer = get_scorer("main.py")
        assert scorer is not None
        assert isinstance(scorer, CodeScorer)


class TestGetScorerForLanguage:
    """Tests for get_scorer_for_language function."""

    def test_python(self) -> None:
        """Should return CodeScorer for python."""
        scorer = get_scorer_for_language("python")
        assert scorer is not None
        assert isinstance(scorer, CodeScorer)

    def test_typescript(self) -> None:
        """Should return TypeScriptScorer for typescript."""
        scorer = get_scorer_for_language("typescript")
        assert scorer is not None
        assert isinstance(scorer, TypeScriptScorer)

    def test_javascript_alias(self) -> None:
        """Should return TypeScriptScorer for javascript (via alias)."""
        scorer = get_scorer_for_language("javascript")
        assert scorer is not None
        assert isinstance(scorer, TypeScriptScorer)

    def test_go(self) -> None:
        """Should return GoScorer for go."""
        scorer = get_scorer_for_language("go")
        assert scorer is not None
        assert isinstance(scorer, GoScorer)

    def test_rust(self) -> None:
        """Should return RustScorer for rust."""
        scorer = get_scorer_for_language("rust")
        assert scorer is not None
        assert isinstance(scorer, RustScorer)

    def test_unsupported(self) -> None:
        """Should return None for unsupported languages."""
        assert get_scorer_for_language("java") is None
        assert get_scorer_for_language("ruby") is None


class TestGetSupportedExtensions:
    """Tests for get_supported_extensions function."""

    def test_returns_frozenset(self) -> None:
        """Should return a frozenset."""
        extensions = get_supported_extensions()
        assert isinstance(extensions, frozenset)

    def test_contains_expected_extensions(self) -> None:
        """Should contain all expected extensions."""
        extensions = get_supported_extensions()
        assert ".py" in extensions
        assert ".pyi" in extensions
        assert ".ts" in extensions
        assert ".tsx" in extensions
        assert ".js" in extensions
        assert ".jsx" in extensions
        assert ".go" in extensions
        assert ".rs" in extensions

    def test_matches_extension_map(self) -> None:
        """Should match the keys of EXTENSION_TO_LANGUAGE."""
        extensions = get_supported_extensions()
        assert extensions == frozenset(EXTENSION_TO_LANGUAGE.keys())


class TestGetLanguagesForExtensions:
    """Tests for get_languages_for_extensions function."""

    def test_single_extension(self) -> None:
        """Should return language for single extension."""
        result = get_languages_for_extensions([".py"])
        assert result == {"python"}

    def test_multiple_extensions_same_language(self) -> None:
        """Should deduplicate languages."""
        result = get_languages_for_extensions([".ts", ".tsx"])
        assert result == {"typescript"}

    def test_multiple_extensions_different_languages(self) -> None:
        """Should return multiple languages."""
        result = get_languages_for_extensions([".py", ".ts", ".go"])
        assert result == {"python", "typescript", "go"}

    def test_javascript_canonicalized(self) -> None:
        """JavaScript should be canonicalized to typescript."""
        result = get_languages_for_extensions([".js", ".jsx"])
        assert result == {"typescript"}

    def test_without_leading_dot(self) -> None:
        """Should accept extensions without leading dot."""
        result = get_languages_for_extensions(["py", "ts"])
        assert result == {"python", "typescript"}

    def test_unknown_extensions_ignored(self) -> None:
        """Should ignore unknown extensions."""
        result = get_languages_for_extensions([".py", ".json", ".yaml"])
        assert result == {"python"}

    def test_empty_list(self) -> None:
        """Should return empty set for empty list."""
        result = get_languages_for_extensions([])
        assert result == set()


class TestScorerInheritance:
    """Test that all scorers inherit from ScorerBase."""

    def test_code_scorer_inheritance(self) -> None:
        """CodeScorer should inherit from ScorerBase."""
        assert issubclass(CodeScorer, ScorerBase)

    def test_typescript_scorer_inheritance(self) -> None:
        """TypeScriptScorer should inherit from ScorerBase."""
        assert issubclass(TypeScriptScorer, ScorerBase)

    def test_go_scorer_inheritance(self) -> None:
        """GoScorer should inherit from ScorerBase."""
        assert issubclass(GoScorer, ScorerBase)

    def test_rust_scorer_inheritance(self) -> None:
        """RustScorer should inherit from ScorerBase."""
        assert issubclass(RustScorer, ScorerBase)


class TestScorerCanHandle:
    """Test that each scorer's can_handle matches its extensions."""

    def test_code_scorer_can_handle(self) -> None:
        """CodeScorer should handle Python files."""
        scorer = CodeScorer()
        assert scorer.can_handle(Path("main.py")) is True
        assert scorer.can_handle(Path("types.pyi")) is True
        assert scorer.can_handle(Path("app.ts")) is False

    def test_typescript_scorer_can_handle(self) -> None:
        """TypeScriptScorer should handle TypeScript and JavaScript files."""
        scorer = TypeScriptScorer()
        assert scorer.can_handle(Path("app.ts")) is True
        assert scorer.can_handle(Path("component.tsx")) is True
        assert scorer.can_handle(Path("script.js")) is True
        assert scorer.can_handle(Path("main.py")) is False

    def test_go_scorer_can_handle(self) -> None:
        """GoScorer should handle Go files."""
        scorer = GoScorer()
        assert scorer.can_handle(Path("main.go")) is True
        assert scorer.can_handle(Path("main.py")) is False

    def test_rust_scorer_can_handle(self) -> None:
        """RustScorer should handle Rust files."""
        scorer = RustScorer()
        assert scorer.can_handle(Path("lib.rs")) is True
        assert scorer.can_handle(Path("main.py")) is False


class TestSupportedLanguagesConstant:
    """Tests for the SUPPORTED_LANGUAGES constant."""

    def test_is_frozenset(self) -> None:
        """Should be a frozenset."""
        assert isinstance(SUPPORTED_LANGUAGES, frozenset)

    def test_contains_expected_languages(self) -> None:
        """Should contain all expected languages."""
        assert "python" in SUPPORTED_LANGUAGES
        assert "typescript" in SUPPORTED_LANGUAGES
        assert "go" in SUPPORTED_LANGUAGES
        assert "rust" in SUPPORTED_LANGUAGES

    def test_count(self) -> None:
        """Should have 4 supported languages."""
        assert len(SUPPORTED_LANGUAGES) == 4

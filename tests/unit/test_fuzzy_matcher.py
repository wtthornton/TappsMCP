"""Unit tests for knowledge/fuzzy_matcher.py — multi-signal fuzzy matching."""

from __future__ import annotations

import pytest

from tapps_mcp.knowledge.fuzzy_matcher import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    combined_score,
    confidence_band,
    did_you_mean,
    edit_distance,
    edit_distance_similarity,
    fuzzy_match_library,
    fuzzy_match_topic,
    lcs_length,
    lcs_similarity,
    multi_signal_score,
    resolve_alias,
    token_overlap_score,
)


class TestLCSLength:
    @pytest.mark.parametrize("a,b,expected", [
        ("abc", "abc", 3),
        ("", "abc", 0),
        ("abc", "", 0),
        ("", "", 0),
        ("xyz", "abc", 0),
        ("ace", "abcde", 3),
        ("fastapi", "flask", 3),
        ("abc", "cba", 1),
    ], ids=["identical", "empty-a", "empty-b", "both-empty",
            "no-common", "subsequence", "partial", "reversed"])
    def test_lcs_length(self, a, b, expected):
        assert lcs_length(a, b) == expected


class TestLCSSimilarity:
    @pytest.mark.parametrize("a,b,expected", [
        ("fastapi", "fastapi", 1.0),
        ("", "", 1.0),
        ("abc", "", 0.0),
        ("FastAPI", "fastapi", 1.0),
    ], ids=["identical", "both-empty", "one-empty", "case-insensitive"])
    def test_exact_values(self, a, b, expected):
        assert lcs_similarity(a, b) == expected

    def test_range(self):
        score = lcs_similarity("fast", "fastapi")
        assert 0.0 < score < 1.0

    def test_symmetric(self):
        assert lcs_similarity("abc", "def") == lcs_similarity("def", "abc")


class TestResolveAlias:
    def test_known_aliases(self):
        assert resolve_alias("pg") == "postgres"
        assert resolve_alias("tf") == "tensorflow"
        assert resolve_alias("np") == "numpy"

    def test_unknown_passes_through(self):
        assert resolve_alias("fastapi") == "fastapi"

    def test_normalisation(self):
        """Strips whitespace and is case-insensitive."""
        assert resolve_alias("  PG  ") == "postgres"
        assert resolve_alias("") == ""

    def test_all_known_aliases(self):
        from tapps_mcp.knowledge.fuzzy_matcher import LIBRARY_ALIASES
        for alias, canonical in LIBRARY_ALIASES.items():
            assert resolve_alias(alias) == canonical


class TestEditDistance:
    @pytest.mark.parametrize("a,b,expected", [
        ("abc", "abc", 0),
        ("abc", "adc", 1),
        ("abc", "abcd", 1),
        ("abcd", "abc", 1),
        ("", "abc", 3),
        ("abc", "", 3),
        ("", "", 0),
        ("fastaip", "fastapi", 2),
        ("abc", "xyz", 3),
        ("ab", "ba", 2),
    ], ids=["identical", "substitution", "insertion", "deletion",
            "empty-a", "empty-b", "both-empty", "typo",
            "completely-different", "transposition"])
    def test_edit_distance(self, a, b, expected):
        assert edit_distance(a, b) == expected


class TestEditDistanceSimilarity:
    @pytest.mark.parametrize("a,b,expected", [
        ("fastapi", "fastapi", 1.0),
        ("", "", 1.0),
        ("abc", "", 0.0),
        ("FastAPI", "fastapi", 1.0),
        ("abc", "xyz", 0.0),
    ], ids=["identical", "both-empty", "one-empty", "case-insensitive", "different"])
    def test_exact_values(self, a, b, expected):
        assert edit_distance_similarity(a, b) == expected

    def test_typo_scores_high(self):
        assert edit_distance_similarity("fastaip", "fastapi") > 0.6


class TestTokenOverlap:
    @pytest.mark.parametrize("a,b,expected", [
        ("scikit-learn", "scikit-learn", 1.0),
        ("fastapi", "django", 0.0),
        ("", "something", 0.0),
        ("", "", 0.0),
        ("my-lib", "my-other", 0.5),
        ("my_lib", "my_other", 0.5),
        ("my lib", "my other", 0.5),
    ], ids=["identical", "no-overlap", "empty-first", "both-empty",
            "hyphen-split", "underscore-split", "space-split"])
    def test_token_overlap(self, a, b, expected):
        assert token_overlap_score(a, b) == expected

    def test_partial_overlap(self):
        score = token_overlap_score("scikit-learn", "scikit-image")
        assert 0.0 < score < 1.0


class TestMultiSignalScore:
    def test_identical(self):
        assert multi_signal_score("fastapi", "fastapi") == 1.0

    def test_range(self):
        score = multi_signal_score("fast", "fastapi")
        assert 0.0 < score < 1.0

    def test_captures_typo(self):
        multi = multi_signal_score("fastaip", "fastapi")
        assert multi > 0.5
        assert edit_distance_similarity("fastaip", "fastapi") > 0.6

    def test_completely_different(self):
        assert multi_signal_score("abc", "xyz") == 0.0

    def test_weights_sum_to_one(self):
        """When all signals return 1.0, total is 1.0."""
        assert multi_signal_score("test", "test") == 1.0


class TestConfidenceBand:
    @pytest.mark.parametrize("score,expected", [
        (0.9, "high"),
        (CONFIDENCE_HIGH, "high"),
        (CONFIDENCE_HIGH - 0.01, "medium"),
        (0.7, "medium"),
        (CONFIDENCE_MEDIUM, "medium"),
        (CONFIDENCE_MEDIUM - 0.01, "low"),
        (0.3, "low"),
        (0.0, "low"),
        (1.0, "high"),
    ], ids=["high", "boundary-high", "just-below-high", "medium",
            "boundary-medium", "just-below-medium", "low", "zero", "one"])
    def test_confidence_band(self, score, expected):
        assert confidence_band(score) == expected


class TestFuzzyMatchLibrary:
    def test_exact_match(self):
        results = fuzzy_match_library("fastapi", ["fastapi", "flask", "django"])
        assert results[0].library == "fastapi"
        assert results[0].score == 1.0
        assert results[0].match_type == "exact"

    def test_similar_match(self):
        results = fuzzy_match_library("fast", ["fastapi", "flask", "django"], threshold=0.4)
        assert results[0].library == "fastapi"

    def test_no_match_below_threshold(self):
        assert fuzzy_match_library("zzz", ["fastapi", "flask"], threshold=0.8) == []

    def test_empty_libraries(self):
        assert fuzzy_match_library("fastapi", []) == []

    def test_max_results(self):
        libs = [f"lib{i}" for i in range(20)]
        assert len(fuzzy_match_library("lib", libs, threshold=0.1, max_results=3)) <= 3

    def test_sorted_by_score(self):
        results = fuzzy_match_library("fast", ["fastapi", "flask", "fast-jsonapi"], threshold=0.3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_alias_resolution(self):
        results = fuzzy_match_library("np", ["numpy", "scipy"], threshold=0.3)
        assert any(r.library == "numpy" for r in results)

    def test_case_insensitive_exact_match(self):
        results = fuzzy_match_library("fastapi", ["FastAPI"])
        assert results[0].score == 1.0

    def test_prefix_match_bonus(self):
        results = fuzzy_match_library("fast", ["fastapi", "django"], threshold=0.3)
        assert next(r for r in results if r.library == "fastapi").score > 0.5

    def test_threshold_zero_matches_all(self):
        assert len(fuzzy_match_library("q", ["abc", "xyz", "mno"], threshold=0.0)) == 3

    def test_threshold_one_only_exact(self):
        results = fuzzy_match_library("fastapi", ["fastapi", "flask"], threshold=1.0)
        assert len(results) == 1 and results[0].library == "fastapi"

    def test_fuzzy_match_type_includes_band(self):
        results = fuzzy_match_library("fast", ["fastapi", "flask"], threshold=0.3)
        for r in results:
            if r.match_type != "exact":
                assert r.match_type.startswith("fuzzy_")


class TestFuzzyMatchTopic:
    def test_match(self):
        result = fuzzy_match_topic("route", ["routing", "middleware", "testing"])
        assert result is not None and result.topic == "routing"

    def test_no_match(self):
        assert fuzzy_match_topic("zzzzz", ["routing", "middleware"], threshold=0.9) is None

    def test_empty_topics(self):
        assert fuzzy_match_topic("test", []) is None

    def test_exact_topic_match(self):
        result = fuzzy_match_topic("routing", ["routing", "middleware"])
        assert result is not None and result.score == 1.0

    def test_result_fields(self):
        result = fuzzy_match_topic("route", ["routing"], threshold=0.3)
        assert result is not None
        assert result.match_type == "topic"
        assert result.library == ""


class TestCombinedScore:
    @pytest.mark.parametrize("lib,topic,weights,expected", [
        (1.0, 0.5, {}, 0.8),                                        # default weights
        (0.8, 0.6, {"library_weight": 0.7, "topic_weight": 0.3}, 0.74),
        (0.0, 0.0, {}, 0.0),
        (1.0, 1.0, {}, 1.0),
    ], ids=["default-weights", "custom-weights", "zeros", "maxed"])
    def test_combined_score(self, lib, topic, weights, expected):
        assert abs(combined_score(lib, topic, **weights) - expected) < 0.001


class TestDidYouMean:
    def test_returns_suggestions_for_typo(self):
        suggestions = did_you_mean("fastaip", ["fastapi", "flask", "django", "pytorch"])
        assert "fastapi" in suggestions

    def test_no_suggestions_for_gibberish(self):
        assert did_you_mean("zzzzzzzz", ["fastapi", "flask"], threshold=0.8) == []

    def test_max_suggestions(self):
        assert len(did_you_mean("lib", [f"lib{i}" for i in range(20)], max_suggestions=2)) <= 2

    def test_excludes_high_confidence_matches(self):
        """Exact match → high confidence → excluded from suggestions."""
        assert "fastapi" not in did_you_mean("fastapi", ["fastapi"])

    def test_empty_libraries(self):
        assert did_you_mean("test", []) == []


class TestProjectManifestPrior:
    def test_project_library_boosted(self):
        libs = ["fastapi", "flask", "django"]
        results_before = fuzzy_match_library("fas", libs, threshold=0.3)
        results_after = fuzzy_match_library("fas", libs, threshold=0.3, project_libraries=["flask"])
        flask_before = next((r.score for r in results_before if r.library == "flask"), 0.0)
        flask_after = next((r.score for r in results_after if r.library == "flask"), 0.0)
        assert flask_after >= flask_before

    def test_empty_project_libraries_same_as_none(self):
        libs = ["fastapi", "flask"]
        r1 = fuzzy_match_library("fast", libs, threshold=0.3, project_libraries=None)
        r2 = fuzzy_match_library("fast", libs, threshold=0.3, project_libraries=[])
        assert len(r1) == len(r2)

    def test_project_library_case_insensitive(self):
        results = fuzzy_match_library("fast", ["FastAPI"], threshold=0.3, project_libraries=["fastapi"])
        results_no = fuzzy_match_library("fast", ["FastAPI"], threshold=0.3)
        assert results[0].score >= results_no[0].score

"""Unit tests for knowledge/fuzzy_matcher.py — LCS-based fuzzy matching."""

from __future__ import annotations

from tapps_mcp.knowledge.fuzzy_matcher import (
    combined_score,
    fuzzy_match_library,
    fuzzy_match_topic,
    lcs_length,
    lcs_similarity,
    resolve_alias,
)


class TestLCSLength:
    def test_identical(self):
        assert lcs_length("abc", "abc") == 3

    def test_empty(self):
        assert lcs_length("", "abc") == 0
        assert lcs_length("abc", "") == 0

    def test_no_common(self):
        assert lcs_length("xyz", "abc") == 0

    def test_subsequence(self):
        assert lcs_length("ace", "abcde") == 3

    def test_partial(self):
        assert lcs_length("fastapi", "flask") == 3  # "fas"


class TestLCSSimilarity:
    def test_identical(self):
        assert lcs_similarity("fastapi", "fastapi") == 1.0

    def test_empty_both(self):
        assert lcs_similarity("", "") == 1.0

    def test_one_empty(self):
        assert lcs_similarity("abc", "") == 0.0

    def test_case_insensitive(self):
        assert lcs_similarity("FastAPI", "fastapi") == 1.0

    def test_range(self):
        score = lcs_similarity("fast", "fastapi")
        assert 0.0 < score < 1.0


class TestResolveAlias:
    def test_known_alias(self):
        assert resolve_alias("pg") == "postgres"
        assert resolve_alias("tf") == "tensorflow"
        assert resolve_alias("np") == "numpy"

    def test_unknown_passes_through(self):
        assert resolve_alias("fastapi") == "fastapi"

    def test_strips_whitespace(self):
        assert resolve_alias("  fastapi  ") == "fastapi"

    def test_case_insensitive(self):
        assert resolve_alias("PG") == "postgres"


class TestFuzzyMatchLibrary:
    def test_exact_match(self):
        libs = ["fastapi", "flask", "django"]
        results = fuzzy_match_library("fastapi", libs)
        assert len(results) > 0
        assert results[0].library == "fastapi"
        assert results[0].score == 1.0

    def test_similar_match(self):
        libs = ["fastapi", "flask", "django"]
        results = fuzzy_match_library("fast", libs, threshold=0.4)
        assert len(results) > 0
        assert results[0].library == "fastapi"

    def test_no_match_below_threshold(self):
        libs = ["fastapi", "flask", "django"]
        results = fuzzy_match_library("zzz", libs, threshold=0.8)
        assert len(results) == 0

    def test_max_results(self):
        libs = [f"lib{i}" for i in range(20)]
        results = fuzzy_match_library("lib", libs, threshold=0.1, max_results=3)
        assert len(results) <= 3

    def test_sorted_by_score(self):
        libs = ["fastapi", "flask", "fast-jsonapi"]
        results = fuzzy_match_library("fast", libs, threshold=0.3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_alias_resolution(self):
        libs = ["numpy", "scipy"]
        results = fuzzy_match_library("np", libs, threshold=0.3)
        assert any(r.library == "numpy" for r in results)


class TestFuzzyMatchTopic:
    def test_match(self):
        topics = ["routing", "middleware", "testing"]
        result = fuzzy_match_topic("route", topics)
        assert result is not None
        assert result.topic == "routing"

    def test_no_match(self):
        topics = ["routing", "middleware"]
        result = fuzzy_match_topic("zzzzz", topics, threshold=0.9)
        assert result is None

    def test_empty_topics(self):
        assert fuzzy_match_topic("test", []) is None


class TestCombinedScore:
    def test_weighted(self):
        score = combined_score(1.0, 0.5)
        expected = 1.0 * 0.6 + 0.5 * 0.4
        assert abs(score - expected) < 0.001

    def test_custom_weights(self):
        score = combined_score(0.8, 0.6, library_weight=0.7, topic_weight=0.3)
        expected = 0.8 * 0.7 + 0.6 * 0.3
        assert abs(score - expected) < 0.001

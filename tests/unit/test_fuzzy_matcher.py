"""Unit tests for knowledge/fuzzy_matcher.py — multi-signal fuzzy matching."""

from __future__ import annotations

from tapps_mcp.knowledge.fuzzy_matcher import (
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


class TestEditDistance:
    def test_identical(self):
        assert edit_distance("abc", "abc") == 0

    def test_one_change(self):
        assert edit_distance("abc", "adc") == 1

    def test_insertion(self):
        assert edit_distance("abc", "abcd") == 1

    def test_deletion(self):
        assert edit_distance("abcd", "abc") == 1

    def test_empty(self):
        assert edit_distance("", "abc") == 3
        assert edit_distance("abc", "") == 3

    def test_typo_fastapi(self):
        assert edit_distance("fastaip", "fastapi") == 2


class TestEditDistanceSimilarity:
    def test_identical(self):
        assert edit_distance_similarity("fastapi", "fastapi") == 1.0

    def test_empty_both(self):
        assert edit_distance_similarity("", "") == 1.0

    def test_one_empty(self):
        assert edit_distance_similarity("abc", "") == 0.0

    def test_typo_scores_high(self):
        score = edit_distance_similarity("fastaip", "fastapi")
        assert score > 0.6


class TestTokenOverlap:
    def test_identical(self):
        assert token_overlap_score("scikit-learn", "scikit-learn") == 1.0

    def test_partial_overlap(self):
        score = token_overlap_score("scikit-learn", "scikit-image")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        assert token_overlap_score("fastapi", "django") == 0.0


class TestMultiSignalScore:
    def test_identical(self):
        assert multi_signal_score("fastapi", "fastapi") == 1.0

    def test_range(self):
        score = multi_signal_score("fast", "fastapi")
        assert 0.0 < score < 1.0

    def test_multi_signal_captures_typo(self):
        # Multi-signal should produce a reasonable score for a transposition typo.
        multi = multi_signal_score("fastaip", "fastapi")
        # Should still detect it as a plausible match (above 0.5).
        assert multi > 0.5
        # Edit distance component should contribute positively.
        ed = edit_distance_similarity("fastaip", "fastapi")
        assert ed > 0.6


class TestConfidenceBand:
    def test_high(self):
        assert confidence_band(0.9) == "high"

    def test_medium(self):
        assert confidence_band(0.7) == "medium"

    def test_low(self):
        assert confidence_band(0.3) == "low"


class TestDidYouMean:
    def test_returns_suggestions_for_typo(self):
        libs = ["fastapi", "flask", "django", "pytorch"]
        suggestions = did_you_mean("fastaip", libs)
        assert "fastapi" in suggestions

    def test_no_suggestions_for_gibberish(self):
        libs = ["fastapi", "flask", "django"]
        suggestions = did_you_mean("zzzzzzzz", libs, threshold=0.8)
        assert suggestions == []

    def test_max_suggestions(self):
        libs = [f"lib{i}" for i in range(20)]
        suggestions = did_you_mean("lib", libs, max_suggestions=2)
        assert len(suggestions) <= 2


class TestProjectManifestPrior:
    def test_project_library_boosted(self):
        libs = ["fastapi", "flask", "django"]
        # Without project prior.
        results_no_prior = fuzzy_match_library("fas", libs, threshold=0.3)
        # With project prior that boosts flask.
        results_with_prior = fuzzy_match_library(
            "fas", libs, threshold=0.3, project_libraries=["flask"]
        )
        # Flask should score higher with the project prior.
        flask_score_before = next((r.score for r in results_no_prior if r.library == "flask"), 0.0)
        flask_score_after = next((r.score for r in results_with_prior if r.library == "flask"), 0.0)
        assert flask_score_after >= flask_score_before

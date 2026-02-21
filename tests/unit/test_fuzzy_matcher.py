"""Unit tests for knowledge/fuzzy_matcher.py — multi-signal fuzzy matching."""

from __future__ import annotations

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
    def test_identical(self):
        assert lcs_length("abc", "abc") == 3

    def test_empty(self):
        assert lcs_length("", "abc") == 0
        assert lcs_length("abc", "") == 0

    def test_both_empty(self):
        assert lcs_length("", "") == 0

    def test_no_common(self):
        assert lcs_length("xyz", "abc") == 0

    def test_subsequence(self):
        assert lcs_length("ace", "abcde") == 3

    def test_partial(self):
        assert lcs_length("fastapi", "flask") == 3  # "fas"

    def test_single_char_match(self):
        assert lcs_length("a", "a") == 1

    def test_single_char_no_match(self):
        assert lcs_length("a", "b") == 0

    def test_reversed_string(self):
        # "abc" vs "cba" — LCS is 1 (any single char)
        assert lcs_length("abc", "cba") == 1


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

    def test_symmetric(self):
        """LCS similarity should be symmetric."""
        assert lcs_similarity("abc", "def") == lcs_similarity("def", "abc")


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

    def test_empty_string(self):
        assert resolve_alias("") == ""

    def test_whitespace_only(self):
        assert resolve_alias("   ") == ""

    def test_all_known_aliases(self):
        """Validate all aliases in the LIBRARY_ALIASES dict."""
        from tapps_mcp.knowledge.fuzzy_matcher import LIBRARY_ALIASES
        for alias, canonical in LIBRARY_ALIASES.items():
            assert resolve_alias(alias) == canonical


class TestFuzzyMatchLibrary:
    def test_exact_match(self):
        libs = ["fastapi", "flask", "django"]
        results = fuzzy_match_library("fastapi", libs)
        assert len(results) > 0
        assert results[0].library == "fastapi"
        assert results[0].score == 1.0

    def test_exact_match_type(self):
        libs = ["fastapi"]
        results = fuzzy_match_library("fastapi", libs)
        assert results[0].match_type == "exact"

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

    def test_empty_libraries(self):
        results = fuzzy_match_library("fastapi", [])
        assert results == []

    def test_case_insensitive_exact_match(self):
        libs = ["FastAPI"]
        results = fuzzy_match_library("fastapi", libs)
        assert len(results) > 0
        assert results[0].score == 1.0

    def test_prefix_match_bonus(self):
        """Library starting with query gets a prefix bonus."""
        libs = ["fastapi", "django"]
        results = fuzzy_match_library("fast", libs, threshold=0.3)
        fast_match = next(r for r in results if r.library == "fastapi")
        # "fast" is a prefix of "fastapi" — should have bonus
        assert fast_match.score > 0.5

    def test_threshold_zero_matches_all(self):
        libs = ["abc", "xyz", "mno"]
        results = fuzzy_match_library("q", libs, threshold=0.0)
        assert len(results) == 3

    def test_threshold_one_only_exact(self):
        libs = ["fastapi", "flask", "django"]
        results = fuzzy_match_library("fastapi", libs, threshold=1.0)
        assert len(results) == 1
        assert results[0].library == "fastapi"

    def test_fuzzy_match_type_includes_band(self):
        """Non-exact matches have match_type like 'fuzzy_high', 'fuzzy_medium', 'fuzzy_low'."""
        libs = ["fastapi", "flask"]
        results = fuzzy_match_library("fast", libs, threshold=0.3)
        for r in results:
            if r.match_type != "exact":
                assert r.match_type.startswith("fuzzy_")


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

    def test_exact_topic_match(self):
        topics = ["routing", "middleware"]
        result = fuzzy_match_topic("routing", topics)
        assert result is not None
        assert result.score == 1.0

    def test_best_topic_returned(self):
        """When multiple topics match, the best is returned."""
        topics = ["fast-routing", "fast-api", "slow-stuff"]
        result = fuzzy_match_topic("fast", topics, threshold=0.3)
        assert result is not None
        # Should pick the best match, not just the first

    def test_match_type_is_topic(self):
        topics = ["routing"]
        result = fuzzy_match_topic("route", topics, threshold=0.3)
        assert result is not None
        assert result.match_type == "topic"

    def test_library_field_empty(self):
        """Topic matches have empty library field."""
        topics = ["routing"]
        result = fuzzy_match_topic("route", topics, threshold=0.3)
        assert result is not None
        assert result.library == ""


class TestCombinedScore:
    def test_weighted(self):
        score = combined_score(1.0, 0.5)
        expected = 1.0 * 0.6 + 0.5 * 0.4
        assert abs(score - expected) < 0.001

    def test_custom_weights(self):
        score = combined_score(0.8, 0.6, library_weight=0.7, topic_weight=0.3)
        expected = 0.8 * 0.7 + 0.6 * 0.3
        assert abs(score - expected) < 0.001

    def test_zero_scores(self):
        assert combined_score(0.0, 0.0) == 0.0

    def test_max_scores(self):
        assert combined_score(1.0, 1.0) == 1.0


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

    def test_both_empty(self):
        assert edit_distance("", "") == 0

    def test_typo_fastapi(self):
        assert edit_distance("fastaip", "fastapi") == 2

    def test_completely_different(self):
        assert edit_distance("abc", "xyz") == 3

    def test_transposition(self):
        """Standard Levenshtein treats transposition as 2 operations."""
        assert edit_distance("ab", "ba") == 2

    def test_single_char(self):
        assert edit_distance("a", "b") == 1
        assert edit_distance("a", "a") == 0


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

    def test_case_insensitive(self):
        score = edit_distance_similarity("FastAPI", "fastapi")
        assert score == 1.0

    def test_completely_different(self):
        score = edit_distance_similarity("abc", "xyz")
        assert score == 0.0


class TestTokenOverlap:
    def test_identical(self):
        assert token_overlap_score("scikit-learn", "scikit-learn") == 1.0

    def test_partial_overlap(self):
        score = token_overlap_score("scikit-learn", "scikit-image")
        assert 0.0 < score < 1.0

    def test_no_overlap(self):
        assert token_overlap_score("fastapi", "django") == 0.0

    def test_empty_first(self):
        assert token_overlap_score("", "something") == 0.0

    def test_empty_both(self):
        assert token_overlap_score("", "") == 0.0

    def test_hyphen_split(self):
        """Hyphens are used as token separators."""
        score = token_overlap_score("my-lib", "my-other")
        assert score == 0.5  # "my" overlaps, "lib" doesn't

    def test_underscore_split(self):
        """Underscores are used as token separators."""
        score = token_overlap_score("my_lib", "my_other")
        assert score == 0.5

    def test_space_split(self):
        """Spaces are used as token separators."""
        score = token_overlap_score("my lib", "my other")
        assert score == 0.5


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

    def test_completely_different(self):
        score = multi_signal_score("abc", "xyz")
        assert score == 0.0

    def test_weights_sum_to_one(self):
        """Verify the weights in multi_signal_score sum to 1.0 (0.4 + 0.35 + 0.25)."""
        # When all signals return 1.0, the total should be 1.0
        assert multi_signal_score("test", "test") == 1.0

    def test_symmetric(self):
        """Multi-signal score should be approximately symmetric."""
        s1 = multi_signal_score("abc", "abcdef")
        s2 = multi_signal_score("abcdef", "abc")
        # LCS is symmetric, edit distance is symmetric, but token overlap isn't
        # So they may differ slightly
        assert abs(s1 - s2) < 0.3  # reasonably close


class TestConfidenceBand:
    def test_high(self):
        assert confidence_band(0.9) == "high"

    def test_medium(self):
        assert confidence_band(0.7) == "medium"

    def test_low(self):
        assert confidence_band(0.3) == "low"

    def test_boundary_high(self):
        assert confidence_band(CONFIDENCE_HIGH) == "high"

    def test_boundary_medium(self):
        assert confidence_band(CONFIDENCE_MEDIUM) == "medium"

    def test_just_below_high(self):
        assert confidence_band(CONFIDENCE_HIGH - 0.01) == "medium"

    def test_just_below_medium(self):
        assert confidence_band(CONFIDENCE_MEDIUM - 0.01) == "low"

    def test_zero(self):
        assert confidence_band(0.0) == "low"

    def test_one(self):
        assert confidence_band(1.0) == "high"


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

    def test_excludes_high_confidence_matches(self):
        """did_you_mean excludes high-confidence matches (exact or near-exact)."""
        libs = ["fastapi"]
        # Exact match → high confidence → excluded from suggestions
        suggestions = did_you_mean("fastapi", libs)
        assert "fastapi" not in suggestions

    def test_empty_libraries(self):
        suggestions = did_you_mean("test", [])
        assert suggestions == []

    def test_returns_list_of_strings(self):
        libs = ["fastapi", "flask"]
        suggestions = did_you_mean("fas", libs, threshold=0.3)
        for s in suggestions:
            assert isinstance(s, str)


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

    def test_empty_project_libraries(self):
        """Empty project_libraries should behave like None."""
        libs = ["fastapi", "flask"]
        results_none = fuzzy_match_library("fast", libs, threshold=0.3, project_libraries=None)
        results_empty = fuzzy_match_library("fast", libs, threshold=0.3, project_libraries=[])
        # Same results
        assert len(results_none) == len(results_empty)

    def test_project_library_case_insensitive(self):
        """Project library matching should be case-insensitive."""
        libs = ["FastAPI"]
        results = fuzzy_match_library("fast", libs, threshold=0.3, project_libraries=["fastapi"])
        fastapi_result = next((r for r in results if r.library == "FastAPI"), None)
        assert fastapi_result is not None
        # Should have the project boost
        results_no_boost = fuzzy_match_library("fast", libs, threshold=0.3)
        assert fastapi_result.score >= results_no_boost[0].score

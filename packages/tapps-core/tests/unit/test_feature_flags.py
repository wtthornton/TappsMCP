"""Tests for tapps_core.config.feature_flags."""

from __future__ import annotations

from unittest.mock import patch

from tapps_core.config.feature_flags import FeatureFlags, feature_flags


class TestFeatureFlags:
    """Unit tests for the FeatureFlags class."""

    def test_singleton_exists(self) -> None:
        assert feature_flags is not None
        assert isinstance(feature_flags, FeatureFlags)

    def test_reset_clears_cache(self) -> None:
        ff = FeatureFlags()
        # Force evaluation then reset — flags should re-evaluate
        first = ff.radon
        ff.reset()
        # After reset, as_dict() re-evaluates all flags from scratch
        d = ff.as_dict()
        assert "radon" in d

    def test_as_dict_evaluates_all_flags(self) -> None:
        ff = FeatureFlags()
        result = ff.as_dict()
        assert "faiss" in result
        assert "numpy" in result
        assert "sentence_transformers" in result
        assert "radon" in result
        assert all(isinstance(v, bool) for v in result.values())

    def test_flags_are_cached(self) -> None:
        ff = FeatureFlags()
        first = ff.radon
        second = ff.radon
        assert first is second

    @patch.object(FeatureFlags, "_probe", return_value=True)
    def test_faiss_flag_delegates_to_probe(self, mock_probe: object) -> None:
        ff = FeatureFlags()
        assert ff.faiss is True

    @patch.object(FeatureFlags, "_probe", return_value=False)
    def test_faiss_flag_false_when_unavailable(self, mock_probe: object) -> None:
        ff = FeatureFlags()
        assert ff.faiss is False

    @patch.object(FeatureFlags, "_probe", return_value=True)
    def test_numpy_flag(self, mock_probe: object) -> None:
        ff = FeatureFlags()
        assert ff.numpy is True

    @patch.object(FeatureFlags, "_probe", return_value=True)
    def test_sentence_transformers_flag(self, mock_probe: object) -> None:
        ff = FeatureFlags()
        assert ff.sentence_transformers is True

    def test_radon_requires_both_submodules(self) -> None:
        ff = FeatureFlags()
        results: list[bool] = []

        def fake_probe(name: str) -> bool:
            results.append(True)
            return name == "radon.complexity"

        with patch.object(FeatureFlags, "_probe", side_effect=fake_probe):
            assert ff.radon is False

    def test_probe_handles_module_not_found(self) -> None:
        with patch("importlib.util.find_spec", side_effect=ModuleNotFoundError):
            result = FeatureFlags._probe("nonexistent.module")
        assert result is False

    def test_probe_handles_value_error(self) -> None:
        with patch("importlib.util.find_spec", side_effect=ValueError):
            result = FeatureFlags._probe("bad.module")
        assert result is False

    def test_probe_returns_false_for_none_spec(self) -> None:
        with patch("importlib.util.find_spec", return_value=None):
            result = FeatureFlags._probe("nonexistent")
        assert result is False

    def test_reset_allows_reevaluation(self) -> None:
        ff = FeatureFlags()
        with patch.object(FeatureFlags, "_probe", return_value=False):
            assert ff.faiss is False
        ff.reset()
        with patch.object(FeatureFlags, "_probe", return_value=True):
            assert ff.faiss is True

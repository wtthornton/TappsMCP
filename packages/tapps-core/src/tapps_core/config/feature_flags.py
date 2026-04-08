"""Unified feature flags for optional dependencies.

Detects optional packages once (lazily on first access) and caches the
results.  Replaces scattered ``try: import X except ImportError`` patterns
across the codebase with a single source of truth.

Usage::

    from tapps_core.config.feature_flags import feature_flags

    if feature_flags.faiss:
        import faiss
        ...

    if feature_flags.radon:
        from radon.complexity import cc_visit
        ...
"""

from __future__ import annotations

import importlib.util


class FeatureFlags:
    """Lazy-evaluated feature flags for optional dependencies.

    Each flag is computed on first access via ``importlib.util.find_spec``
    and cached for subsequent reads.  Call :meth:`reset` in tests to
    clear the cache.
    """

    def __init__(self) -> None:
        self._cache: dict[str, bool] = {}

    @staticmethod
    def _probe(module_name: str) -> bool:
        """Return whether *module_name* is importable."""
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ModuleNotFoundError, ValueError):
            return False

    # -- public flags -------------------------------------------------------

    @property
    def faiss(self) -> bool:
        """True when ``faiss`` (faiss-cpu) is importable."""
        if "faiss" not in self._cache:
            self._cache["faiss"] = self._probe("faiss")
        return self._cache["faiss"]

    @property
    def numpy(self) -> bool:
        """True when ``numpy`` is importable."""
        if "numpy" not in self._cache:
            self._cache["numpy"] = self._probe("numpy")
        return self._cache["numpy"]

    @property
    def sentence_transformers(self) -> bool:
        """True when ``sentence_transformers`` is importable."""
        if "sentence_transformers" not in self._cache:
            self._cache["sentence_transformers"] = self._probe("sentence_transformers")
        return self._cache["sentence_transformers"]

    @property
    def radon(self) -> bool:
        """True when both ``radon.complexity`` and ``radon.metrics`` are importable."""
        if "radon" not in self._cache:
            self._cache["radon"] = (
                self._probe("radon.complexity") and self._probe("radon.metrics")
            )
        return self._cache["radon"]

    @property
    def perflint(self) -> bool:
        """True when ``perflint`` is importable (pylint performance plugin)."""
        if "perflint" not in self._cache:
            self._cache["perflint"] = self._probe("perflint")
        return self._cache["perflint"]

    @property
    def memory_semantic_search(self) -> bool:
        """True when optional deps for memory semantic search (sentence-transformers) are available.

        Gates the semantic search path in memory retrieval (Epic 65.7, 65.8).
        """
        return self.sentence_transformers

    # -- introspection / testing -------------------------------------------

    def reset(self) -> None:
        """Clear the cached detection results (for test isolation)."""
        self._cache.clear()

    def as_dict(self) -> dict[str, bool]:
        """Return all evaluated flags as a plain dict.

        Forces evaluation of all flags.
        """
        # Touch each property to ensure cache is populated.
        _ = (
            self.faiss,
            self.numpy,
            self.sentence_transformers,
            self.radon,
            self.perflint,
            self.memory_semantic_search,
        )
        return dict(self._cache)


#: Module-level singleton.  Import and use directly::
#:
#:     from tapps_core.config.feature_flags import feature_flags
feature_flags = FeatureFlags()

"""Backward-compatible re-export from tapps-brain.

In tapps-brain >= 3.0 the ``EmbeddingProvider`` Protocol and ``NoopProvider``
class were removed.  ``SentenceTransformerProvider`` is now the single concrete
embedding class.  ``EmbeddingProvider`` is aliased here for import compat;
``NoopProvider`` is provided as a stub that raises ``ImportError`` at call time.
"""

from __future__ import annotations

from tapps_brain.embeddings import (
    SentenceTransformerProvider as SentenceTransformerProvider,
)
from tapps_brain.embeddings import (
    get_embedding_provider as get_embedding_provider,
)

# tapps-brain v3: EmbeddingProvider Protocol removed; alias to concrete class.
EmbeddingProvider = SentenceTransformerProvider


class NoopProvider:
    """Stub — NoopProvider was removed in tapps-brain v3.

    Semantic search is either enabled (SentenceTransformerProvider) or disabled
    by passing ``None`` to MemoryStore.  There is no explicit noop provider.
    """

    def __init__(self, *a: object, **kw: object) -> None:
        raise ImportError(
            "NoopProvider was removed in tapps-brain v3. "
            "Pass embedding_provider=None to MemoryStore to disable embeddings."
        )

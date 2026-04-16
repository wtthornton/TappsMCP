"""Backward-compatible re-export from tapps-brain.

In tapps-brain >= 3.0 (ADR-007) the file-backed federation store
(``FederatedStore``, ``FederationConfig``, etc.) was removed.  Federation in
v3 is postgres-only and accessed via ``tapps_brain.backends.create_federation_backend()``.

This shim re-exports the v2 symbols when available (tapps-brain < 3.0), and
provides stub objects when they are absent.  Call sites that were already
wrapped in ``try/except ImportError`` will degrade gracefully; direct calls to
the stub classes/functions raise :class:`ImportError` at call time with a
helpful message.
"""

from __future__ import annotations

from pathlib import Path

try:
    from tapps_brain.federation import _DEFAULT_HUB_DIR as _DEFAULT_HUB_DIR
    from tapps_brain.federation import FederatedSearchResult as FederatedSearchResult
    from tapps_brain.federation import FederatedStore as FederatedStore
    from tapps_brain.federation import FederationConfig as FederationConfig
    from tapps_brain.federation import FederationProject as FederationProject
    from tapps_brain.federation import (
        FederationSubscription as FederationSubscription,
    )
    from tapps_brain.federation import add_subscription as add_subscription
    from tapps_brain.federation import federated_search as federated_search
    from tapps_brain.federation import (
        load_federation_config as load_federation_config,
    )
    from tapps_brain.federation import register_project as register_project
    from tapps_brain.federation import (
        save_federation_config as save_federation_config,
    )
    from tapps_brain.federation import sync_from_hub as sync_from_hub
    from tapps_brain.federation import sync_to_hub as sync_to_hub
    from tapps_brain.federation import unregister_project as unregister_project
except ImportError:
    # tapps-brain >= 3.0: file-based federation removed (ADR-007).
    # Use tapps_brain.backends.create_federation_backend() with a PostgreSQL DSN.
    # The blanket type: ignore on each definition suppresses mypy's inconsistent
    # no-redef behaviour when ignore_missing_imports is active.
    _ERR = (
        "File-based federation was removed in tapps-brain v3 (ADR-007). "
        "Use tapps_brain.backends.create_federation_backend() with a PostgreSQL DSN."
    )

    _DEFAULT_HUB_DIR: Path = Path.home() / ".tapps-brain" / "hub"  # type: ignore[no-redef]

    class FederatedSearchResult:  # type: ignore
        """Stub — not available in tapps-brain >= 3.0."""

        def __init__(self, *a: object, **kw: object) -> None:
            raise ImportError(_ERR)

    class FederatedStore:  # type: ignore
        """Stub — not available in tapps-brain >= 3.0."""

        def __init__(self, *a: object, **kw: object) -> None:
            raise ImportError(_ERR)

    class FederationConfig:  # type: ignore
        """Stub — not available in tapps-brain >= 3.0."""

        projects: list[object] = []
        subscriptions: list[object] = []

        def __init__(self, *a: object, **kw: object) -> None:
            raise ImportError(_ERR)

    class FederationProject:  # type: ignore
        """Stub — not available in tapps-brain >= 3.0."""

        def __init__(self, *a: object, **kw: object) -> None:
            raise ImportError(_ERR)

    class FederationSubscription:  # type: ignore
        """Stub — not available in tapps-brain >= 3.0."""

        def __init__(self, *a: object, **kw: object) -> None:
            raise ImportError(_ERR)

    def add_subscription(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def federated_search(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def load_federation_config(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def register_project(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def save_federation_config(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def sync_from_hub(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def sync_to_hub(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

    def unregister_project(*a: object, **kw: object) -> object:  # type: ignore
        raise ImportError(_ERR)

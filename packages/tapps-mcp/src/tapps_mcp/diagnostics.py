"""Startup diagnostics - local-only health checks for TappsMCP subsystems."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from tapps_core.common.models import (
    CacheDiagnostic,
    Context7Diagnostic,
    KnowledgeBaseDiagnostic,
    StartupDiagnostics,
)

if TYPE_CHECKING:
    from pydantic import SecretStr


def check_context7(api_key: SecretStr | None) -> Context7Diagnostic:
    """Check whether a Context7 API key is configured."""
    has_key = api_key is not None and len(api_key.get_secret_value()) > 0
    return Context7Diagnostic(
        api_key_set=has_key,
        status="available" if has_key else "no_key",
    )


def check_cache(cache_dir: Path) -> CacheDiagnostic:
    """Check cache directory existence, writability, and stats.

    Only instantiates ``KBCache`` if the directory already exists to avoid
    auto-creating it as a side effect.
    """
    exists = cache_dir.exists() and cache_dir.is_dir()
    writable = False
    entry_count = 0
    total_size_bytes = 0
    stale_count = 0

    if exists:
        try:
            fd, tmp = tempfile.mkstemp(dir=str(cache_dir), prefix=".diag_")
            os.close(fd)
            Path(tmp).unlink(missing_ok=True)
            writable = True
        except OSError:
            writable = False

        from tapps_core.knowledge.cache import KBCache

        cache = KBCache(cache_dir)
        stats = cache.stats
        entry_count = stats.total_entries
        total_size_bytes = stats.total_size_bytes
        stale_count = stats.stale_entries

    return CacheDiagnostic(
        cache_dir=str(cache_dir),
        exists=exists,
        writable=writable,
        entry_count=entry_count,
        total_size_bytes=total_size_bytes,
        stale_count=stale_count,
    )


def check_knowledge_base() -> KnowledgeBaseDiagnostic:
    """Expert system removed (EPIC-94). Returns empty diagnostic."""
    return KnowledgeBaseDiagnostic(
        total_domains=0,
        total_files=0,
        expected_domains=0,
        missing_domains=[],
        domains=[],
    )


def collect_diagnostics(
    api_key: SecretStr | None,
    cache_dir: Path,
) -> StartupDiagnostics:
    """Run all diagnostic checks and return a single ``StartupDiagnostics``."""
    return StartupDiagnostics(
        context7=check_context7(api_key),
        cache=check_cache(cache_dir),
        knowledge_base=check_knowledge_base(),
    )

"""Startup diagnostics - local-only health checks for TappsMCP subsystems."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from tapps_mcp.common.models import (
    CacheDiagnostic,
    Context7Diagnostic,
    KnowledgeBaseDiagnostic,
    KnowledgeDomainInfo,
    StartupDiagnostics,
    VectorRagDiagnostic,
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

        from tapps_mcp.knowledge.cache import KBCache

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


def check_vector_rag() -> VectorRagDiagnostic:
    """Check availability of optional vector RAG dependencies."""
    from tapps_mcp.experts.rag_embedder import SENTENCE_TRANSFORMERS_AVAILABLE
    from tapps_mcp.experts.rag_index import FAISS_AVAILABLE

    try:
        import numpy as _np

        numpy_available = True
        del _np
    except ImportError:
        numpy_available = False

    all_present = FAISS_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE and numpy_available
    return VectorRagDiagnostic(
        faiss_available=FAISS_AVAILABLE,
        sentence_transformers_available=SENTENCE_TRANSFORMERS_AVAILABLE,
        numpy_available=numpy_available,
        status="full_vector" if all_present else "keyword_only",
    )


def check_knowledge_base() -> KnowledgeBaseDiagnostic:
    """Check knowledge base integrity: domain dirs, file counts, missing domains."""
    from tapps_mcp.experts.domain_utils import sanitize_domain_for_path
    from tapps_mcp.experts.registry import ExpertRegistry

    base_path = ExpertRegistry.get_knowledge_base_path()
    expected_domains = ExpertRegistry.TECHNICAL_DOMAINS

    domains_info: list[KnowledgeDomainInfo] = []
    total_files = 0
    found_domains: set[str] = set()

    for expert in ExpertRegistry.get_all_experts():
        dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
        kb_path = base_path / dir_name
        if kb_path.exists() and kb_path.is_dir():
            file_count = len(list(kb_path.glob("*.md")))
            total_files += file_count
            found_domains.add(expert.primary_domain)
            domains_info.append(
                KnowledgeDomainInfo(domain=expert.primary_domain, file_count=file_count)
            )
        else:
            domains_info.append(KnowledgeDomainInfo(domain=expert.primary_domain, file_count=0))

    missing = sorted(expected_domains - found_domains)

    return KnowledgeBaseDiagnostic(
        total_domains=len(found_domains),
        total_files=total_files,
        expected_domains=len(expected_domains),
        missing_domains=missing,
        domains=sorted(domains_info, key=lambda d: d.domain),
    )


def collect_diagnostics(
    api_key: SecretStr | None,
    cache_dir: Path,
) -> StartupDiagnostics:
    """Run all diagnostic checks and return a single ``StartupDiagnostics``."""
    return StartupDiagnostics(
        context7=check_context7(api_key),
        cache=check_cache(cache_dir),
        vector_rag=check_vector_rag(),
        knowledge_base=check_knowledge_base(),
    )

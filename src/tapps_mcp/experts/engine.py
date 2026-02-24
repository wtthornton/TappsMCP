"""Expert consultation engine — orchestrates RAG lookup and confidence scoring.

This is the main entry point for expert consultations.  It:

1. Detects the best domain for the user's question.
2. Loads the domain's knowledge base (RAG).
3. Searches for relevant chunks.
4. Computes a confidence score.
5. Returns a :class:`ConsultationResult`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_mcp.config.settings import TappsMCPSettings

from tapps_mcp.experts.confidence import (
    compute_chunk_coverage,
    compute_confidence,
    compute_rag_quality,
)
from tapps_mcp.experts.domain_detector import DomainDetector
from tapps_mcp.experts.domain_utils import sanitize_domain_for_path
from tapps_mcp.experts.models import (
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ConfidenceFactors,
    ConsultationResult,
    DomainMapping,
    ExpertInfo,
)
from tapps_mcp.experts.rag import _extract_keywords
from tapps_mcp.experts.registry import ExpertRegistry
from tapps_mcp.experts.vector_rag import VectorKnowledgeBase

logger = structlog.get_logger(__name__)


def _infer_lookup_hints(question: str, domain: str) -> tuple[str, str]:
    """Infer best-effort library/topic hints for docs lookup."""
    q = question.lower()

    library_candidates: list[tuple[str, list[str]]] = [
        ("pytest", ["pytest", "fixture", "conftest", "monkeypatch"]),
        ("fastapi", ["fastapi", "apirouter", "pydantic", "uvicorn"]),
        ("flask", ["flask", "werkzeug", "jinja"]),
        ("django", ["django", "orm", "settings.py"]),
        ("sqlalchemy", ["sqlalchemy", "session", "declarative", "alembic"]),
        ("pydantic", ["pydantic", "basemodel", "field"]),
        ("requests", ["requests", "http", "session"]),
        ("docker", ["docker", "dockerfile", "compose"]),
        ("kubernetes", ["kubernetes", "k8s", "kubectl"]),
        ("prometheus", ["prometheus", "metrics", "exporter"]),
    ]

    library = "python"
    for candidate, signals in library_candidates:
        if any(signal in q for signal in signals):
            library = candidate
            break
    else:
        domain_defaults = {
            "testing-strategies": "pytest",
            "api-design-integration": "fastapi",
            "database-data-management": "sqlalchemy",
            "cloud-infrastructure": "docker",
            "observability-monitoring": "prometheus",
        }
        library = domain_defaults.get(domain, "python")

    topic = "overview"
    topic_signals = [
        ("security", ["security", "auth", "vulnerability", "owasp"]),
        ("testing", ["test", "fixture", "mock", "assert"]),
        ("configuration", ["config", "env", "setting", "url"]),
        ("performance", ["performance", "optimiz", "latency", "throughput"]),
        ("api", ["api", "endpoint", "route", "request", "response"]),
    ]
    for candidate, signals in topic_signals:
        if any(signal in q for signal in signals):
            topic = candidate
            break

    return library, topic


def _lookup_docs_sync(library: str, topic: str) -> tuple[bool, str | None]:
    """Run async docs lookup from this sync module."""
    try:
        from tapps_mcp.config.settings import load_settings
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.lookup import LookupEngine

        settings = load_settings()
        cache = KBCache(settings.project_root / ".tapps-mcp-cache")

        async def _run() -> tuple[bool, str | None]:
            engine = LookupEngine(cache, settings=settings)
            try:
                result = await engine.lookup(library=library, topic=topic, mode="code")
            finally:
                await engine.close()
            return result.success, result.content

        return asyncio.run(_run())
    except Exception as exc:
        logger.debug(
            "expert_context7_fallback_failed",
            library=library,
            topic=topic,
            reason=str(exc),
        )
        return False, None


def consult_expert(
    question: str,
    domain: str | None = None,
    max_chunks: int = 5,
    max_context_length: int = 3000,
) -> ConsultationResult:
    """Run an expert consultation for *question*.

    Args:
        question: The user's question (natural language).
        domain: Optional domain override.  When ``None``, the best domain is
            detected automatically from the question text.
        max_chunks: Maximum RAG chunks to retrieve.
        max_context_length: Maximum character length of the context block.

    Returns:
        A :class:`ConsultationResult` with the expert's knowledge-backed
        answer, confidence score, and source references.
    """
    # 1. Resolve domain.
    detected: list[DomainMapping] = []
    if domain:
        resolved_domain = domain
    else:
        mappings = DomainDetector.detect_from_question(question)
        resolved_domain = mappings[0].domain if mappings else "software-architecture"
        detected = mappings[:3]  # top-3 for transparency

    expert = ExpertRegistry.get_expert_for_domain(resolved_domain)
    if expert is None:
        # Fallback to the closest match.
        expert = ExpertRegistry.get_expert_for_domain("software-architecture")
        if expert is None:
            # Should never happen — architecture is always registered.
            msg = f"No expert found for domain: {resolved_domain}"
            raise ValueError(msg)

    logger.debug(
        "expert_consultation_start",
        question=question[:80],
        domain=resolved_domain,
        expert_id=expert.expert_id,
    )

    # 2. Load knowledge base for the domain.
    # VectorKnowledgeBase uses semantic search when [rag] extras are installed,
    # otherwise falls back to SimpleKnowledgeBase automatically.
    # When project_root is available, use project-level indices (from tapps_init warming).
    knowledge_dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
    knowledge_path = ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name
    index_dir = None
    try:
        from tapps_mcp.config.settings import load_settings

        settings = load_settings()
        domain_slug = sanitize_domain_for_path(resolved_domain)
        index_dir = settings.project_root / ".tapps-mcp" / "rag_index" / domain_slug
    except Exception as e:
        logger.debug("rag_index_dir_skip", reason=str(e))
    kb = VectorKnowledgeBase(
        knowledge_path,
        domain=resolved_domain,
        index_dir=index_dir,
    )

    # 3. Search.
    chunks = kb.search(question, max_results=max_chunks)
    context = kb.get_context(question, max_length=max_context_length) if chunks else ""
    sources = kb.get_sources(question, max_results=max_chunks)

    # 4. Confidence scoring.
    keywords = _extract_keywords(question)
    chunk_scores = [c.score for c in chunks]
    chunk_texts = [c.content for c in chunks]

    rag_quality = compute_rag_quality(chunk_scores)
    chunk_coverage = compute_chunk_coverage(keywords, chunk_texts)

    factors = ConfidenceFactors(
        rag_quality=rag_quality,
        source_count=len(sources),
        chunk_coverage=chunk_coverage,
    )
    confidence = compute_confidence(factors, resolved_domain)

    # 5. Build answer text.
    suggested_tool: str | None = None
    suggested_library: str | None = None
    suggested_topic: str | None = None
    fallback_used = False
    fallback_library: str | None = None
    fallback_topic: str | None = None
    if context:
        answer = (
            f"## {expert.expert_name} — {resolved_domain}\n\n"
            f"Based on domain knowledge ({len(chunks)} source(s), "
            f"confidence {confidence:.0%}):\n\n"
            f"{context}"
        )
    else:
        suggested_tool = "tapps_lookup_docs"
        suggested_library, suggested_topic = _infer_lookup_hints(question, resolved_domain)
        answer = (
            f"## {expert.expert_name} — {resolved_domain}\n\n"
            f"No specific knowledge found for this query in the "
            f"{resolved_domain} knowledge base. The expert can still "
            f"provide general guidance based on domain principles.\n\n"
            f"Suggested next step: call {suggested_tool}(library='{suggested_library}', "
            f"topic='{suggested_topic}')."
        )

        try:
            from tapps_mcp.config.settings import load_settings

            fallback_settings: TappsMCPSettings | None = load_settings()
        except Exception as exc:
            logger.debug("expert_fallback_settings_unavailable", reason=str(exc))
            fallback_settings = None

        if fallback_settings is not None and fallback_settings.expert_auto_fallback:
            ok, docs_content = _lookup_docs_sync(suggested_library, suggested_topic)
            if ok and docs_content:
                fallback_used = True
                fallback_library = suggested_library
                fallback_topic = suggested_topic
                fallback_excerpt = docs_content[: fallback_settings.expert_fallback_max_chars]
                answer = (
                    f"{answer}\n\n---\n\n"
                    "### Context7 fallback (auto-attached)\n\n"
                    f"Library: `{fallback_library}` | Topic: `{fallback_topic}`\n\n"
                    f"{fallback_excerpt}"
                )

    # Low-confidence nudge: help the AI supplement with other tools
    low_confidence_nudge = None
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        low_confidence_nudge = (
            "Confidence is low. Consider also calling tapps_lookup_docs(library='<name>') "
            "for library-specific details, or try a different domain if the question may fit "
            "better elsewhere (use tapps_list_experts to see options)."
        )
        answer = f"{answer}\n\n---\n\n**Note:** {low_confidence_nudge}"

    # Actionable recommendation based on confidence level
    _lib = suggested_library or "python"
    _topic = suggested_topic or "overview"
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        recommendation = "Expert guidance is high-confidence. Proceed with implementation."
    elif confidence >= LOW_CONFIDENCE_THRESHOLD:
        recommendation = (
            f"Moderate confidence. Consider supplementing with "
            f"tapps_lookup_docs(library='{_lib}', topic='{_topic}')."
        )
    else:
        recommendation = (
            f"Low confidence. Call tapps_research(question=...) for combined "
            f"expert + docs, or tapps_lookup_docs(library='{_lib}', "
            f"topic='{_topic}') directly."
        )

    return ConsultationResult(
        domain=resolved_domain,
        expert_id=expert.expert_id,
        expert_name=expert.expert_name,
        answer=answer,
        confidence=confidence,
        factors=factors,
        sources=sources,
        chunks_used=len(chunks),
        detected_domains=detected,
        recommendation=recommendation,
        low_confidence_nudge=low_confidence_nudge,
        suggested_tool=suggested_tool,
        suggested_library=suggested_library,
        suggested_topic=suggested_topic,
        fallback_used=fallback_used,
        fallback_library=fallback_library,
        fallback_topic=fallback_topic,
    )


def list_experts() -> list[ExpertInfo]:
    """Return info for every registered expert, including knowledge-file counts."""
    results: list[ExpertInfo] = []
    base_path = ExpertRegistry.get_knowledge_base_path()

    for expert in ExpertRegistry.get_all_experts():
        dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
        kb_path = base_path / dir_name
        file_count = len(list(kb_path.rglob("*.md"))) if kb_path.exists() else 0

        results.append(
            ExpertInfo(
                expert_id=expert.expert_id,
                expert_name=expert.expert_name,
                primary_domain=expert.primary_domain,
                description=expert.description,
                rag_enabled=expert.rag_enabled,
                knowledge_files=file_count,
            )
        )
    return results

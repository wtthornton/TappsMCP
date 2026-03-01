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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tapps_core.config.settings import TappsMCPSettings

from tapps_core.experts.confidence import (
    compute_chunk_coverage,
    compute_confidence,
    compute_rag_quality,
)
from tapps_core.experts.domain_detector import DomainDetector
from tapps_core.experts.domain_utils import sanitize_domain_for_path
from tapps_core.experts.models import (
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ConfidenceFactors,
    ConsultationResult,
    DomainMapping,
    ExpertConfig,
    ExpertInfo,
)
from tapps_core.experts.rag import _extract_keywords
from tapps_core.experts.registry import ExpertRegistry
from tapps_core.experts.vector_rag import VectorKnowledgeBase

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
    """Run async docs lookup from this sync module.

    Detects whether an event loop is already running (e.g. when called from
    ``tapps_research`` via ``asyncio.to_thread``).  If so, the fallback is
    skipped — the caller (``tapps_research``) handles docs lookup directly.
    """
    # Guard against nested event loop: asyncio.run() raises RuntimeError
    # when called inside an already-running loop.
    try:
        loop = asyncio.get_running_loop()  # noqa: F841
        logger.debug(
            "expert_context7_fallback_skipped",
            reason="event loop already running; caller should handle docs lookup",
        )
        return False, None
    except RuntimeError:
        pass  # No running loop — safe to use asyncio.run()

    try:
        from tapps_core.config.settings import load_settings
        from tapps_core.knowledge.cache import KBCache
        from tapps_core.knowledge.lookup import LookupEngine

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


@dataclass
class _ResolvedDomain:
    """Result of domain resolution step."""

    domain: str
    expert: ExpertConfig
    detected: list[DomainMapping]


@dataclass
class _KnowledgeResult:
    """Result of knowledge retrieval step."""

    chunks: list[Any]
    context: str
    sources: list[Any]


@dataclass
class _ConfidenceResult:
    """Result of confidence scoring step."""

    confidence: float
    factors: ConfidenceFactors


@dataclass
class _AnswerResult:
    """Result of answer building step."""

    answer: str = ""
    suggested_tool: str | None = None
    suggested_library: str | None = None
    suggested_topic: str | None = None
    fallback_used: bool = False
    fallback_library: str | None = None
    fallback_topic: str | None = None
    low_confidence_nudge: str | None = None


def _resolve_domain(
    question: str, domain: str | None
) -> _ResolvedDomain:
    """Resolve the expert domain from a question or explicit override.

    Raises ValueError if no expert can be found for the resolved domain.
    """
    detected: list[DomainMapping] = []
    if domain:
        resolved_domain = domain
    else:
        mappings = DomainDetector.detect_from_question(question)
        resolved_domain = mappings[0].domain if mappings else "software-architecture"
        detected = mappings[:3]

    expert = ExpertRegistry.get_expert_for_domain(resolved_domain)
    if expert is None:
        expert = ExpertRegistry.get_expert_for_domain("software-architecture")
        if expert is None:
            msg = f"No expert found for domain: {resolved_domain}"
            raise ValueError(msg)

    return _ResolvedDomain(domain=resolved_domain, expert=expert, detected=detected)


def _retrieve_knowledge(
    question: str,
    resolved_domain: str,
    expert: ExpertConfig,
    max_chunks: int,
    max_context_length: int,
) -> _KnowledgeResult:
    """Load the knowledge base and search for relevant chunks."""
    knowledge_dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
    knowledge_path = ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name
    index_dir = None
    try:
        from tapps_core.config.settings import load_settings

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

    chunks = kb.search(question, max_results=max_chunks)
    context = kb.get_context(question, max_length=max_context_length) if chunks else ""
    sources = kb.get_sources(question, max_results=max_chunks)
    return _KnowledgeResult(chunks=chunks, context=context, sources=sources)


def _compute_confidence(
    question: str,
    knowledge: _KnowledgeResult,
    resolved_domain: str,
) -> _ConfidenceResult:
    """Score confidence based on RAG quality and chunk coverage."""
    keywords = _extract_keywords(question)
    chunk_scores = [c.score for c in knowledge.chunks]
    chunk_texts = [c.content for c in knowledge.chunks]

    rag_quality = compute_rag_quality(chunk_scores)
    chunk_coverage = compute_chunk_coverage(keywords, chunk_texts)

    factors = ConfidenceFactors(
        rag_quality=rag_quality,
        source_count=len(knowledge.sources),
        chunk_coverage=chunk_coverage,
    )
    confidence = compute_confidence(factors, resolved_domain)
    return _ConfidenceResult(confidence=confidence, factors=factors)


def _build_answer(
    question: str,
    expert: ExpertConfig,
    resolved_domain: str,
    knowledge: _KnowledgeResult,
    conf: _ConfidenceResult,
) -> _AnswerResult:
    """Build the answer text, including fallback docs if needed."""
    result = _AnswerResult()

    if knowledge.context:
        result.answer = (
            f"## {expert.expert_name} \u2014 {resolved_domain}\n\n"
            f"Based on domain knowledge ({len(knowledge.chunks)} source(s), "
            f"confidence {conf.confidence:.0%}):\n\n"
            f"{knowledge.context}"
        )
    else:
        result.suggested_tool = "tapps_lookup_docs"
        result.suggested_library, result.suggested_topic = _infer_lookup_hints(
            question, resolved_domain
        )
        result.answer = (
            f"## {expert.expert_name} \u2014 {resolved_domain}\n\n"
            f"No specific knowledge found for this query in the "
            f"{resolved_domain} knowledge base. The expert can still "
            f"provide general guidance based on domain principles.\n\n"
            f"Suggested next step: call {result.suggested_tool}"
            f"(library='{result.suggested_library}', "
            f"topic='{result.suggested_topic}')."
        )
        _try_fallback_docs(result)

    # Low-confidence nudge
    if conf.confidence < LOW_CONFIDENCE_THRESHOLD:
        result.low_confidence_nudge = (
            "Confidence is low. Consider also calling tapps_lookup_docs(library='<name>') "
            "for library-specific details, or try a different domain if the question may fit "
            "better elsewhere (use tapps_list_experts to see options)."
        )
        result.answer = f"{result.answer}\n\n---\n\n**Note:** {result.low_confidence_nudge}"

    return result


def _try_fallback_docs(result: _AnswerResult) -> None:
    """Attempt Context7 fallback docs lookup when no RAG context found."""
    try:
        from tapps_core.config.settings import load_settings

        fallback_settings: TappsMCPSettings | None = load_settings()
    except Exception as exc:
        logger.debug("expert_fallback_settings_unavailable", reason=str(exc))
        fallback_settings = None

    if fallback_settings is None or not fallback_settings.expert_auto_fallback:
        return

    ok, docs_content = _lookup_docs_sync(
        result.suggested_library or "python",
        result.suggested_topic or "overview",
    )
    if not ok or not docs_content:
        return

    result.fallback_used = True
    result.fallback_library = result.suggested_library
    result.fallback_topic = result.suggested_topic
    fallback_excerpt = docs_content[: fallback_settings.expert_fallback_max_chars]
    result.answer = (
        f"{result.answer}\n\n---\n\n"
        "### Context7 fallback (auto-attached)\n\n"
        f"Library: `{result.fallback_library}` | Topic: `{result.fallback_topic}`\n\n"
        f"{fallback_excerpt}"
    )


def _build_recommendation(
    conf: _ConfidenceResult,
    suggested_library: str | None,
    suggested_topic: str | None,
) -> str:
    """Build an actionable recommendation based on confidence level."""
    lib = suggested_library or "python"
    topic = suggested_topic or "overview"

    if conf.confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return "Expert guidance is high-confidence. Proceed with implementation."
    if conf.confidence >= LOW_CONFIDENCE_THRESHOLD:
        return (
            f"Moderate confidence. Consider supplementing with "
            f"tapps_lookup_docs(library='{lib}', topic='{topic}')."
        )
    return (
        f"Low confidence. Call tapps_research(question=...) for combined "
        f"expert + docs, or tapps_lookup_docs(library='{lib}', "
        f"topic='{topic}') directly."
    )


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
    resolved = _resolve_domain(question, domain)

    logger.debug(
        "expert_consultation_start",
        question=question[:80],
        domain=resolved.domain,
        expert_id=resolved.expert.expert_id,
    )

    knowledge = _retrieve_knowledge(
        question, resolved.domain, resolved.expert, max_chunks, max_context_length
    )
    conf = _compute_confidence(question, knowledge, resolved.domain)
    answer_result = _build_answer(
        question, resolved.expert, resolved.domain, knowledge, conf
    )
    recommendation = _build_recommendation(
        conf, answer_result.suggested_library, answer_result.suggested_topic
    )

    return ConsultationResult(
        domain=resolved.domain,
        expert_id=resolved.expert.expert_id,
        expert_name=resolved.expert.expert_name,
        answer=answer_result.answer,
        confidence=conf.confidence,
        factors=conf.factors,
        sources=knowledge.sources,
        chunks_used=len(knowledge.chunks),
        detected_domains=resolved.detected,
        recommendation=recommendation,
        low_confidence_nudge=answer_result.low_confidence_nudge,
        suggested_tool=answer_result.suggested_tool,
        suggested_library=answer_result.suggested_library,
        suggested_topic=answer_result.suggested_topic,
        fallback_used=answer_result.fallback_used,
        fallback_library=answer_result.fallback_library,
        fallback_topic=answer_result.fallback_topic,
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

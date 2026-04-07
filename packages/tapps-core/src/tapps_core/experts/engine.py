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
from datetime import UTC, date, datetime
from pathlib import Path
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

_STALE_KNOWLEDGE_DAYS = 365

logger = structlog.get_logger(__name__)


def _is_architectural_question(question: str, domain: str) -> bool:
    """Detect questions that are architectural/conceptual rather than API-specific.

    Architectural questions benefit from expert RAG knowledge, not library API docs.
    Returns ``True`` when docs lookup should be skipped or deprioritized.
    """
    q = question.lower()

    # Domains where questions are typically conceptual, not API-specific.
    architectural_domains: frozenset[str] = frozenset({
        "software-architecture",
        "agent-learning",
        "ai-frameworks",
        "data-privacy-compliance",
        "documentation-knowledge-management",
    })

    # Strong architectural signal keywords — patterns, strategies, approaches.
    architectural_signals: list[str] = [
        "pattern", "architecture", "design", "strategy", "approach",
        "orchestrat", "coordinat", "best practice", "trade-off", "tradeoff",
        "when to use", "how to architect", "multi-agent", "agent memory",
        "hive", "federation", "prompt composition", "memory injection",
        "memory sharing", "cross-session", "cross-agent",
    ]

    # Count architectural signal matches.
    signal_count = sum(1 for sig in architectural_signals if sig in q)

    if domain in architectural_domains and signal_count >= 1:
        # In an architectural domain with at least one conceptual signal,
        # skip docs if there are no library-specific signals.
        library_signals = [
            "pytest", "fastapi", "flask", "django", "sqlalchemy", "pydantic",
            "requests", "docker", "kubernetes", "prometheus", "langchain",
            "openai", "asyncio", "uvicorn",
        ]
        if not any(sig in q for sig in library_signals):
            return True

    # In any domain, 2+ architectural signals indicate a conceptual question.
    return signal_count >= 2


def _infer_lookup_hints(question: str, domain: str) -> tuple[str, str]:
    """Infer best-effort library/topic hints for docs lookup.

    Returns ``("", "")`` when the question is architectural/conceptual and
    library docs would be off-topic (caller should skip docs lookup).
    """
    # Skip docs entirely for architectural questions.
    if _is_architectural_question(question, domain):
        return "", ""

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
        ("langchain", ["langchain", "lcel", "runnable"]),
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
            "agent-learning": "",
            "ai-frameworks": "",
        }
        library = domain_defaults.get(domain, "python")

    # If library resolved to empty, skip docs.
    if not library:
        return "", ""

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
    adaptive_domain_used: bool = False


@dataclass
class _KnowledgeResult:
    """Result of knowledge retrieval step."""

    chunks: list[Any]
    context: str
    sources: list[Any]


@dataclass
class _FreshnessResult:
    """Result of freshness checking step."""

    stale_knowledge: bool = False
    oldest_chunk_age_days: int | None = None
    freshness_caveat: str | None = None


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


_ADAPTIVE_MIN_CONFIDENCE = 0.4


def _try_adaptive_detection(question: str) -> tuple[str | None, list[DomainMapping]]:
    """Attempt domain detection via the adaptive detector.

    Returns ``(domain, detected_mappings)`` if a high-confidence result is found,
    or ``(None, [])`` if adaptive detection is unavailable or low-confidence.
    """
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        if not settings.adaptive.enabled:
            return None, []

        from tapps_core.adaptive.persistence import FileOutcomeTracker

        tracker = FileOutcomeTracker(settings.project_root)
        outcome_count = len(tracker.load_outcomes())
        if outcome_count < settings.adaptive.min_outcomes:
            logger.debug(
                "adaptive_domain_skip_insufficient_data",
                outcomes=outcome_count,
                min_required=settings.adaptive.min_outcomes,
            )
            return None, []

        from tapps_core.experts.adaptive_domain_detector import AdaptiveDomainDetector

        detector = AdaptiveDomainDetector()
        # Run the async detect_domains synchronously.
        import asyncio

        suggestions = asyncio.run(detector.detect_domains(prompt=question))
        if not suggestions:
            return None, []

        best = suggestions[0]
        if best.confidence < _ADAPTIVE_MIN_CONFIDENCE:
            logger.debug(
                "adaptive_domain_low_confidence",
                domain=best.domain,
                confidence=best.confidence,
            )
            return None, []

        # Convert DomainSuggestion list to DomainMapping list for compatibility.
        detected = [
            DomainMapping(
                domain=s.domain,
                confidence=s.confidence,
                signals=[f"adaptive:{s.source}"],
                reasoning=", ".join(s.evidence) if s.evidence else f"Adaptive: {s.source}",
            )
            for s in suggestions[:3]
        ]
        return best.domain, detected

    except Exception as exc:
        logger.debug("adaptive_domain_detection_failed", reason=str(exc))
        return None, []


def _resolve_domain(
    question: str, domain: str | None
) -> _ResolvedDomain:
    """Resolve the expert domain from a question or explicit override.

    When adaptive learning is enabled and has sufficient training data,
    the :class:`AdaptiveDomainDetector` is tried first.  If it returns a
    result with confidence >= 0.4, that domain is used.  Otherwise the
    static :class:`DomainDetector` provides the fallback.

    Raises ValueError if no expert can be found for the resolved domain.
    """
    detected: list[DomainMapping] = []
    adaptive_used = False

    if domain:
        resolved_domain = domain
    else:
        # Try adaptive detection first.
        adaptive_domain, adaptive_detected = _try_adaptive_detection(question)
        if adaptive_domain is not None:
            resolved_domain = adaptive_domain
            detected = adaptive_detected
            adaptive_used = True
            logger.debug(
                "adaptive_domain_resolved",
                domain=resolved_domain,
                confidence=detected[0].confidence if detected else 0,
            )
        else:
            mappings = DomainDetector.detect_from_question_merged(question)
            resolved_domain = mappings[0].domain if mappings else "software-architecture"
            detected = mappings[:3]

    expert = ExpertRegistry.get_expert_for_domain_merged(resolved_domain)
    if expert is None:
        expert = ExpertRegistry.get_expert_for_domain_merged("software-architecture")
        if expert is None:
            msg = f"No expert found for domain: {resolved_domain}"
            raise ValueError(msg)

    return _ResolvedDomain(
        domain=resolved_domain,
        expert=expert,
        detected=detected,
        adaptive_domain_used=adaptive_used,
    )


def _resolve_knowledge_path(expert: ExpertConfig) -> Path:
    """Determine the knowledge base path for an expert.

    Built-in experts use the bundled knowledge directory.  Business experts
    use ``{project_root}/.tapps-mcp/knowledge/<domain>/``.
    """
    knowledge_dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)

    if expert.is_builtin:
        return ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name

    try:
        from tapps_core.config.settings import load_settings
        from tapps_core.experts.business_knowledge import get_business_knowledge_path

        settings = load_settings()
        return get_business_knowledge_path(settings.project_root, expert)
    except Exception as exc:
        logger.debug("business_knowledge_path_fallback", reason=str(exc))
        # Fallback to bundled path (will likely be empty, handled downstream).
        return ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name


_cached_tech_stack_domains: set[str] | None = None


def set_tech_stack_domains(domains: set[str]) -> None:
    """Set the cached tech stack domains (called once during session start)."""
    global _cached_tech_stack_domains
    _cached_tech_stack_domains = domains


def _reset_tech_stack_domains_cache() -> None:
    """Reset the cached tech stack domains (for testing)."""
    global _cached_tech_stack_domains
    _cached_tech_stack_domains = None


def _get_tech_stack_domains() -> set[str]:
    """Get expert domains relevant to the current project's tech stack.

    Returns the cached domains set, or an empty set if not yet populated.
    Call ``set_tech_stack_domains()`` during session start to populate.
    This avoids expensive file-system scanning on every expert consultation.
    """
    return _cached_tech_stack_domains or set()


def _apply_tech_stack_boost(
    chunks: list[Any],
    resolved_domain: str,
    boost: float,
) -> list[Any]:
    """Apply a score boost to chunks when their domain matches the project tech stack.

    Args:
        chunks: Retrieved knowledge chunks.
        resolved_domain: The expert domain being consulted.
        boost: Multiplier to apply (e.g. 1.2 = 20% boost).

    Returns:
        The same chunks with boosted scores (capped at 1.0).
    """
    if boost <= 1.0:
        return chunks

    tech_domains = _get_tech_stack_domains()
    if not tech_domains or resolved_domain not in tech_domains:
        return chunks

    for chunk in chunks:
        chunk.score = min(chunk.score * boost, 1.0)

    logger.debug(
        "tech_stack_boost_applied",
        domain=resolved_domain,
        boost=boost,
        chunk_count=len(chunks),
    )
    return chunks


def _retrieve_knowledge(
    question: str,
    resolved_domain: str,
    expert: ExpertConfig,
    max_chunks: int,
    max_context_length: int,
) -> _KnowledgeResult:
    """Load the knowledge base and search for relevant chunks."""
    knowledge_path = _resolve_knowledge_path(expert)

    # Handle missing knowledge directory for business experts gracefully.
    if not expert.is_builtin and not knowledge_path.exists():
        logger.info(
            "business_knowledge_dir_missing",
            domain=resolved_domain,
            path=str(knowledge_path),
        )
        return _KnowledgeResult(chunks=[], context="", sources=[])

    index_dir = None
    tech_stack_boost = 1.2
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        domain_slug = sanitize_domain_for_path(resolved_domain)
        index_dir = settings.project_root / ".tapps-mcp" / "rag_index" / domain_slug
        tech_stack_boost = settings.tech_stack_boost
    except Exception as e:
        logger.debug("rag_index_dir_skip", reason=str(e))

    kb = VectorKnowledgeBase(
        knowledge_path,
        domain=resolved_domain,
        index_dir=index_dir,
    )

    chunks = kb.search(question, max_results=max_chunks)

    # Apply tech stack boost to chunk scores (Epic 54).
    chunks = _apply_tech_stack_boost(chunks, resolved_domain, tech_stack_boost)

    context = kb.get_context(question, max_length=max_context_length) if chunks else ""
    sources = kb.get_sources(question, max_results=max_chunks)
    return _KnowledgeResult(chunks=chunks, context=context, sources=sources)


def _unique_top_sources(chunks: list[Any], limit: int = 3) -> list[str]:
    """Extract unique source file names from the top *limit* chunks.

    Preserves insertion order while deduplicating.
    """
    sources: list[str] = []
    seen: set[str] = set()
    for chunk in chunks[:limit]:
        if chunk.source_file not in seen:
            seen.add(chunk.source_file)
            sources.append(chunk.source_file)
    return sources


def _parse_frontmatter_last_reviewed_utc(content: str) -> datetime | None:
    """Return UTC midnight for ``last_reviewed`` in YAML frontmatter, if present.

    Optional frontmatter (first lines of a knowledge markdown file)::

        ---
        last_reviewed: 2026-03-24
        ---

    When set, freshness uses ``max(mtime_age, review_age)`` so a recent file
    touch does not hide an old editorial review date.
    """
    stripped = content.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return None
    end = stripped.find("\n---", 3)
    if end == -1:
        return None
    block = stripped[3:end]
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() != "last_reviewed":
            continue
        val = value.strip().strip('"').strip("'")
        if not val:
            return None
        try:
            day = date.fromisoformat(val[:10])
        except ValueError:
            return None
        return datetime(day.year, day.month, day.day, tzinfo=UTC)
    return None


def _collect_source_ages(
    sources: list[str],
    knowledge_base_path: Path,
) -> list[int]:
    """Compute effective ages in days for each source that exists on disk.

    Effective age is ``max(mtime age, last_reviewed age)`` when the file declares
    ``last_reviewed`` in YAML frontmatter; otherwise mtime age only.

    Silently skips missing files and files that cannot be stat'd.
    """
    now = datetime.now(tz=UTC)
    ages_days: list[int] = []
    for source in sources:
        source_path = knowledge_base_path / source
        if not source_path.exists():
            continue
        try:
            mtime = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
            m_age = (now - mtime).days
        except OSError:
            continue
        try:
            raw = source_path.read_text(encoding="utf-8")
        except OSError:
            ages_days.append(m_age)
            continue
        reviewed_at = _parse_frontmatter_last_reviewed_utc(raw)
        if reviewed_at is None:
            ages_days.append(m_age)
        else:
            r_age = (now - reviewed_at).days
            ages_days.append(max(m_age, r_age))
    return ages_days


def _check_freshness(
    knowledge: _KnowledgeResult,
    knowledge_base_path: Path,
) -> _FreshnessResult:
    """Check freshness of retrieved knowledge source files.

    Examines each source file's effective age: ``max(mtime, last_reviewed)``
    when optional YAML frontmatter includes ``last_reviewed: YYYY-MM-DD``;
    otherwise mtime only. If all top chunks (up to 3) come from files whose
    effective age exceeds ``_STALE_KNOWLEDGE_DAYS``, marks the knowledge as
    stale and produces a caveat message.
    """
    if not knowledge.chunks:
        return _FreshnessResult()

    top_sources = _unique_top_sources(knowledge.chunks)
    if not top_sources:
        return _FreshnessResult()

    ages_days = _collect_source_ages(top_sources, knowledge_base_path)
    if not ages_days:
        return _FreshnessResult()

    oldest_age = max(ages_days)
    all_stale = all(age > _STALE_KNOWLEDGE_DAYS for age in ages_days)

    if all_stale:
        caveat = (
            f"Note: Retrieved knowledge may be outdated (oldest source: {oldest_age} days). "
            "Consider verifying with tapps_lookup_docs() for the latest documentation."
        )
        return _FreshnessResult(
            stale_knowledge=True,
            oldest_chunk_age_days=oldest_age,
            freshness_caveat=caveat,
        )

    return _FreshnessResult(oldest_chunk_age_days=oldest_age)


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

    # Persona preamble (Epic 69) — prepended when expert has a persona defined.
    persona_line = ""
    if expert.persona:
        persona_line = f"*{expert.persona}*\n\n"
    # Critical rules (Epic 71) — prepended after persona when expert has rules defined.
    rules_line = ""
    if expert.critical_rules:
        rules_line = f"**Critical rules:** {expert.critical_rules}\n\n"
    # Communication style (Epic 73) — appended after persona and rules.
    style_line = ""
    if expert.communication_style:
        style_line = f"*Style: {expert.communication_style}*\n\n"

    if knowledge.context:
        result.answer = (
            f"## {expert.expert_name} \u2014 {resolved_domain}\n\n"
            f"{persona_line}"
            f"{rules_line}"
            f"{style_line}"
            f"Based on domain knowledge ({len(knowledge.chunks)} source(s), "
            f"confidence {conf.confidence:.0%}):\n\n"
            f"{knowledge.context}"
        )
    else:
        result.suggested_library, result.suggested_topic = _infer_lookup_hints(
            question, resolved_domain
        )
        # Only suggest docs lookup when the question is API-specific (non-empty hints).
        if result.suggested_library:
            result.suggested_tool = "tapps_lookup_docs"
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
        else:
            # Architectural question — docs lookup would return off-topic results.
            result.answer = (
                f"## {expert.expert_name} \u2014 {resolved_domain}\n\n"
                f"No specific knowledge found for this query in the "
                f"{resolved_domain} knowledge base. This appears to be an "
                f"architectural/conceptual question — consider adding domain "
                f"knowledge files to `experts/knowledge/{resolved_domain}/` "
                f"for better coverage."
            )

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

    # Freshness check: detect stale knowledge sources.
    kb_path = _resolve_knowledge_path(resolved.expert)
    freshness = _check_freshness(knowledge, kb_path)

    conf = _compute_confidence(question, knowledge, resolved.domain)
    answer_result = _build_answer(
        question, resolved.expert, resolved.domain, knowledge, conf
    )

    # Append freshness caveat to answer when knowledge is stale.
    answer = answer_result.answer
    if freshness.freshness_caveat:
        answer = f"{answer}\n\n---\n\n**{freshness.freshness_caveat}**"

    recommendation = _build_recommendation(
        conf, answer_result.suggested_library, answer_result.suggested_topic
    )

    return ConsultationResult(
        domain=resolved.domain,
        expert_id=resolved.expert.expert_id,
        expert_name=resolved.expert.expert_name,
        answer=answer,
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
        adaptive_domain_used=resolved.adaptive_domain_used,
        stale_knowledge=freshness.stale_knowledge,
        oldest_chunk_age_days=freshness.oldest_chunk_age_days,
        freshness_caveat=freshness.freshness_caveat,
    )


def list_experts() -> list[ExpertInfo]:
    """Return info for every registered expert, including knowledge-file counts."""
    results: list[ExpertInfo] = []

    for expert in ExpertRegistry.get_all_experts_merged():
        kb_path = _resolve_knowledge_path(expert)
        file_count = len(list(kb_path.rglob("*.md"))) if kb_path.exists() else 0

        results.append(
            ExpertInfo(
                expert_id=expert.expert_id,
                expert_name=expert.expert_name,
                primary_domain=expert.primary_domain,
                description=expert.description,
                rag_enabled=expert.rag_enabled,
                knowledge_files=file_count,
                is_builtin=expert.is_builtin,
                keywords=expert.keywords,
                persona=expert.persona,
                critical_rules=expert.critical_rules,
                communication_style=expert.communication_style,
            )
        )
    return results

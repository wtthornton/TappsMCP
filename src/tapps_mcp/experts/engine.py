"""Expert consultation engine — orchestrates RAG lookup and confidence scoring.

This is the main entry point for expert consultations.  It:

1. Detects the best domain for the user's question.
2. Loads the domain's knowledge base (RAG).
3. Searches for relevant chunks.
4. Computes a confidence score.
5. Returns a :class:`ConsultationResult`.
"""

from __future__ import annotations

import structlog

from tapps_mcp.experts.confidence import (
    compute_chunk_coverage,
    compute_confidence,
    compute_rag_quality,
)
from tapps_mcp.experts.domain_detector import DomainDetector
from tapps_mcp.experts.domain_utils import sanitize_domain_for_path
from tapps_mcp.experts.models import (
    ConfidenceFactors,
    ConsultationResult,
    ExpertInfo,
)
from tapps_mcp.experts.rag import SimpleKnowledgeBase, _extract_keywords
from tapps_mcp.experts.registry import ExpertRegistry

logger = structlog.get_logger(__name__)


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
    if domain:
        resolved_domain = domain
    else:
        mappings = DomainDetector.detect_from_question(question)
        resolved_domain = mappings[0].domain if mappings else "software-architecture"

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
    knowledge_dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
    knowledge_path = ExpertRegistry.get_knowledge_base_path() / knowledge_dir_name
    kb = SimpleKnowledgeBase(knowledge_path)

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
    if context:
        answer = (
            f"## {expert.expert_name} — {resolved_domain}\n\n"
            f"Based on domain knowledge ({len(chunks)} source(s), "
            f"confidence {confidence:.0%}):\n\n"
            f"{context}"
        )
    else:
        answer = (
            f"## {expert.expert_name} — {resolved_domain}\n\n"
            f"No specific knowledge found for this query in the "
            f"{resolved_domain} knowledge base.  The expert can still "
            f"provide general guidance based on domain principles."
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

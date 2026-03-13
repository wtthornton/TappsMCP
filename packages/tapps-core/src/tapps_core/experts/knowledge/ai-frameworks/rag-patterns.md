# RAG (Retrieval-Augmented Generation) Patterns

## Overview

Retrieval-Augmented Generation combines LLM capabilities with external knowledge retrieval, enabling accurate, up-to-date, and source-grounded responses. This guide covers architecture patterns, chunking strategies, and quality optimization.

## Core Architecture

### Pattern 1: Basic RAG Pipeline

```python
from dataclasses import dataclass

@dataclass
class RetrievedChunk:
    content: str
    source: str
    score: float

class RAGPipeline:
    """Standard RAG pipeline: embed -> retrieve -> generate."""

    def __init__(self, embedder, vector_store, llm_client):
        self.embedder = embedder
        self.vector_store = vector_store
        self.llm = llm_client

    async def query(self, question: str, top_k: int = 5) -> str:
        # 1. Embed the query
        query_embedding = await self.embedder.embed(question)

        # 2. Retrieve relevant chunks
        chunks = await self.vector_store.search(query_embedding, top_k=top_k)

        # 3. Build context-augmented prompt
        context = "\n\n".join(c.content for c in chunks)
        prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"

        # 4. Generate response
        return await self.llm.complete(prompt)
```

### Pattern 2: Hybrid Search (Vector + Keyword)

```python
class HybridRetriever:
    """Combine vector similarity with BM25 keyword search."""

    def __init__(self, vector_store, keyword_index, alpha: float = 0.7):
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.alpha = alpha  # Weight for vector vs keyword

    async def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        # Get results from both
        vector_results = await self.vector_store.search(query, top_k=top_k * 2)
        keyword_results = await self.keyword_index.search(query, top_k=top_k * 2)

        # Reciprocal rank fusion
        scores: dict[str, float] = {}
        for rank, chunk in enumerate(vector_results):
            scores[chunk.source] = scores.get(chunk.source, 0) + self.alpha / (rank + 60)
        for rank, chunk in enumerate(keyword_results):
            scores[chunk.source] = scores.get(chunk.source, 0) + (1 - self.alpha) / (rank + 60)

        # Sort by fused score, return top_k
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return [c for c in vector_results + keyword_results if c.source in sorted_ids]
```

## Document Processing

### Chunking Strategies

**1. Fixed-Size Chunking:**
```python
def chunk_fixed(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Split text into fixed-size overlapping chunks."""
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks
```

**2. Semantic Chunking (by section/paragraph):**
```python
import re

def chunk_semantic(text: str, max_size: int = 1000) -> list[str]:
    """Split on semantic boundaries (headings, paragraphs)."""
    sections = re.split(r"\n#{1,3}\s", text)
    chunks = []
    current = ""

    for section in sections:
        if len(current) + len(section) > max_size and current:
            chunks.append(current.strip())
            current = ""
        current += "\n" + section

    if current.strip():
        chunks.append(current.strip())
    return chunks
```

**3. Code-Aware Chunking:**
```python
import ast

def chunk_python_file(source: str) -> list[str]:
    """Chunk Python file by function/class boundaries."""
    tree = ast.parse(source)
    chunks = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = node.end_lineno or start + 1
            chunk = "\n".join(lines[start:end])
            chunks.append(chunk)

    return chunks
```

## Quality Optimization

### Pattern 1: Re-Ranking

```python
class CrossEncoderReranker:
    """Re-rank retrieved chunks using a cross-encoder model."""

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 3,
    ) -> list[RetrievedChunk]:
        scored = []
        for chunk in chunks:
            score = await self.cross_encoder.predict(query, chunk.content)
            scored.append((score, chunk))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [chunk for _, chunk in scored[:top_k]]
```

### Pattern 2: Query Expansion

```python
async def expand_query(llm: LLMClient, original_query: str) -> list[str]:
    """Generate multiple search queries from a single question."""
    prompt = (
        f"Generate 3 different search queries that would help answer: {original_query}\n"
        "Return one query per line."
    )
    expanded = await llm.complete(prompt)
    queries = [original_query] + expanded.strip().splitlines()
    return queries
```

### Pattern 3: Source Attribution

```python
async def generate_with_citations(
    llm: LLMClient,
    question: str,
    chunks: list[RetrievedChunk],
) -> str:
    """Generate answer with inline source citations."""
    numbered_context = "\n".join(
        f"[{i+1}] {c.content} (source: {c.source})"
        for i, c in enumerate(chunks)
    )
    prompt = (
        f"Answer the question using the provided sources. "
        f"Cite sources using [N] notation.\n\n"
        f"Sources:\n{numbered_context}\n\n"
        f"Question: {question}"
    )
    return await llm.complete(prompt)
```

## Best Practices

1. **Chunk size**: 256-1024 tokens works well for most use cases
2. **Overlap**: 10-20% overlap prevents information loss at boundaries
3. **Metadata**: Store source file, section, timestamp with each chunk
4. **Freshness**: Re-index on content changes; use cache invalidation
5. **Evaluation**: Measure retrieval precision@k and answer faithfulness
6. **Embedding models**: Use task-specific models (e.g., retrieval-optimized)
7. **Context window**: Don't exceed 30-50% of the LLM's context with retrieved content

## Advanced RAG Patterns (2025-2026)

### GraphRAG and Knowledge Graphs

GraphRAG combines vector retrieval with knowledge graph traversal for richer context:

```python
class GraphRAGPipeline:
    """RAG pipeline augmented with knowledge graph relationships."""

    def __init__(self, vector_store, knowledge_graph, llm_client):
        self.vector_store = vector_store
        self.kg = knowledge_graph
        self.llm = llm_client

    async def query(self, question: str, top_k: int = 5) -> str:
        # 1. Retrieve relevant chunks via vector search
        chunks = await self.vector_store.search(question, top_k=top_k)

        # 2. Extract entities from chunks and traverse graph
        entities = extract_entities(chunks)
        related = await self.kg.get_neighbors(entities, hops=2)

        # 3. Combine vector context with graph context
        graph_context = format_graph_relations(related)
        vector_context = "\n\n".join(c.content for c in chunks)

        prompt = (
            f"Knowledge graph context:\n{graph_context}\n\n"
            f"Retrieved passages:\n{vector_context}\n\n"
            f"Question: {question}"
        )
        return await self.llm.complete(prompt)
```

**When to use GraphRAG:**
- Multi-hop reasoning ("How does X relate to Y through Z?")
- Entity-centric queries (people, products, concepts)
- Domain-specific knowledge bases with structured relationships

### Agentic RAG

Agents that dynamically decide when and how to retrieve, rather than always retrieving:

```python
class AgenticRAGAgent:
    """Agent that decides retrieval strategy dynamically."""

    async def answer(self, question: str) -> str:
        # Agent decides: retrieve, decompose, or answer directly
        plan = await self.plan_retrieval(question)

        if plan.strategy == "direct":
            return await self.llm.complete(question)

        if plan.strategy == "decompose":
            # Break complex question into sub-queries
            sub_questions = plan.sub_queries
            sub_answers = []
            for sq in sub_questions:
                chunks = await self.retrieve(sq)
                sub_answers.append(await self.answer_with_context(sq, chunks))
            return await self.synthesize(question, sub_answers)

        if plan.strategy == "iterative":
            # Retrieve, evaluate, retrieve more if needed
            context = []
            for _ in range(plan.max_iterations):
                chunks = await self.retrieve(question, exclude=context)
                context.extend(chunks)
                if await self.has_sufficient_context(question, context):
                    break
            return await self.answer_with_context(question, context)
```

### Hybrid Search as Standard Practice

Hybrid search (dense vectors + sparse/keyword) is now the default recommendation:

- **Dense vectors** (embeddings): Capture semantic similarity
- **Sparse vectors** (BM25/SPLADE): Capture exact keyword matches
- **Reciprocal Rank Fusion (RRF)**: Standard method to combine ranked lists
- Most vector databases (Qdrant, Weaviate, Pinecone) now support hybrid search natively

### ColBERT and Late Interaction Models

ColBERT-style models gaining traction for high-quality retrieval:

```python
class ColBERTRetriever:
    """Late interaction retrieval using per-token embeddings."""

    async def search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        # Encode query into per-token embeddings
        query_embeddings = self.model.encode_query(query)  # (num_query_tokens, dim)

        # MaxSim: for each query token, find max similarity with any doc token
        # Score = sum of MaxSim across query tokens
        candidates = await self.index.search(query_embeddings, top_k=top_k)
        return candidates
```

**Advantages over bi-encoder (single-vector) retrieval:**
- Per-token interaction captures fine-grained matching
- Better handling of multi-aspect queries
- ~2-5x better recall on complex queries, with moderate latency increase

### Contextual Retrieval (Anthropic)

Prepend document-level context to each chunk before embedding:

```
Original chunk: "Revenue grew 15% year-over-year."
Contextualized: "From Acme Corp Q3 2025 earnings report: Revenue grew 15% year-over-year."
```

This simple technique reduces retrieval failures by 49% (per Anthropic benchmarks) by disambiguating chunks that lack standalone context.

## Anti-Patterns

1. **Stuffing entire documents** into context instead of relevant chunks
2. **No re-ranking** - returning raw vector similarity results without filtering
3. **Ignoring chunk boundaries** - splitting mid-sentence or mid-code-block
4. **Stale indexes** - not refreshing embeddings when source content changes
5. **No fallback** - failing silently when retrieval returns no relevant results
6. **Vector-only retrieval** - not using hybrid search; misses exact keyword matches
7. **Static retrieval strategy** - always retrieving the same way regardless of query type

## References

- [LangChain RAG Documentation](https://python.langchain.com/docs/tutorials/rag/)
- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [Anthropic Contextual Retrieval](https://docs.anthropic.com/en/docs/build-with-claude/retrieval-augmented-generation)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [ColBERT Documentation](https://github.com/stanford-futuredata/ColBERT)
- [RAGAs Evaluation Framework](https://docs.ragas.io/)

# LLM Integration Patterns

## Overview

This guide covers best practices for integrating Large Language Models (LLMs) into applications, including API usage, error handling, structured output, and cost management.

## API Integration

### Pattern 1: Client Initialization with Retry

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMClient:
    """Resilient LLM API client with retries and timeout."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def complete(self, messages: list[dict], model: str) -> str:
        response = await self._client.post(
            "/v1/messages",
            json={"model": model, "messages": messages, "max_tokens": 4096},
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]
```

### Pattern 2: Structured Output with Pydantic

```python
from pydantic import BaseModel

class CodeReview(BaseModel):
    summary: str
    issues: list[str]
    score: int  # 0-100

async def get_structured_review(client: LLMClient, code: str) -> CodeReview:
    """Get structured code review from LLM."""
    messages = [
        {"role": "user", "content": f"Review this code and respond in JSON:\n{code}"},
    ]
    raw = await client.complete(messages, model="claude-sonnet-4-5-20250929")
    return CodeReview.model_validate_json(raw)
```

### Pattern 3: Streaming Responses

```python
import httpx
from collections.abc import AsyncIterator

async def stream_completion(
    client: httpx.AsyncClient,
    messages: list[dict],
    model: str,
) -> AsyncIterator[str]:
    """Stream LLM responses token by token."""
    async with client.stream(
        "POST",
        "/v1/messages",
        json={"model": model, "messages": messages, "stream": True},
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                chunk = json.loads(line[6:])
                if chunk["type"] == "content_block_delta":
                    yield chunk["delta"]["text"]
```

## Tool Use / Function Calling

### Pattern 1: Tool Definition

```python
tools = [
    {
        "name": "search_codebase",
        "description": "Search the codebase for a pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search pattern"},
                "file_type": {"type": "string", "description": "File extension filter"},
            },
            "required": ["query"],
        },
    }
]
```

### Pattern 2: Tool Dispatch Loop

```python
async def agent_loop(client: LLMClient, messages: list[dict]) -> str:
    """Run agent loop with tool use until completion."""
    while True:
        response = await client.complete_with_tools(messages, tools)

        if response.stop_reason == "end_turn":
            return response.content

        # Process tool calls
        for tool_use in response.tool_calls:
            result = await dispatch_tool(tool_use.name, tool_use.input)
            messages.append({"role": "tool", "content": result, "tool_use_id": tool_use.id})
```

## Error Handling

### Pattern 1: Rate Limit Handling

```python
import asyncio

async def rate_limited_call(client: LLMClient, messages: list[dict]) -> str:
    """Handle rate limits with exponential backoff."""
    for attempt in range(5):
        try:
            return await client.complete(messages)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = float(e.response.headers.get("retry-after", 2 ** attempt))
                await asyncio.sleep(retry_after)
            else:
                raise
    raise RuntimeError("Exceeded rate limit retries")
```

### Pattern 2: Graceful Degradation

```python
async def complete_with_fallback(
    primary: LLMClient,
    fallback: LLMClient,
    messages: list[dict],
) -> str:
    """Try primary model, fall back to secondary on failure."""
    try:
        return await primary.complete(messages, model="claude-sonnet-4-5-20250929")
    except (httpx.HTTPStatusError, httpx.TimeoutException):
        return await fallback.complete(messages, model="claude-haiku-4-5-20251001")
```

## Cost Management

### Best Practices

1. **Token budgeting**: Set `max_tokens` appropriately per use case
2. **Prompt caching**: Reuse system prompts with caching headers
3. **Model tiering**: Use smaller models for simple tasks, larger for complex
4. **Batch processing**: Group related requests to amortize system prompt costs
5. **Response truncation**: Request only needed fields via structured output

### Pattern: Token-Aware Batching

```python
def estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars for English)."""
    return len(text) // 4

async def batch_within_budget(
    items: list[str],
    budget_tokens: int,
    client: LLMClient,
) -> list[str]:
    """Process items in batches that fit within token budget."""
    results: list[str] = []
    batch: list[str] = []
    batch_tokens = 0

    for item in items:
        item_tokens = estimate_tokens(item)
        if batch_tokens + item_tokens > budget_tokens and batch:
            results.extend(await process_batch(client, batch))
            batch, batch_tokens = [], 0
        batch.append(item)
        batch_tokens += item_tokens

    if batch:
        results.extend(await process_batch(client, batch))
    return results
```

## Security

### API Key Management

- **Never** hardcode API keys in source code
- Use environment variables or secret managers
- Rotate keys periodically
- Use separate keys for development and production
- Monitor API key usage for anomalies

### Prompt Injection Prevention

```python
def sanitize_user_input(user_input: str) -> str:
    """Basic input sanitization for LLM prompts."""
    # Remove potential injection markers
    sanitized = user_input.replace("```", "")
    # Limit length
    max_chars = 10000
    return sanitized[:max_chars]

def build_safe_prompt(system: str, user_input: str) -> list[dict]:
    """Build prompt with clear role separation."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": sanitize_user_input(user_input)},
    ]
```

## References

- [Anthropic API Documentation](https://docs.anthropic.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

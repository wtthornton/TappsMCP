"""Markdown-aware document chunker for RAG knowledge retrieval.

Splits markdown files into overlapping chunks of configurable token size,
respecting header boundaries where possible.
"""

from __future__ import annotations

import hashlib
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A single chunk of a knowledge document."""

    content: str = Field(description="Chunk text content.")
    source_file: str = Field(description="Source file path (as string for JSON serialization).")
    line_start: int = Field(ge=1, description="Start line (1-indexed).")
    line_end: int = Field(ge=1, description="End line (1-indexed).")
    chunk_id: str = Field(description="Deterministic content hash (hex, 16 chars).")
    token_count: int = Field(ge=0, description="Approximate token count.")


# Approximate conversion: ~4 chars per token.
_CHARS_PER_TOKEN = 4


class Chunker:
    """Splits markdown content into overlapping chunks.

    Respects header boundaries and produces chunks of approximately
    *target_tokens* tokens with *overlap_tokens* overlap.
    """

    def __init__(
        self,
        target_tokens: int = 512,
        overlap_tokens: int = 50,
    ) -> None:
        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._target_chars = target_tokens * _CHARS_PER_TOKEN
        self._overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    def chunk_file(self, file_path: Path, content: str) -> list[Chunk]:
        """Split *content* into chunks, attributing them to *file_path*.

        Returns an empty list for empty content.
        """
        if not content.strip():
            return []

        lines = content.split("\n")
        chunks: list[Chunk] = []
        current_lines: list[str] = []
        current_chars = 0
        chunk_start_line = 1

        for i, line in enumerate(lines, start=1):
            line_chars = len(line) + 1  # +1 for newline
            is_header = line.strip().startswith("#")

            # Start a new chunk if this header would exceed the target.
            if is_header and current_chars > 0 and current_chars + line_chars > self._target_chars:
                chunk = self._build_chunk(file_path, current_lines, chunk_start_line)
                if chunk is not None:
                    chunks.append(chunk)

                # Overlap: keep the tail of the previous chunk.
                overlap_lines = self._get_overlap_lines(current_lines)
                current_lines = overlap_lines
                current_chars = sum(len(ln) + 1 for ln in current_lines)
                chunk_start_line = i - len(overlap_lines)

            current_lines.append(line)
            current_chars += line_chars

            # Non-header split at target size.
            if current_chars >= self._target_chars:
                chunk = self._build_chunk(file_path, current_lines, chunk_start_line)
                if chunk is not None:
                    chunks.append(chunk)

                overlap_lines = self._get_overlap_lines(current_lines)
                current_lines = overlap_lines
                current_chars = sum(len(ln) + 1 for ln in current_lines)
                chunk_start_line = i + 1 - len(overlap_lines)

        # Final chunk.
        if current_lines:
            chunk = self._build_chunk(file_path, current_lines, chunk_start_line)
            if chunk is not None:
                chunks.append(chunk)

        return chunks

    def _get_overlap_lines(self, lines: list[str]) -> list[str]:
        """Return the trailing lines that fit within the overlap budget."""
        overlap_lines: list[str] = []
        chars = 0
        for line in reversed(lines):
            chars += len(line) + 1
            if chars > self._overlap_chars:
                break
            overlap_lines.insert(0, line)
        return overlap_lines

    def _build_chunk(
        self,
        file_path: Path,
        lines: list[str],
        start_line: int,
    ) -> Chunk | None:
        """Construct a :class:`Chunk` from accumulated lines."""
        text = "\n".join(lines).strip()
        if not text:
            return None

        end_line = start_line + len(lines) - 1
        token_count = max(1, len(text) // _CHARS_PER_TOKEN)

        return Chunk(
            content=text,
            source_file=str(file_path),
            line_start=max(1, start_line),
            line_end=max(1, end_line),
            chunk_id=_generate_chunk_id(file_path, start_line, end_line, text),
            token_count=token_count,
        )


def _generate_chunk_id(
    file_path: Path,
    line_start: int,
    line_end: int,
    content: str,
) -> str:
    """Return a deterministic 16-char hex hash for a chunk."""
    raw = f"{file_path}:{line_start}-{line_end}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

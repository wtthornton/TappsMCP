"""Base protocol for source code extractors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from docs_mcp.extractors.models import ModuleInfo


class Extractor(Protocol):
    """Protocol that all source code extractors must implement."""

    def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
        """Extract structured information from a source file."""
        ...

    def can_handle(self, file_path: Path) -> bool:
        """Return True if this extractor can handle the given file type."""
        ...

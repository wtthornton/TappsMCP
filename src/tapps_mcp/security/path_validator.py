"""Path validation for TappsMCP file operations.

Ensures all file operations occur within the configured project root boundary.
Rejects symlinks that escape the boundary and path traversal attempts.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.common.exceptions import PathValidationError


class PathValidator:
    """Validates file paths against the project root boundary.

    All file-path-accepting tools MUST validate paths through this class
    before performing any I/O.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def validate_path(
        self,
        file_path: str | Path,
        *,
        must_exist: bool = True,
        max_file_size: int | None = 10 * 1024 * 1024,
    ) -> Path:
        """Validate a file path against the project root.

        Args:
            file_path: Path to validate (relative or absolute).
            must_exist: If ``True``, the file must already exist.
            max_file_size: Maximum allowed file size in bytes.  ``None``
                disables the check.

        Returns:
            Resolved absolute ``Path``.

        Raises:
            PathValidationError: If the path fails validation.
            FileNotFoundError: If *must_exist* is ``True`` and the file
                does not exist.
        """
        path = Path(file_path)

        # Check for traversal patterns in the raw input
        self._check_traversal_patterns(path)

        # Resolve relative paths against project root
        # (so Docker/remote clients can send "src/foo.py")
        if not path.is_absolute():
            path = (self.project_root / path).resolve()

        # Resolve to an absolute, canonical path (follows symlinks atomically,
        # eliminating TOCTOU between is_symlink() and resolve())
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise PathValidationError(f"Cannot resolve path {file_path}: {exc}") from exc

        # Boundary check (resolve() already followed symlinks)
        if not self._is_within_root(resolved):
            raise PathValidationError(
                f"Path outside project root: {resolved}. Project root: {self.project_root}"
            )

        # Existence check
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Size check
        if max_file_size is not None and resolved.exists() and resolved.is_file():
            file_size = resolved.stat().st_size
            if file_size > max_file_size:
                raise PathValidationError(
                    f"File too large: {file_size} bytes (max {max_file_size} bytes)"
                )

        return resolved

    def validate_read_path(
        self,
        file_path: str | Path,
        max_file_size: int | None = 10 * 1024 * 1024,
    ) -> Path:
        """Validate a path for read operations (must exist)."""
        return self.validate_path(file_path, must_exist=True, max_file_size=max_file_size)

    def validate_write_path(self, file_path: str | Path) -> Path:
        """Validate a path for write operations (need not exist yet)."""
        return self.validate_path(file_path, must_exist=False, max_file_size=None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_within_root(self, resolved_path: Path) -> bool:
        try:
            resolved_path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _check_traversal_patterns(file_path: Path) -> None:
        path_str = str(file_path)

        # Literal directory traversal
        if ".." in file_path.parts:
            raise PathValidationError(f"Directory traversal ('..') in path: {file_path}")

        # URL-encoded traversal
        suspicious = ["%2e%2e", "%2f", "%5c"]
        if any(p in path_str.lower() for p in suspicious):
            raise PathValidationError(f"Suspicious encoded pattern in path: {file_path}")

        # Null bytes
        if "\x00" in path_str:
            raise PathValidationError(f"Null byte in path: {file_path}")


def assert_write_allowed(
    path: str | Path,
    project_root: str | Path,
    allowed_prefixes: list[str] | None = None,
) -> None:
    """Assert that a write to *path* is within project root and allowed prefixes.

    When *allowed_prefixes* is non-empty the first component of the path
    relative to *project_root* must be one of the listed prefixes (e.g.
    ``["src", "tests", "docs"]``).

    Raises:
        PathValidationError: If the write is not allowed.
    """
    resolved = Path(path).resolve()
    root = Path(project_root).resolve()

    try:
        rel = resolved.relative_to(root)
    except ValueError:
        raise PathValidationError(
            f"Write path {resolved} is not under project root {root}"
        ) from None

    if not allowed_prefixes:
        return

    parts = rel.parts
    if not parts:
        return  # root itself

    if parts[0] not in allowed_prefixes:
        raise PathValidationError(
            f"Write path {resolved} is not under an allowed prefix. "
            f"Allowed: {allowed_prefixes}. First component: {parts[0]}"
        )

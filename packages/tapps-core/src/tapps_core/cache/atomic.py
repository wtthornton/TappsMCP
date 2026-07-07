"""Atomic JSON file primitive (TAP-4556, ADR-0029).

The single read / write / atomic-replace primitive shared across tapps caches,
replacing the hand-rolled ``_write_atomic`` copies. Mechanics only — it holds no
staleness or provider opinion (those are ``StalenessStrategy`` and each cache's
own provider, per ADR-0029). A cache is not a retriever: this never fetches,
embeds, or decides freshness.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class AtomicJsonCache:
    """Atomic file read/write via ``tempfile`` + ``os.replace``.

    The class is a namespace of static methods, not a stateful cache: every call
    targets an explicit path, so single-file callers (the code-graph index) and
    directory-of-entries callers (the docs cache) share one implementation.
    """

    @staticmethod
    def write_text(target: Path, content: str) -> None:
        """Write *content* to *target* atomically.

        The temp file is created in *target*'s directory so ``os.replace`` is
        atomic on the same filesystem. On any failure the partial temp file is
        removed and *target* is left untouched (readers never see a half-written
        file).
        """
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=".tmp_",
            suffix=target.suffix,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            Path(tmp_path).replace(target)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise

    @staticmethod
    def write_json(
        target: Path,
        obj: Any,
        *,
        indent: int | None = 2,
        sort_keys: bool = False,
    ) -> None:
        """Serialize *obj* to JSON and write it atomically to *target*.

        ``indent`` / ``sort_keys`` mirror :func:`json.dumps` so a caller
        migrating onto this primitive preserves its existing on-disk byte layout.
        """
        AtomicJsonCache.write_text(target, json.dumps(obj, indent=indent, sort_keys=sort_keys))

    @staticmethod
    def read_json(path: Path) -> Any | None:
        """Return the parsed JSON at *path*, or ``None`` if absent or unreadable.

        A missing file or malformed JSON returns ``None`` rather than raising — a
        derived cache treats an unreadable entry as a miss and rebuilds it.
        """
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

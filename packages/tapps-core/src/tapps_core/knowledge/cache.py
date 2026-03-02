"""KB cache — file-based documentation cache with TTL and atomic writes.

Stores documentation as markdown files with metadata in JSON sidecars.
Uses ``filelock`` for cross-platform file locking (Windows compatible).
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import structlog
from filelock import FileLock

from tapps_core.knowledge.models import CacheEntry

logger = structlog.get_logger(__name__)

# Default TTL: 24 hours
DEFAULT_TTL_SECONDS: float = 86_400.0

# Staleness policies: library → TTL override in seconds
DEFAULT_STALENESS_POLICIES: dict[str, float] = {
    # Fast-moving libraries get shorter TTL
    "next": 43_200.0,  # 12h
    "react": 43_200.0,
    "vue": 43_200.0,
    "svelte": 43_200.0,
    # Stable libraries get longer TTL
    "python": 172_800.0,  # 48h
    "flask": 172_800.0,
    "django": 172_800.0,
    "sqlalchemy": 172_800.0,
}


def _safe_name(name: str) -> str:
    """Sanitise a string for use as a filename component."""
    return name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_").lower()


@dataclass
class CacheStats:
    """Aggregate cache statistics."""

    total_entries: int = 0
    total_size_bytes: int = 0
    hits: int = 0
    misses: int = 0
    stale_entries: int = 0


@dataclass
class KBCache:
    """File-based knowledge base cache.

    Directory layout::

        cache_dir/
          {library}/
            {topic}.md        — documentation content
            {topic}.meta.json — metadata sidecar
            {topic}.lock      — filelock
    """

    cache_dir: Path
    default_ttl: float = DEFAULT_TTL_SECONDS
    staleness_policies: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_STALENESS_POLICIES)
    )
    _stats: CacheStats = field(default_factory=CacheStats, init=False, repr=False)

    # Class-level lock timeout (seconds)
    LOCK_TIMEOUT: ClassVar[float] = 5.0

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, library: str, topic: str = "overview") -> CacheEntry | None:
        """Retrieve a cache entry, or ``None`` if not found.

        Does NOT check staleness — the caller decides how to handle stale data.
        """
        meta_path = self._meta_path(library, topic)
        content_path = self._content_path(library, topic)

        if not meta_path.exists() or not content_path.exists():
            self._stats.misses += 1
            return None

        lock = FileLock(str(self._lock_path(library, topic)), timeout=self.LOCK_TIMEOUT)
        try:
            with lock:
                meta = self._read_meta(meta_path)
                if meta is None:
                    self._stats.misses += 1
                    return None
                content = content_path.read_text(encoding="utf-8")

                # Update hit count inside the lock to avoid races
                new_hits = meta.get("cache_hits", 0) + 1
                meta["cache_hits"] = new_hits
                self._write_meta_atomic(meta_path, meta)
        except TimeoutError:
            logger.warning("cache_lock_timeout", library=library, topic=topic)
            self._stats.misses += 1
            return None

        # Record access timestamp for LRU eviction
        key = f"{library}/{topic}"
        access_meta = self._load_metadata()
        access_meta[key] = time.time()
        self._save_metadata(access_meta)

        entry = CacheEntry(
            library=meta.get("library", library),
            topic=meta.get("topic", topic),
            content=content,
            context7_id=meta.get("context7_id"),
            provider_source=meta.get("provider_source"),
            snippet_count=meta.get("snippet_count", 0),
            token_count=meta.get("token_count", 0),
            cached_at=meta.get("cached_at"),
            fetched_at=meta.get("fetched_at"),
            cache_hits=new_hits,
        )

        self._stats.hits += 1
        return entry

    def put(self, entry: CacheEntry) -> None:
        """Write or update a cache entry atomically."""
        lib_dir = self._lib_dir(entry.library)
        lib_dir.mkdir(parents=True, exist_ok=True)

        content_path = self._content_path(entry.library, entry.topic)
        meta_path = self._meta_path(entry.library, entry.topic)
        lock = FileLock(str(self._lock_path(entry.library, entry.topic)), timeout=self.LOCK_TIMEOUT)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        meta = {
            "library": entry.library,
            "topic": entry.topic,
            "context7_id": entry.context7_id,
            "provider_source": entry.provider_source,
            "snippet_count": entry.snippet_count,
            "token_count": entry.token_count,
            "cached_at": now,
            "fetched_at": entry.fetched_at or now,
            "cache_hits": entry.cache_hits,
        }

        try:
            with lock:
                self._write_atomic(content_path, entry.content)
                self._write_meta_atomic(meta_path, meta)
        except TimeoutError:
            logger.warning("cache_write_lock_timeout", library=entry.library, topic=entry.topic)
            return

        # Record access timestamp for LRU eviction
        key = f"{entry.library}/{entry.topic}"
        access_meta = self._load_metadata()
        access_meta[key] = time.time()
        self._save_metadata(access_meta)

        logger.debug(
            "cache_put",
            library=entry.library,
            topic=entry.topic,
            token_count=entry.token_count,
        )

        # Check size and evict if over limit
        self._check_size()

    def has(self, library: str, topic: str = "overview") -> bool:
        """Check whether a cache entry exists (does not check staleness)."""
        return (
            self._content_path(library, topic).exists() and self._meta_path(library, topic).exists()
        )

    def is_stale(self, library: str, topic: str = "overview") -> bool:
        """Check whether a cache entry is stale (past TTL)."""
        meta_path = self._meta_path(library, topic)
        if not meta_path.exists():
            return True
        meta = self._read_meta(meta_path)
        if meta is None or "cached_at" not in meta:
            return True
        return self._is_expired(library, meta["cached_at"])

    def remove(self, library: str, topic: str = "overview") -> bool:
        """Remove a cache entry.  Returns True if entry existed."""
        removed = False
        for path in [
            self._content_path(library, topic),
            self._meta_path(library, topic),
            self._lock_path(library, topic),
        ]:
            if path.exists():
                path.unlink(missing_ok=True)
                removed = True
        return removed

    def list_entries(self) -> list[CacheEntry]:
        """List all cache entries (metadata only, no content)."""
        entries: list[CacheEntry] = []
        if not self.cache_dir.exists():
            return entries
        for lib_dir in sorted(self.cache_dir.iterdir()):
            if not lib_dir.is_dir():
                continue
            for meta_file in sorted(lib_dir.glob("*.meta.json")):
                meta = self._read_meta(meta_file)
                if meta is None:
                    continue
                entries.append(
                    CacheEntry(
                        library=meta.get("library", lib_dir.name),
                        topic=meta.get("topic", "overview"),
                        context7_id=meta.get("context7_id"),
                        provider_source=meta.get("provider_source"),
                        snippet_count=meta.get("snippet_count", 0),
                        token_count=meta.get("token_count", 0),
                        cached_at=meta.get("cached_at"),
                        fetched_at=meta.get("fetched_at"),
                        cache_hits=meta.get("cache_hits", 0),
                    )
                )
        return entries

    def clear(self) -> int:
        """Remove all cache entries.  Returns count of removed entries."""
        count = 0
        if not self.cache_dir.exists():
            return count
        for lib_dir in list(self.cache_dir.iterdir()):
            if not lib_dir.is_dir():
                continue
            for f in lib_dir.iterdir():
                if f.suffix == ".md":
                    count += 1
                f.unlink(missing_ok=True)
            lib_dir.rmdir()
        return count

    @property
    def stats(self) -> CacheStats:
        """Return current cache statistics."""
        total_entries = 0
        total_size = 0
        stale = 0
        if self.cache_dir.exists():
            for lib_dir in self.cache_dir.iterdir():
                if not lib_dir.is_dir():
                    continue
                for content_file in lib_dir.glob("*.md"):
                    total_entries += 1
                    total_size += content_file.stat().st_size
                    topic = content_file.stem
                    if self.is_stale(lib_dir.name, topic):
                        stale += 1
        self._stats.total_entries = total_entries
        self._stats.total_size_bytes = total_size
        self._stats.stale_entries = stale
        return self._stats

    def evict_lru(self, max_mb: int = 100) -> int:
        """Evict least-recently-used entries until cache is under *max_mb*.

        Returns the number of evicted entries.
        """
        return self._check_size(max_mb)

    # ------------------------------------------------------------------
    # LRU metadata helpers
    # ------------------------------------------------------------------

    @property
    def _metadata_path(self) -> Path:
        """Path to the LRU access-timestamp metadata file."""
        return self.cache_dir / "_metadata.json"

    def _load_metadata(self) -> dict[str, float]:
        """Load access-timestamp metadata from disk."""
        if not self._metadata_path.exists():
            return {}
        try:
            raw = self._metadata_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): float(v) for k, v in data.items()}
            return {}
        except (json.JSONDecodeError, OSError, ValueError):
            return {}

    def _save_metadata(self, metadata: dict[str, float]) -> None:
        """Persist access-timestamp metadata to disk atomically."""
        self._write_atomic(self._metadata_path, json.dumps(metadata, indent=2))

    def _check_size(self, max_mb: int = 100) -> int:
        """Evict LRU entries if total cache size exceeds *max_mb* MB.

        Returns the number of evicted entries.
        """
        limit_bytes = max_mb * 1024 * 1024
        total = self._total_cache_bytes()
        if total <= limit_bytes:
            return 0

        metadata = self._load_metadata()
        # Build list of (key, timestamp) sorted oldest-first
        sorted_entries = sorted(metadata.items(), key=lambda kv: kv[1])

        evicted = 0
        for key, _ts in sorted_entries:
            if total <= limit_bytes:
                break
            parts = key.split("/", 1)
            if len(parts) != 2:  # noqa: PLR2004
                continue
            library, topic = parts

            # Calculate size of this entry before removal
            entry_size = self._entry_size(library, topic)
            if entry_size == 0:
                # Entry files already gone — just clean metadata
                metadata.pop(key, None)
                continue

            self.remove(library, topic)
            metadata.pop(key, None)
            total -= entry_size
            evicted += 1
            logger.debug(
                "cache_evict_lru",
                library=library,
                topic=topic,
                freed_bytes=entry_size,
            )

        self._save_metadata(metadata)
        return evicted

    def _total_cache_bytes(self) -> int:
        """Sum the size of all files under the cache directory recursively."""
        total = 0
        if not self.cache_dir.exists():
            return total
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def _entry_size(self, library: str, topic: str) -> int:
        """Return total bytes used by a single cache entry (md + meta + lock)."""
        size = 0
        for path in [
            self._content_path(library, topic),
            self._meta_path(library, topic),
            self._lock_path(library, topic),
        ]:
            if path.exists():
                size += path.stat().st_size
        return size

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lib_dir(self, library: str) -> Path:
        return self.cache_dir / _safe_name(library)

    def _content_path(self, library: str, topic: str) -> Path:
        return self._lib_dir(library) / f"{_safe_name(topic)}.md"

    def _meta_path(self, library: str, topic: str) -> Path:
        return self._lib_dir(library) / f"{_safe_name(topic)}.meta.json"

    def _lock_path(self, library: str, topic: str) -> Path:
        return self._lib_dir(library) / f"{_safe_name(topic)}.lock"

    def _ttl_for(self, library: str) -> float:
        return self.staleness_policies.get(library.lower(), self.default_ttl)

    def _is_expired(self, library: str, cached_at: str) -> bool:
        """Check if *cached_at* ISO timestamp is past TTL for *library*."""
        try:
            ts = datetime.datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
            age = (datetime.datetime.now(datetime.UTC) - ts).total_seconds()
            return age > self._ttl_for(library)
        except (ValueError, TypeError):
            return True

    @staticmethod
    def _read_meta(meta_path: Path) -> dict[str, Any] | None:
        try:
            raw = meta_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return None
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _write_meta_atomic(meta_path: Path, meta: dict[str, Any]) -> None:
        """Write metadata via atomic temp-file + rename."""
        raw = json.dumps(meta, indent=2, default=str)
        KBCache._write_atomic(meta_path, raw)

    @staticmethod
    def _write_atomic(target: Path, content: str) -> None:
        """Write *content* to *target* atomically via tempfile + replace."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=".tmp_",
            suffix=target.suffix,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp_path).replace(target)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise

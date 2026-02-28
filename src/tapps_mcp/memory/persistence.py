"""SQLite-backed persistence layer for the shared memory subsystem.

Uses WAL journal mode for concurrent reads during writes, FTS5 for
full-text search, and schema versioning with forward migrations.
A JSONL audit log is maintained for debugging/compliance (append-only).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.memory.models import MemoryEntry

logger = structlog.get_logger(__name__)

# Current schema version - bump when adding migrations.
_SCHEMA_VERSION = 1

# Maximum JSONL audit log lines before truncation.
_MAX_AUDIT_LINES = 10_000


class MemoryPersistence:
    """SQLite-backed persistence for memory entries.

    Storage directory: ``{project_root}/.tapps-mcp/memory/``

    Files:
    - ``memory.db`` -- SQLite database (WAL mode, FTS5)
    - ``memory_log.jsonl`` -- append-only audit log
    """

    def __init__(self, project_root: Path) -> None:
        self._store_dir = project_root / ".tapps-mcp" / "memory"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._store_dir / "memory.db"
        self._audit_path = self._store_dir / "memory_log.jsonl"
        self._lock = threading.Lock()

        self._conn = self._connect()
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection and schema
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with recommended pragmas."""
        conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables if absent and apply forward migrations."""
        with self._lock:
            cur = self._conn.cursor()

            # Schema version table
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL, migrated_at TEXT NOT NULL)"
            )

            # Check current version
            row = cur.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            current_version: int = row[0] if row[0] is not None else 0

            if current_version < 1:
                self._create_v1_schema(cur)

            # Future: if current_version < 2: self._migrate_v1_to_v2(cur)

            self._conn.commit()

    def _create_v1_schema(self, cur: sqlite3.Cursor) -> None:
        """Create the initial v1 schema."""
        # Main memories table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'pattern',
                confidence REAL NOT NULL DEFAULT 0.6,
                source TEXT NOT NULL DEFAULT 'agent',
                source_agent TEXT NOT NULL DEFAULT 'unknown',
                scope TEXT NOT NULL DEFAULT 'project',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                branch TEXT,
                last_reinforced TEXT,
                reinforce_count INTEGER NOT NULL DEFAULT 0,
                contradicted INTEGER NOT NULL DEFAULT 0,
                contradiction_reason TEXT,
                seeded_from TEXT,
                PRIMARY KEY (key)
            )
        """)

        # Indexes for common queries
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_confidence "
            "ON memories(confidence)"
        )

        # FTS5 full-text search index
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(key, value, tags, content=memories, content_rowid=rowid)
        """)

        # Triggers to keep FTS in sync
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, key, value, tags)
                VALUES (new.rowid, new.key, new.value, new.tags);
            END
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
                VALUES ('delete', old.rowid, old.key, old.value, old.tags);
            END
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
                VALUES ('delete', old.rowid, old.key, old.value, old.tags);
                INSERT INTO memories_fts(rowid, key, value, tags)
                VALUES (new.rowid, new.key, new.value, new.tags);
            END
        """)

        # Reserved for Epic 24 GC
        cur.execute("""
            CREATE TABLE IF NOT EXISTS archived_memories (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                tier TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                scope TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                branch TEXT,
                last_reinforced TEXT,
                reinforce_count INTEGER NOT NULL DEFAULT 0,
                contradicted INTEGER NOT NULL DEFAULT 0,
                contradiction_reason TEXT,
                seeded_from TEXT,
                archived_at TEXT NOT NULL
            )
        """)

        # Record schema version
        cur.execute(
            "INSERT INTO schema_version (version, migrated_at) VALUES (?, ?)",
            (1, datetime.now(tz=UTC).isoformat()),
        )

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def save(self, entry: MemoryEntry) -> None:
        """Insert or replace a memory entry."""
        tags_json = json.dumps(entry.tags, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memories
                (key, value, tier, confidence, source, source_agent, scope,
                 tags, created_at, updated_at, last_accessed, access_count,
                 branch, last_reinforced, reinforce_count, contradicted,
                 contradiction_reason, seeded_from)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.key,
                    entry.value,
                    entry.tier.value,
                    entry.confidence,
                    entry.source.value,
                    entry.source_agent,
                    entry.scope.value,
                    tags_json,
                    entry.created_at,
                    entry.updated_at,
                    entry.last_accessed,
                    entry.access_count,
                    entry.branch,
                    entry.last_reinforced,
                    entry.reinforce_count,
                    1 if entry.contradicted else 0,
                    entry.contradiction_reason,
                    entry.seeded_from,
                ),
            )
            self._conn.commit()
        self._audit_log("save", entry.key)

    def get(self, key: str) -> MemoryEntry | None:
        """Retrieve a single memory entry by key."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_all(
        self,
        tier: str | None = None,
        scope: str | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """List entries with optional filters."""
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []

        if tier is not None:
            query += " AND tier = ?"
            params.append(tier)
        if scope is not None:
            query += " AND scope = ?"
            params.append(scope)

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()

        entries = [self._row_to_entry(r) for r in rows]

        # Filter by tags in Python (tags stored as JSON array)
        if tags:
            tag_set = set(tags)
            entries = [
                e for e in entries if tag_set.intersection(e.tags)
            ]

        return entries

    def delete(self, key: str) -> bool:
        """Delete a memory entry by key. Returns True if deleted."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE key = ?", (key,)
            )
            self._conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            self._audit_log("delete", key)
        return deleted

    def search(self, query: str) -> list[MemoryEntry]:
        """Full-text search via FTS5 across key, value, and tags."""
        if not query.strip():
            return []

        # Escape FTS5 special characters for safety
        safe_query = self._escape_fts_query(query)
        if not safe_query:
            return []

        with self._lock:
            try:
                rows = self._conn.execute(
                    """
                    SELECT m.* FROM memories m
                    JOIN memories_fts fts ON m.rowid = fts.rowid
                    WHERE memories_fts MATCH ?
                    """,
                    (safe_query,),
                ).fetchall()
            except sqlite3.OperationalError:
                logger.debug("fts_search_failed", query=query)
                return []

        return [self._row_to_entry(r) for r in rows]

    def load_all(self) -> list[MemoryEntry]:
        """Load all entries (for cold-start into in-memory cache)."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def count(self) -> int:
        """Return the total number of memory entries."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memories"
            ).fetchone()
        return int(row[0]) if row else 0

    def get_schema_version(self) -> int:
        """Return the current schema version."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        """Convert a SQLite Row to a MemoryEntry."""
        tags_raw = row["tags"]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        return MemoryEntry(
            key=row["key"],
            value=row["value"],
            tier=row["tier"],
            confidence=row["confidence"],
            source=row["source"],
            source_agent=row["source_agent"],
            scope=row["scope"],
            tags=tags,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            branch=row["branch"],
            last_reinforced=row["last_reinforced"],
            reinforce_count=row["reinforce_count"],
            contradicted=bool(row["contradicted"]),
            contradiction_reason=row["contradiction_reason"],
            seeded_from=row["seeded_from"],
        )

    @staticmethod
    def _escape_fts_query(query: str) -> str:
        """Escape an FTS5 query string for safe matching.

        Wraps each token in double quotes to treat them as literals.
        """
        tokens = query.strip().split()
        if not tokens:
            return ""
        return " ".join(f'"{t}"' for t in tokens)

    def _audit_log(self, action: str, key: str) -> None:
        """Append an entry to the JSONL audit log."""
        record = {
            "action": action,
            "key": key,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        try:
            with self._audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._maybe_truncate_audit()
        except OSError:
            logger.debug("audit_log_write_failed", key=key, action=action)

    def _maybe_truncate_audit(self) -> None:
        """Truncate audit log if it exceeds the max line count."""
        try:
            lines = self._audit_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > _MAX_AUDIT_LINES:
                # Keep the most recent entries
                keep = lines[-_MAX_AUDIT_LINES:]
                self._audit_path.write_text(
                    "\n".join(keep) + "\n", encoding="utf-8"
                )
        except OSError:
            pass

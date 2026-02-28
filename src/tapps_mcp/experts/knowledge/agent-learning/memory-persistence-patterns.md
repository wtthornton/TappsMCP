# Memory Persistence Patterns

## Overview

Persistent memory for AI agents requires reliable storage, fast retrieval,
concurrent access safety, and audit capabilities. This guide covers SQLite
WAL mode, schema versioning, JSONL audit logging, FTS5 full-text search,
path-sandboxed storage, RAG safety on writes, and backup/recovery patterns.

## SQLite WAL Mode

### What is WAL?

Write-Ahead Logging (WAL) allows concurrent readers during writes, unlike
the default rollback journal which blocks all readers during a write:

```python
import sqlite3

def create_wal_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with WAL journal mode."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

### WAL Advantages for Memory Systems

| Feature | Rollback Journal | WAL Mode |
|---|---|---|
| Concurrent reads during write | No | Yes |
| Read performance | Blocked by writes | Unaffected |
| Write performance | Moderate | Slightly better |
| Crash recovery | Full | Full |
| File count | 1 (+ journal) | 3 (db + wal + shm) |

### WAL Best Practices

```python
# Set busy timeout to avoid SQLITE_BUSY errors
conn.execute("PRAGMA busy_timeout=5000")

# Periodic WAL checkpoint (optional, SQLite auto-checkpoints at 1000 pages)
conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
```

### Thread Safety

Use a threading lock for write serialization while allowing concurrent reads:

```python
import threading

class ThreadSafeStore:
    """Thread-safe SQLite wrapper for memory persistence."""

    def __init__(self, db_path: str) -> None:
        self._conn = create_wal_connection(db_path)
        self._lock = threading.Lock()

    def read(self, key: str) -> dict | None:
        """Read operation (concurrent-safe with WAL)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def write(self, key: str, value: str) -> None:
        """Write operation (serialized via lock)."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()
```

## Schema Versioning

### Version Tracking Table

Track schema versions for forward migrations:

```python
def create_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema version tracking table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            migrated_at TEXT NOT NULL
        )
    """)
```

### Forward Migration Pattern

```python
from datetime import datetime, UTC

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply all pending schema migrations."""
    create_version_table(conn)

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current_version = row[0] if row[0] is not None else 0

    if current_version < 1:
        migrate_to_v1(conn)

    if current_version < 2:
        migrate_to_v2(conn)

    # Future: if current_version < 3: migrate_to_v3(conn)

    conn.commit()


def migrate_to_v1(conn: sqlite3.Connection) -> None:
    """Create initial schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            key TEXT PRIMARY KEY,
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
            seeded_from TEXT
        )
    """)

    # Indexes for common queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tier ON memories(tier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON memories(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_confidence ON memories(confidence)")

    conn.execute(
        "INSERT INTO schema_version (version, migrated_at) VALUES (?, ?)",
        (1, datetime.now(tz=UTC).isoformat()),
    )


def migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Example: add a new column in v2."""
    conn.execute("""
        ALTER TABLE memories ADD COLUMN priority INTEGER NOT NULL DEFAULT 0
    """)
    conn.execute(
        "INSERT INTO schema_version (version, migrated_at) VALUES (?, ?)",
        (2, datetime.now(tz=UTC).isoformat()),
    )
```

### Migration Safety

- Always use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`
- Use `ALTER TABLE ADD COLUMN` for additive changes (safe in SQLite)
- Never drop columns in SQLite (not supported before 3.35, risky even after)
- Test migrations against both empty and populated databases
- Record each migration version after successful application

## JSONL Audit Log

### Append-Only Logging

Maintain an audit trail of all memory operations:

```python
import json
from datetime import datetime, UTC
from pathlib import Path

class AuditLog:
    """Append-only JSONL audit log for memory operations."""

    MAX_LINES = 10_000

    def __init__(self, log_path: Path) -> None:
        self._path = log_path

    def log(self, action: str, key: str, metadata: dict | None = None) -> None:
        """Append an audit entry."""
        record = {
            "action": action,
            "key": key,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        if metadata:
            record["metadata"] = metadata

        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._maybe_truncate()
        except OSError:
            pass  # non-critical, log and continue

    def _maybe_truncate(self) -> None:
        """Truncate log if it exceeds max lines, keeping most recent."""
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            if len(lines) > self.MAX_LINES:
                keep = lines[-self.MAX_LINES:]
                self._path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except OSError:
            pass
```

### Audit Log Format

Each line is a JSON object:

```json
{"action": "save", "key": "pattern.async", "timestamp": "2026-02-27T10:15:30+00:00"}
{"action": "get", "key": "pattern.async", "timestamp": "2026-02-27T10:16:00+00:00"}
{"action": "delete", "key": "context.temp", "timestamp": "2026-02-27T10:20:00+00:00"}
{"action": "reinforce", "key": "pattern.async", "timestamp": "2026-02-27T11:00:00+00:00"}
```

### Audit Log Analysis

```python
import json
from collections import Counter
from pathlib import Path

def analyze_audit_log(log_path: Path) -> dict:
    """Analyze memory audit log for usage patterns."""
    actions = Counter()
    keys = Counter()

    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            actions[record["action"]] += 1
            keys[record["key"]] += 1
        except (json.JSONDecodeError, KeyError):
            continue

    return {
        "action_counts": dict(actions),
        "most_accessed": keys.most_common(10),
        "total_operations": sum(actions.values()),
    }
```

## FTS5 Full-Text Search

### Creating FTS5 Index

```python
def create_fts_index(conn: sqlite3.Connection) -> None:
    """Create FTS5 virtual table for full-text search."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(key, value, tags, content=memories, content_rowid=rowid)
    """)

    # Triggers to keep FTS in sync with the main table
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, value, tags)
            VALUES (new.rowid, new.key, new.value, new.tags);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
            VALUES ('delete', old.rowid, old.key, old.value, old.tags);
        END
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
            VALUES ('delete', old.rowid, old.key, old.value, old.tags);
            INSERT INTO memories_fts(rowid, key, value, tags)
            VALUES (new.rowid, new.key, new.value, new.tags);
        END
    """)
```

### Safe FTS5 Queries

FTS5 has special characters that must be escaped:

```python
def escape_fts_query(query: str) -> str:
    """Escape FTS5 query for safe matching.

    Wraps each token in double quotes to treat as literals.
    """
    tokens = query.strip().split()
    if not tokens:
        return ""
    return " ".join(f'"{t}"' for t in tokens)


def search_memories(
    conn: sqlite3.Connection,
    query: str,
) -> list[dict]:
    """Search memories using FTS5 full-text index."""
    safe_query = escape_fts_query(query)
    if not safe_query:
        return []

    try:
        rows = conn.execute("""
            SELECT m.* FROM memories m
            JOIN memories_fts fts ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
        """, (safe_query,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
```

### FTS5 Ranking

```python
def ranked_search(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Search with BM25 ranking for relevance ordering."""
    safe_query = escape_fts_query(query)
    if not safe_query:
        return []

    try:
        rows = conn.execute("""
            SELECT m.*, rank FROM memories m
            JOIN memories_fts fts ON m.rowid = fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY rank
        """, (safe_query,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
```

## Path-Sandboxed Storage

### Storage Directory Structure

Memory storage is sandboxed within the project root:

```
{project_root}/
  .tapps-mcp/
    memory/
      memory.db          # SQLite database (WAL mode)
      memory.db-wal      # WAL file (auto-managed)
      memory.db-shm      # Shared memory file (auto-managed)
      memory_log.jsonl   # Append-only audit log
```

### Path Validation

```python
from pathlib import Path

def validate_storage_path(project_root: Path) -> Path:
    """Validate and create the memory storage directory."""
    store_dir = project_root / ".tapps-mcp" / "memory"

    # Ensure path is within project root (prevent traversal)
    resolved = store_dir.resolve()
    root_resolved = project_root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        raise PermissionError("Storage path outside project root")

    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir
```

### gitignore Integration

Add memory storage to `.gitignore` (local state, not for version control):

```
# .gitignore
.tapps-mcp/memory/
```

## RAG Safety on Writes

### Content Safety Check

Every memory write passes through RAG safety to prevent prompt injection:

```python
def check_content_safety(value: str) -> dict:
    """Check memory content for prompt injection patterns."""
    dangerous_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+(now\s+)?a\s+(new|different|evil)",
        r"system\s*:\s*you\s+are",
        r"<\s*system\s*>",
    ]

    import re
    matches = []
    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            matches.append(pattern)

    return {
        "safe": len(matches) == 0,
        "match_count": len(matches),
        "flagged_patterns": matches,
    }
```

### Block vs Sanitize

| Match Count | Action |
|---|---|
| 0 | Allow (safe content) |
| 1-2 | Sanitize (remove flagged content, allow rest) |
| 3+ | Block (reject the entire write) |

## Write-Through Caching

### In-Memory Cache with SQLite Backing

```python
class WriteThoughCache:
    """In-memory dict backed by SQLite for durability."""

    def __init__(self, db_path: str) -> None:
        self._cache: dict[str, dict] = {}
        self._persistence = create_wal_connection(db_path)
        self._lock = threading.Lock()

        # Cold start: load all entries into memory
        self._load_all()

    def _load_all(self) -> None:
        """Load all entries from SQLite into the in-memory cache."""
        rows = self._persistence.execute("SELECT * FROM memories").fetchall()
        for row in rows:
            self._cache[row["key"]] = dict(row)

    def get(self, key: str) -> dict | None:
        """Read from in-memory cache (fast path)."""
        with self._lock:
            return self._cache.get(key)

    def save(self, key: str, entry: dict) -> None:
        """Write to both cache and SQLite (write-through)."""
        with self._lock:
            self._cache[key] = entry
        # Write to SQLite outside the lock for reduced contention
        self._persist(key, entry)
```

### Eviction on Max Entries

```python
MAX_ENTRIES = 500

def evict_lowest_confidence(cache: dict) -> str | None:
    """Evict the entry with the lowest confidence to make room."""
    if not cache:
        return None

    lowest_key = min(cache, key=lambda k: cache[k].get("confidence", 0))
    del cache[lowest_key]
    return lowest_key
```

## Backup and Recovery

### Database Backup

```python
import shutil
from pathlib import Path

def backup_memory_db(project_root: Path) -> Path:
    """Create a backup of the memory database."""
    db_path = project_root / ".tapps-mcp" / "memory" / "memory.db"
    backup_dir = project_root / ".tapps-mcp" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"memory_{timestamp}.db"

    # Use SQLite backup API for consistency
    import sqlite3
    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(backup_path))
    source.backup(dest)
    source.close()
    dest.close()

    return backup_path
```

### Recovery from Backup

```python
def restore_from_backup(project_root: Path, backup_path: Path) -> None:
    """Restore memory database from a backup."""
    db_path = project_root / ".tapps-mcp" / "memory" / "memory.db"

    # Close existing connection first
    # Then copy backup over the current database
    import sqlite3
    source = sqlite3.connect(str(backup_path))
    dest = sqlite3.connect(str(db_path))
    source.backup(dest)
    source.close()
    dest.close()
```

### Export/Import (JSONL)

```python
import json
from pathlib import Path

def export_memories(store: object, output_path: Path) -> int:
    """Export all memories to a JSONL file."""
    entries = store.list_all()
    with output_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(entries)


def import_memories(store: object, input_path: Path) -> int:
    """Import memories from a JSONL file."""
    imported = 0
    for line in input_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            store.save(**entry)
            imported += 1
        except (json.JSONDecodeError, TypeError):
            continue
    return imported
```

## Anti-Patterns

### No WAL Mode

Default journal mode blocks readers during writes. Always enable WAL for
concurrent access.

### Missing Schema Versioning

Without version tracking, database migrations are impossible to manage.
Always track and apply migrations incrementally.

### Unbounded Audit Logs

JSONL logs grow indefinitely without truncation. Set a max line count
and truncate periodically.

### Direct File Path Construction

Constructing storage paths without validation enables directory traversal.
Always validate paths are within the project root.

### No FTS Escaping

Passing raw user input to FTS5 MATCH can cause SQL errors or unexpected
behavior. Always escape queries by wrapping tokens in double quotes.

## Quick Reference

| Aspect | Recommendation |
|---|---|
| Journal mode | WAL (PRAGMA journal_mode=WAL) |
| Thread safety | threading.Lock for writes |
| Schema tracking | schema_version table with migrations |
| Full-text search | FTS5 with sync triggers |
| Audit logging | JSONL, append-only, 10K line cap |
| Storage location | {project_root}/.tapps-mcp/memory/ |
| Path safety | Validate within project root |
| Content safety | RAG safety check on every write |
| Backup | SQLite backup API (not file copy) |
| Max entries | 500 with lowest-confidence eviction |

"""Linear tool handlers for TappsMCP (TAP-964).

Provides a cache-only surface for Linear issue snapshots. The agent is
the authoritative Linear caller — it fetches via the Linear MCP plugin
(which already holds OAuth via Claude Code) and passes results here for
storage. tapps-mcp never calls Linear itself; that would duplicate the
plugin's auth and create a parallel credential surface.

Tools:
- ``tapps_linear_snapshot_get(team, project, state, label, limit)`` —
  cache-only read. Returns ``cached=True`` with the stored issue list
  when fresh, or ``cached=False`` with a hint to fetch via the plugin.
- ``tapps_linear_snapshot_put(team, project, issues_json, state, label,
  limit)`` — cache-set after the agent fetched via the plugin. TTL
  depends on the requested ``state`` bucket.
- ``tapps_linear_snapshot_invalidate(team, project)`` — prefix-match
  delete, called after a Linear write (``save_issue``, ``save_comment``)
  so the next ``_get`` sees fresh data.

Cache layout::

    <project_root>/.tapps-mcp-cache/linear-snapshots/<cache_key>.json

Each file stores ``{issues, cached_at, expires_at, team, project,
state}``. ``expires_at`` is enforced on read; stale entries are treated
as misses.

Split under TAP-5606 — this module is a thin facade over three siblings,
mirroring the ``loop_metrics`` split:

* :mod:`tapps_mcp.server_linear_tools_keys` — cache-key/state-bucket
  primitives and payload shaping (leaf).
* :mod:`tapps_mcp.server_linear_tools_cache` — snapshot cache I/O,
  pruning, and stats (imports keys only).
* :mod:`tapps_mcp.server_linear_tools_handlers` — the five async MCP
  tools + registration wiring (imports keys + cache).

This facade re-exports the public (and doctor/test-private) API so
existing imports of ``tapps_mcp.server_linear_tools`` stay stable. It
also owns the ``load_settings`` import: :mod:`server_linear_tools_handlers`
re-resolves ``load_settings`` from *this* module on every call so that
``unittest.mock.patch("tapps_mcp.server_linear_tools.load_settings", ...)``
in existing tests keeps working after the split.
"""

from __future__ import annotations

from tapps_core.config.settings import load_settings as load_settings
from tapps_mcp.server_linear_tools_cache import (
    _CACHE_MAX_FILES as _CACHE_MAX_FILES,
)
from tapps_mcp.server_linear_tools_cache import (
    _cache_dir as _cache_dir,
)
from tapps_mcp.server_linear_tools_cache import (
    _cache_invalidate_glob as _cache_invalidate_glob,
)
from tapps_mcp.server_linear_tools_cache import (
    _cache_read as _cache_read,
)
from tapps_mcp.server_linear_tools_cache import (
    _cache_write as _cache_write,
)
from tapps_mcp.server_linear_tools_cache import (
    _linear_snapshot_stats as _linear_snapshot_stats,
)
from tapps_mcp.server_linear_tools_cache import (
    _prune_linear_snapshot_cache as _prune_linear_snapshot_cache,
)
from tapps_mcp.server_linear_tools_cache import (
    _snapshot_last_write_ts as _snapshot_last_write_ts,
)
from tapps_mcp.server_linear_tools_cache import (
    _snapshot_stats as _snapshot_stats,
)
from tapps_mcp.server_linear_tools_handlers import (
    register as register,
)
from tapps_mcp.server_linear_tools_handlers import (
    tapps_linear_count as tapps_linear_count,
)
from tapps_mcp.server_linear_tools_handlers import (
    tapps_linear_list_issues as tapps_linear_list_issues,
)
from tapps_mcp.server_linear_tools_handlers import (
    tapps_linear_snapshot_get as tapps_linear_snapshot_get,
)
from tapps_mcp.server_linear_tools_handlers import (
    tapps_linear_snapshot_invalidate as tapps_linear_snapshot_invalidate,
)
from tapps_mcp.server_linear_tools_handlers import (
    tapps_linear_snapshot_put as tapps_linear_snapshot_put,
)
from tapps_mcp.server_linear_tools_keys import (
    _COMPACT_FIELDS as _COMPACT_FIELDS,
)
from tapps_mcp.server_linear_tools_keys import (
    _cache_key as _cache_key,
)
from tapps_mcp.server_linear_tools_keys import (
    _compact_issue as _compact_issue,
)
from tapps_mcp.server_linear_tools_keys import (
    _filter_hash as _filter_hash,
)
from tapps_mcp.server_linear_tools_keys import (
    _resolve_cache_key as _resolve_cache_key,
)
from tapps_mcp.server_linear_tools_keys import (
    _ttl_for_state as _ttl_for_state,
)

"""TAP-6081 acceptance 6: a seventh bare shared-state writer cannot land quietly.

Six writers persisted shared JSON state with a bare ``Path.write_text`` and had
to be routed onto :class:`AtomicJsonCache`. Nothing stopped a seventh from being
added, so this test is the constraint.

**Why an allowlisted module scope rather than a repo-wide rule.** A repo-wide
ban on ``write_text`` is not honest: most calls in this tree write generated
artifacts (hook scripts, AGENTS.md, plugin bundles, rendered reports) that have
exactly one writer and no concurrent reader — atomicity buys them nothing, and
banning them would produce ~20 meaningless allowlist entries. AST analysis also
cannot tell which ``Path`` object points at shared state: the receiver is a
runtime value (``self._file``, ``cache_path``), not a literal.

So the guarded scope is the set of modules and directories whose *job* is
shared state — the caches, the metrics stores, the identity file. Inside that
scope any ``write_text`` / ``write_bytes`` call is a finding unless it carries
an explicit allowlist entry with a reason, which is a visible diff line and not
something that slips through review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CORE_SRC = _REPO_ROOT / "packages" / "tapps-core" / "src" / "tapps_core"
_MCP_SRC = _REPO_ROOT / "packages" / "tapps-mcp" / "src" / "tapps_mcp"

# Directories whose modules exist to hold shared, concurrently-read state.
_GUARDED_DIRS = (
    _CORE_SRC / "cache",
    _CORE_SRC / "metrics",
    _MCP_SRC / "project",
)

# Individual shared-state modules outside those directories.
_GUARDED_MODULES = (
    _CORE_SRC / "brain_bridge.py",
    _CORE_SRC / "agent_identity.py",
    _MCP_SRC / "tools" / "tool_detection.py",
)

_BANNED_METHODS = frozenset({"write_text", "write_bytes"})

# The atomic primitive exposes a ``write_text`` of its own; a call on it is the
# fix, not the defect.
_ATOMIC_RECEIVER = "AtomicJsonCache"

# Path (repo-relative) -> why a bare write is correct there. Adding an entry is
# a deliberate, reviewable act; that is the point of the constraint.
_ALLOWLIST: dict[str, str] = {
    "packages/tapps-core/src/tapps_core/metrics/dashboard.py": (
        "save_dashboard renders a user-requested report artifact on demand; it is "
        "not read back as a cache and has no concurrent reader."
    ),
    "packages/tapps-core/src/tapps_core/metrics/otel_export.py": (
        "write_otel_trace appends a day-stamped trace export consumed by external "
        "OTel tooling, not by tapps at runtime."
    ),
    "packages/tapps-mcp/src/tapps_mcp/project/call_graph_eval.py": (
        "evaluate_case materializes golden-case fixture sources into a scratch "
        "directory it owns exclusively."
    ),
    "packages/tapps-mcp/src/tapps_mcp/project/diff_impact.py": (
        "renders the test-edge report to a caller-supplied output path."
    ),
}


def _guarded_files() -> list[Path]:
    files: list[Path] = []
    for directory in _GUARDED_DIRS:
        files.extend(sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts))
    files.extend(_GUARDED_MODULES)
    return files


def _bare_writes(path: Path) -> list[int]:
    """Return the line numbers of ``.write_text`` / ``.write_bytes`` calls in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _BANNED_METHODS
        and ast.unparse(node.func.value) != _ATOMIC_RECEIVER
    ]


def test_guarded_scope_resolves() -> None:
    """Guard against the scope silently emptying out after a file move."""
    for directory in _GUARDED_DIRS:
        assert directory.is_dir(), f"guarded dir vanished: {directory}"
    for module in _GUARDED_MODULES:
        assert module.is_file(), f"guarded module vanished: {module}"
    assert len(_guarded_files()) > 10


@pytest.mark.parametrize("path", _guarded_files(), ids=lambda p: p.name)
def test_no_bare_write_text_on_shared_state(path: Path) -> None:
    """A new bare ``write_text`` inside the shared-state scope fails here."""
    rel = path.relative_to(_REPO_ROOT).as_posix()
    lines = _bare_writes(path)
    if rel in _ALLOWLIST:
        assert lines, (
            f"{rel} is allowlisted but no longer contains a bare write — "
            "drop the stale allowlist entry"
        )
        return
    assert not lines, (
        f"{rel}:{lines} writes shared state with a bare write_text/write_bytes. "
        "Route it through tapps_core.cache.atomic.AtomicJsonCache (tempfile + "
        "os.replace), or add an allowlist entry in this module explaining why "
        "the path is not concurrently read. See TAP-6081."
    )


def test_allowlist_entries_all_exist() -> None:
    """A moved or deleted allowlisted module must not leave a dead entry behind."""
    for rel in _ALLOWLIST:
        assert (_REPO_ROOT / rel).is_file(), f"allowlist points at a missing file: {rel}"


def test_constraint_detects_a_new_bare_writer(tmp_path: Path) -> None:
    """The AST walk actually fires on a freshly-added shared-state write."""
    seventh = tmp_path / "seventh_writer.py"
    seventh.write_text(
        "from pathlib import Path\n"
        "def save(root: Path, payload: str) -> None:\n"
        '    (root / ".tapps-mcp" / "new-cache.json").write_text(payload)\n',
        encoding="utf-8",
    )
    assert _bare_writes(seventh) == [3]

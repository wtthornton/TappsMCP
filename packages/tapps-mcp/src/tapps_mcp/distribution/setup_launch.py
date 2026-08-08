"""Launch-command resolution for generated MCP host configs.

Decides *what binary to exec* for each MCP server entry: a global ``uv tool
install`` shim, a blue/green release under ``~/.tapps-mcp/current``, a frozen
PyInstaller exe, or a ``uv run --directory`` fallback. Split out of
``setup_generator`` (TAP-5733).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_SPECS

# Placeholder for uv-based configs when ``tapps-mcp`` is not on PATH (Epic 80.5).
_TAPPS_MCP_UV_ROOT_PLACEHOLDER = "<PATH_TO_TAPPS_MCP_MONOREPO_ROOT>"

_UV_AUTO_EXTRA_CANDIDATES = ("mcp", "tapps-mcp", "tapps")


def _resolve_global_cli(command: str) -> str | None:
    """Resolve the MCP server binary for Cursor wrapper scripts.

    Returns a **stable launcher path** only — never a path inside the mutable
    ``~/.local/share/uv/tools/*`` venv tree. In-place ``uv tool install
    --reinstall`` replaces that tree under live MCP stdio servers and kills them
    (ADR-0023). Wrappers always try ``~/.tapps-mcp/current/bin/*`` at runtime
    first; this function supplies the fallback exec target.

    Prefer ``~/.local/bin/<command>`` shims. Dev-monorepo ``current`` is handled
    in :func:`_resolve_dev_monorepo_launch`.
    """
    shim = Path.home() / ".local" / "bin" / command
    if shim.is_file():
        return str(shim)
    which_result = shutil.which(command)
    if which_result is None:
        return None
    which_path = Path(which_result)
    if ".venv" in which_path.parts:
        return None
    # Never bake the uv tool venv path into generated wrappers — it is mutated
    # in place on reinstall while MCP children keep the old inode open.
    if ".local/share/uv/tools" in which_path.as_posix():
        return None
    return which_result


def _resolve_tapps_mcp_monorepo_root() -> str | None:
    """Best-effort lookup of the tapps-mcp monorepo root on disk (Issue #79 sub).

    Resolution order:
    1. Walk up from ``tapps_mcp.__file__`` looking for a ``packages/tapps-mcp``
       layout plus a ``pyproject.toml`` at the workspace root.
    2. Return ``None`` if no monorepo layout is detected (e.g. pip install).
    """
    try:
        import tapps_mcp as _pkg
    except Exception:
        return None
    pkg_file = getattr(_pkg, "__file__", None)
    if not pkg_file:
        return None
    # Expect ``<root>/packages/tapps-mcp/src/tapps_mcp/__init__.py``:
    # parents[0]=tapps_mcp, [1]=src, [2]=packages/tapps-mcp, [3]=packages, [4]=monorepo root.
    try:
        resolved = Path(pkg_file).resolve()
        pkg_dir = resolved.parents[2]
        packages_dir = resolved.parents[3]
        monorepo = resolved.parents[4]
    except IndexError:
        return None
    if (
        pkg_dir.name == "tapps-mcp"
        and packages_dir.name == "packages"
        and (monorepo / "pyproject.toml").exists()
    ):
        return str(monorepo)
    return None


def _resolve_tapps_mcp_launch() -> tuple[str, list[str]]:
    """Return ``command`` and ``args`` to launch ``tapps-mcp serve``.

    Resolution order:
    1. PyInstaller frozen exe: ``sys.executable`` + ``["serve"]``.
    2. ``tapps-mcp`` on PATH: absolute path + ``["serve"]`` (GUI MCP hosts
       often omit ``~/.local/bin`` from PATH — wrappers also export it).
    3. Monorepo checkout: ``uv run --directory <monorepo-root> tapps-mcp serve``
       when the installed ``tapps_mcp`` package lives inside a monorepo layout.
    4. Fallback: ``uv run --directory <placeholder> tapps-mcp serve``.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ["serve"]
    resolved = _resolve_global_cli("tapps-mcp")
    if resolved is not None:
        return resolved, ["serve"]
    directory = _resolve_tapps_mcp_monorepo_root() or _TAPPS_MCP_UV_ROOT_PLACEHOLDER
    return (
        "uv",
        [
            "run",
            "--directory",
            directory,
            "tapps-mcp",
            "serve",
        ],
    )


def _resolve_docsmcp_launch() -> tuple[str, list[str]]:
    """Return command + args to launch DocsMCP (``docsmcp serve``)."""
    resolved = _resolve_global_cli("docsmcp")
    if resolved is not None:
        return resolved, ["serve"]
    directory = _resolve_tapps_mcp_monorepo_root() or _TAPPS_MCP_UV_ROOT_PLACEHOLDER
    return (
        "uv",
        [
            "run",
            "--directory",
            directory,
            "docsmcp",
            "serve",
        ],
    )


def _detect_command_path() -> str:
    """Return the primary executable name or path for MCP configs (compat shim).

    Prefer :func:`_resolve_tapps_mcp_launch` for full ``command`` + ``args``.
    """
    cmd, _args = _resolve_tapps_mcp_launch()
    return cmd


# ---------------------------------------------------------------------------
# uv / pyproject detection for consumer projects (Issue #77)
# ---------------------------------------------------------------------------


def _detect_uv_context(project_root: Path) -> dict[str, Any] | None:
    """Detect whether *project_root* is a uv-managed project that ships tapps-mcp.

    Returns a dict with ``has_uv_lock``, ``has_pyproject``, ``tapps_mcp_extra``
    (name of an optional-dependency group that references ``tapps-mcp``, or
    ``None``), and ``uv_available``. Returns ``None`` when no pyproject.toml
    exists at all.
    """
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None

    info: dict[str, Any] = {
        "has_uv_lock": (project_root / "uv.lock").exists(),
        "has_pyproject": True,
        "tapps_mcp_extra": None,
        "uv_available": shutil.which("uv") is not None,
    }

    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    # Look through [project.optional-dependencies] + [dependency-groups]
    def _has_tapps(entries: Any) -> bool:
        if not isinstance(entries, list):
            return False
        return any(isinstance(e, str) and "tapps-mcp" in e.lower() for e in entries)

    opt = data.get("project", {}).get("optional-dependencies") or {}
    dep_groups = data.get("dependency-groups") or {}

    found_extra: str | None = None
    for name in _UV_AUTO_EXTRA_CANDIDATES:
        if _has_tapps(opt.get(name)) or _has_tapps(dep_groups.get(name)):
            found_extra = name
            break
    if found_extra is None:
        # Fall back: any group that mentions tapps-mcp.
        for name, entries in {**opt, **dep_groups}.items():
            if _has_tapps(entries):
                found_extra = str(name)
                break

    info["tapps_mcp_extra"] = found_extra
    return info


def _should_include_docs_mcp(
    with_docs_mcp: bool,
    *,
    existing: dict[str, Any] | None = None,
    servers_key: str = "mcpServers",
) -> bool:
    """Return whether to emit a ``docs-mcp`` server entry.

    Enabled when explicitly requested, when ``docsmcp`` is on ``PATH``, or when
    an existing config already opted in (preserve on upgrade).
    """
    if with_docs_mcp:
        return True
    if shutil.which("docsmcp") is not None:
        return True
    if existing is not None:
        servers = existing.get(servers_key, {})
        if isinstance(servers, dict) and "docs-mcp" in servers:
            return True
    return False


def _preserve_launch_on_upgrade(
    upgrade_mode: bool,
    old_entry: dict[str, Any],
    *,
    binary_name: str,
    project_root: Path | None = None,
) -> bool:
    """Return True when upgrade should keep the on-disk command/args.

    When a global ``uv tool install`` binary is available, prefer upgrading to
    that launcher instead of preserving a stale ``uv run`` entry.

    Dev monorepo checkouts always regenerate wrappers (Epic 116) so Cursor uses
    ``uv run`` instead of the fleet-shared global CLI.
    """
    if project_root is not None and is_tapps_mcp_dev_monorepo(project_root):
        return False
    if not upgrade_mode or "command" not in old_entry:
        return False
    return shutil.which(binary_name) is None


def _should_use_uv_launch(
    project_root: Path,
    *,
    uv_mode: str | None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Decide whether to emit a ``uv run`` launcher for *project_root*.

    Args:
        project_root: Consumer project root.
        uv_mode: One of ``"on"`` (force), ``"off"`` (force classic), or
            ``None`` (auto-detect).

    Returns:
        ``(use_uv, extra_name, detection_info)`` tuple.
    """
    if uv_mode == "off":
        return False, None, None
    # Epic 116: dev monorepo always emits ``uv run`` — never the shared global CLI.
    if is_tapps_mcp_dev_monorepo(project_root):
        ctx = _detect_uv_context(project_root)
        extra = (ctx or {}).get("tapps_mcp_extra") if ctx else None
        return True, extra, ctx
    # Global ``uv tool install`` CLIs take precedence over workspace uv run.
    if uv_mode != "on" and _resolve_global_cli("tapps-mcp") is not None:
        return False, None, None
    ctx = _detect_uv_context(project_root)
    if uv_mode == "on":
        # Forced: emit uv-run even if we couldn't find a group.
        extra = (ctx or {}).get("tapps_mcp_extra") if ctx else None
        return True, extra, ctx
    if ctx is None:
        return False, None, None
    # Auto: only flip to uv when pyproject lists tapps-mcp in a known extra
    # AND uv is available (or uv.lock is present → likely to be available).
    if ctx["tapps_mcp_extra"] is not None and (ctx["uv_available"] or ctx["has_uv_lock"]):
        return True, ctx["tapps_mcp_extra"], ctx
    return False, None, ctx


def _build_uv_run_tapps_launch(extra: str | None) -> tuple[str, list[str]]:
    """Return (command, args) for ``uv run --extra <extra> --no-sync tapps-mcp serve``."""
    args = ["run"]
    if extra:
        args.extend(["--extra", extra])
    args.extend(["--no-sync", "tapps-mcp", "serve"])
    return "uv", args


# ---------------------------------------------------------------------------
# Monorepo layout detection
# ---------------------------------------------------------------------------


def is_tapps_mcp_package_layout(project_root: Path) -> bool:
    """Return True if *project_root* looks like ``.../packages/tapps-mcp`` (Epic 80.3)."""
    resolved = project_root.resolve()
    parts = resolved.parts
    min_segments = 2
    return len(parts) >= min_segments and parts[-2] == "packages" and parts[-1] == "tapps-mcp"


def is_tapps_mcp_dev_monorepo(project_root: Path) -> bool:
    """Return True when *project_root* is the tapps-mcp workspace checkout (Epic 116 / TAP-4100).

    Dev monorepo MCP wrappers launch from the **deployed global** ``uv tool install``
    binary — the same isolated env consumer repos use — not the workspace ``.venv``
    or ``uv run``. See ``_resolve_dev_monorepo_launch`` for why.
    """
    root = project_root.resolve()
    return (
        (root / "packages" / "tapps-mcp" / "src" / "tapps_mcp").is_dir()
        and (root / "packages" / "docs-mcp").is_dir()
        and (root / "pyproject.toml").is_file()
    )


def _resolve_dev_monorepo_launch(
    serve_cmd: str,
    serve_args: list[str],
    project_root: Path,
) -> tuple[str, list[str]]:
    """Launch command for dev-monorepo MCP wrappers — blue/green ``current`` binary.

    The dev repo continuously runs ``pytest`` and ``uv`` against its workspace
    ``.venv``. Launching the six-server MCP fleet from that same env (via
    ``uv run`` or a direct ``.venv/bin`` exec) let test/build churn crash live
    servers mid-session: Cursor saw the stdio transport drop and flapped
    error↔good on a 5-minute relaunch backoff.

    Blue/green deploys build immutable release venvs under ``~/.tapps-mcp/releases/``
    and atomically flip ``~/.tapps-mcp/current``. Wrappers exec ``current/bin/*``
    so running servers stay pinned to their release dir; only new launches pick up
    a deploy flip. Falls back to the legacy ``uv tool install`` global shim, then
    ``uv run --directory`` when no deploy exists yet (fresh checkout).
    """
    if getattr(sys, "frozen", False):
        return (sys.executable, serve_args)
    from tapps_mcp.distribution.blue_green import CURRENT_LINK

    current_bin = CURRENT_LINK / "bin" / serve_cmd
    if current_bin.is_file():
        return (str(current_bin), serve_args)
    resolved = _resolve_global_cli(serve_cmd)
    if resolved is not None:
        return (resolved, serve_args)
    root = project_root.resolve()
    return ("uv", ["run", "--directory", str(root), serve_cmd, *serve_args])


# ---------------------------------------------------------------------------
# NLT plugin launch (Epic 109)
# ---------------------------------------------------------------------------


def _adapt_uv_launch_for_nlt(
    uv_launch: tuple[str, list[str]],
    serve_cmd: str,
    serve_args: list[str],
) -> tuple[str, list[str]]:
    """Rewrite a consumer ``uv run … tapps-mcp serve`` launch for another NLT binary."""
    command, args = uv_launch
    new_args = list(args)
    for legacy_tool in ("tapps-mcp", "docsmcp", "tapps-platform"):
        if legacy_tool in new_args:
            idx = new_args.index(legacy_tool)
            new_args = [*new_args[:idx], serve_cmd, *serve_args]
            return command, new_args
    return command, [*new_args, serve_cmd, *serve_args]


def _build_nlt_launch(
    server_id: str,
    uv_launch: tuple[str, list[str]] | None,
    *,
    project_root: Path | None = None,
) -> tuple[str, list[str]]:
    """Return ``command`` + ``args`` to launch an NLT MCP server."""
    spec = NLT_SERVER_SPECS[server_id]
    serve_cmd = str(spec["serve_command"])
    serve_args = [str(a) for a in spec["serve_args"]]

    if project_root is not None and is_tapps_mcp_dev_monorepo(project_root):
        return _resolve_dev_monorepo_launch(serve_cmd, serve_args, project_root)

    if uv_launch is not None:
        return _adapt_uv_launch_for_nlt(uv_launch, serve_cmd, serve_args)

    if getattr(sys, "frozen", False):
        return sys.executable, serve_args

    resolved = _resolve_global_cli(serve_cmd)
    if resolved is not None:
        return resolved, serve_args

    directory = _resolve_tapps_mcp_monorepo_root() or _TAPPS_MCP_UV_ROOT_PLACEHOLDER
    return (
        "uv",
        ["run", "--directory", directory, serve_cmd, *serve_args],
    )

"""TAP-5442: resolve ``project_id`` for shared-fleet memory CRUD."""

from __future__ import annotations

from typing import Any, Protocol


class _HasProjectId(Protocol):
    project_id: str | None


def resolve_params_project_id(p: _HasProjectId) -> str | None:
    """Explicit ``project_id`` wins; else current settings tenant (TAP-5442)."""
    pid = (p.project_id or "").strip()
    if pid:
        return pid
    from tapps_core.config.settings import load_settings

    derived = (load_settings().memory.brain_project_id or "").strip()
    return derived or None


def install_memory_project_id_patch() -> None:
    """Replace ``server_memory_tools._params_project_id`` (idempotent)."""
    from tapps_mcp import server_memory_tools as smt

    current = smt._params_project_id
    if getattr(current, "__tapps_fleet_patched__", False):
        return

    def _patched(p: Any) -> str | None:
        return resolve_params_project_id(p)

    _patched.__tapps_fleet_patched__ = True  # type: ignore[attr-defined]
    # Keep the pre-patch function reachable so the mutation is reversible.
    # Without this the patch is a one-way global: once any code path builds a
    # brain bridge, every later caller in the process silently gets the
    # settings-tenant fallback. In tests that made results order-dependent —
    # test_related_happy_path passed alone and failed after test_audit_campaign.
    _patched.__tapps_fleet_original__ = current  # type: ignore[attr-defined]
    smt._params_project_id = _patched


def uninstall_memory_project_id_patch() -> None:
    """Restore the unpatched ``_params_project_id`` (idempotent).

    Production never calls this — the patch is installed once per process when
    the brain bridge is built. It exists so tests can guarantee a known state
    instead of inheriting whatever an earlier test left behind.
    """
    from tapps_mcp import server_memory_tools as smt

    current = smt._params_project_id
    original = getattr(current, "__tapps_fleet_original__", None)
    if original is not None:
        smt._params_project_id = original

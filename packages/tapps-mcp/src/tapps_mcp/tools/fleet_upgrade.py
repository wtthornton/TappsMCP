"""Fleet-level TAPPS upgrade across bootstrapped consumer repos.

Runs ``tapps-mcp upgrade --force`` per project (scaffolding + legacy→NLT MCP
migration) and optionally refreshes MCP host config via ``init --force``.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tapps_mcp.tools.fleet_audit import discover_project_roots

UvMode = Literal["auto", "on", "off"]


@dataclass
class FleetUpgradeProjectResult:
    """Outcome for one consumer project."""

    root: Path
    success: bool
    upgrade_ok: bool = False
    init_ok: bool | None = None
    doctor_ok: bool | None = None
    upgrade_binary: str = ""
    upgrade_binary_version: str = ""
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def default_fleet_roots() -> list[Path]:
    """Return the maintainer fleet list when ``TAPPS_FLEET_ROOTS`` is unset."""
    code = Path.home() / "code"
    candidates = [
        code / "AgentForge",
        code / "NLTlabsPE",
        code / "ReportLab",
        code / "tapps-mcp",
        code / "nlt-portfolio",
        Path.home() / "NewCompanyIdeas",
    ]
    return [p for p in candidates if (p / ".tapps-mcp.yaml").is_file()]


def resolve_fleet_roots(
    *,
    explicit_roots: list[Path] | None = None,
    scan_parent: Path | None = None,
) -> list[Path]:
    """Resolve bootstrapped project roots for a fleet upgrade."""
    if explicit_roots:
        return discover_project_roots(explicit_roots=explicit_roots)
    discovered = discover_project_roots(scan_parent=scan_parent)
    if discovered:
        return discovered
    return default_fleet_roots()


def _run_cli(
    args: list[str],
    *,
    cwd: Path,
    dry_run: bool,
    command_prefix: str = "tapps-mcp",
) -> tuple[bool, str]:
    """Run ``tapps-mcp`` (or *command_prefix*) subprocess; return (ok, combined output)."""
    binary = resolve_cli_binary(command_prefix)
    if dry_run:
        return True, f"[dry-run] {binary} {' '.join(args)}"
    proc = subprocess.run(
        [binary, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def resolve_cli_binary(name: str) -> str:
    """Resolve a CLI binary without trusting a stale PATH shim (TAP-4836).

    Preference order:
    1. ``sys.executable``-adjacent bin (release / uv tool venv that launched us)
    2. ``sys.argv[0]`` when its basename matches *name*
    3. ``~/.tapps-mcp/current/bin/<name>`` (blue/green current symlink)
    4. ``shutil.which`` / bare *name* as last resort
    """
    import shutil
    import sys

    exe_adjacent = Path(sys.executable).resolve().parent / name
    if exe_adjacent.is_file() and os.access(exe_adjacent, os.X_OK):
        return str(exe_adjacent)

    argv0 = Path(sys.argv[0]).resolve()
    if argv0.is_file() and name in (argv0.name, argv0.stem):
        return str(argv0)

    current = Path.home() / ".tapps-mcp" / "current" / "bin" / name
    if current.is_file() and os.access(current, os.X_OK):
        return str(current)

    found = shutil.which(name)
    return found or name


def _cli_binary_version(binary: str) -> str:
    """Best-effort ``--version`` for fleet report visibility."""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        text = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return text.splitlines()[0] if text else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def upgrade_project_root(
    root: Path,
    *,
    force: bool = True,
    dry_run: bool = False,
    mcp_host: str = "auto",
    mcp_bundle: str = "full",
    refresh_mcp: bool = True,
    uv_mode: UvMode = "auto",
    run_doctor: bool = True,
    import_legacy_doc_cache: bool = False,
    strip_context7_env: bool = False,
) -> FleetUpgradeProjectResult:
    """Upgrade one bootstrapped consumer project."""
    result = FleetUpgradeProjectResult(root=root.resolve(), success=False)
    binary = resolve_cli_binary("tapps-mcp")
    result.upgrade_binary = binary
    result.upgrade_binary_version = _cli_binary_version(binary) if not dry_run else "(dry-run)"
    result.messages.append(f"upgrade_binary={binary} version={result.upgrade_binary_version}")

    upgrade_args = [
        "upgrade",
        "--project-root",
        str(root),
        "--host",
        mcp_host,
    ]
    if force:
        upgrade_args.append("--force")

    ok, output = _run_cli(upgrade_args, cwd=root, dry_run=dry_run)
    result.upgrade_ok = ok
    if output:
        result.messages.append(output[-2000:])
    if not ok:
        result.errors.append("upgrade failed")
        return result

    if import_legacy_doc_cache:
        cache_dir = root / ".tapps-mcp-cache"
        if cache_dir.is_dir():
            import_ok, import_out = _run_cli(
                ["docs", "import-dir", str(cache_dir)],
                cwd=root,
                dry_run=dry_run,
                command_prefix="tapps-brain",
            )
            if import_out:
                result.messages.append(import_out[-1500:])
            if not import_ok:
                result.errors.append("legacy doc cache import failed")

    if refresh_mcp:
        init_args = [
            "init",
            "--project-root",
            str(root),
            "--host",
            mcp_host,
            "--bundle",
            mcp_bundle,
            "--no-rules",
        ]
        prev_docs_via_brain = os.environ.get("TAPPS_MCP_DOCS_VIA_BRAIN")
        if strip_context7_env:
            os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
        try:
            if force:
                init_args.append("--force")
            if uv_mode == "off":
                init_args.append("--no-uv")
            elif uv_mode == "on":
                init_args.append("--uv")

            init_ok, init_out = _run_cli(init_args, cwd=root, dry_run=dry_run)
        finally:
            if strip_context7_env:
                if prev_docs_via_brain is None:
                    os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
                else:
                    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = prev_docs_via_brain
        result.init_ok = init_ok
        if init_out:
            result.messages.append(init_out[-2000:])
        if not init_ok:
            result.errors.append("init (MCP refresh) failed")
            return result

    if run_doctor and not dry_run:
        doctor_ok, doctor_out = _run_cli(
            ["doctor", "--project-root", str(root), "--quick"],
            cwd=root,
            dry_run=False,
        )
        result.doctor_ok = doctor_ok
        if doctor_out:
            result.messages.append(doctor_out[-1500:])
        if not doctor_ok:
            result.errors.append("doctor reported failures")

    result.success = not result.errors
    return result


def run_fleet_upgrade(
    *,
    roots: list[Path] | None = None,
    scan_parent: Path | None = None,
    force: bool = True,
    dry_run: bool = False,
    mcp_host: str = "auto",
    mcp_bundle: str = "full",
    refresh_mcp: bool = True,
    uv_mode: UvMode = "auto",
    run_doctor: bool = True,
    reinstall_clis: bool = False,
    blue_green_deploy: bool = True,
    force_inplace_cli_reinstall: bool = False,
    tapps_checkout: Path | None = None,
    import_legacy_doc_cache: bool = False,
    strip_context7_env: bool = False,
) -> dict[str, Any]:
    """Upgrade every bootstrapped project in the fleet."""
    resolved = resolve_fleet_roots(explicit_roots=roots, scan_parent=scan_parent)
    cli_reinstall: dict[str, Any] | None = None

    if reinstall_clis and not dry_run:
        checkout = (tapps_checkout or Path.cwd()).resolve()
        cli_reinstall = _reinstall_global_clis(
            checkout,
            use_blue_green=blue_green_deploy,
            force_inplace=force_inplace_cli_reinstall,
        )
        if cli_reinstall.get("ok") and cli_reinstall.get("strategy", "").startswith("blue_green"):
            from tapps_mcp.distribution.setup_generator import regenerate_cursor_nlt_wrappers

            wrapper_refresh: list[dict[str, Any]] = []
            for root in resolved:
                cursor_mcp = root / ".cursor" / "mcp.json"
                if not cursor_mcp.is_file():
                    continue
                try:
                    written = regenerate_cursor_nlt_wrappers(root)
                    wrapper_refresh.append({"root": str(root), "ok": True, "written": written})
                except Exception as exc:
                    wrapper_refresh.append({"root": str(root), "ok": False, "error": str(exc)})
            cli_reinstall["wrapper_refresh"] = wrapper_refresh

    project_results: list[FleetUpgradeProjectResult] = [
        upgrade_project_root(
            root,
            force=force,
            dry_run=dry_run,
            mcp_host=mcp_host,
            mcp_bundle=mcp_bundle,
            refresh_mcp=refresh_mcp,
            uv_mode=uv_mode,
            run_doctor=run_doctor,
            import_legacy_doc_cache=import_legacy_doc_cache,
            strip_context7_env=strip_context7_env,
        )
        for root in resolved
    ]

    ok_count = sum(1 for r in project_results if r.success)
    return {
        "dry_run": dry_run,
        "roots": [str(r.root) for r in project_results],
        "bundle": mcp_bundle,
        "uv_mode": uv_mode,
        "reinstall_clis": cli_reinstall,
        "summary": {
            "total": len(project_results),
            "ok": ok_count,
            "failed": len(project_results) - ok_count,
        },
        "projects": [
            {
                "root": str(r.root),
                "success": r.success,
                "upgrade_ok": r.upgrade_ok,
                "init_ok": r.init_ok,
                "doctor_ok": r.doctor_ok,
                "upgrade_binary": r.upgrade_binary,
                "upgrade_binary_version": r.upgrade_binary_version,
                "errors": r.errors,
            }
            for r in project_results
        ],
    }


def _reinstall_global_clis(
    checkout: Path,
    *,
    use_blue_green: bool = True,
    force_inplace: bool = False,
) -> dict[str, Any]:
    """Reinstall global tapps-mcp + docs-mcp from *checkout*.

    Default is immutable blue/green ``deploy-local`` (ADR-0023). In-place
    ``uv tool install --reinstall`` mutates ``~/.local/share/uv/tools/*`` under
    live MCP stdio servers and corrupts them — only allowed with
    *force_inplace* when the operator accepts killing every MCP window.
    """
    from tapps_mcp.distribution.mcp_zombie_reap import find_live_mcp_serve_pids

    live_pids = find_live_mcp_serve_pids()
    auto_promoted = False
    if force_inplace:
        strategy = "inplace_forced"
    elif use_blue_green:
        strategy = "blue_green_auto" if live_pids else "blue_green"
    elif live_pids:
        use_blue_green = True
        strategy = "blue_green_auto"
        auto_promoted = True
    else:
        strategy = "inplace"

    meta: dict[str, Any] = {
        "live_mcp_pids": live_pids,
        "strategy": strategy,
        "auto_promoted": auto_promoted,
    }

    if use_blue_green and not force_inplace:
        from tapps_mcp.distribution.blue_green import deploy_blue_green

        deploy = deploy_blue_green(checkout, skip_gate=True)
        ok = bool(deploy.get("ok"))
        summary = json.dumps(
            {
                "release": deploy.get("release"),
                "current": deploy.get("current"),
                "smoke_test": (deploy.get("smoke_test") or {}).get("versions"),
            },
            sort_keys=True,
        )[-500:]
        shared = {"ok": ok, "output": summary}
        if not ok:
            err = (
                deploy.get("quiescence_gate")
                or deploy.get("build")
                or deploy.get("smoke_test")
                or deploy
            )
            shared["error"] = json.dumps(err, default=str)[-500:]
        return {
            **meta,
            "ok": ok,
            "blue_green": deploy,
            "tapps-mcp": {**shared, "binary": "tapps-mcp"},
            "docs-mcp": {**shared, "binary": "docsmcp"},
        }

    results: dict[str, Any] = {**meta}
    for package, binary in (
        ("packages/tapps-mcp", "tapps-mcp"),
        ("packages/docs-mcp", "docsmcp"),
    ):
        proc = subprocess.run(
            ["uv", "tool", "install", "-e", "--reinstall", str(checkout / package)],
            capture_output=True,
            text=True,
            check=False,
        )
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()[-500:]
        results[binary] = {"ok": proc.returncode == 0, "output": output, "binary": binary}
    results["ok"] = all(
        info.get("ok") for key, info in results.items() if key in {"tapps-mcp", "docsmcp"}
    )
    return results


def format_fleet_upgrade_markdown(report: dict[str, Any]) -> str:
    """Render a fleet upgrade report as Markdown."""
    lines = [
        "# TAPPS fleet upgrade",
        "",
        f"- Projects: **{report['summary']['total']}** "
        f"(ok: {report['summary']['ok']}, failed: {report['summary']['failed']})",
        f"- Bundle: `{report.get('bundle', 'developer')}`",
        f"- UV mode: `{report.get('uv_mode', 'auto')}`",
        "",
        "| Project | Upgrade | MCP init | Doctor | Status |",
        "|---------|---------|----------|--------|--------|",
    ]
    for proj in report.get("projects", []):
        status = "OK" if proj.get("success") else "FAIL"
        errors = ", ".join(proj.get("errors") or [])
        if errors:
            status = f"{status} ({errors})"
        lines.append(
            f"| `{Path(proj['root']).name}` | "
            f"{'✓' if proj.get('upgrade_ok') else '✗'} | "
            f"{'✓' if proj.get('init_ok') else ('—' if proj.get('init_ok') is None else '✗')} | "
            f"{'✓' if proj.get('doctor_ok') else ('—' if proj.get('doctor_ok') is None else '✗')} | "
            f"{status} |"
        )
    lines.append("")
    if report.get("reinstall_clis"):
        lines.append("## CLI reinstall")
        lines.append("")
        reinstall = report["reinstall_clis"]
        if isinstance(reinstall, dict):
            strategy = reinstall.get("strategy")
            live = reinstall.get("live_mcp_pids") or []
            if strategy:
                lines.append(f"- Strategy: `{strategy}`")
            if live:
                lines.append(
                    f"- Live MCP servers during reinstall: {len(live)} "
                    "(blue/green avoids killing them; reload MCP to pick up new code)"
                )
            if reinstall.get("auto_promoted"):
                lines.append(
                    "- Auto-promoted to blue/green because in-place reinstall "
                    "would kill live MCP stdio servers"
                )
        for name, info in report["reinstall_clis"].items():
            if not isinstance(info, dict) or name in {
                "live_mcp_pids",
                "strategy",
                "auto_promoted",
                "ok",
                "blue_green",
            }:
                continue
            mark = "ok" if info.get("ok") else "failed"
            lines.append(f"- **{name}**: {mark}")
    return "\n".join(lines)

"""Fleet-level TAPPS upgrade across bootstrapped consumer repos.

Runs ``tapps-mcp upgrade --force`` per project (scaffolding + legacy→NLT MCP
migration) and optionally refreshes MCP host config via ``init --force``.
"""

from __future__ import annotations

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
    if dry_run:
        return True, f"[dry-run] {command_prefix} {' '.join(args)}"
    proc = subprocess.run(
        [command_prefix, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


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
    tapps_checkout: Path | None = None,
    import_legacy_doc_cache: bool = False,
    strip_context7_env: bool = False,
) -> dict[str, Any]:
    """Upgrade every bootstrapped project in the fleet."""
    resolved = resolve_fleet_roots(explicit_roots=roots, scan_parent=scan_parent)
    cli_reinstall: dict[str, Any] | None = None

    if reinstall_clis and not dry_run:
        checkout = (tapps_checkout or Path.cwd()).resolve()
        cli_reinstall = _reinstall_global_clis(checkout)

    project_results: list[FleetUpgradeProjectResult] = []
    for root in resolved:
        project_results.append(
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
        )

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
                "errors": r.errors,
            }
            for r in project_results
        ],
    }


def _reinstall_global_clis(checkout: Path) -> dict[str, Any]:
    """Reinstall tapps-mcp + docs-mcp global CLIs from a checkout."""
    specs = (
        ("tapps-mcp", checkout / "packages" / "tapps-mcp", "tapps-mcp"),
        ("docs-mcp", checkout / "packages" / "docs-mcp", "docs-mcp"),
    )
    results: dict[str, Any] = {}
    for label, pkg, tool_name in specs:
        if not pkg.is_dir():
            results[label] = {"ok": False, "error": f"missing {pkg}"}
            continue
        proc = subprocess.run(
            ["uv", "tool", "install", "--reinstall", "--from", str(pkg), tool_name],
            capture_output=True,
            text=True,
            check=False,
        )
        results[label] = {
            "ok": proc.returncode == 0,
            "binary": "docsmcp" if label == "docs-mcp" else "tapps-mcp",
            "output": (proc.stdout or proc.stderr or "").strip()[-500:],
        }
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
        for name, info in report["reinstall_clis"].items():
            mark = "ok" if info.get("ok") else "failed"
            lines.append(f"- **{name}**: {mark}")
    return "\n".join(lines)

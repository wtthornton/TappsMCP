"""Dependency vulnerability scanner wrapper using pip-audit."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field

import structlog

from tapps_mcp.tools.subprocess_runner import run_command_async

logger = structlog.get_logger(__name__)

# Severity ordering from most to least severe
_SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


@dataclass
class VulnerabilityFinding:
    """A single dependency vulnerability finding."""

    package: str
    installed_version: str
    fixed_version: str = ""
    vulnerability_id: str = ""  # CVE or PYSEC ID
    description: str = ""
    severity: str = "unknown"  # critical/high/medium/low/unknown
    aliases: list[str] = field(default_factory=list)


@dataclass
class DependencyAuditResult:
    """Result of a dependency vulnerability scan."""

    findings: list[VulnerabilityFinding] = field(default_factory=list)
    scanned_packages: int = 0
    vulnerable_packages: int = 0
    scan_source: str = "environment"  # environment/requirements/pyproject
    error: str | None = None


def _severity_meets_threshold(severity: str, threshold: str) -> bool:
    """Check if a severity level meets the minimum threshold.

    Args:
        severity: The severity of the finding.
        threshold: The minimum severity to include.

    Returns:
        True if the severity is at or above the threshold.
    """
    sev_rank = _SEVERITY_ORDER.get(severity.lower(), 0)
    thresh_rank = _SEVERITY_ORDER.get(threshold.lower(), 0)
    return sev_rank >= thresh_rank


def _infer_severity_from_id(vuln_id: str) -> str:
    """Infer a default severity from vulnerability ID prefix.

    pip-audit does not always include severity information.
    CVE-prefixed IDs are generally treated as high by default;
    PYSEC IDs default to medium since they vary widely.

    Args:
        vuln_id: The vulnerability identifier (e.g. CVE-2024-26130).

    Returns:
        An inferred severity string.
    """
    upper_id = vuln_id.upper()
    if upper_id.startswith("CVE"):
        return "high"
    if upper_id.startswith("PYSEC"):
        return "medium"
    return "unknown"


def _parse_pip_audit_json(raw: str) -> DependencyAuditResult:
    """Parse pip-audit ``--format=json`` output.

    JSON structure::

        {"dependencies": [
            {"name": "pkg", "version": "1.0", "vulns": [
                {"id": "PYSEC-2024-1", "fix_versions": ["1.1"],
                 "description": "...", "aliases": ["CVE-..."]}
            ]}
        ]}

    Args:
        raw: Raw JSON string from pip-audit stdout.

    Returns:
        Parsed ``DependencyAuditResult``.
    """
    if not raw.strip():
        return DependencyAuditResult(error="Empty pip-audit output")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return DependencyAuditResult(error=f"Invalid JSON from pip-audit: {exc}")

    if not isinstance(data, dict):
        return DependencyAuditResult(error="Unexpected pip-audit output format")

    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list):
        return DependencyAuditResult(error="Missing 'dependencies' key in pip-audit output")

    findings: list[VulnerabilityFinding] = []
    scanned = 0
    vulnerable_pkgs: set[str] = set()

    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        scanned += 1
        pkg_name = dep.get("name", "unknown")
        pkg_version = dep.get("version", "unknown")
        vulns = dep.get("vulns", [])
        if not isinstance(vulns, list):
            continue

        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            vuln_id = vuln.get("id", "")
            fix_versions = vuln.get("fix_versions", [])
            fix_version = fix_versions[0] if fix_versions else ""
            aliases_raw = vuln.get("aliases", [])
            aliases = aliases_raw if isinstance(aliases_raw, list) else []
            description = vuln.get("description", "")

            severity = _infer_severity_from_id(vuln_id)

            findings.append(
                VulnerabilityFinding(
                    package=pkg_name,
                    installed_version=pkg_version,
                    fixed_version=fix_version,
                    vulnerability_id=vuln_id,
                    description=description,
                    severity=severity,
                    aliases=aliases,
                )
            )
            vulnerable_pkgs.add(pkg_name)

    return DependencyAuditResult(
        findings=findings,
        scanned_packages=scanned,
        vulnerable_packages=len(vulnerable_pkgs),
    )


def _build_pip_audit_args(
    source: str,
    project_root: str,
    ignore_ids: list[str] | None = None,
) -> tuple[list[str], str]:
    """Build pip-audit command arguments.

    Args:
        source: Scan source mode (auto/environment/requirements/pyproject).
        project_root: Project root directory.
        ignore_ids: Vulnerability IDs to exclude (passed as --ignore-vuln).

    Returns:
        Tuple of (command args, resolved scan source name).
    """
    base_args = ["pip-audit", "--format=json", "--desc"]
    if ignore_ids:
        for vid in ignore_ids:
            base_args.extend(["--ignore-vuln", vid])
    resolved_source = "environment"

    if source == "requirements":
        base_args.extend(["-r", "requirements.txt"])
        resolved_source = "requirements"
    elif source == "pyproject":
        base_args.extend(["-r", "pyproject.toml"])
        resolved_source = "pyproject"
    elif source in ("auto", "environment"):
        import pathlib

        root = pathlib.Path(project_root) if project_root else pathlib.Path.cwd()
        if source == "auto" and (root / "requirements.txt").exists():
            base_args.extend(["-r", "requirements.txt"])
            resolved_source = "requirements"
        else:
            # Environment scan: skip editable installs (workspace members, local
            # packages) — they have no PyPI hash and cause pip-audit to error in
            # uv workspaces.  CVE scanning is only meaningful for PyPI deps anyway.
            base_args.append("--skip-editable")

    return base_args, resolved_source


async def run_pip_audit_async(
    project_root: str = "",
    *,
    source: str = "auto",
    severity_threshold: str = "medium",
    ignore_ids: list[str] | None = None,
    timeout: int = 60,
) -> DependencyAuditResult:
    """Run pip-audit and return parsed findings.

    Args:
        project_root: Project root directory for requirements file discovery.
        source: Scan source - auto/environment/requirements/pyproject.
        severity_threshold: Minimum severity to include (critical/high/medium/low/unknown).
        ignore_ids: Vulnerability IDs to exclude from results.
        timeout: Command timeout in seconds (default 60, network calls involved).

    Returns:
        ``DependencyAuditResult`` with findings and metadata.
    """
    if not shutil.which("pip-audit"):
        logger.warning("pip_audit_not_found")
        return DependencyAuditResult(
            error="pip-audit not installed. Install with: pip install pip-audit",
        )

    args, resolved_source = _build_pip_audit_args(source, project_root, ignore_ids)
    cwd = project_root if project_root else None

    logger.info(
        "running_pip_audit",
        source=resolved_source,
        severity_threshold=severity_threshold,
        cwd=cwd,
    )

    result = await run_command_async(args, cwd=cwd, timeout=timeout)

    if result.timed_out:
        return DependencyAuditResult(
            scan_source=resolved_source,
            error=f"pip-audit timed out after {timeout}s",
        )

    # pip-audit exits non-zero when vulnerabilities are found
    # Only treat as error if stdout is empty (real failure)
    if not result.stdout.strip():
        if result.returncode != 0:
            return DependencyAuditResult(
                scan_source=resolved_source,
                error=f"pip-audit failed: {result.stderr}",
            )
        return DependencyAuditResult(scan_source=resolved_source)

    audit_result = _parse_pip_audit_json(result.stdout)
    audit_result.scan_source = resolved_source

    # Apply severity threshold filter
    if severity_threshold != "unknown":
        audit_result.findings = [
            f
            for f in audit_result.findings
            if _severity_meets_threshold(f.severity, severity_threshold)
        ]

    # Apply ignore list filter
    if ignore_ids:
        ignore_set = set(ignore_ids)
        audit_result.findings = [
            f for f in audit_result.findings if f.vulnerability_id not in ignore_set
        ]

    # Recalculate vulnerable_packages after filtering
    audit_result.vulnerable_packages = len({f.package for f in audit_result.findings})

    return audit_result

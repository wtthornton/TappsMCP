"""Dockerfile validator — best-practice and security checks."""

from __future__ import annotations

import re

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding

# Patterns
_FROM_RE = re.compile(r"^FROM\s+", re.MULTILINE | re.IGNORECASE)
_FROM_LATEST_RE = re.compile(r"^FROM\s+\S+:latest\b", re.MULTILINE | re.IGNORECASE)
_USER_RE = re.compile(r"^USER\s+", re.MULTILINE | re.IGNORECASE)
_HEALTHCHECK_RE = re.compile(r"^HEALTHCHECK\s+", re.MULTILINE | re.IGNORECASE)
_ENV_SECRET_RE = re.compile(
    r"^ENV\s+\S*(PASSWORD|SECRET|KEY|TOKEN)\s*=",
    re.MULTILINE | re.IGNORECASE,
)
_RUN_RE = re.compile(r"^RUN\s+", re.MULTILINE | re.IGNORECASE)
_APT_CACHE_RE = re.compile(r"rm\s+-rf\s+/var/lib/apt/lists", re.MULTILINE)
_APT_GET_RE = re.compile(r"apt-get\s+install", re.MULTILINE)
_COPY_REQ_RE = re.compile(r"^COPY\s+requirements", re.MULTILINE | re.IGNORECASE)
_COPY_DOT_RE = re.compile(r"^COPY\s+\.\s+", re.MULTILINE | re.IGNORECASE)
_MULTI_STAGE_RE = re.compile(r"^FROM\s+", re.MULTILINE | re.IGNORECASE)
_MAX_RUN_COMMANDS = 5


def _check_from(
    content: str,
    _lines: list[str],
    findings: list[ValidationFinding],
    _sug: list[str],
) -> None:
    if not _FROM_RE.search(content):
        findings.append(
            ValidationFinding(
                severity="critical",
                message="No FROM instruction found. Every Dockerfile must start with FROM.",
                category="structure",
            )
        )


def _check_latest_tag(
    content: str,
    lines: list[str],
    findings: list[ValidationFinding],
    _sug: list[str],
) -> None:
    if _FROM_LATEST_RE.search(content):
        for i, line in enumerate(lines, 1):
            if re.match(r"^FROM\s+\S+:latest\b", line, re.IGNORECASE):
                findings.append(
                    ValidationFinding(
                        severity="warning",
                        message=(
                            "Avoid 'latest' tag - pin a specific version for reproducibility."
                        ),
                        line=i,
                        category="best_practice",
                    )
                )


def _check_user(
    content: str,
    _lines: list[str],
    findings: list[ValidationFinding],
    _sug: list[str],
) -> None:
    if not _USER_RE.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message=("No USER instruction - container runs as root. Add a non-root USER."),
                category="security",
            )
        )


def _check_healthcheck(
    content: str,
    _lines: list[str],
    _findings: list[ValidationFinding],
    suggestions: list[str],
) -> None:
    if not _HEALTHCHECK_RE.search(content):
        suggestions.append("Add a HEALTHCHECK instruction for container orchestration.")


def _check_env_secrets(
    _content: str,
    lines: list[str],
    findings: list[ValidationFinding],
    _sug: list[str],
) -> None:
    for i, line in enumerate(lines, 1):
        if re.match(r"^ENV\s+\S*(PASSWORD|SECRET|KEY|TOKEN)\s*=", line, re.IGNORECASE):
            findings.append(
                ValidationFinding(
                    severity="critical",
                    message="Potential secret in ENV variable. Use Docker secrets or build args.",
                    line=i,
                    category="security",
                )
            )


def _check_apt_cache(
    content: str,
    _lines: list[str],
    _findings: list[ValidationFinding],
    suggestions: list[str],
) -> None:
    if _APT_GET_RE.search(content) and not _APT_CACHE_RE.search(content):
        suggestions.append("Add 'rm -rf /var/lib/apt/lists/*' after apt-get to reduce image size.")


def _check_multi_stage(
    content: str,
    _lines: list[str],
    _findings: list[ValidationFinding],
    suggestions: list[str],
) -> None:
    if len(_MULTI_STAGE_RE.findall(content)) == 1:
        suggestions.append("Consider using multi-stage builds to reduce final image size.")


def _check_run_count(
    content: str,
    _lines: list[str],
    _findings: list[ValidationFinding],
    suggestions: list[str],
) -> None:
    run_count = len(_RUN_RE.findall(content))
    if run_count > _MAX_RUN_COMMANDS:
        suggestions.append(
            f"Found {run_count} RUN commands. Consider combining with '&&' to reduce layers."
        )


def _check_layer_ordering(
    content: str,
    _lines: list[str],
    _findings: list[ValidationFinding],
    suggestions: list[str],
) -> None:
    copy_req_pos = _COPY_REQ_RE.search(content)
    copy_dot_pos = _COPY_DOT_RE.search(content)
    if copy_req_pos and copy_dot_pos and copy_req_pos.start() > copy_dot_pos.start():
        suggestions.append("COPY requirements.txt before COPY . for better Docker layer caching.")


_DOCKERFILE_CHECKS = (
    _check_from,
    _check_latest_tag,
    _check_user,
    _check_healthcheck,
    _check_env_secrets,
    _check_apt_cache,
    _check_multi_stage,
    _check_run_count,
    _check_layer_ordering,
)


def validate_dockerfile(file_path: str, content: str) -> ConfigValidationResult:
    """Validate a Dockerfile against best practices and security rules."""
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []
    lines = content.splitlines()

    for check in _DOCKERFILE_CHECKS:
        check(content, lines, findings, suggestions)

    has_critical = any(f.severity == "critical" for f in findings)
    return ConfigValidationResult(
        file_path=file_path,
        config_type="dockerfile",
        valid=not has_critical,
        findings=findings,
        suggestions=suggestions,
    )

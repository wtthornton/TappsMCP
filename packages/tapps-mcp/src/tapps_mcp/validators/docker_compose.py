"""Docker Compose validator — structure and best-practice checks."""

from __future__ import annotations

import yaml

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding


def validate_docker_compose(file_path: str, content: str) -> ConfigValidationResult:
    """Validate a docker-compose.yml file."""
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []

    # Parse YAML
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        findings.append(
            ValidationFinding(
                severity="critical",
                message=f"YAML parse error: {exc}",
                category="syntax",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="docker_compose",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    if not isinstance(data, dict):
        findings.append(
            ValidationFinding(
                severity="critical",
                message="Root element must be a YAML mapping.",
                category="structure",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="docker_compose",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    # Services section
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        findings.append(
            ValidationFinding(
                severity="critical",
                message="Missing or empty 'services' section.",
                category="structure",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="docker_compose",
            valid=False,
            findings=findings,
            suggestions=suggestions,
        )

    # Check each service
    for svc_name, svc_config in services.items():
        if not isinstance(svc_config, dict):
            findings.append(
                ValidationFinding(
                    severity="warning",
                    message=f"Service '{svc_name}' has invalid configuration.",
                    category="structure",
                )
            )
            continue

        # Health check
        if "healthcheck" not in svc_config:
            suggestions.append(f"Service '{svc_name}': add a healthcheck.")

        # Resource limits
        deploy = svc_config.get("deploy", {})
        if isinstance(deploy, dict) and "resources" not in deploy:
            suggestions.append(f"Service '{svc_name}': add resource limits (deploy.resources).")

        # Environment configuration
        if "environment" not in svc_config and "env_file" not in svc_config:
            suggestions.append(f"Service '{svc_name}': consider explicit environment or env_file.")

        # Network assignment
        if "networks" not in svc_config:
            suggestions.append(f"Service '{svc_name}': assign to an explicit network.")

    # Global network definitions
    if "networks" not in data:
        suggestions.append("Define explicit networks for inter-service communication.")

    # Volume definitions
    volumes_used = False
    for svc_config in services.values():
        if isinstance(svc_config, dict) and "volumes" in svc_config:
            volumes_used = True
            break
    if volumes_used and "volumes" not in data:
        suggestions.append("Define named volumes at top level for data persistence.")

    has_critical = any(f.severity == "critical" for f in findings)
    return ConfigValidationResult(
        file_path=file_path,
        config_type="docker_compose",
        valid=not has_critical,
        findings=findings,
        suggestions=suggestions,
    )

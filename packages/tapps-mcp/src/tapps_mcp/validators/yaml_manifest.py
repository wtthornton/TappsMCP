"""Generic YAML manifest validation for document consumer repos."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding


def _matches_manifest_glob(rel_path: str, globs: list[str]) -> bool:
    normalised = rel_path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalised, pattern) for pattern in globs)


def validate_yaml_manifest(
    file_path: str,
    content: str,
    *,
    path_globs: list[str] | None = None,
    required_keys: list[str] | None = None,
    project_root: Path | None = None,
) -> ConfigValidationResult:
    """Validate a consumer YAML manifest (brands/, templates/, etc.)."""
    root = project_root or Path.cwd()
    rel = Path(file_path)
    if rel.is_absolute():
        try:
            rel = rel.relative_to(root)
        except ValueError:
            rel = Path(file_path).name
    rel_str = rel.as_posix()

    globs = path_globs or ["brands/**/*.yaml", "brands/**/*.yml", "templates/**/*.yaml"]
    if not _matches_manifest_glob(rel_str, globs):
        return ConfigValidationResult(
            file_path=file_path,
            config_type="yaml_manifest",
            valid=True,
            findings=[],
            suggestions=["Path does not match manifest_validation.path_globs — syntax-only check."],
        )

    findings: list[ValidationFinding] = []
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        findings.append(
            ValidationFinding(
                severity="critical",
                message=f"Invalid YAML: {exc}",
                category="syntax",
            )
        )
        return ConfigValidationResult(
            file_path=file_path,
            config_type="yaml_manifest",
            valid=False,
            findings=findings,
            suggestions=[],
        )

    if data is None:
        findings.append(
            ValidationFinding(
                severity="critical",
                message="Manifest YAML is empty",
                category="structure",
            )
        )
    elif not isinstance(data, dict):
        findings.append(
            ValidationFinding(
                severity="critical",
                message="Manifest YAML root must be a mapping/object",
                category="structure",
            )
        )
    else:
        for key in required_keys or []:
            if key not in data:
                findings.append(
                    ValidationFinding(
                        severity="critical",
                        message=f"Missing required key: {key!r}",
                        category="schema",
                    )
                )

    valid = not any(f.severity == "critical" for f in findings)
    return ConfigValidationResult(
        file_path=file_path,
        config_type="yaml_manifest",
        valid=valid,
        findings=findings,
        suggestions=_manifest_suggestions(data if isinstance(data, dict) else {}),
    )


def _manifest_suggestions(data: dict[str, Any]) -> list[str]:
    if not data:
        return ["Add top-level manifest keys expected by your document toolchain."]
    return []

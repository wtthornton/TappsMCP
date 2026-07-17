"""Document-output judge presets and configuration helpers (EPIC-104/105)."""

from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path
from typing import Any

import yaml

from tapps_mcp.pipeline.report_studio.installer import check_report_studio

_DOCUMENT_PATH_MARKERS = ("reports/", "templates/", "brands/")


def is_document_consumer(project_root: Path) -> bool:
    """Return True when the project looks like a document-shipping consumer.

    Requires a stronger signal than a bare ``reports/`` directory (TAP-4810):
    report-studio installed, or both ``brands/`` and ``templates/`` present.
    """
    root = project_root.resolve()
    if check_report_studio(root).get("installed"):
        return True
    return (root / "brands").is_dir() and (root / "templates").is_dir()


_SKIP_BUILD_SCRIPT_PARTS = ("node_modules", ".venv", "venv", "dist", "build", ".git")


def _find_build_script(project_root: Path) -> Path | None:
    """Locate a document build script, skipping generated/vendor trees (TAP-4836)."""
    candidates = sorted(project_root.glob("**/build-pdfs.mjs"))
    if not candidates:
        candidates = sorted(project_root.glob("**/build*.mjs"))
    for candidate in candidates:
        parts = set(candidate.parts)
        if parts.intersection(_SKIP_BUILD_SCRIPT_PARTS):
            continue
        return candidate
    return None


_WHEN_CHANGED_DOC_PATHS = ["reports/**", "src/**", "brands/**", "templates/**"]


def _report_studio_cli_prefix(project_root: Path) -> str | None:
    """Return a shell prefix when report-studio CLI is likely available."""
    if shutil.which("report-studio"):
        return "report-studio"
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        if "report-studio" in text or "nlt-report-studio" in text:
            return "uv run report-studio"
    if check_report_studio(project_root).get("installed"):
        return "uv run report-studio"
    return None


def _find_reference_pdf(project_root: Path) -> Path | None:
    """Return the first discoverable built PDF fixture for audit judges."""
    patterns = (
        "**/public/downloads/vol-*.pdf",
        "**/public/downloads/*.pdf",
        "**/downloads/vol-*.pdf",
        "**/out/**/*.pdf",
    )
    for pattern in patterns:
        matches = sorted(project_root.glob(pattern))
        if matches:
            return matches[0]
    return None


def _find_pdf_audit_test(project_root: Path) -> Path | None:
    for pattern in (
        "tests/test_pdf_audit.py",
        "tests/unit/test_pdf_audit.py",
        "test/test_pdf_audit.py",
    ):
        candidate = project_root / pattern
        if candidate.is_file():
            return candidate
    matches = sorted(project_root.glob("**/test_pdf_audit.py"))
    return matches[0] if matches else None


def discover_document_judge_preset(project_root: Path) -> list[dict[str, Any]]:
    """Return blocking judge presets discovered for document consumers."""
    root = project_root.resolve()
    if not is_document_consumer(root):
        return []

    judges: list[dict[str, Any]] = []
    build_script = _find_build_script(root)
    if build_script is not None:
        judges.append(
            {
                "type": "grep",
                "target": str(build_script.relative_to(root)),
                "expect": r"--audit",
                "description": "Site prebuild runs document build with post-build audit",
                "blocking": True,
                "when_changed": [
                    str(build_script.relative_to(root)),
                    *_WHEN_CHANGED_DOC_PATHS,
                ],
            }
        )

    audit_test = _find_pdf_audit_test(root)
    if audit_test is not None:
        rel = audit_test.relative_to(root)
        judges.append(
            {
                "type": "pytest",
                "target": str(rel.parent if rel.name.startswith("test_") else rel),
                "description": "PDF audit CLI contract tests",
                "blocking": True,
                "when_changed": list(_WHEN_CHANGED_DOC_PATHS),
            }
        )
        if rel.name == "test_pdf_audit.py":
            judges[-1]["target"] = str(rel)

    cli_prefix = _report_studio_cli_prefix(root)
    reference_pdf = _find_reference_pdf(root)
    if cli_prefix is not None and reference_pdf is not None:
        pdf_rel = reference_pdf.relative_to(root).as_posix()
        judges.append(
            {
                "type": "shell",
                "target": f"{cli_prefix} audit --profile reference {pdf_rel}",
                "description": "Rendered PDF passes report-studio reference audit profile",
                "blocking": True,
                "when_changed": list(_WHEN_CHANGED_DOC_PATHS),
                "timeout_s": 120,
            }
        )

    return judges


def summarise_configured_judges(judges: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise validate_changed.judges for doctor output."""
    if not judges:
        return {"configured": False, "count": 0, "blocking": 0, "advisory": 0}
    blocking = sum(1 for j in judges if j.get("blocking"))
    return {
        "configured": True,
        "count": len(judges),
        "blocking": blocking,
        "advisory": len(judges) - blocking,
    }


def merge_document_judges_into_yaml(project_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Merge discovered document judges into `.tapps-mcp.yaml` when missing."""
    root = project_root.resolve()
    config_path = root / ".tapps-mcp.yaml"
    preset = discover_document_judge_preset(root)
    result: dict[str, Any] = {
        "merged": False,
        "preset_count": len(preset),
        "messages": [],
    }
    if not preset:
        result["messages"].append("No document tooling detected — judges unchanged")
        return result

    existing: dict[str, Any] = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded

    current = existing.get("validate_changed", {})
    if not isinstance(current, dict):
        current = {}
    current_judges = current.get("judges", [])
    if not isinstance(current_judges, list):
        current_judges = []

    if current_judges:
        result["messages"].append(
            f"validate_changed.judges already has {len(current_judges)} entries — preserved"
        )
        return result

    merged = {**existing, "validate_changed": {**current, "judges": preset}}
    if dry_run:
        result["merged"] = True
        result["messages"].append(f"Would merge {len(preset)} document judge(s)")
        return result

    config_path.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    result["merged"] = True
    result["messages"].append(f"Merged {len(preset)} document judge(s) into .tapps-mcp.yaml")
    return result


def is_document_layout_path(file_path: Path, project_root: Path) -> bool:
    """Return True when a changed file lives under document layout directories."""
    try:
        rel = file_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return False
    return any(marker in f"{rel}/" or rel.startswith(marker.rstrip("/")) for marker in _DOCUMENT_PATH_MARKERS)


DOCUMENT_BUILDER_PROFILE = "document-builder"


def merge_document_memory_profile(project_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """No-op document memory profile merge (TAP-4810).

    Previously wrote ``memory.profile: document-builder``, which is not a
    tapps-brain builtin and raised ``FileNotFoundError`` on resolve. Document
    consumers keep the default ``repo-brain`` (or whatever is already set).
    """
    del dry_run
    root = project_root.resolve()
    result: dict[str, Any] = {
        "merged": False,
        "profile": None,
        "messages": [],
    }
    if not is_document_consumer(root):
        result["messages"].append("Not a document consumer — memory profile unchanged")
        return result

    config_path = root / ".tapps-mcp.yaml"
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            memory = loaded.get("memory", {})
            if isinstance(memory, dict) and memory.get("profile"):
                result["profile"] = memory.get("profile")
                result["messages"].append(
                    f"memory.profile already set to {memory.get('profile')!r} — preserved"
                )
                return result

    result["messages"].append(
        "Document consumer detected — leaving memory.profile unset "
        f"(do not write {DOCUMENT_BUILDER_PROFILE!r}; use a real brain builtin)"
    )
    return result


def path_matches_narrative_glob(file_path: Path, project_root: Path, globs: list[str]) -> bool:
    """Return True when file_path matches any narrative path glob."""
    if not globs:
        return False
    try:
        rel = file_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel = file_path.as_posix()
    return any(fnmatch.fnmatch(rel, pattern) for pattern in globs)

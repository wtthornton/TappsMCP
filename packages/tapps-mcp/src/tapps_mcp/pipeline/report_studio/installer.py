"""Install nlt-report-studio consumer wiring during tapps_init."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_GIT_REPO = "https://github.com/wtthornton/ReportLab.git"
_DEFAULT_TAG = "v0.1.3"
_VERSION_FLOOR = "0.1.3"


def _merge_pyproject_text(text: str, *, tag: str) -> tuple[str, list[str]]:
    messages: list[str] = []
    if "nlt-report-studio" in text:
        messages.append("pyproject.toml already references nlt-report-studio (unchanged)")
        return text, messages

    dep_entry = f'    "nlt-report-studio>={_VERSION_FLOOR},<0.2",'
    source_line = f'nlt-report-studio = {{ git = "{_GIT_REPO}", tag = "{tag}" }}'

    if "[dependency-groups]" in text:
        text = re.sub(
            r"(\[dependency-groups\]\s*\n)",
            rf"\1reports = [\n{dep_entry}\n]\n",
            text,
            count=1,
        )
        messages.append("pyproject.toml: added [dependency-groups] reports")
    elif "[project.optional-dependencies]" in text:
        text = re.sub(
            r"(\[project\.optional-dependencies\]\s*\n)",
            rf"\1reports = [\n{dep_entry}\n]\n",
            text,
            count=1,
        )
        messages.append("pyproject.toml: added [project.optional-dependencies] reports")
    else:
        text = text.rstrip() + f"\n\n[dependency-groups]\nreports = [\n{dep_entry}\n]\n"
        messages.append("pyproject.toml: appended [dependency-groups] reports")

    if "[tool.uv.sources]" in text:
        text = re.sub(
            r"(\[tool\.uv\.sources\]\s*\n)",
            rf"\1{source_line}\n",
            text,
            count=1,
        )
        messages.append("pyproject.toml: added [tool.uv.sources] nlt-report-studio")
    else:
        text = text.rstrip() + f"\n\n[tool.uv.sources]\n{source_line}\n"
        messages.append("pyproject.toml: appended [tool.uv.sources]")

    return text, messages


def _try_scaffold_report(
    project_root: Path,
    *,
    report_name: str,
    template_id: str,
    brand_id: str,
) -> dict[str, Any]:
    uv = shutil.which("uv")
    if uv is None:
        return {
            "scaffolded": False,
            "skipped_reason": "uv not on PATH — run report-studio init manually",
        }
    cmd = [
        uv,
        "run",
        "report-studio",
        "init",
        "--report",
        report_name,
        "--template",
        template_id,
        "--brand",
        brand_id,
        "--root",
        str(project_root),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"scaffolded": False, "skipped_reason": str(exc)}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "report-studio init failed").strip()
        return {"scaffolded": False, "skipped_reason": detail}
    return {
        "scaffolded": True,
        "report": report_name,
        "stdout": proc.stdout.strip(),
    }


def install_report_studio(
    project_root: Path,
    *,
    tag: str = _DEFAULT_TAG,
    report_name: str | None = None,
    template_id: str = "architecture_theory",
    brand_id: str = "nlt-v3.2",
    dry_run: bool = False,
    content_return: bool = False,
) -> dict[str, Any]:
    """Pin nlt-report-studio in pyproject.toml and optionally scaffold a report."""
    pyproject_path = project_root / "pyproject.toml"
    result: dict[str, Any] = {
        "files_written": [],
        "pyproject_merged": False,
        "scaffold": None,
        "messages": [],
    }

    if pyproject_path.is_file():
        merged, messages = _merge_pyproject_text(
            pyproject_path.read_text(encoding="utf-8"),
            tag=tag,
        )
        result["messages"] = messages
        if content_return:
            result["content"] = {pyproject_path.name: merged}
            result["skipped_reason"] = "content_return mode — caller must write files"
            return result
        if dry_run:
            result["files_written"] = [pyproject_path.name]
            result["pyproject_merged"] = "nlt-report-studio" not in merged or bool(messages)
            return result
        pyproject_path.write_text(merged, encoding="utf-8")
        result["files_written"].append(pyproject_path.name)
        result["pyproject_merged"] = True
    else:
        msg = f"pyproject.toml not found at {pyproject_path}"
        result["skipped_reason"] = msg
        return result

    if report_name:
        if dry_run or content_return:
            result["scaffold"] = {
                "scaffolded": False,
                "skipped_reason": "dry_run or content_return — run report-studio init after sync",
            }
        else:
            result["scaffold"] = _try_scaffold_report(
                project_root,
                report_name=report_name,
                template_id=template_id,
                brand_id=brand_id,
            )

    result["messages"].append(
        "Next: uv sync --group reports  # or --extra reports / --group dev per pyproject"
    )
    result["messages"].append("CI: copy templates/consumer/report-studio-verify.yml from ReportLab")
    return result


def check_report_studio(project_root: Path) -> dict[str, Any]:
    """Return whether pyproject pins nlt-report-studio."""
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return {"installed": False, "detail": "no pyproject.toml"}
    text = pyproject_path.read_text(encoding="utf-8")
    if "nlt-report-studio" not in text:
        return {"installed": False, "detail": "nlt-report-studio not pinned"}
    reports_dir = project_root / "reports"
    return {
        "installed": True,
        "has_reports_dir": reports_dir.is_dir(),
        "report_count": len(list(reports_dir.glob("*/story.py"))) if reports_dir.is_dir() else 0,
    }

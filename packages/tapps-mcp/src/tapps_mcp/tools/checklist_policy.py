"""Optional project overrides for ``tapps_checklist`` policy maps.

Reads ``.tapps-mcp/checklist-policy.yaml`` when present and merges
``extra_required`` / ``extra_recommended`` into built-in engagement maps.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

POLICY_FILENAME = "checklist-policy.yaml"


@dataclass(frozen=True)
class ChecklistPolicyExtras:
    """Parsed extras from checklist-policy.yaml."""

    extra_required: dict[str, list[str]]
    extra_recommended: dict[str, list[str]]
    content_fingerprint: str


def _stable_fingerprint(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[
        :20
    ]


def load_checklist_policy_extras(project_root: Path) -> ChecklistPolicyExtras | None:
    """Load optional checklist policy file from the project root."""
    path = project_root / ".tapps-mcp" / POLICY_FILENAME
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("checklist_policy_load_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    er = raw.get("extra_required") or {}
    er2 = raw.get("extra_recommended") or {}
    if not isinstance(er, dict):
        er = {}
    if not isinstance(er2, dict):
        er2 = {}
    extra_required: dict[str, list[str]] = {}
    extra_recommended: dict[str, list[str]] = {}
    for _key, dct, out in (
        ("extra_required", er, extra_required),
        ("extra_recommended", er2, extra_recommended),
    ):
        for task, tools in dct.items():
            if not isinstance(task, str) or not isinstance(tools, list):
                continue
            clean = [t for t in tools if isinstance(t, str) and t.strip()]
            if clean:
                out[task] = clean
    fp = _stable_fingerprint({"extra_required": extra_required, "path": str(path)})
    return ChecklistPolicyExtras(
        extra_required=extra_required,
        extra_recommended=extra_recommended,
        content_fingerprint=fp,
    )


def merge_engagement_maps(
    base: dict[str, dict[str, dict[str, list[str]]]],
    extras: ChecklistPolicyExtras | None,
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Deep-copy *base* and append tools from *extras* per task type."""
    merged = copy.deepcopy(base)
    if extras is None:
        return merged
    for _engagement, task_map in merged.items():
        for task_name, tier_lists in task_map.items():
            if not isinstance(tier_lists, dict):
                continue
            req = list(tier_lists.get("required", []))
            rec = list(tier_lists.get("recommended", []))
            for t in extras.extra_required.get(task_name, []):
                if t not in req:
                    req.append(t)
            for t in extras.extra_recommended.get(task_name, []):
                if t not in rec:
                    rec.append(t)
            tier_lists["required"] = req
            tier_lists["recommended"] = rec
    return merged


def compute_policy_version(
    merged_maps: dict[str, dict[str, dict[str, list[str]]]],
    extras: ChecklistPolicyExtras | None,
) -> str:
    """Short stable version token for clients and CI."""
    payload = json.dumps(merged_maps, sort_keys=True)
    if extras is not None:
        payload += extras.content_fingerprint
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

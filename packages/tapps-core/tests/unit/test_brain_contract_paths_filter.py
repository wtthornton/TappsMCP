"""TAP-6736: pin brain-contract.yml's path filter to the on-disk bridge modules.

The megafile split moved HttpBrainBridge mixin bodies out of brain_bridge.py
into sibling brain_bridge_*.py modules. brain-contract.yml's pull_request
path filter only listed the single facade file, so a PR editing only a
mixin module would never trigger the contract workflow. This test parses
the workflow YAML and asserts every brain_bridge*.py file on disk is
matched by at least one `paths:` pattern.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "brain-contract.yml"
_BRIDGE_DIR = _REPO_ROOT / "packages" / "tapps-core" / "src" / "tapps_core"


def _bridge_module_paths() -> list[str]:
    return sorted(
        p.relative_to(_REPO_ROOT).as_posix() for p in _BRIDGE_DIR.glob("brain_bridge*.py")
    )


def _path_filter_patterns() -> list[str]:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))
    # PyYAML follows YAML 1.1: the unquoted `on:` key parses as the boolean
    # True, not the string "on".
    on_section = workflow.get("on", workflow.get(True))
    return list(on_section["pull_request"]["paths"])


def test_all_bridge_modules_matched_by_path_filter() -> None:
    modules = _bridge_module_paths()
    assert modules, "expected at least one brain_bridge*.py module on disk"

    patterns = _path_filter_patterns()
    unmatched = [
        module
        for module in modules
        if not any(fnmatch.fnmatch(module, pattern) for pattern in patterns)
    ]

    assert not unmatched, (
        f"brain-contract.yml paths filter does not match: {unmatched} "
        f"(patterns={patterns})"
    )

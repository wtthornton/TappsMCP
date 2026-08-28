"""Tests for staged instinct -> brain memory promotion (TAP-6701, VAL-23).

Selector boundary cases, dry-run diff content, and apply + idempotency all run
against ``tmp_path`` fixtures — never the real ``~/.claude/homunculus/`` tree
(SC-6). ``--apply`` is exercised only with a mocked ``bridge.promote_instinct``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tapps_mcp.tools.instinct_promotion import (
    apply_promotions,
    render_dry_run_report,
    select_instinct_candidates,
)

_FRONTMATTER = """---
id: {id}
trigger: when doing the thing
confidence: {confidence}
domain: workflow
source: session-observation
scope: project
project_id: {project_id}
project_name: {project_name}
---
"""

_BODY = """
# {title}

## Action
{action}

## Evidence
- Observed {observed} times in session abc123
- Last observed: 2026-08-20T00:00:00Z
"""


def _write_instinct(
    instincts_dir: Path,
    *,
    instinct_id: str,
    confidence: float,
    observed: int,
    project_id: str = "9a88a8e9f245",
    project_name: str = "tapps-mcp",
    action: str = "Do the thing carefully.",
    extra_frontmatter: str = "",
) -> Path:
    instincts_dir.mkdir(parents=True, exist_ok=True)
    text = _FRONTMATTER.format(
        id=instinct_id, confidence=confidence, project_id=project_id, project_name=project_name
    )
    if extra_frontmatter:
        text = text.rstrip("\n")[: -len("---\n")] + extra_frontmatter + "---\n"
    text += _BODY.format(title=instinct_id, action=action, observed=observed)
    path = instincts_dir / f"{instinct_id}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _write_projects_json(homunculus_root: Path, *, project_id: str, name: str, root: Path) -> None:
    homunculus_root.mkdir(parents=True, exist_ok=True)
    data = {project_id: {"id": project_id, "name": name, "root": str(root)}}
    (homunculus_root / "projects.json").write_text(json.dumps(data), encoding="utf-8")


class TestSelectInstinctCandidates:
    def test_no_projects_json_returns_empty(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        assert select_instinct_candidates(homunculus_root, project_root) == []

    def test_confidence_boundary_0_84_excluded_0_85_included(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=project_root)
        instincts_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        _write_instinct(instincts_dir, instinct_id="low-conf", confidence=0.84, observed=5)
        _write_instinct(instincts_dir, instinct_id="high-conf", confidence=0.85, observed=5)

        candidates = select_instinct_candidates(homunculus_root, project_root)
        ids = {c["id"] for c in candidates}
        assert "high-conf" in ids
        assert "low-conf" not in ids

    def test_observation_boundary_2_excluded_3_included(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=project_root)
        instincts_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        _write_instinct(instincts_dir, instinct_id="few-obs", confidence=0.9, observed=2)
        _write_instinct(instincts_dir, instinct_id="enough-obs", confidence=0.9, observed=3)

        candidates = select_instinct_candidates(homunculus_root, project_root)
        ids = {c["id"] for c in candidates}
        assert "enough-obs" in ids
        assert "few-obs" not in ids

    def test_observation_count_matches_non_times_wording(self, tmp_path: Path) -> None:
        """The count noun varies across projects ("writes", "Read calls", ...) —
        only the "Observed <N>" prefix should be required (fleet recon finding)."""
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=project_root)
        instincts_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        instincts_dir.mkdir(parents=True)
        text = _FRONTMATTER.format(
            id="alt-wording", confidence=0.9, project_id="p1", project_name="tapps-mcp"
        )
        text += (
            "\n# alt-wording\n\n## Action\nDo the thing.\n\n"
            "## Evidence\n- Observed 12 writes in session x\n"
            "- Last observed: 2026-08-20\n"
        )
        (instincts_dir / "alt-wording.md").write_text(text, encoding="utf-8")

        candidates = select_instinct_candidates(homunculus_root, project_root)
        assert {c["id"] for c in candidates} == {"alt-wording"}
        assert candidates[0]["observed_count"] == 12

    def test_already_promoted_excluded(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=project_root)
        instincts_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        _write_instinct(
            instincts_dir,
            instinct_id="already-promoted",
            confidence=0.9,
            observed=5,
            extra_frontmatter="promoted_key: already-promoted\n",
        )
        candidates = select_instinct_candidates(homunculus_root, project_root)
        assert candidates == []

    def test_matches_project_by_root(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        repo_a = tmp_path / "repo-a"
        repo_b = tmp_path / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        homunculus_root.mkdir(parents=True)
        data = {
            "hash-a": {"id": "hash-a", "name": "repo-a", "root": str(repo_a)},
            "hash-b": {"id": "hash-b", "name": "repo-b", "root": str(repo_b)},
        }
        (homunculus_root / "projects.json").write_text(json.dumps(data), encoding="utf-8")
        _write_instinct(
            homunculus_root / "projects" / "hash-a" / "instincts" / "personal",
            instinct_id="a-instinct",
            confidence=0.9,
            observed=5,
            project_id="hash-a",
            project_name="repo-a",
        )
        _write_instinct(
            homunculus_root / "projects" / "hash-b" / "instincts" / "personal",
            instinct_id="b-instinct",
            confidence=0.9,
            observed=5,
            project_id="hash-b",
            project_name="repo-b",
        )

        candidates = select_instinct_candidates(homunculus_root, repo_a)
        ids = {c["id"] for c in candidates}
        assert ids == {"a-instinct"}

    def test_project_name_override(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(
            homunculus_root,
            project_id="other-hash",
            name="other-project",
            root=tmp_path / "elsewhere",
        )
        _write_instinct(
            homunculus_root / "projects" / "other-hash" / "instincts" / "personal",
            instinct_id="other-instinct",
            confidence=0.9,
            observed=5,
            project_id="other-hash",
            project_name="other-project",
        )
        # project_root does not match "elsewhere" — only --project name override finds it.
        assert select_instinct_candidates(homunculus_root, project_root) == []
        candidates = select_instinct_candidates(
            homunculus_root, project_root, project_name="other-project"
        )
        assert {c["id"] for c in candidates} == {"other-instinct"}

    def test_candidate_shape(self, tmp_path: Path) -> None:
        homunculus_root = tmp_path / "homunculus"
        project_root = tmp_path / "repo"
        project_root.mkdir()
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=project_root)
        instincts_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        _write_instinct(
            instincts_dir,
            instinct_id="shape-check",
            confidence=0.9,
            observed=8,
            action="Use grep before reading files.",
        )
        candidates = select_instinct_candidates(homunculus_root, project_root)
        assert len(candidates) == 1
        c = candidates[0]
        assert c["proposed_key"] == "shape-check"
        assert c["tier"] == "pattern"
        assert c["scope"] == "project"
        assert c["evidence"] == "instinct:shape-check"
        assert c["value"] == "Use grep before reading files."
        assert c["observed_count"] == 8


class TestRenderDryRunReport:
    def test_empty_candidates(self) -> None:
        report = render_dry_run_report([])
        assert "No instinct promotion candidates" in report

    def test_report_content(self) -> None:
        candidates = [
            {
                "id": "x",
                "proposed_key": "x",
                "value": "do the thing",
                "tier": "pattern",
                "scope": "project",
                "evidence": "instinct:x",
                "confidence": 0.9,
                "observed_count": 5,
            }
        ]
        report = render_dry_run_report(candidates)
        assert "key: x" in report
        assert "tier: pattern" in report
        assert "scope: project" in report
        assert "evidence: instinct:x" in report
        assert "do the thing" in report


class TestApplyPromotions:
    @pytest.fixture()
    def candidate_file(self, tmp_path: Path) -> Path:
        instincts_dir = tmp_path / "instincts" / "personal"
        return _write_instinct(instincts_dir, instinct_id="apply-me", confidence=0.9, observed=5)

    async def _candidates_for(self, tmp_path: Path, path: Path) -> list[dict[str, object]]:
        homunculus_root = tmp_path / "homunculus"
        _write_projects_json(homunculus_root, project_id="p1", name="tapps-mcp", root=tmp_path)
        # Point selector at the real instincts dir we already wrote.
        target_dir = homunculus_root / "projects" / "p1" / "instincts" / "personal"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_dir.joinpath(path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return select_instinct_candidates(homunculus_root, tmp_path)

    @pytest.mark.asyncio
    async def test_apply_calls_bridge_and_appends_promoted_key(
        self, tmp_path: Path, candidate_file: Path
    ) -> None:
        candidates = await self._candidates_for(tmp_path, candidate_file)
        assert len(candidates) == 1
        bridge = AsyncMock()
        bridge.promote_instinct = AsyncMock(return_value={"key": "apply-me", "success": True})

        results = await apply_promotions(candidates, bridge, operator="bill")

        assert len(results) == 1
        bridge.promote_instinct.assert_awaited_once_with(
            key="apply-me",
            value="Do the thing carefully.",
            tier="pattern",
            scope="project",
            signal="human",
            actor="operator:bill",
            evidence="instinct:apply-me",
        )
        written = candidates[0]["file"].read_text(encoding="utf-8")
        assert "promoted_key: apply-me" in written

    @pytest.mark.asyncio
    async def test_apply_idempotent_second_run_zero_calls(
        self, tmp_path: Path, candidate_file: Path
    ) -> None:
        candidates = await self._candidates_for(tmp_path, candidate_file)
        bridge = AsyncMock()
        bridge.promote_instinct = AsyncMock(return_value={"key": "apply-me", "success": True})

        await apply_promotions(candidates, bridge, operator="bill")
        assert bridge.promote_instinct.await_count == 1

        # Re-running apply_promotions with the SAME (now-stale) candidate list
        # must not call the bridge again — the file already carries promoted_key.
        second_results = await apply_promotions(candidates, bridge, operator="bill")
        assert second_results == []
        assert bridge.promote_instinct.await_count == 1

        # And re-selecting from disk finds no candidates at all.
        instincts_dir = candidates[0]["file"].parent
        homunculus_root = instincts_dir.parent.parent.parent
        project_id = instincts_dir.parent.parent.name
        assert select_instinct_candidates(homunculus_root, tmp_path) == []
        # Sanity: the file really is under the expected homunculus layout.
        assert project_id == "p1"

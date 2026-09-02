"""Tests for server_skill_tools — the tapps_skill_learnings MCP tool (TAP-6861)."""

from __future__ import annotations

import json

import pytest

from tapps_mcp.pipeline.skill_learnings import bullet_content_hash
from tapps_mcp.pipeline.skill_managed_block import MARKER_BEGIN_PREFIX, MARKER_END
from tapps_mcp.server_skill_tools import tapps_skill_learnings

pytestmark = pytest.mark.usefixtures("envelope_guard")

SKILL_MD = (
    "---\nname: demo\ndescription: A demo skill.\n---\n\n"
    f"{MARKER_BEGIN_PREFIX} demo v1.0.0 -->\n"
    "policy header\n\n"
    "- Verifiers are tiered by proof shape.\n"
    f"{MARKER_END}\n\n"
    "- Fleet manifest refs live in .tapps-mcp.yaml.\n"
)
LEARNINGS_MD = "- Retry the flaky network call up to three times.\n"


def _write_skill_dir(tmp_path, skill_md: str = SKILL_MD, learnings_md: str = LEARNINGS_MD):
    (tmp_path / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (tmp_path / "learnings.md").write_text(learnings_md, encoding="utf-8")
    return str(tmp_path)


class TestValidation:
    @pytest.mark.asyncio
    async def test_invalid_action_rejected(self, tmp_path) -> None:
        result = await tapps_skill_learnings("bogus", skill_dir=str(tmp_path))

        assert result["success"] is False
        assert result["error"]["code"] == "invalid_action"

    @pytest.mark.asyncio
    async def test_missing_skill_dir_rejected(self) -> None:
        result = await tapps_skill_learnings("audit", skill_dir="")

        assert result["success"] is False
        assert result["error"]["code"] == "missing_skill_dir"

    @pytest.mark.asyncio
    async def test_missing_skill_md_reported(self, tmp_path) -> None:
        (tmp_path / "learnings.md").write_text(LEARNINGS_MD, encoding="utf-8")

        result = await tapps_skill_learnings("audit", skill_dir=str(tmp_path))

        assert result["success"] is False
        assert result["error"]["code"] == "skill_md_missing"

    @pytest.mark.asyncio
    async def test_missing_learnings_md_reported(self, tmp_path) -> None:
        (tmp_path / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

        result = await tapps_skill_learnings("audit", skill_dir=str(tmp_path))

        assert result["success"] is False
        assert result["error"]["code"] == "learnings_md_missing"


class TestAuditAction:
    @pytest.mark.asyncio
    async def test_audit_returns_all_finding_classes(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings("audit", skill_dir=skill_dir)

        assert result["success"] is True
        data = result["data"]
        assert set(data) >= {
            "size",
            "already_covered",
            "near_duplicate",
            "contradictions",
            "region",
        }
        assert data["size"]["bullet_count"] == 1

    @pytest.mark.asyncio
    async def test_audit_performs_no_writes(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)
        before_skill = (tmp_path / "SKILL.md").read_bytes()
        before_learnings = (tmp_path / "learnings.md").read_bytes()

        await tapps_skill_learnings("audit", skill_dir=skill_dir)

        assert (tmp_path / "SKILL.md").read_bytes() == before_skill
        assert (tmp_path / "learnings.md").read_bytes() == before_learnings


class TestVerifyAction:
    @pytest.mark.asyncio
    async def test_verify_requires_rule_texts(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings("verify", skill_dir=skill_dir)

        assert result["success"] is False
        assert result["error"]["code"] == "missing_rule_texts"

    @pytest.mark.asyncio
    async def test_verify_reports_present_in_neither(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings(
            "verify", skill_dir=skill_dir, rule_texts="A rule that appears nowhere at all."
        )

        assert result["success"] is True
        assert result["data"]["results"][0]["status"] == "present_in_neither"


class TestPromoteAction:
    @pytest.mark.asyncio
    async def test_promote_below_end_marker_succeeds_and_writes(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings(
            "promote",
            skill_dir=skill_dir,
            rule_text="Retry the flaky network call up to three times.",
            generator_file="pipeline/platform_skills.py",
        )

        assert result["success"] is True
        assert result["data"]["accepted"] is True
        assert result["data"]["region"] == "project_region"
        updated = (tmp_path / "SKILL.md").read_text(encoding="utf-8")
        assert "Retry the flaky network call" in updated

    @pytest.mark.asyncio
    async def test_promote_requires_rule_text_and_generator_file(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        missing_rule = await tapps_skill_learnings(
            "promote", skill_dir=skill_dir, generator_file="pipeline/platform_skills.py"
        )
        missing_generator = await tapps_skill_learnings(
            "promote", skill_dir=skill_dir, rule_text="Some rule."
        )

        assert missing_rule["error"]["code"] == "missing_rule_text"
        assert missing_generator["error"]["code"] == "missing_generator_file"


class TestTrimAction:
    @pytest.mark.asyncio
    async def test_trim_requires_plan(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings("trim", skill_dir=skill_dir)

        assert result["success"] is False
        assert result["error"]["code"] == "missing_trim_plan"

    @pytest.mark.asyncio
    async def test_trim_invalid_json_rejected(self, tmp_path) -> None:
        skill_dir = _write_skill_dir(tmp_path)

        result = await tapps_skill_learnings("trim", skill_dir=skill_dir, trim_plan_json="not json")

        assert result["success"] is False
        assert result["error"]["code"] == "invalid_trim_plan"

    @pytest.mark.asyncio
    async def test_trim_deletes_and_writes_file(self, tmp_path) -> None:
        learnings = "- keep this\n- delete this\n"
        skill_dir = _write_skill_dir(tmp_path, learnings_md=learnings)
        plan = json.dumps(
            [{"content_hash": bullet_content_hash("- delete this\n"), "action": "delete"}]
        )

        result = await tapps_skill_learnings("trim", skill_dir=skill_dir, trim_plan_json=plan)

        assert result["success"] is True
        assert result["data"]["applied"] is True
        updated = (tmp_path / "learnings.md").read_text(encoding="utf-8")
        assert "delete this" not in updated
        assert "keep this" in updated

    @pytest.mark.asyncio
    async def test_trim_refuses_and_does_not_write_on_ambiguous_hash(self, tmp_path) -> None:
        learnings = "- duplicate\n- duplicate\n"
        skill_dir = _write_skill_dir(tmp_path, learnings_md=learnings)
        plan = json.dumps(
            [{"content_hash": bullet_content_hash("- duplicate\n"), "action": "delete"}]
        )

        result = await tapps_skill_learnings("trim", skill_dir=skill_dir, trim_plan_json=plan)

        # The tool call itself succeeds (it determined the correct, safe
        # answer); the domain-level refusal lives in data.applied, matching
        # promote_rule's accepted=False convention — nothing was written.
        assert result["success"] is True
        assert result["data"]["applied"] is False
        assert (tmp_path / "learnings.md").read_text(encoding="utf-8") == learnings

"""Byte-identity regression tests for the CLAUDE_SKILLS / CLAUDE_AGENTS
asset extraction (TAP-#### Lane 1: move 16 templated skill bodies + 5
subagent bodies out of ``platform_skills.py`` / ``platform_subagents.py``
into package-data ``.md`` files under ``assets/claude_skills/`` and
``assets/claude_agents/``, loaded via ``importlib.resources``).

This is a pure refactor: every resolved body must be byte-identical to the
value it had as an inline Python string literal at base sha
670edd1c2d663df8f81d60fe596d57c3b8c4f98f. The golden sha256 hashes below
were computed directly from that base sha's runtime ``CLAUDE_SKILLS`` /
``CLAUDE_AGENTS`` dict values (not re-derived from the extracted files —
an independent reference so this test cannot pass by construction).

The corruption tests are the negative control: they prove the hash check
actually discriminates (would fail on a real one-byte drift) rather than
being a vacuous comparison that can never go red.
"""

from __future__ import annotations

import hashlib

import pytest

from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS
from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS

# Golden hashes: sha256 of each body's exact string value at base sha
# 670edd1c2d663df8f81d60fe596d57c3b8c4f98f, captured before any file
# extraction. The 16 CLAUDE_SKILLS entries below are exactly the ones that
# were dict-literal + resolve_role_model(role) concatenations at base; the
# other 10 CLAUDE_SKILLS entries (6 from CLAUDE_DOMAIN_SKILLS, 4 assigned
# post-hoc from sibling skill-body modules) are out of this lane's scope
# and untouched.
EXPECTED_CLAUDE_SKILLS_SHA256: dict[str, str] = {
    "tapps-finish-task": "d8b984a965ea1ef9e82681a258fcb9be2eadd8d552494dd72d3ae604ed995824",
    "tapps-handoff-session": "d97f9e268d0cd4da44a8031ac06a3717312a756158e79dcdc8f2e39c1cd3ef26",
    "tapps-continue-session": "46e6794e4042f01e8a8be94f2b609b4f42285b600e23b0ad54d218204b548c77",
    "tapps-review-pipeline": "9cf055a76582fb02c4d489a73993e9af9c7e4472e9e2976af6c8461c7e191ba0",
    "tapps-refactor": "f47b9d131e6c74914beee8fc2058a04387b1695fe2559ac1b8822995e5dd40fe",
    "tapps-research": "faa060ea4201d57847dd9f0c78a7cb8dcc343453296a9bcf28ab870bbec9e524",
    "tapps-security": "34a2eae03a3681951e20c9d4dc1da3dd753c5ccf7cc7e47bf9638417b3f84f63",
    "tapps-memory": "d85763eca372e976adb0324d9f6c21ef7bf5e78ba332ec91d8781f26208b9bd2",
    "tapps-tool-reference": "2858992ee16b0cf3fa6f8f096c28b3b6ea1f2fb5d52a842a757b975e3d7396b5",
    "tapps-init": "581ff1e481c31965c3f5cca2fa2f9b2d3ec15420a92b78fa88a8c27c12492f13",
    "tapps-upgrade": "84f9ec41c47618bacd5aab55a154fca314cb78b42d83f163a24cf1aee3b1bbfe",
    "tapps-engagement": "0049edd1251b08aab113e630ffaad9778c3247c4a4c1a49914a1d414074da449",
    "tapps-apply-files": "e1d1c9d20ee59387afd72e1c58ea035f54cb8570c51fe575945acfcc64661fd5",
    "linear-issue": "e0409220ce6d91f05102a090dc335be19922e2d1c054ccbebce2120f55f3e7e3",
    "linear-read": "5d4cee019ea9f5f067ea5ecf80e5a7d1dedf8953b0f22112bc434eb04ade3bc1",
    "linear-release-update": "ad0068d97c572775582126fbc600b0adeaab4a10c7f907ea803c173e7ce71a75",
}

EXPECTED_CLAUDE_AGENTS_SHA256: dict[str, str] = {
    "tapps-reviewer.md": "cee15e91f8d00ad97153d0d5a8183d95d7f383e8c8784f1507f4ac26b4933bcc",
    "tapps-researcher.md": "6786bbe35e3a9d17b160f1f1156513c8b1ac5239f678cb0b170d7d911c4ff0dd",
    "tapps-validator.md": "d9175180fa23da1b1a097f50132b545c316aaf7c779e0074087e2890c45ffdf2",
    "tapps-review-fixer.md": "63ee9cd7a64e11004c465e05adcdfde204a7538d563bfbb0e80651d1e9eacd04",
    "tapps-frontend-reviewer.md": "66ca4871776be29d7e24f0c294bdb21e7ff5a76eeee58431a4df338cba672397",
}


class TestClaudeSkillsByteIdentical:
    """VAL-01: CLAUDE_SKILLS bodies resolve to content byte-identical to base."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_SKILLS_SHA256))
    def test_skill_body_matches_base_hash(self, name: str) -> None:
        body = CLAUDE_SKILLS[name]
        actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert actual == EXPECTED_CLAUDE_SKILLS_SHA256[name], (
            f"{name}: resolved body drifted from base sha "
            "670edd1c2d663df8f81d60fe596d57c3b8c4f98f's literal value"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_SKILLS_SHA256))
    def test_no_unresolved_model_marker_leaks(self, name: str) -> None:
        """The {{model:role}} placeholder must always be resolved by import
        time -- a leaked marker would silently ship a broken SKILL.md."""
        assert "{{model:" not in CLAUDE_SKILLS[name]
        assert "model: {{" not in CLAUDE_SKILLS[name]

    def test_all_16_extracted_names_present(self) -> None:
        assert set(EXPECTED_CLAUDE_SKILLS_SHA256).issubset(CLAUDE_SKILLS.keys())

    def test_negative_control_hash_check_discriminates(self) -> None:
        """Corrupt a copy of a real body in memory and confirm the SAME hash
        check used above would have failed -- proves the positive checks
        are not vacuous (they can actually go red)."""
        name = "tapps-finish-task"
        real_body = CLAUDE_SKILLS[name]
        corrupted = real_body.replace("Run the end-of-task", "Run the end-of-tasK", 1)
        assert corrupted != real_body, "corruption fixture no-op'd — body text changed upstream"
        corrupted_hash = hashlib.sha256(corrupted.encode("utf-8")).hexdigest()
        assert corrupted_hash != EXPECTED_CLAUDE_SKILLS_SHA256[name]


class TestClaudeAgentsByteIdentical:
    """VAL-01: CLAUDE_AGENTS bodies resolve to content byte-identical to base."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_AGENTS_SHA256))
    def test_agent_body_matches_base_hash(self, name: str) -> None:
        body = CLAUDE_AGENTS[name]
        actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert actual == EXPECTED_CLAUDE_AGENTS_SHA256[name], (
            f"{name}: resolved body drifted from base sha "
            "670edd1c2d663df8f81d60fe596d57c3b8c4f98f's literal value"
        )

    def test_all_5_agents_present(self) -> None:
        assert set(EXPECTED_CLAUDE_AGENTS_SHA256) == set(CLAUDE_AGENTS.keys())

    def test_negative_control_hash_check_discriminates(self) -> None:
        name = "tapps-reviewer.md"
        real_body = CLAUDE_AGENTS[name]
        corrupted = real_body.replace("quality reviewer", "quality reviewer!", 1)
        assert corrupted != real_body, "corruption fixture no-op'd — body text changed upstream"
        corrupted_hash = hashlib.sha256(corrupted.encode("utf-8")).hexdigest()
        assert corrupted_hash != EXPECTED_CLAUDE_AGENTS_SHA256[name]

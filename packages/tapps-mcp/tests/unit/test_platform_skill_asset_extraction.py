"""Byte-identity regression tests for the CLAUDE_SKILLS / CLAUDE_AGENTS /
CLAUDE_DOC_AGENTS / CLAUDE_DOCS_SKILLS asset extraction (plugin-dist
program, Lanes 1-2): every templated skill/agent body that used to live as
an inline Python string literal in ``platform_skills.py``,
``platform_subagents.py``, ``platform_domain_skills.py``, and
``platform_docs_automation.py`` now lives as package-data ``.md`` files
under ``assets/claude_skills/``, ``assets/claude_agents/``,
``assets/claude_doc_agents/``, and ``assets/claude_docs_skills/``, loaded
via ``importlib.resources``.

This is a pure refactor: every resolved body must be byte-identical to the
value it had as an inline Python string literal at base sha
670edd1c2d663df8f81d60fe596d57c3b8c4f98f. The golden sha256 hashes below
were computed directly from that base sha's runtime dict values (not
re-derived from the extracted files — an independent reference so this
test cannot pass by construction).

The corruption tests are the negative control: they prove the hash check
actually discriminates (would fail on a real one-byte drift) rather than
being a vacuous comparison that can never go red.
"""

from __future__ import annotations

import hashlib

import pytest

from tapps_mcp.pipeline.platform_docs_automation import CLAUDE_DOC_AGENTS, CLAUDE_DOCS_SKILLS
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS
from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS

# Golden hashes: sha256 of each body's exact string value at base sha
# 670edd1c2d663df8f81d60fe596d57c3b8c4f98f, captured before any file
# extraction. All 26 CLAUDE_SKILLS entries are covered: the 16 that were
# dict-literal + resolve_role_model(role) concatenations (Lane 1), the 6
# merged in from CLAUDE_DOMAIN_SKILLS (3 built via an f-string helper, 3
# raw triple-quoted literals), and the 4 assigned post-hoc from sibling
# skill-body modules (Lane 2 / round 2).
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
    "tapps-domain-security": "33aee2260a432372ef156cac684717552187630b66dbc7cefa96f8745bf66bbd",
    "tapps-domain-testing": "a2c8396f4d150d1eb979eee34687b6a4153edcc4ba21895bd2a5428712a51cad",
    "tapps-domain-frontend": "ce1c7856a9ebc57486e660d236e201a16fe1689f10cb3f3468bbf09630093282",
    "tapps-flow-develop": "e33b0bf1eb2dd9e33b25ef87008af21ab38e64fd325288dbab91c7a97ee98789",
    "tapps-flow-review": "2f2665f0bcad078734647c8fd6056b862d8a82c99a888c80e4010c9117d007b6",
    "tapps-flow-frontend": "2ab9fc958f249f4ab024da7167ee09890c9baaf67733d7fbd2732c8ab852e3cf",
    "orchestration-prompt": "b8fae2d47b07f689668d5b7199c021bbdda3258a3e19e75dfc67dab26ccae4c3",
    "tapps-wayfind": "2ac3ad26d20db6b62703dbff852907cc682fcd929dd0b5be68fa6aaa212a4136",
    "tapps-validation-contract": "04a6649458bb3df50cf1f870fccab2a1cfc45be1b2b9d9ca811eef5bf0416101",
    "continuous-learning-v2": "110d4cf8484567e5113805408d4f5fc5a89e1e233460d7da00660d747fae5cf8",
}

EXPECTED_CLAUDE_AGENTS_SHA256: dict[str, str] = {
    "tapps-reviewer.md": "cee15e91f8d00ad97153d0d5a8183d95d7f383e8c8784f1507f4ac26b4933bcc",
    "tapps-researcher.md": "6786bbe35e3a9d17b160f1f1156513c8b1ac5239f678cb0b170d7d911c4ff0dd",
    "tapps-validator.md": "d9175180fa23da1b1a097f50132b545c316aaf7c779e0074087e2890c45ffdf2",
    "tapps-review-fixer.md": "63ee9cd7a64e11004c465e05adcdfde204a7538d563bfbb0e80651d1e9eacd04",
    "tapps-frontend-reviewer.md": "66ca4871776be29d7e24f0c294bdb21e7ff5a76eeee58431a4df338cba672397",
}

EXPECTED_CLAUDE_DOC_AGENTS_SHA256: dict[str, str] = {
    "tapps-docs-reviewer.md": "c1acb61dcfd7929dea175cc2428ff9965f4573975ee2e277bf0ab1d3e69b0012",
    "tapps-docs-validator.md": "6ebb0e98542e34217526f9076476865854798d4f3d8b8088603af96d7243f56c",
}

EXPECTED_CLAUDE_DOCS_SKILLS_SHA256: dict[str, str] = {
    "tapps-docs-refresh": "dbd1e4e0437d9f31f4fce8b44965b0db227d0614f1bc5e34d764556d4225413e",
    "tapps-docs-bootstrap": "9a47a5095ab7c9ddb4517afd9280717e3d0b32444710aaab11a5f139a7a0c363",
    "tapps-docs-finish-task": "9b7b2144ac5733d6f4718d5cd0d10684cc9cb64bff44d6bd80184e2d680a2625",
    "tapps-docs-report": "fd33ebda5a8a314fc7372437a5a7a79cb39e43ade630747ed9b51eeba0ef6732",
    "tapps-docs-validate": "3446a1304ade18a2bfde8b87bc428a189d9678488aa17578c88774fd20eb604f",
    "tapps-docs-generate": "3b2b780ab456873ea67fed81febb05d6e0a918f1080149ae1b8ced2fa686ca9a",
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

    def test_all_26_extracted_names_present(self) -> None:
        assert set(EXPECTED_CLAUDE_SKILLS_SHA256) == set(CLAUDE_SKILLS.keys())

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


class TestClaudeDocAgentsByteIdentical:
    """VAL-01 (round 2): CLAUDE_DOC_AGENTS bodies byte-identical to base."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_DOC_AGENTS_SHA256))
    def test_doc_agent_body_matches_base_hash(self, name: str) -> None:
        body = CLAUDE_DOC_AGENTS[name]
        actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert actual == EXPECTED_CLAUDE_DOC_AGENTS_SHA256[name], (
            f"{name}: resolved body drifted from base sha "
            "670edd1c2d663df8f81d60fe596d57c3b8c4f98f's literal value"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_DOC_AGENTS_SHA256))
    def test_no_unresolved_docs_prefix_marker_leaks(self, name: str) -> None:
        assert "{{docs_prefix}}" not in CLAUDE_DOC_AGENTS[name]

    def test_all_2_doc_agents_present(self) -> None:
        assert set(EXPECTED_CLAUDE_DOC_AGENTS_SHA256) == set(CLAUDE_DOC_AGENTS.keys())

    def test_negative_control_hash_check_discriminates(self) -> None:
        name = "tapps-docs-reviewer.md"
        real_body = CLAUDE_DOC_AGENTS[name]
        corrupted = real_body.replace("documentation reviewer", "documentation reviewer!", 1)
        assert corrupted != real_body, "corruption fixture no-op'd — body text changed upstream"
        corrupted_hash = hashlib.sha256(corrupted.encode("utf-8")).hexdigest()
        assert corrupted_hash != EXPECTED_CLAUDE_DOC_AGENTS_SHA256[name]


class TestClaudeDocsSkillsByteIdentical:
    """VAL-01 (round 2): CLAUDE_DOCS_SKILLS bodies byte-identical to base."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_DOCS_SKILLS_SHA256))
    def test_docs_skill_body_matches_base_hash(self, name: str) -> None:
        body = CLAUDE_DOCS_SKILLS[name]
        actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert actual == EXPECTED_CLAUDE_DOCS_SKILLS_SHA256[name], (
            f"{name}: resolved body drifted from base sha "
            "670edd1c2d663df8f81d60fe596d57c3b8c4f98f's literal value"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_CLAUDE_DOCS_SKILLS_SHA256))
    def test_no_unresolved_docs_prefix_marker_leaks(self, name: str) -> None:
        assert "{{docs_prefix}}" not in CLAUDE_DOCS_SKILLS[name]

    def test_all_6_docs_skills_present(self) -> None:
        assert set(EXPECTED_CLAUDE_DOCS_SKILLS_SHA256) == set(CLAUDE_DOCS_SKILLS.keys())

    def test_negative_control_hash_check_discriminates(self) -> None:
        name = "tapps-docs-refresh"
        real_body = CLAUDE_DOCS_SKILLS[name]
        corrupted = real_body.replace("Run the full documentation", "Run the FULL documentation", 1)
        assert corrupted != real_body, "corruption fixture no-op'd — body text changed upstream"
        corrupted_hash = hashlib.sha256(corrupted.encode("utf-8")).hexdigest()
        assert corrupted_hash != EXPECTED_CLAUDE_DOCS_SKILLS_SHA256[name]

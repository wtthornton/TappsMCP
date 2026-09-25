"""Byte-identity regression tests for the CLAUDE_SKILLS / CLAUDE_AGENTS /
CLAUDE_DOC_AGENTS / CLAUDE_DOCS_SKILLS asset extraction (plugin-dist
program, Lanes 1-2): every templated skill/agent body that used to live as
an inline Python string literal in ``platform_skills.py``,
``platform_subagents.py``, ``platform_domain_skills.py``, and
``platform_docs_automation.py`` now lives as package-data ``.md`` files
under ``assets/claude_skills/``, ``assets/claude_agents/``,
``assets/claude_doc_agents/``, and ``assets/claude_docs_skills/``, loaded
via ``importlib.resources``.

The extraction itself was a pure refactor: every resolved body must be
byte-identical to the value it had as an inline Python string literal at base
sha 670edd1c2d663df8f81d60fe596d57c3b8c4f98f. The golden sha256 hashes below
were computed directly from that base sha's runtime dict values (not
re-derived from the extracted files — an independent reference so this
test cannot pass by construction).

Most entries are pinned to a LATER value than that base sha, each because a
reviewed content change moved it deliberately; see the notes on
``EXPECTED_CLAUDE_SKILLS_SHA256``. A pin is only ever advanced alongside the
edit that moved it, named in the note — a pin updated to "make the test pass"
is green-by-suppression and the whole point of this file is to make that
visible in review.

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
#
# Unpin (v3.12.91) — every entry except tapps-finish-task,
# tapps-continue-session and tapps-wayfind was advanced by one reviewed edit:
# the single frontmatter line ``disable-model-invocation: true`` was removed,
# so the agent can invoke every generated skill. Verified by diffing each
# pre-edit body (hashing to its previous pin) against the new one: the only
# change is that one line. No other frontmatter or body text changed.
#
# TAP-8101 — twelve pins advanced by one reviewed edit each: the single
# frontmatter line ``model: claude-haiku-4-5-20251001`` became
# ``model: claude-sonnet-5`` (MODEL_ROLES verifier-deterministic / explorer /
# prose moved off Haiku 4.5, which lacks effort support). Covers the ten
# CLAUDE_SKILLS entries linear-issue, linear-read, linear-release-update,
# tapps-apply-files, tapps-continue-session, tapps-engagement,
# tapps-finish-task, tapps-flow-develop, tapps-handoff-session and
# tapps-tool-reference, plus CLAUDE_AGENTS tapps-validator.md and
# CLAUDE_DOC_AGENTS tapps-docs-validator.md. Verified: each previous pin equals
# the sha256 of the pre-edit body, and a line diff of pre- vs post-edit body
# shows that model line as the only change.
EXPECTED_CLAUDE_SKILLS_SHA256: dict[str, str] = {
    "tapps-finish-task": "df4f7733af7969b0de5d380107a346dd7aa001b07cd621fe8bacdbb90d08af07",
    "tapps-handoff-session": "dfa4a1c354c60940511fa6f2d59fadd6848e904565898097a99fd3c11ce3854b",
    # TAP-7753 round 2 — advanced from the base-sha value
    # 46e6794e4042f01e8a8be94f2b609b4f42285b600e23b0ad54d218204b548c77 by one
    # reviewed edit: a "## Degrades without" section appended to
    # assets/claude_skills/tapps-continue-session.md documenting that step 4's
    # TAP-#### lookup needs mcp__plugin_linear_linear__get_issue. Body-only
    # append; no frontmatter, step, or tool grant changed.
    "tapps-continue-session": "2eb96bc2b8855ce9cc4610ae27c55d8a53b0248c1446794f31bed864751a9437",
    "tapps-review-pipeline": "3489ae94cb46c97dc3a5ab8fba96be6101d3cb713d1219ee6218bb4c54fb00d6",
    "tapps-refactor": "207c4ed7ae7edbcd45be2bf4ac8dcbbf8968dbc19815f45ae6ea8a2d9e965d3c",
    "tapps-research": "3c0821e21fc2bbf23f678cb4e0a44f291fa6eb852762aef1e4b88a614a650e8b",
    "tapps-security": "e2d213468ce055c6a2096b6591d3e015fa442b722f4cdd7a5c6c6224fe585a44",
    "tapps-memory": "1cec3947a695aad02fa03a03843ac4988a9233ddc3d2cf9c0d9fbbf2498f546e",
    "tapps-tool-reference": "2966d8b5aaa0de4ec69ffa4d67dcfb545e6e9d7d3ea1a1cfcd464f1862e71815",
    "tapps-init": "f72f166ca9a8d804bd78bd35789ac01a3023182bcc7df31d2e93204144408a90",
    "tapps-upgrade": "6b13f9af0fe0525a2f8b97eb17841621d6a46ef5f8afb26507eaaac6342bf125",
    "tapps-engagement": "b7dda41e3696188c5ac733e3955d8869c86e89117f4d3d473a3fb03d0f2732b8",
    "tapps-apply-files": "ed8679d0ea07fda9f13a2138e27a046a6c829232bb9029f38e39eeb856b67dbc",
    "linear-issue": "6df1018d342019fda3a0a06b0e063b7d78704842df76d3e7700d1338c2180080",
    # TAP-7753 round 2 — advanced from the base-sha value
    # 5d4cee019ea9f5f067ea5ecf80e5a7d1dedf8953b0f22112bc434eb04ade3bc1 by one
    # reviewed edit: a "## Degrades without" section appended to
    # assets/claude_skills/linear-read.md documenting that steps 3-4 need
    # mcp__plugin_linear_linear__list_issues/get_issue. Body-only append; no
    # frontmatter, step, or tool grant changed.
    "linear-read": "0e76b7db5ba199022d73cbd5e9659cb64b9a4e09ab7ff9f3fdf655212b672187",
    # TAP-7753 round 2 — advanced from the base-sha value
    # ad0068d97c572775582126fbc600b0adeaab4a10c7f907ea803c173e7ce71a75 by two
    # reviewed edits to assets/claude_skills/linear-release-update.md:
    #   1. frontmatter — two tool grants removed from `allowed-tools`
    #      (mcp__nlt-release-ship__docs_generate_release_update and
    #      ...__docs_validate_release_update), neither called anywhere in the
    #      skill body, and the `description` line's flow updated from
    #      docs_validate_release_update to the docs_release_gate that step 1b
    #      actually calls;
    #   2. body — a "## Degrades without" section appended documenting the
    #      docs_release_gate and mcp__plugin_linear_linear__save_document gaps.
    "linear-release-update": "941b477621c965a971d2d2f5792faa95bdf8e1320576e79aabcee9ffc3378996",
    "tapps-domain-security": "0571d7be26f570e5ac0931bf1d56102cba346be64296c49cf8588a890338c3a6",
    "tapps-domain-testing": "0ad16dc6c4903f9a60138e8480bde71c93cd9013539643c8cc08df8ac642843a",
    "tapps-domain-frontend": "f400222e5b0ba952561b1701070a75d6c00e58bda9da917a1a210f06aa3236bd",
    "tapps-flow-develop": "28284732f2967ed114bc2cb37aa7e60a2ad6077f9f15385d84ea0f8b21d00a95",
    "tapps-flow-review": "377e3c5aa0424c648a7d1662b21fe7ad7ad4a94932758bf7fdd6cf5bdcf4b261",
    "tapps-flow-frontend": "21ba41721fc4aa485e1fb989450eefa89e83ac3a12570f48a37e4def82b5e562",
    "orchestration-prompt": "d630b4d01151b6ce360581e6ed125c6bd741bbd346ff66d5977296a199a17eb7",
    "tapps-wayfind": "2ac3ad26d20db6b62703dbff852907cc682fcd929dd0b5be68fa6aaa212a4136",
    "tapps-validation-contract": "c6a55ae0584738a40962cf76faff697e1173acef65a8ff7467a6e4be05a91388",
    "continuous-learning-v2": "99533d855d1830af252db08941a8afa0cf32db4ae26e6754d1d2f2d6023a6728",
}

EXPECTED_CLAUDE_AGENTS_SHA256: dict[str, str] = {
    "tapps-reviewer.md": "cee15e91f8d00ad97153d0d5a8183d95d7f383e8c8784f1507f4ac26b4933bcc",
    "tapps-researcher.md": "6786bbe35e3a9d17b160f1f1156513c8b1ac5239f678cb0b170d7d911c4ff0dd",
    "tapps-validator.md": "18741578103b31107f0a707d940986438c2c025053cc9fee210c94fa0da081d8",
    "tapps-review-fixer.md": "63ee9cd7a64e11004c465e05adcdfde204a7538d563bfbb0e80651d1e9eacd04",
    "tapps-frontend-reviewer.md": "66ca4871776be29d7e24f0c294bdb21e7ff5a76eeee58431a4df338cba672397",
}

EXPECTED_CLAUDE_DOC_AGENTS_SHA256: dict[str, str] = {
    "tapps-docs-reviewer.md": "c1acb61dcfd7929dea175cc2428ff9965f4573975ee2e277bf0ab1d3e69b0012",
    "tapps-docs-validator.md": "fd987bef1507a91a34222b6d27aa4909478f99ecc2d1606773bdceb405e5b039",
}

# #454 (9aa870ce) added one frontmatter line, ``user-invocable: true``, to
# tapps-docs-generate / -report / -validate without advancing these pins.
# Verified: each current body with that one line removed hashes to its
# previous pin, so the new values reflect that single reviewed edit.
EXPECTED_CLAUDE_DOCS_SKILLS_SHA256: dict[str, str] = {
    "tapps-docs-refresh": "dbd1e4e0437d9f31f4fce8b44965b0db227d0614f1bc5e34d764556d4225413e",
    "tapps-docs-bootstrap": "9a47a5095ab7c9ddb4517afd9280717e3d0b32444710aaab11a5f139a7a0c363",
    "tapps-docs-finish-task": "9b7b2144ac5733d6f4718d5cd0d10684cc9cb64bff44d6bd80184e2d680a2625",
    "tapps-docs-report": "66bcc27228d1aa36b2d414706bc4e937667c84dba8d69bdf02517f11c6abdca0",
    "tapps-docs-validate": "85d6bd9102b20655bb3eaa7a0082c9b228f0d99c91d1003da8fb760b1a8ae776",
    "tapps-docs-generate": "a984e5ee4f2e1ba49ec5e1c71906e9c409e4a34988baf1591ccb6bcd299eb68d",
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

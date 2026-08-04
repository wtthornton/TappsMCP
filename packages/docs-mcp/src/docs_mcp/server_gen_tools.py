"""DocsMCP generation tools.

Registers generation tools on the shared ``mcp`` FastMCP instance from
``server.py``: README, changelog, release notes, API docs, ADR,
onboarding/contributing guides, diagrams, architecture reports, epics,
and user stories.

Split under TAP-5608 — this module is a registration facade over five
family siblings plus a shared helper module:

* :mod:`docs_mcp.server_gen_release` — changelog, release notes,
  release update.
* :mod:`docs_mcp.server_gen_project` — README, API, ADR, llms.txt,
  frontmatter, purpose, doc index.
* :mod:`docs_mcp.server_gen_guides` — onboarding, contributing,
  runbook, postmortem, PRD.
* :mod:`docs_mcp.server_gen_diagrams` — diagrams, architecture report,
  interactive viewer.
* :mod:`docs_mcp.server_gen_planning` — epic, story, prompt.
* :mod:`docs_mcp.server_gen_helpers` — wire-tag and criteria splitters,
  plus the settings / call-recording seam.

Every handler is re-exported here so existing imports of
``docs_mcp.server_gen_tools`` keep resolving after the split. This module
also stays the single settings seam for the generation surface: the family
siblings resolve ``_get_settings`` / ``_record_call`` through it on every
call, so ``mock.patch("docs_mcp.server_gen_tools._get_settings", ...)``
still reaches handlers that now live elsewhere (same approach as the
TAP-5606 ``server_linear_tools`` split).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docs_mcp.mcp_register import register_tool
from docs_mcp.server import (
    _ANNOTATIONS_READ_ONLY,
    _ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
    _META_DEFERRED,
    _META_SIZE_100K_D,
    _META_SIZE_200K_D,
    _META_SIZE_400K_D,
)
from docs_mcp.server import _record_call as _record_call
from docs_mcp.server_gen_diagrams import docs_generate_architecture as docs_generate_architecture
from docs_mcp.server_gen_diagrams import docs_generate_diagram as docs_generate_diagram
from docs_mcp.server_gen_diagrams import (
    docs_generate_interactive_diagrams as docs_generate_interactive_diagrams,
)
from docs_mcp.server_gen_guides import docs_generate_contributing as docs_generate_contributing
from docs_mcp.server_gen_guides import docs_generate_onboarding as docs_generate_onboarding
from docs_mcp.server_gen_guides import docs_generate_postmortem as docs_generate_postmortem
from docs_mcp.server_gen_guides import docs_generate_prd as docs_generate_prd
from docs_mcp.server_gen_guides import docs_generate_runbook as docs_generate_runbook
from docs_mcp.server_gen_helpers import _CRITERIA_PREFIX_RE as _CRITERIA_PREFIX_RE
from docs_mcp.server_gen_helpers import _STRIP_WIRE_TAGS as _STRIP_WIRE_TAGS
from docs_mcp.server_gen_helpers import _WIRE_TAG_NAMES as _WIRE_TAG_NAMES
from docs_mcp.server_gen_helpers import _split_criteria_list as _split_criteria_list
from docs_mcp.server_gen_helpers import _split_csv as _split_csv
from docs_mcp.server_gen_helpers import _strip_wire_tags as _strip_wire_tags
from docs_mcp.server_gen_planning import docs_generate_epic as docs_generate_epic
from docs_mcp.server_gen_planning import docs_generate_prompt as docs_generate_prompt
from docs_mcp.server_gen_planning import docs_generate_story as docs_generate_story
from docs_mcp.server_gen_project import docs_generate_adr as docs_generate_adr
from docs_mcp.server_gen_project import docs_generate_api as docs_generate_api
from docs_mcp.server_gen_project import docs_generate_doc_index as docs_generate_doc_index
from docs_mcp.server_gen_project import docs_generate_frontmatter as docs_generate_frontmatter
from docs_mcp.server_gen_project import docs_generate_llms_txt as docs_generate_llms_txt
from docs_mcp.server_gen_project import docs_generate_purpose as docs_generate_purpose
from docs_mcp.server_gen_project import docs_generate_readme as docs_generate_readme
from docs_mcp.server_gen_release import docs_generate_changelog as docs_generate_changelog
from docs_mcp.server_gen_release import docs_generate_release_notes as docs_generate_release_notes
from docs_mcp.server_gen_release import docs_generate_release_update as docs_generate_release_update
from docs_mcp.server_helpers import _get_settings as _get_settings

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register generation tools on the shared mcp instance (Epic 79.2: conditional).

    TAP-1987: Daily drivers (EAGER — no defer_loading):
      docs_generate_changelog, docs_generate_epic, docs_generate_story.
    All other generators are DEFERRED and loaded on-demand via Tool Search.
    """
    # EAGER — daily drivers
    if "docs_generate_changelog" in allowed_tools:
        register_tool(
            mcp_instance, docs_generate_changelog, annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT
        )
    if "docs_generate_epic" in allowed_tools:
        register_tool(
            mcp_instance, docs_generate_epic, annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT
        )
    if "docs_generate_story" in allowed_tools:
        register_tool(
            mcp_instance, docs_generate_story, annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT
        )

    # DEFERRED — loaded on-demand via Tool Search
    if "docs_generate_release_notes" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_release_notes,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "docs_generate_readme" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_readme,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_api" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_api,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_SIZE_200K_D,
        )
    if "docs_generate_adr" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_adr,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_onboarding" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_onboarding,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_contributing" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_contributing,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_runbook" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_runbook,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_postmortem" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_postmortem,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_prd" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_prd,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_diagram" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_diagram,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_SIZE_100K_D,
        )
    if "docs_generate_architecture" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_architecture,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_SIZE_400K_D,
        )
    if "docs_generate_prompt" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_prompt,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_llms_txt" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_llms_txt,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_frontmatter" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_frontmatter,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_interactive_diagrams" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_interactive_diagrams,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_SIZE_400K_D,
        )
    if "docs_generate_purpose" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_purpose,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_doc_index" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_doc_index,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "docs_generate_release_update" in allowed_tools:
        register_tool(
            mcp_instance,
            docs_generate_release_update,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )

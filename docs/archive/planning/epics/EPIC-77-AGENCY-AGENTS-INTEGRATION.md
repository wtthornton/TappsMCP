# Epic 77: Agency-Agents Integration (Documentation & Optional Hint)

<!-- docsmcp:start:metadata -->
- **Status:** Complete (2026-03-11)
- **Priority:** P3
- **Estimated LOE:** ~2–4 days (documentation + optional init hint)
- **Dependencies:** Epic 12 (Platform Integration), docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md
- **Blocks:** None
- **Source:** User request to “include agents and bring it all together” with [agency-agents](https://github.com/msitarzewski/agency-agents)
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Document how TappsMCP’s four quality subagents and platform rules coexist with the optional [agency-agents](https://github.com/msitarzewski/agency-agents) roster (~120 domain personas). Optionally surface a one-line hint during init or in generated AGENTS.md so users know they can add agency-agents for more specialized agents (Frontend Developer, Reality Checker, etc.) without conflict.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

1. **Clarify ecosystem:** TappsMCP creates 4 subagents (reviewer, researcher, validator, review-fixer) in `.claude/agents/` or `.cursor/agents/`; agency-agents provides many more personas. Users need a single place to understand install order and that both can coexist (no path conflict: Cursor uses `.cursor/rules/` for agency-agents and `.cursor/agents/` + `.cursor/rules/` for TappsMCP).
2. **Discoverability:** Users who want “more agents” may not know about agency-agents; a short pointer in docs or init output improves discoverability.
3. **No code coupling:** This epic is documentation + optional one-sentence hint only. No bundled install of agency-agents or convert/install scripts inside TappsMCP unless later prioritized.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that **users understand how TappsMCP and agency-agents fit together** and can confidently add specialized personas (Frontend Developer, Reality Checker, etc.) without fearing conflicts or missing the option. TappsMCP delivers four quality-focused subagents; agency-agents delivers many more domain personas. Without a single place that explains install order, path layout, and coexistence, users may assume they must choose one or the other, or may install in the wrong order and get confusing behavior. By documenting the ecosystem and optionally surfacing a one-line hint at init or in AGENTS.md, we improve discoverability and reduce support burden while keeping the two systems loosely coupled. The intent is clarity and optionality: "use TappsMCP for quality; add agency-agents when you want more agents" — with no code coupling, only clear docs and a nudge.
<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [ ] A dedicated doc (or section in AGENTS.md / README) explains: TappsMCP’s 4 subagents + rules + skills; optional agency-agents; recommended install order; where each system writes (Claude: agents dir; Cursor: rules vs agents).
- [ ] Optional: init success message or generated AGENTS.md includes a single sentence linking to agency-agents for “more specialized agents (e.g. Frontend Developer, Reality Checker).”
- [ ] No path or behavior conflict between TappsMCP and agency-agents installs; doc states this explicitly.
- [ ] Research reference: docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md is linked from this epic and from the new doc.
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE |
|-------|--------|----------|-----|
| [77.1](EPIC-77/story-77.1-document-tappsmcp-agency-agents-coexistence.md) | Document TappsMCP + agency-agents coexistence | P3 | 1–2 days |
| [77.2](EPIC-77/story-77.2-optional-init-agents-md-hint-agency-agents.md) | Optional: init/AGENTS.md hint for agency-agents | P3 | 0.5 day |

<!-- docsmcp:end:stories -->

## Implementation notes

| Item | Location |
|------|----------|
| Doc section (77.1) | `AGENTS.md` and/or `README.md` and/or `docs/TAPPS_MCP_SETUP_AND_USE.md` — add “Agent ecosystem” or “Using TappsMCP with other agent libraries” |
| Init success message (77.2 Option A) | `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` — append one line after init summary |
| AGENTS.md template (77.2 Option B) | `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_medium.md` (and agents_template.md, _high, _low if all levels); loaded via `prompt_loader.load_agents_template()` |

**Story order:** 77.1 first (full doc); 77.2 optional and can be done standalone.

## References

- **Research:** docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md
- **Deep dive:** docs/reviews/AGENCY-AGENTS-REPO-DEEP-DIVE.md
- **agency-agents:** https://github.com/msitarzewski/agency-agents (README, integrations/, scripts/convert.sh, install.sh)

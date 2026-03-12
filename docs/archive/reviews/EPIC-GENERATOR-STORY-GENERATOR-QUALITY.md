# EpicGenerator & StoryGenerator — Output Quality & Enhancement Recommendations

**Date:** 2026-03-10  
**Scope:** `packages/docs-mcp/src/docs_mcp/generators/epics.py`, `stories.py`  
**Context:** Repo-specific script uses these generators to produce EPIC-69 and story docs; this review assesses output quality and suggests improvements.

---

## Summary

The generators produce **structurally sound**, **template-consistent** output with clear placeholders and docsmcp markers. Quality is good for structure and optional enrichment (tech stack, module map, expert guidance). The main gaps are: **expert advice extraction** often surfaces boilerplate instead of real content, **story stubs** default to generic tasks when callers omit them, and **StoryGenerator** does not filter low-quality expert guidance like EpicGenerator does. Below: what works well, then concrete enhancement recommendations.

---

## What Works Well

### Structure and consistency
- **Epic:** Metadata, Goal, Motivation, Acceptance Criteria, Stories, Technical Notes, Non-Goals; comprehensive style adds Success Metrics, Stakeholders, References, Implementation Order, Risk Assessment, Files Affected. All sections use `<!-- docsmcp:start/end -->` markers for SmartMerger.
- **Story:** User story statement (As a / I want / So that), sizing, description, tasks, acceptance criteria (checkbox or Gherkin), definition of done; comprehensive adds test cases, technical notes, dependencies, INVEST checklist.
- Placeholders are explicit (“Describe what this story delivers…”, “TBD”) so they are clearly fill-in, not fake content.

### Enrichment (when `auto_populate=True`)
- **Epic:** Tech stack, module summary, dependencies, git summary, and **expert guidance** from multiple domains (security, architecture, testing, performance, devops, code-quality, api-design, observability). Risk assessment uses `RiskClassifier` and expert-derived mitigations. Expert-identified risks appended when available.
- **Story:** Tech stack, module summary, expert guidance in technical notes; definition of done gains “Security review completed” / “Test coverage meets quality gate” when security/testing experts contribute.
- **Expert filtering (Epic only):** Confidence &lt; 30% dropped; 30–50% replaced with “Expert review recommended for {domain}”; “no specific knowledge” and empty advice suppressed (DOCSMCP Epic 18.3).

### Flexibility
- Optional parameters (goal, motivation, acceptance_criteria, stories JSON, technical_notes, non_goals, risks, etc.) let callers supply as much as they have; empty sections get sensible placeholders or derived content (e.g. success metrics from AC count).

---

## Quality Gaps and Enhancement Recommendations

### 1. Expert advice extraction (Epic and Story) — **High impact**

**Issue:** The first “meaningful” paragraph is taken as the first non-header paragraph. Consultation answers start with:
- `## Expert Name — domain`
- `Based on domain knowledge (N source(s), confidence X%):`
- then the actual knowledge.

So the stored “advice” is often the boilerplate line (“Based on domain knowledge…”) instead of the real recommendation.

**Evidence:** In generated EPIC-69, Expert Recommendations show:
- “**Security Expert** (70%): Based on domain knowledge (3 source(s), confidence 70%):”
- with no substantive advice after the colon.

**Recommendation:** In both `EpicGenerator._enrich_experts` and `StoryGenerator._enrich_experts` (and any shared helper), when extracting “first paragraph” from `result.answer`:
- Skip paragraphs that match patterns such as `Based on domain knowledge` or `No specific knowledge found`.
- Take the first paragraph that is non-empty, not a header, and either (a) does not match those patterns, or (b) is longer than a threshold (e.g. 80 chars) so that real content is preferred.
- Optionally cap advice length (e.g. first 300 chars of the chosen paragraph) for readability in the epic/story doc.

---

### 2. StoryGenerator expert guidance — **Medium impact**

**Issue:** EpicGenerator filters expert guidance (`_filter_expert_guidance`: low confidence, “no knowledge”, empty). StoryGenerator does not; it renders all `expert_guidance` in Technical Notes and uses raw guidance for DoD. So low-confidence or “no specific knowledge” advice can appear in story docs.

**Recommendation:** Reuse the same filtering in StoryGenerator (e.g. call a shared `_filter_expert_guidance` or duplicate the logic). Use filtered list for both Technical Notes and Definition of Done so story output matches epic quality bar.

---

### 3. Epic story stub tasks and descriptions — **Medium impact**

**Issue:** When story stubs are passed with only `title` and `points` (no `description`, no `tasks`), the epic renders “Describe what this story delivers…” and generic tasks: “Implement {title}”, “Write unit tests”, “Update documentation”. DOCSMCP Epic 19 AC7/AC8 expect stubs to reflect full story content (first 4 tasks, AC count).

**Current behavior:** The generator already supports `EpicStoryStub.tasks` and `description`; the gap is caller input (e.g. our script didn’t pass them).

**Recommendation (optional):** Improve defaults when stub has no tasks:
- Derive 2–3 task-like bullets from the story title (e.g. “Add persona field to ExpertConfig and business config” → “Add persona field to ExpertConfig”, “Update BusinessExpertEntry and experts.yaml schema”, “Add/update tests”). Keep them clearly generic (e.g. “(draft from title)”) or only use when `tasks` is empty. This improves readability of epic-only generation when full story docs aren’t generated first.

---

### 4. Gherkin acceptance criteria (Story) — **Low impact**

**Issue:** For `criteria_format="gherkin"` with explicit acceptance criteria, the template still uses generic “Given [precondition]”, “When [action]”, “Then [outcome]” instead of weaving the AC text into the scenario.

**Recommendation:** At least use the AC as the Scenario name; optionally add a one-line hint for Given/When/Then derived from the AC (e.g. “Given the system has X, When the user does Y, Then Z”) so the Gherkin block is a better starting point.

---

### 5. Success metrics and stakeholders (Epic) — **Already addressed**

DOCSMCP Epic 19 added Success Metrics (with derived suggestions when empty), Stakeholders (omitted when empty), and References. No further change needed for structure.

---

## Summary Table

| Area                         | Quality today              | Recommendation                                      |
|-----------------------------|----------------------------|----------------------------------------------------|
| Structure & placeholders    | Good                       | None                                               |
| Epic enrichment             | Good except expert text    | Skip boilerplate in first-paragraph extraction    |
| Story enrichment            | Good except expert text    | Same extraction fix; add expert filtering         |
| Expert filtering            | Epic: yes; Story: no       | Apply same filter in StoryGenerator                |
| Story stub tasks/descriptions | Caller-driven; generic defaults | Optional: title-derived task suggestions when empty |
| Gherkin AC                  | Template-only              | Optional: AC-driven scenario text                 |

---

## Conclusion

Output quality is **good for structure and integration** (markers, sections, enrichment hooks). The one **high-impact** improvement is fixing expert advice extraction so epic and story docs show real recommendations instead of the “Based on domain knowledge…” line. Applying the same expert filtering to StoryGenerator and optional improvements for stub tasks and Gherkin would bring the generators to a higher bar without changing the external API.

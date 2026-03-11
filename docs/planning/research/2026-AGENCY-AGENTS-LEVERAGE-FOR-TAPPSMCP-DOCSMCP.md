# Which agency-agents to Copy, Leverage, or Reference for TappsMCP & DocsMCP

**Source:** [agency-agents](https://github.com/msitarzewski/agency-agents) (29k+ stars, 120 agents across Engineering, Design, Testing, Product, PM, Support, etc.)  
**Goal:** Get better results in TappsMCP (code quality, experts, validation) and DocsMCP (PRDs, epics, stories, docs) by copying, adapting, or recommending specific agents.

---

## Summary

| Action | TappsMCP | DocsMCP |
|--------|----------|---------|
| **Copy** (ship with init/upgrade or optional bundle) | Reality Checker, Evidence Collector (optional) | Technical Writer (optional) |
| **Leverage** (enrich experts/prompts from their content) | Reality Checker, Security Engineer, Evidence Collector, Accessibility Auditor, Tool Evaluator | Technical Writer, UX Researcher, Feedback Synthesizer, Sprint Prioritizer |
| **Reference** (doc + optional install hint) | Testing division, Security Engineer, Accessibility Auditor | Technical Writer, product/PM agents for PRD/epic flows |

---

## 1. TappsMCP — Recommended agents

### 1.1 Copy (include with init/upgrade or optional bundle)

| Agency agent | Why |
|--------------|-----|
| **Reality Checker** (testing) | Directly aligns with “validate before done” and evidence-based sign-off. Default “NEEDS WORK”; requires screenshots, test results, grep evidence. Fits pre-completion gate and tapps_validate_changed. Copy as an optional Cursor rule or subagent so users can “Use Reality Checker before sign-off.” |
| **Evidence Collector** (testing) | Screenshot-based QA, visual proof, bug documentation. Complements tapps_quick_check and security scan with “show me the evidence.” Optional copy for projects that want explicit visual verification steps. |

**Mechanism:** Epic 77 (agency-agents integration): doc + optional init hint. Optionally: init/upgrade can offer “Add Reality Checker (and N other agents) from agency-agents?” and run their `install.sh --tool cursor` (or claude-code) for a curated subset (e.g. testing division).

### 1.2 Leverage (enrich TappsMCP experts or pipeline prompts)

Use agency-agents’ **identity, critical rules, success metrics, and workflow** to strengthen existing experts and prompts. Don’t ship their .md as-is; pull structure and wording into our knowledge and expert config.

| Agency agent | TappsMCP area | How to leverage |
|--------------|---------------|-----------------|
| **Reality Checker** | Testing expert, validator subagent, pipeline rules | Add “default NEEDS WORK,” “require evidence (screenshots, test output, grep),” “automatic fail: zero issues without proof” to testing-strategies knowledge and/or to tapps-validator instructions. |
| **Security Engineer** | Security expert | Enrich security expert persona and critical rules: “assume breach,” “threat model first,” secure code review checklist. Add to `security` knowledge. |
| **Evidence Collector** | Testing expert, checklist | Add “visual proof” and screenshot/E2E evidence requirements to testing-strategies knowledge; optional checklist step “capture evidence for critical flows.” |
| **Accessibility Auditor** | Accessibility expert | Enrich accessibility expert with WCAG audit workflow, assistive-tech testing steps, and “inclusive by default” stance from agency’s Accessibility Auditor. |
| **Tool Evaluator** (testing) | Code quality / development-workflow | Use “technology assessment, tool selection” angle in expert knowledge for “when to use which linter/checker” and tool recommendations in project_profile. |

**Mechanism:** Epics 70–73 (Expert Persona Completion, Critical Rules, Knowledge Enrichment). When adding persona, critical rules, success metrics, and workflow hints to experts, use agency-agents’ Testing and Engineering agents as reference (docs/reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md).

### 1.3 Reference only (doc, no code change)

Recommend in AGENTS.md or “Agent ecosystem” doc; user installs via agency-agents’ install script.

| Agency agents | Why |
|---------------|-----|
| **Testing division** (Reality Checker, Evidence Collector, Test Results Analyzer, Performance Benchmarker, API Tester, Accessibility Auditor) | Full roster for teams that want dedicated “personas” for QA; TappsMCP covers tooling (score, validate, security_scan). |
| **Security Engineer** (engineering) | Deeper security persona; we have security expert + tapps_security_scan. |
| **Senior Developer** (engineering) | Architecture and patterns; we have software-architecture expert. |

---

## 2. DocsMCP — Recommended agents

### 2.1 Copy (optional)

| Agency agent | Why |
|--------------|-----|
| **Technical Writer** (engineering) | Clear fit for doc generation: developer docs, API reference, tutorials. Optional: ship as Cursor/Claude agent so “use Technical Writer for this doc” is one click. |

### 2.2 Leverage (enrich DocsMCP generators and prompts)

| Agency agent | DocsMCP area | How to leverage |
|--------------|--------------|-----------------|
| **Technical Writer** | docs_generate_* tools, templates | Add structure and style from Technical Writer (clarity, code samples, audience level) into PRD/epic/story/spec templates and generator prompts. |
| **UX Researcher** (design) | PRD personas, user research | Use “user testing, behavior analysis, research” to shape PRD “Target Users & Personas” and user research sections. |
| **Feedback Synthesizer** (product) | PRD, epics | Use “user feedback analysis, insights extraction” to add prompts or sections for feedback-driven priorities in PRDs and epic prompts. |
| **Sprint Prioritizer** (product) | Epics, stories | Use “Agile planning, feature prioritization” to improve epic/story ordering and “Definition of done” in story templates. |
| **Reality Checker** (testing) | Specs, acceptance criteria | Reference “evidence-based certification” in spec/AC generation: e.g. “require measurable evidence for done.” |

**Mechanism:** Epic 75 (LLM Artifact Structure & Prompt Generation): when defining PromptConfig, common schema, and docs_generate_prompt, pull deliverable structure and success metrics from these agents into generator prompts and templates.

### 2.3 Reference only

| Agency agents | Why |
|---------------|-----|
| **Technical Writer, Content Creator** (marketing) | For narrative/marketing docs; DocsMCP is technical/PRD/epic/story. Reference for teams that also do content. |
| **Studio Producer, Project Shepherd** (PM) | For PM users who want PM personas; DocsMCP stays focused on artifact generation, not full PM workflow. |

---

## 3. Priority order

1. **TappsMCP**
   - **High:** Leverage Reality Checker + Security Engineer + Accessibility Auditor in experts and pipeline (persona, critical rules, success metrics).
   - **Medium:** Copy or recommend Reality Checker (and optionally Evidence Collector) via Epic 77 so projects can install for “validate before sign-off.”
   - **Lower:** Tool Evaluator leverage; Reference Testing division + Security Engineer in docs.
2. **DocsMCP**
   - **High:** Leverage Technical Writer, Feedback Synthesizer, Sprint Prioritizer in PRD/epic/story prompts and templates (Epic 75).
   - **Medium:** Leverage UX Researcher for PRD personas; Reality Checker for evidence-based AC in specs.
   - **Lower:** Optional copy of Technical Writer agent; reference Content/PM agents in docs.

---

## 4. What not to add

- **Marketing, Sales, Paid Media, Support** (non-technical): Out of scope for TappsMCP and DocsMCP unless we add business-doc or GTM tooling later.
- **Game dev, Spatial, WeChat/Baidu/Bilibili specialists:** Niche; reference only if a consumer project needs them.
- **Full agency roster in init:** Don’t ship 120 agents by default. Curated subset (e.g. Reality Checker, Evidence Collector, Technical Writer) or “install agency-agents” hint is enough.

---

## 5. References

- [agency-agents](https://github.com/msitarzewski/agency-agents) — roster, CONTRIBUTING, integrations (Cursor, Claude Code, etc.)
- docs/reviews/AGENCY-AGENTS-REPO-DEEP-DIVE.md
- docs/reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md
- Epic 75 (LLM Artifact & Prompt Generation), Epic 77 (Agency-Agents Integration), Epics 70–73 (Expert Persona / Critical Rules / Knowledge Enrichment)

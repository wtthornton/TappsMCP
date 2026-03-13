# TappsMCP Epics

## Documentation Excellence Series (Epics 80-86)

Goal: Elevate DocsMCP from B+ to A+ -- the best documentation tooling for AI-assisted development.

| Epic | Title | Priority | LOE | Stories | Status |
|------|-------|----------|-----|---------|--------|
| [80](EPIC-80-C4-MODEL-SEQUENCE-DIAGRAM-SUPPORT.md) | C4 Model & Sequence Diagram Support | P1 | ~2-3 weeks | 5 (26 pts) | Proposed |
| [81](EPIC-81-D2-FORMAT-INTERACTIVE-HTML-DIAGRAMS.md) | D2 Format & Interactive HTML Diagrams | P1 | ~2 weeks | 4 (24 pts) | Proposed |
| [82](EPIC-82-DIATAXIS-CONTENT-CLASSIFICATION.md) | Diataxis Content Classification & Validation | P1 | ~2 weeks | 3 (16 pts) | Proposed |
| [83](EPIC-83-LLMS-TXT-MACHINE-READABLE-DOCS.md) | llms.txt & Machine-Readable Documentation | P1 | ~1.5 weeks | 3 (13 pts) | Proposed |
| [84](EPIC-84-DOC-STYLE-TONE-VALIDATION.md) | Doc Style & Tone Validation (Vale Integration) | P2 | ~2 weeks | 4 (18 pts) | Proposed |
| [85](EPIC-85-PURPOSE-INTENT-TEMPLATES-DOC-INDEX.md) | Purpose/Intent Architecture Templates & Doc Index | P2 | ~2 weeks | 4 (21 pts) | Proposed |
| [86](EPIC-86-DOCUMENTATION-PLATFORM-INIT-INTEGRATION.md) | Documentation Platform Init & Upgrade Integration | P1 | ~2 weeks | 5 (21 pts) | Proposed |

**Total: 7 epics, 28 stories, 139 story points, ~14 weeks estimated**

### Recommended Implementation Order

```
Phase 1 (Foundation):  Epic 80 (C4/Sequence) --> Epic 81 (D2/Interactive)
Phase 2 (Intelligence): Epic 82 (Diataxis) --> Epic 83 (llms.txt)
Phase 3 (Quality):      Epic 84 (Style) --> Epic 85 (Architecture Templates)
Phase 4 (Integration):  Epic 86 (Init/Upgrade) -- depends on 82, 83
```

### Dependency Graph

```
Epic 80 (C4/Sequence)
  |
  v
Epic 81 (D2/Interactive) --> Epic 85 (Architecture Templates)
                                |
Epic 82 (Diataxis) ----------->|
  |                             v
  v                       Epic 86 (Init Integration)
Epic 83 (llms.txt) ----------->|
                                |
Epic 84 (Style) -------------->|
```

### What This Achieves (Before vs After)

| Category | Current Grade | Target Grade | Key Additions |
|----------|--------------|--------------|---------------|
| Diagram Quality | B | A | C4 model, sequence, D2 format, interactive HTML |
| Content Organization | B+ | A | Diataxis classification, balance validation |
| AI Readiness | B+ | A+ | llms.txt, structured frontmatter |
| Validation Suite | A | A+ | Style/tone checking, Diataxis validation |
| Architecture Templates | B- | A | Purpose/Intent template, series bootstrap, doc index |
| Init Automation | D (docs) | A | Doc agents, skills, hooks in init/upgrade |
| **Overall** | **B+** | **A+** | |

## Previous Epics (0-79)

All complete. See [docs/archive/planning/epics/](../../archive/planning/epics/) for historical epics.

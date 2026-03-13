# TappsMCP Epics

## Documentation Excellence Series (Epics 80-87)

Goal: Elevate DocsMCP from B+ to A+ -- the best documentation tooling for AI-assisted development.

| Epic | Title | Priority | LOE | Stories | Status |
|------|-------|----------|-----|---------|--------|
| [83](EPIC-83-LLMS-TXT-MACHINE-READABLE-DOCS.md) | llms.txt & Machine-Readable Documentation | P1 | ~1.5 weeks | 3 (13 pts) | **Complete** |
| [82](EPIC-82-DIATAXIS-CONTENT-CLASSIFICATION.md) | Diataxis Content Classification & Validation | P1 | ~2 weeks | 3 (16 pts) | **Complete** |
| [86](EPIC-86-DOCUMENTATION-PLATFORM-INIT-INTEGRATION.md) | Documentation Platform Init & Upgrade Integration | P1 | ~2 weeks | 5 (21 pts) | **Complete** |
| [80](EPIC-80-C4-MODEL-SEQUENCE-DIAGRAM-SUPPORT.md) | C4 Model & Sequence Diagram Support | P1 | ~2-3 weeks | 5 (26 pts) | **Complete** |
| [81](EPIC-81-D2-FORMAT-INTERACTIVE-HTML-DIAGRAMS.md) | Interactive HTML Diagrams (81.3 only) | P2 | ~1 week | 1 (8 pts) | **Complete** (D2 deferred) |
| [85](EPIC-85-PURPOSE-INTENT-TEMPLATES-DOC-INDEX.md) | Architecture Templates & Doc Index (reduced) | P2 | ~1.5 weeks | 3 (16 pts) | **Complete** (85.3 cut) |
| [84](EPIC-84-DOC-STYLE-TONE-VALIDATION.md) | Doc Style & Tone Validation (Vale Integration) | P3 | ~2 weeks | 4 (18 pts) | Deferred |
| [87](EPIC-87-CONTENT-RETURN-PATTERN-DOCKER-FILE-WRITES.md) | Content-Return Pattern for Docker File Writes | P0 | ~3-4 weeks | 7 (39 pts) | **Complete** |

**7 of 8 epics complete. 1 deferred (Epic 84). 2 individual stories deferred (81.1/2/4, 85.3).**

### Revised Implementation Order (2026-03-13)

Reprioritized for maximum value per effort, shipping quick wins first.

```
Phase 1 (Quick wins):     Epic 83 (llms.txt)                    ─── 1.5 weeks
Phase 2 (Intelligence):   Epic 82 (Diataxis)                    ─── 2 weeks
Phase 3 (Integration):    Epic 86 (Init/Upgrade)                ─── 2 weeks
Phase 4 (Diagrams):       Epic 80 (C4 + sequence) + 81.3 (interactive HTML) ─── 2.5 weeks
Phase 5 (Templates):      Epic 85 (reduced: no series bootstrap) ─── 1.5 weeks
Deferred:                 Epic 84 (Style), 81.1/81.2/81.4 (D2)
```

### Scope Adjustments

| Epic | Change | Rationale |
|------|--------|-----------|
| 80 | Story 80.4 (Sequence Diagrams) now complete | Originally deferred; implemented with depth-limited auto-detect + manual flow_spec modes |
| 81 | Extract Story 81.3 only; defer 81.1/81.2/81.4 (D2 format) | D2 is niche; interactive HTML is independently valuable |
| 85 | Cut Story 85.3 (Architecture Series Bootstrap) | Auto-generating 25+ files produces heavy manual editing; ship building blocks instead |
| 84 | Defer entirely | P2 style checking is noisy for terse technical docs; English-only limits adoption |

### Dependency Graph

```
Epic 83 (llms.txt)
  |
  v
Epic 82 (Diataxis) ────────> Epic 86 (Init Integration)
                                |
Epic 80 (C4 diagrams) ────> Epic 85 (Architecture Templates)
  |
  v
Epic 81.3 (Interactive HTML)
```

### What This Achieves (Before vs After)

| Category | Current Grade | Target Grade | Key Additions |
|----------|--------------|--------------|---------------|
| AI Readiness | B+ | A+ | llms.txt, structured frontmatter |
| Content Organization | B+ | A | Diataxis classification, balance validation |
| Init Automation | D (docs) | A | Doc agents, skills, hooks in init/upgrade |
| Diagram Quality | B | A | C4 model diagrams, sequence diagrams, interactive HTML |
| Architecture Templates | B- | A- | Purpose/Intent template, doc index |
| **Overall** | **B+** | **A** | |

## Previous Epics (0-79)

All complete. See [docs/archive/planning/epics/](../../archive/planning/epics/) for historical epics.

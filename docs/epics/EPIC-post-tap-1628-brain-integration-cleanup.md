# Post-TAP-1628 brain integration cleanup

## Purpose & Intent
We are completing the tapps-brain 3.17.2 integration by addressing 7 remaining cleanup items that finish the TAP-1628 epic and prepare the platform for full brain-native features.

## Goal
Finalize brain integration by updating version pins, wiring new batch operations into Ralph cold-start, reconciling infrastructure policy, and documenting health diagnostics.

## Motivation
TAP-1628 shipped 9 new memory actions but left trailing cleanup work. Completing these items unlocks full adoption of recall_many, rate, related, and knowledge-graph features across the platform.

## Acceptance Criteria
- [ ] All 7 stories complete and moved to Done
- [ ] Version pin reflects 3.17.0 floor
- [ ] Brain-health docs surface in AGENTS.md
- [ ] Temporary session files cleaned from repo

## Stories

### 0.1: Bump tapps-brain floor pin from 3.7.2 to 3.17.0
- Points: 3
- Update pyproject.toml to reflect minimum supported tapps-brain version after TAP-1628 ship. Document the breaking changes and new capability floor in a new ADR superseding ADR-0002.

### 0.2: Wire recall_many/rate/related into Ralph cold-start
- Points: 5
- Integrate batch memory recall, feedback routing, and knowledge-graph traversal into Ralph's task bootstrap. Simplify skill flows by deferring entity lookups to the brain.

### 0.3: Reconcile .mcp.json brain entry policy
- Points: 3
- Decide whether brain should be exposed as a direct HTTP entry in .mcp.json or remain bridge-only. Document in integration-hygiene.md or new ADR.

### 0.4: Move TAP-1629/1630/1631/1632/1633 children to Done
- Points: 2
- Update Linear issue statuses for the 5 child epics to 'Done' now that TAP-1628 ship is complete.

### 0.5: Surface brain-health row documentation
- Points: 2
- Add brain-health diagnostics row to AGENTS.md and docs/MEMORY_REFERENCE.md. Include dashboard links and troubleshooting steps.

### 0.6: Clean up temporary files from recent sessions
- Points: 1
- Delete .mcp.json.backup-20260514, .ralphrc.legacy-20260513, .ralph/.audit.jsonl, .ralph/.token_count from repo root.

### 0.7: Review and merge pending documentation updates
- Points: 2
- Audit remaining docs for drift vs TAP-1628 changes; confirm MEMORY_REFERENCE.md, docs/ARCHITECTURE.md, and ADR index are in sync.

## Out of Scope
- Refactoring of existing memory action handlers
- Major breaking changes to the BrainBridge interface
- Cross-project or external dependency updates

## References
- Epic TAP-1628: Brain native session memory + batch ops + knowledge graph + feedback flywheel
- ADR-0001: In-process AgentBrain via BrainBridge
- ADR-0002: Pin tapps-brain version floor (to be superseded)
- docs/ARCHITECTURE.md: Module dependency graph

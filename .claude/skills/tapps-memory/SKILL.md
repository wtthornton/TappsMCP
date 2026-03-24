---
name: tapps-memory
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  33 actions: save, search, consolidate, federation, profiles, Hive, and more.
mcp_tools:
  - tapps_memory
  - tapps_session_notes
---

Manage shared project memory using TappsMCP (**33 actions** via `action=` on `tapps_memory`):

**Core CRUD:** save, save_bulk, get, list, delete (architectural **save** may **supersede** when enabled in config)
**Search:** search (ranked BM25 with composite scoring)
**Intelligence:** reinforce, gc, contradictions, reseed
**Consolidation:** consolidate, unconsolidate
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status
**Maintenance:** index_session, validate, maintain
**Security:** safety_check, verify_integrity
**Profiles:** profile_info, profile_list, profile_switch
**Diagnostics:** health
**Hive / Agent Teams:** hive_status, hive_search, hive_propagate, agent_register

Shipped defaults turn on expert auto-save, recurring quick_check memory, architectural supersede, impact enrichment, and memory_hooks (auto-recall/capture). Override in `.tapps-mcp.yaml`. See `docs/MEMORY_REFERENCE.md`.

Steps:
1. Determine the action from the list above
2. For saves, classify tier (architectural/pattern/procedural/context) and scope (project/branch/session/shared)
3. Call `tapps_memory` with the action and parameters
4. Display results with confidence scores and composite relevance scores

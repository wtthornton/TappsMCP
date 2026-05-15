---
name: tapps-memory
description: >-
  Manage shared project memory for cross-session knowledge persistence.
  42 actions: save, search, federation, profiles, Hive, knowledge graph, batch ops, feedback, native session memory, and more.
mcp_tools:
  - tapps_memory
  - tapps_session_notes
---

Manage shared project memory using TappsMCP (42 actions):

**Core CRUD:** save, save_bulk, get, list, delete
**Search:** search (ranked BM25 with composite scoring; auto-emits `feedback_gap` on low-similarity hits)
**Intelligence:** reinforce, gc, contradictions, reseed
**Consolidation:** consolidate (merge related entries), unconsolidate (undo)
**Import/export:** import (JSON), export (JSON or Markdown)
**Federation:** federate_register, federate_publish, federate_subscribe, federate_sync, federate_search, federate_status
**Maintenance:** validate (check store integrity), maintain (GC + consolidation + contradiction detection)
**Security:** safety_check, verify_integrity | **Profiles:** profile_info, profile_list, profile_switch | **Diagnostics:** health
**Hive / Agent Teams:** hive_status, hive_search, hive_propagate, agent_register
**Knowledge graph (TAP-1630):** related, relations, neighbors, explain_connection
**Batch ops (TAP-1631):** recall_many, reinforce_many
**Feedback flywheel (TAP-1632):** rate (+ auto-emitted feedback_gap on search misses)
**Native session memory (TAP-1633):** index_session, search_sessions, session_end

Steps:
1. Determine the action from the list above
2. For saves, classify tier (architectural/pattern/procedural/context) and scope (project/branch/session/shared)
3. Call `tapps_memory` with the action and parameters
4. Display results with confidence scores and composite relevance scores

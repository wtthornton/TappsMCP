# TappsMCP Platform — Backlog Execution Plan

Generated: 2026-04-21  
Issues: 49 open in TappsMCP Platform project  
Strategy: 8 waves, ordered by impact + dependency order

---

## Wave 1 — Critical Correctness (7 issues)
*Data integrity, tool errors, race conditions. Execute first.*

| Issue | Title | Risk |
|-------|-------|------|
| TAP-682 | `_session_state` mutated without lock — race across concurrent MCP sessions | Data corruption |
| TAP-701 | `_session_state` uses magic string keys with no TypedDict — typos silently do nothing | Silent bugs |
| TAP-683 | `_upgrade_agents_md`: non-atomic `write_text` — interrupt mid-write corrupts AGENTS.md | Data loss |
| TAP-707 | `upgrade_pipeline`: backup claimed atomic but failure path is not | Data loss |
| TAP-706 | `_mcp_json_has_tapps_entry` only checks one host's config — consent gate miss | Security |
| TAP-610 | `tapps_dependency_scan` errors out on monorepo (editable + no hash) | Tool broken |
| TAP-614 | `tapps_session_start` reports `has_tests=false` on repo with ~6,900 tests | False reporting |

---

## Wave 2 — Quality Gate Self-Consistency (2 issues)
*TappsMCP must pass its own quality gate. Prerequisite to Wave 3.*

| Issue | Title | Current Score |
|-------|-------|--------------|
| TAP-609 | `server_pipeline_tools.py` 2,755 LOC, MI=0 — fails gate (41.8/70) | 41.8 |
| TAP-611 | `upgrade.py` `_upgrade_platform` CC=33, 1,006 LOC — fails gate (51.6/70) | 51.6 |

---

## Wave 3 — Silent Error Epidemic (6 issues)
*`except Exception: pass` hides all bugs. Fix after Wave 2 splits the large files.*

| Issue | Title | Location |
|-------|-------|----------|
| TAP-693 | 5x `except Exception: pass` in tapps-mcp server tools | server_*.py |
| TAP-694 | 15+ `except Exception: pass` in docs-mcp | docs-mcp |
| TAP-695 | `except Exception: pass` in metrics/dashboard.py:757 | tapps-core |
| TAP-684 | upgrade_pipeline: 4 blanket `except Exception` mask programming errors | upgrade.py |
| TAP-685 | `_refresh_karpathy_blocks` swallows stack trace, stores only `f"error: {exc}"` | upgrade.py |
| TAP-612 | Bare `try/except/pass` in `_DOCS_COVERED` workspace scan (B110) | server_pipeline_tools.py |

---

## Wave 4 — Upgrade Pipeline Correctness (8 issues)
*All in `upgrade.py` / `server_pipeline_tools.py`. Fix together after Wave 2 refactors those files.*

| Issue | Title |
|-------|-------|
| TAP-704 | `mcp_only` not propagated to checklist/fingerprint |
| TAP-705 | `mcp_only` branch result shape inconsistent (`settings` key absent when skipped) |
| TAP-689 | `_collect_upgrade_targets` misses `.claude/rules/*.md` — backup incomplete |
| TAP-690 | `_upgrade_content_return` does not honor `mcp_only` — Docker consumers blocked |
| TAP-691 | `upgrade_skip_files` tokens case-sensitive — silent no-op on typos |
| TAP-692 | Unknown `upgrade_skip_files` tokens reported but never error |
| TAP-702 | `_refresh_karpathy_blocks` reaches into `karpathy_block._find_block_span` (private API) |
| TAP-703 | `_collect_upgrade_targets` uses `startswith("tapps-")` — too broad |

---

## Wave 5 — Scoring / Detection Noise (9 issues)
*Reduce false positives that degrade UX on consuming projects.*

| Issue | Title |
|-------|-------|
| TAP-620 | Test files score 70.1–74.1 with 49–75 "security issues" — bandit noise |
| TAP-613 | `.claude/worktrees/` leaks into `tapps_dependency_graph` (2,994 modules scanned) |
| TAP-615 | Fragile PEP 508 dependency parsing in `_DOCS_COVERED` scan |
| TAP-616 | Vulture false-positives on `@field_validator` classmethods in settings.py |
| TAP-617 | `session_start.diagnostics.vector_rag` is dead telemetry (`status="removed"`) |
| TAP-618 | `tapps_score_file` docs_hint nags about workspace-internal libraries |
| TAP-686 | `_has_python_signals`: unbounded `rglob` traverses vendor/node_modules |
| TAP-687 | `_has_python_signals`: `skip_dirs` misses `.tox`, `.pytest_cache`, `site-packages` |
| TAP-688 | `_has_python_signals` returns `False` on `OSError` — silent false negative |

---

## Wave 6 — Config / Settings Hardening (3 issues)
*Pydantic strictness, doc drift, placeholder cleanup.*

| Issue | Title |
|-------|-------|
| TAP-698 | `TappsMCPSettings` does not set `extra="forbid"` — typos in `.tapps-mcp.yaml` silently dropped |
| TAP-699 | `dependency_security.py` docstrings use `"CVE-2024-XXXXX"` placeholder |
| TAP-700 | New Ralph-feedback settings undocumented in `.tapps-mcp.yaml` example |

---

## Wave 7 — Test Quality (3 issues)
*Fix after main code is stable.*

| Issue | Title |
|-------|-------|
| TAP-696 | `test_existing_tapps_entry_triggers_regeneration`: assertion too permissive |
| TAP-697 | `_fresh_settings` fixture annotated `-> None` but is a generator |
| TAP-516 | No contract test against running tapps-brain HTTP adapter |

---

## Wave 8 — Major Feature (1 issue)
*Depends on Wave 1 correctness work and TAP-516 test harness.*

| Issue | Title |
|-------|-------|
| TAP-778 | BrainBridge: migrate runtime from in-process `AgentBrain` to authenticated HTTP (full runtime switch) |

---

## Execution Order Summary

```
Wave 1 (7)  →  Wave 2 (2)  →  Wave 3 (6)  →  Wave 4 (8)
                                                    ↓
                             Wave 8 (1)  ←  Wave 7 (3)  ←  Wave 5 (9)  ←  Wave 6 (3)
```

Total: 49 issues across 8 waves.

## Notes

- Waves 1–3 are the highest ROI: fix correctness, dogfood own quality gate, eliminate silent swallowing.
- Wave 2 (TAP-609, TAP-611) requires splitting large files — creates the clean structure that Wave 3/4 fixes land in.
- TAP-516 (contract test harness) is prerequisite for TAP-778 (HTTP migration validation).
- All Linear SDLC steps (Template A/B/C) required per issue.

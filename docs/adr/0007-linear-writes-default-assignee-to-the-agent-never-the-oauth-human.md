# 7. Linear writes default assignee to the agent, never the OAuth human

Date: 2026-05-02

## Status

accepted

## Context

Linear access in Claude Code is OAuth via the `mcp__plugin_linear_linear__*` plugin; tokens live in `~/.claude/.credentials.json` and identify a single human (the operator who installed the credential). When the agent creates or updates a Linear epic, story, or issue, Linear's default behavior is to assign the issue to the OAuth user unless `assignee` is explicitly set. This means every issue the agent files lands in the human operator's "Assigned to me" queue — including the ones the agent itself is going to execute next.</parameter>
<parameter name="decision">**All Linear writes (`save_issue`, including create and update) default `assignee` to a designated agent user, not the OAuth human.** The agent user is resolved once per session via `mcp__plugin_linear_linear__list_users`, matching against `name` / `displayName` / `email` containing `agent`, `bot`, `tapps`, `claude`, or the `agent_user` value in `.tapps-mcp.yaml`. The id is cached for the session. If no agent user exists in the team, `assignee` is left unset — the OAuth human is **never** the fallback. Override only when the user explicitly names a different assignee.</decision>
<parameter name="consequences">**Positive:** The human's Linear queue reflects work the human is doing, not work the agent filed and will execute. **Positive:** Ownership signals stay accurate — `agent`-assigned issues are agent-owned, `human`-assigned issues are human-owned. **Negative:** Teams without an agent user see un-assigned issues until an agent user is provisioned. Acceptable: better than silently dumping on the operator. **Operational note:** Codified in `.claude/rules/autonomy.md` and `.claude/rules/linear-standards.md`; enforced by the `linear-issue` skill.</consequences>
</invoke>

## Decision

Describe the decision that was made...

## Consequences

Describe the consequences of this decision...

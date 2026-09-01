export const meta = {
  name: 'webstoredna-linear-cleanup',
  description: 'Read-only evidence gathering + adversarial verify for Web-Store-DNA Linear dispositions (writes happen in the main session)',
  whenToUse: 'Lane D1 of prompts/archive/webstoredna-bringup.md. Pass args.candidates = [{id, hypothesis}]. Returns confirmed dispositions; the main session applies them via the linear-issue skill.',
  phases: [
    { title: 'Evidence', detail: 'per-issue ground truth from repo + live Linear state' },
    { title: 'Verify', detail: 'adversarial confirm/refute of each disposition' },
  ],
}

const DISPOSITION = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'current_state', 'verdict', 'evidence', 'rationale'],
  properties: {
    id: { type: 'string' },
    current_state: { type: 'string', description: 'live Linear state at read time' },
    verdict: { type: 'string', enum: ['close', 'cancel', 'dedupe', 'reparent', 'demote', 'reopen', 'update_state', 'keep', 'blocked'] },
    target: { type: 'string', description: 'target state / parent / canonical duplicate id, when applicable' },
    evidence: { type: 'array', items: { type: 'string' }, description: 'file:line, commit sha, PR #, probe output lines' },
    rationale: { type: 'string' },
    blocked_on: { type: 'string', description: 'when verdict=blocked: the VAL id or external condition this waits on' },
  },
}

const VERDICT = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'confirmed', 'reason'],
  properties: {
    id: { type: 'string' },
    confirmed: { type: 'boolean' },
    corrected_verdict: { type: 'string', description: 'when refuted: the verdict the evidence actually supports' },
    reason: { type: 'string' },
  },
}

// The Workflow harness may deliver args as a JSON-encoded string.
const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args
const candidates = (parsedArgs && parsedArgs.candidates) || []
if (!candidates.length) {
  throw new Error('Pass args.candidates = [{id: "TAP-####", hypothesis: "..."}] — see prompts/archive/webstoredna-bringup.md Lane D.')
}
if (candidates.length > 30) {
  throw new Error('Cap: ≤30 candidates per invocation. Chunk the list.')
}

const RULES = [
  'READ-ONLY: no file writes, no Linear writes, no state changes of any kind. You gather evidence; the orchestrator applies dispositions.',
  'Linear reads: load tools via ToolSearch ("select:mcp__nlt-linear-issues__tapps_linear_snapshot_get,mcp__plugin_linear_linear__get_issue,mcp__plugin_linear_linear__list_issues"). Single-issue lookups go straight to get_issue(id). Any multi-issue slice needs tapps_linear_snapshot_get(team="TappsCodingAgents", project=..., state=...) FIRST.',
  'Ground truth lives in /home/wtthornton/code/WebStoreDNA (CHANGELOG.md, git log, docs/, prompts/, reports/) and, for live claims, read-only probes (curl GET). Docs can be stale — commits and live probes outrank prose.',
  'Never print secret values. Cite every claim as file:line, commit sha, or pasted probe line.',
].join('\n')

phase('Evidence')
const results = await pipeline(
  candidates,
  (c) => agent([
    `Gather ground-truth evidence for Linear issue ${c.id} (team TappsCodingAgents, project Web-Store-DNA).`,
    `Working hypothesis from the 2026-08-11 audit: ${c.hypothesis}`,
    '',
    'Do: (1) get_issue for live state/parent/children; (2) check the hypothesis against repo reality — WebStoreDNA CHANGELOG.md, git log --oneline (main), the specific docs/prompts the issue names, and cheap read-only probes if the claim is about a live surface; (3) decide the disposition the EVIDENCE supports (which may contradict the hypothesis).',
    'Verdicts: close (work verifiably shipped) | cancel (premise invalid/superseded — name the superseding ruling) | dedupe (name canonical id in target) | reparent (name new parent in target) | demote (In Progress but idle/blocked — target state in target) | reopen | update_state (epic state to match children) | keep (state is accurate) | blocked (needs evidence this run has not produced yet — name it in blocked_on).',
    'Rule: an issue is closeable ONLY on deterministic evidence (commit/PR/probe), never on a doc claim alone.',
    '',
    RULES,
  ].join('\n'), { label: `evidence:${c.id}`, phase: 'Evidence', schema: DISPOSITION, effort: 'medium' }),
  (d, c) => d && agent([
    `Adversarially verify this proposed Linear disposition. REFUTE it if the evidence does not hold.`,
    `Issue: ${d.id} (Web-Store-DNA). Current state: ${d.current_state}. Proposed: ${d.verdict}${d.target ? ' -> ' + d.target : ''}.`,
    `Rationale: ${d.rationale}`,
    `Evidence claimed: ${JSON.stringify(d.evidence)}`,
    '',
    'Independently re-check the load-bearing evidence yourself (open the file:line, git show the sha, re-run the probe). Default to confirmed=false on any doubt. A "close" verdict with only prose evidence is refuted. If refuted, state the verdict the evidence actually supports in corrected_verdict.',
    '',
    RULES,
  ].join('\n'), { label: `verify:${d.id}`, phase: 'Verify', schema: VERDICT, effort: 'high' })
    .then((v) => ({ ...d, verify: v })),
)

const done = results.filter(Boolean)
const confirmed = done.filter((r) => r.verify && r.verify.confirmed)
const refuted = done.filter((r) => r.verify && !r.verify.confirmed)
const unverified = done.filter((r) => !r.verify)
log(`Dispositions: ${confirmed.length} confirmed, ${refuted.length} refuted, ${unverified.length} unverified, ${candidates.length - done.length} agent-failed`)
return { confirmed, refuted, unverified, failed_count: candidates.length - done.length }

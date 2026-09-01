export const meta = {
  name: 'epic-4145',
  description: 'Drive TAP-4145: fix the poc-ship engine+agents in NLTlabsPE, score every group, then tear down ShipProof and regenerate Pawvlov clean',
  phases: [
    { title: 'G1 deploy/infra' },
    { title: 'G2 template' },
    { title: 'G3 quality gates' },
    { title: 'G4 content' },
    { title: 'G5 dossier' },
    { title: 'Score' },
    { title: 'G6 teardown+regen' },
  ],
}

// All engine + agent code lives in NLTlabsPE (NLT Engine project, brain nlt-engine).
// Fix the ENGINE (poc/.template, builder, deploy, dossier) and the AGENTS
// (agents/poc-*, agents/number-auditor) — NEVER the throwaway ShipProof pages.
const ENGINE = '/home/wtthornton/code/NLTlabsPE'
const SCORE_LOG = '.loop/epic-4145-score.jsonl' // relative to the orchestrator repo
const TRAILER = 'Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>'
// Total stories the G6 barrier must see merged: g1a,g1b(2) + G2(5) + g3(<=3) + g4(<=3) + g5a,g5b(2).
const EXPECTED_STORY_COUNT = 15

const STORY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['story', 'branch', 'filesChanged', 'testsPassed', 'prUrl', 'capsAddressed'],
  properties: {
    story: { type: 'string' },
    branch: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    testsPassed: { type: 'boolean', description: 'full local test gate green before merge' },
    prUrl: { type: 'string', description: 'squash-merged PR URL with (#NNN), or "blocked: <reason>"' },
    capsAddressed: { type: 'array', items: { type: 'string' }, description: 'required-fail caps this story clears, e.g. ["C2"]' },
    notes: { type: 'string' },
  },
}

const SCORE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['after', 'ecs', 'weightedProgress', 'capsFired', 'logged'],
  properties: {
    after: { type: 'string', description: 'the group just completed, e.g. "G3"' },
    ecs: { type: 'integer' },
    weightedProgress: { type: 'integer' },
    capsFired: { type: 'array', items: { type: 'string' }, description: 'firing caps C1..C7' },
    logged: { type: 'boolean', description: 'a line was appended to the score log' },
    notes: { type: 'string' },
  },
}

// Implement one story in NLTlabsPE: branch -> fix engine/agent -> test -> squash PR.
function implStory(id, what, phaseTitle, isolate) {
  return agent(
    `In ${ENGINE}, implement TAP-${id}: ${what}\n` +
      `- Follow the issue's ## What/## Where/## Acceptance. Fix the ENGINE/AGENTS, never the generated ShipProof pages.\n` +
      `- Move the issue In Progress; post the kickoff comment; assignee = the agent identity (never the OAuth human).\n` +
      `- git checkout -b the issue's gitBranchName. Implement. Run the full local test gate; do NOT merge red.\n` +
      `- No green-by-suppression: never skip/disable a QA check to pass — a blocking gate is a signal, fix the real cause.\n` +
      `- Commit with trailer '${TRAILER}'. gh pr create then gh pr merge --squash --delete-branch.\n` +
      `- Post the summary comment with test pass/fail + changed files; move to Done only after the PR shows a (#NNN) suffix.\n` +
      `Return the structured result.`,
    { label: `impl:${id}`, phase: phaseTitle, schema: STORY_SCHEMA, ...(isolate ? { isolation: 'worktree' } : {}) },
  )
}

// Recompute the deterministic score and append one line to the score log.
function recompute(after, prevEcs) {
  return agent(
    `Recompute the Epic Completion Score for TAP-4145 after ${after}.\n` +
      `- Run NLTlabsPE/scripts/e2e_score.py (extend it if it doesn't yet emit ECS) against the most recent real build/deploy ` +
      `(ShipProof until torn down, then Pawvlov). weighted_progress = sum of per-acceptance-item credit (A1=12 TAP-4148, ` +
      `A2=12 TAP-4147, A3=14 TAP-4149/4151/4152/4153/4154, A4=16 TAP-4155/4157/4146, A5=12 TAP-4150/4156/4158, ` +
      `A6=12 TAP-4159/4160, A7=22 TAP-4161/4162) by fraction of stories merged+verified.\n` +
      `- Evaluate caps C1..C7 (deterministic): C1 degraded run deployed; C2 site_url host != *.nltlabs.ai; ` +
      `C3 live HTML has 'Needs populating'/'Coming in v2'/'Mock data — replace'; C4 nav/footer 404 (/tech-specs); ` +
      `C5 cross-vertical /dashboard mock; C6 dossier shows {} or 'unavailable' scores; C7 quality_reviewer missing. ` +
      `If ANY fires, ecs = min(weighted_progress, 59).\n` +
      `- Previous ECS was ${prevEcs}. Append {iteration, ts, ecs, weighted_progress, caps_fired, delta_vs_prev} to ${SCORE_LOG} ` +
      `(in the orchestrator repo). If ecs < ${prevEcs}, set notes to "REGRESSION: <which cap/story dropped it>".\n` +
      `Return the structured score.`,
    { label: `score:${after}`, phase: 'Score', schema: SCORE_SCHEMA },
  )
}

// G6 barrier guard: g2/g3/g4 are each already `.filter(Boolean)`-reduced (or built plain)
// before reaching here, so a story whose implStory() call failed outright and resolved
// falsy is invisible to a `blocked` check computed only from the survivors — the barrier
// could clear into the irreversible-adjacent G6 teardown+regen phase even though a G1-G5
// story never merged. Compare against EXPECTED_STORY_COUNT so a missing story blocks too.
// Pure (no workflow-harness globals) so scripts/test-epic-4145-barrier.js can extract and
// unit-test it — see check-fleet-sync.js for the same slice-and-eval idiom.
function checkBarrier(assembled, expectedCount) {
  const merged = assembled.filter(Boolean)
  const missing = expectedCount - merged.length
  const blocked = merged.filter((s) => !s.prUrl || s.prUrl.startsWith('blocked'))
  return {
    proceed: missing === 0 && blocked.length === 0,
    merged,
    blocked: blocked.map((s) => s.story),
    missing,
  }
}

if (budget.total && budget.remaining() < 60_000) {
  log(`insufficient budget (${budget.remaining()} left) for the epic sweep — aborting`)
  return { aborted: true, reason: 'budget' }
}

const scores = []
let prev = 0
async function scoreGate(after) {
  const s = await recompute(after, prev)
  scores.push(s)
  const delta = s.ecs - prev
  log(`ECS after ${after} = ${s.ecs} (Δ${delta >= 0 ? '+' : ''}${delta}) caps=${JSON.stringify(s.capsFired)}`)
  if (s.ecs < prev) log(`⚠ REGRESSION at ${after} — ${s.notes || 'investigate before continuing'}`)
  prev = s.ecs
  return s
}

// --- G1 deploy/infra: coupled (shared builder/deploy) -> sequential ---
phase('G1 deploy/infra')
const g1a = await implStory('4147', 'auto-bind <slug>.nltlabs.ai (Render custom-domain API + GoDaddy CNAME, poll SSL, set site_url); never leave a POC on raw onrender', 'G1 deploy/infra', false)
const g1b = await implStory('4148', 'block ship on a degraded/partial run (builder_failed, missing quality_reviewer/post_deploy_audit, incomplete_workflow) — surface a blocked status naming the missing nodes', 'G1 deploy/infra', false)
await scoreGate('G1')

// --- G2 template: coupled (shared .template components) -> sequential ---
phase('G2 template')
const G2 = [
  ['4149', 'never render author-facing placeholders on live public/investor pages (gate ValidationModeSections, StubSection, DashboardMock, author hints)'],
  ['4151', 'fix the dead /tech-specs nav + footer link (repoint to /inside/engineering or create the route)'],
  ['4152', 'DashboardMock must be data-driven from the POC domain (or product-neutral) and hidden when there is no real data — no wrong-vertical default'],
  ['4153', 'VideoSlot renders once max with a real poster; no empty "coming soon" gray box; stop gaming the QA rubric'],
  ['4154', 'make the template software/hardware-aware: drop hardware residue (isHardware default, 3D model-viewer dead path, chip/sensor meta) on software POCs'],
]
const g2 = []
for (const [id, what] of G2) g2.push(await implStory(id, what, 'G2 template', false))
await scoreGate('G2')

// --- G3 quality gates: distinct agent dirs -> parallel (worktree-isolated) ---
phase('G3 quality gates')
const g3 = (await parallel([
  () => implStory('4155', 'poc-quality-reviewer runs as a guaranteed blocking gate + expanded rubric (cross-vertical leakage, dead links, stub/placeholder leaks, empty scores)', 'G3 quality gates', true),
  () => implStory('4157', 'poc-content-qa FAILS any page with author-facing placeholder text or a dead internal link', 'G3 quality gates', true),
  () => implStory('4146', 'poc-visual-qa + scoring emit judge/FATE/gate scores for software POCs (or explicit "Not captured") — never empty {} or "unavailable"', 'G3 quality gates', true),
])).filter(Boolean)
await scoreGate('G3')

// --- G4 content producers: distinct agent dirs -> parallel (worktree-isolated) ---
phase('G4 content')
const g4 = (await parallel([
  () => implStory('4150', 'gtm-operator populates homepage Validation-Mode data (ICP, exclusions, 3 hypotheses, concierge_offer, pricing_test)', 'G4 content', true),
  () => implStory('4156', 'poc-director populates required investor fields (competitive.moats, overview.highlight_metrics, intro/wedge_detail, product_bom, decision.top_risks)', 'G4 content', true),
  () => implStory('4158', 'number-auditor runs before dossier finalize; poc-post-deploy-audit runs post-ship and populates dossier Ch.10', 'G4 content', true),
])).filter(Boolean)
await scoreGate('G4')

// --- G5 dossier builder: coupled (shared builder) -> sequential ---
phase('G5 dossier')
const g5a = await implStory('4159', 'fix dossier rendering: garbled Ch.9/Ch.13 diagrams (overlap/strike-through/truncation), blank Ch.12 Tear-Sheet page, truncated run-ids', 'G5 dossier', false)
const g5b = await implStory('4160', 'dossier formatting/content: acronym casing (TAM/SAM/SOM/LTV/CAC/MRR/MVP), render "Not captured" for empty scores, strip internal/TAP/fixture language, citations, stub chapters', 'G5 dossier', false)
await scoreGate('G5')

// --- Barrier: G6 runs ONLY after all EXPECTED_STORY_COUNT G1-G5 stories are merged ---
const barrier = checkBarrier([g1a, g1b, ...g2, ...g3, ...g4, g5a, g5b], EXPECTED_STORY_COUNT)
if (!barrier.proceed) {
  log(`G6 barrier NOT cleared — ${barrier.missing} story(ies) missing (agent failure), ` +
    `${barrier.blocked.length} unmerged: ${barrier.blocked.join(', ') || 'none named'}`)
  return { phase: 'pre-G6', scores, merged: barrier.merged, blocked: barrier.blocked, missing: barrier.missing, ecs: prev }
}

phase('G6 teardown+regen')
// Teardown: do all reversible code-side removal via PR; the Render service DELETE is
// irreversible/outward — surface the exact command, do NOT call the delete API here.
const teardown = await agent(
  `In ${ENGINE}, tear down ShipProof (TAP-4161), CODE SIDE ONLY: remove poc/shipproof/, the shipproof block in render.yaml, ` +
    `data/ideas/idea-shipproof/, and revert the related commits — via a squash PR (trailer '${TRAILER}'). ` +
    `Do NOT call the Render delete API for service srv-d8pl6fpkh4rs739c1q30 — instead return the exact curl/CLI command for a human to run ` +
    `(irreversible outward step). Return {prUrl, renderDeleteCommand, notes}.`,
  { label: 'teardown:4161', phase: 'G6 teardown+regen', schema: {
    type: 'object', additionalProperties: false,
    required: ['prUrl', 'renderDeleteCommand'],
    properties: { prUrl: { type: 'string' }, renderDeleteCommand: { type: 'string' }, notes: { type: 'string' } },
  } },
)

// Regenerate the flagship as Pawvlov with the fixed pipeline — a clean, NON-degraded run.
const regen = await agent(
  `In ${ENGINE}, run a full NON-degraded poc-ship for the Pawvlov idea (TAP-4162): all QA/audit nodes run, custom domain bound. ` +
    `Land it on pawvlov.nltlabs.ai (not raw onrender). Then re-audit against every TAP-4145 acceptance item and the caps C1..C7. ` +
    `Return {siteUrl, degraded, missingNodes, auditClean, failedItems}.`,
  { label: 'regen:4162', phase: 'G6 teardown+regen', schema: {
    type: 'object', additionalProperties: false,
    required: ['siteUrl', 'degraded', 'auditClean'],
    properties: {
      siteUrl: { type: 'string' }, degraded: { type: 'boolean' },
      missingNodes: { type: 'array', items: { type: 'string' } },
      auditClean: { type: 'boolean' },
      failedItems: { type: 'array', items: { type: 'string' } },
    },
  } },
)

const final = await scoreGate('G6')

return {
  scores,
  finalEcs: final.ecs,
  capsFired: final.capsFired,
  pawvlov: regen,
  renderDeleteCommand: teardown.renderDeleteCommand,
  done: final.ecs === 100 && final.capsFired.length === 0 && regen.auditClean === true,
}

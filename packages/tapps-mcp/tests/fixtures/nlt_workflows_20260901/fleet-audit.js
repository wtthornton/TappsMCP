export const meta = {
  name: 'fleet-audit',
  description: 'Parallel read-only audit of every repo in the NLT fleet → one synthesized readiness report',
  phases: [
    { title: 'Audit', detail: 'one read-only agent per repo' },
    { title: 'Synthesize', detail: 'merge findings into a fleet readiness report' },
  ],
}

// Fleet manifest. Canonical source is ../../fleet.paths.json — but Workflow
// scripts run in a sandbox with no fs/env access, so this inline copy MUST be
// kept in sync with fleet.paths.json by hand (paths are the current Linux host).
// `node scripts/check-fleet-sync.js` fails if the two drift apart.
const REPOS = [
  { name: 'TappsMCP',           path: '/home/wtthornton/code/tapps-mcp',                     brain: 'tapps-mcp',       linear: 'TappsMCP Platform',       tier: 'platform' },
  { name: 'tapps-brain',        path: '/home/wtthornton/code/tapps-brain',                   brain: null,              linear: 'tapps-brain',             tier: 'platform' },
  { name: 'AgentForge',         path: '/home/wtthornton/code/AgentForge',                    brain: 'agentforge',      linear: 'AgentForge Platform',     tier: 'platform' },
  { name: 'ralph-claude-code',  path: '/home/wtthornton/code/ralph-claude-code',             brain: null,              linear: 'Ralph Continuous Coding', tier: 'platform' },
  { name: 'TappsCommandCenter', path: '/home/wtthornton/Tapps Command Center',               brain: null,              linear: 'Tapps Command Center',    tier: 'platform' },
  { name: 'Scout',              path: '/home/wtthornton/code/nlt-ideas-scout',               deploy_root: '/home/wtthornton/NewCompanyIdeas', brain: 'nlt-ideas-scout', linear: 'NLT Ideas Scout',         tier: 'pe-pipeline' },
  { name: 'Engine',             path: '/home/wtthornton/code/NLTlabsPE',                     brain: 'nlt-engine',      linear: 'NLT Engine',              tier: 'pe-pipeline' },
  { name: 'nlt-portfolio',      path: '/home/wtthornton/code/nlt-portfolio',                 brain: null,              linear: 'NLT Portfolio',           tier: 'pe-pipeline' },
  { name: 'ReportLab',          path: '/home/wtthornton/code/ReportLab',                     brain: 'reportlab',       linear: 'NLT Report Studio',       tier: 'pe-pipeline' },
  { name: 'NLTWeb',             path: '/home/wtthornton/code/NLTWeb',                        brain: null,              linear: null,                      tier: 'web-brand' },
  { name: 'NLTMarketing',       path: '/home/wtthornton/code/NLTMarketing',                  brain: null,              linear: 'NLT Marketing',           tier: 'web-brand' },
  { name: 'personal-ops',       path: '/home/wtthornton/code/personal-ops',                  brain: null,              linear: 'personal-ops',            tier: 'agent-dna' },
  { name: 'WebStoreDNA',        path: '/home/wtthornton/code/WebStoreDNA',                   brain: null,              linear: 'Web-Store-DNA',           tier: 'agent-dna' },
  { name: 'Alpaca',             path: '/home/wtthornton/code/Alpaca',                        brain: null,              linear: 'Alpaca',                  tier: 'product' },
  { name: 'tapps-3d-printing',  path: '/home/wtthornton/BambuStudio',                        brain: null,              linear: 'tapps-3d-printing',       tier: 'product' },
  { name: 'TheStudio',          path: '/home/wtthornton/TheStudio',                          brain: null,              linear: null,                      tier: 'product' },
  { name: 'Workstation',        path: '/home/wtthornton/code/Workstation',                   brain: null,              linear: null,                      tier: 'product' },
  { name: 'TradingAgents',      path: '/home/wtthornton/tradingagents',                      brain: null,              linear: null,                      tier: 'product' },
  { name: 'hearth-goods-store', path: '/home/wtthornton/hearth-goods-store',                 brain: null,              linear: null,                      tier: 'product' },
  { name: 'CuttingEdgeGraphix', path: '/home/wtthornton/code/CuttingEdgeGraphix',            brain: null,              linear: 'CuttingEdgeGraphix',      tier: 'client-store' },
  { name: 'cuttingedgegraphix-store', path: '/home/wtthornton/cuttingedgegraphix-store', brain: null,              linear: 'CuttingEdgeGraphix',      tier: 'client-store' },
  { name: 'rig-echo',           path: '/home/wtthornton/code/agentforge-echo-plugin',        brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-a2a',            path: '/home/wtthornton/code/agentforge-a2a-plugin',         brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-policy',         path: '/home/wtthornton/code/agentforge-policy-plugin',      brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-brain',          path: '/home/wtthornton/code/agentforge-brain-plugin',       brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-credentials',    path: '/home/wtthornton/code/agentforge-credentials-plugin', brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-federation',     path: '/home/wtthornton/code/agentforge-federation-plugin',  brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-matcher',        path: '/home/wtthornton/code/agentforge-matcher-plugin',     brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-mcp',            path: '/home/wtthornton/code/agentforge-mcp-plugin',         brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-replay',         path: '/home/wtthornton/code/agentforge-replay-plugin',      brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-resources',      path: '/home/wtthornton/code/agentforge-resources-plugin',   brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-sinks',          path: '/home/wtthornton/code/agentforge-sinks-plugin',       brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-stream',         path: '/home/wtthornton/code/agentforge-stream-plugin',      brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-trigger',        path: '/home/wtthornton/code/agentforge-trigger-plugin',     brain: null,              linear: null,                      tier: 'rig' },
  { name: 'rig-workflow',       path: '/home/wtthornton/code/agentforge-workflow-plugin',    brain: null,              linear: null,                      tier: 'rig' },
]

// Auditing all 35 repos at once is rarely what you want — one agent per repo.
// Default to the tiers that cross-cut everything; widen explicitly via args.
// e.g. Workflow({name:'fleet-audit', args:{tiers:['all']}}) or {tiers:['rig']}.
const DEFAULT_TIERS = ['platform', 'pe-pipeline']
const requested = (args && args.tiers) || DEFAULT_TIERS
const TARGETS = requested.includes('all') ? REPOS : REPOS.filter((r) => requested.includes(r.tier))

const REPO_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['repo', 'branch', 'clean', 'health', 'findings'],
  properties: {
    repo: { type: 'string' },
    branch: { type: 'string' },
    clean: { type: 'boolean', description: 'working tree clean' },
    health: { type: 'string', enum: ['green', 'yellow', 'red'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'summary'],
        properties: {
          severity: { type: 'string', enum: ['info', 'warn', 'block'] },
          summary: { type: 'string' },
        },
      },
    },
  },
}

// Pure aggregation helper: names of TARGETS whose agent() call did not land in
// `clean` (failed, returned falsy, or was dropped by results.filter(Boolean)).
// Extracted so it can be unit-tested without the top-level workflow harness calls
// (phase/agent/parallel) that make this file un-importable — see
// scripts/test-fleet-audit-missing.js.
function computeMissing(targets, clean) {
  const reported = new Set(clean.map((r) => r.repo))
  return targets.map((t) => t.name).filter((name) => !reported.has(name))
}

phase('Audit')
log(`auditing ${TARGETS.length} of ${REPOS.length} repos (tiers: ${requested.join(', ')})`)
const results = await parallel(
  TARGETS.map((r) => () =>
    agent(
      `Read-only audit of the repo at ${r.path} (role: ${r.name}). Do NOT edit anything.\n` +
        `Report: current branch, whether the working tree is clean (git status), and 0-5 findings ` +
        `(severity info/warn/block) covering: uncommitted/stale state, failing or skipped test signals ` +
        `visible in the tree, obvious quality/security smells, and stale Ralph briefs (.ralph/brief.json). ` +
        `Assign an overall health: green (clean, no warn/block), yellow (warns), red (any block).`,
      { label: `audit:${r.name}`, phase: 'Audit', schema: REPO_SCHEMA, agentType: 'Explore' },
    ),
  ),
)

const clean = results.filter(Boolean)
const missing = computeMissing(TARGETS, clean)
phase('Synthesize')
const report = await agent(
  `Synthesize a fleet readiness report from these per-repo audits (JSON):\n` +
    JSON.stringify(clean, null, 2) +
    `\n\nRepos that failed to report (their agent() call errored or returned nothing): ` +
    (missing.length ? missing.join(', ') : 'none') +
    `\n\nProduce a short markdown report: a status table (repo · branch · clean · health), ` +
    `then a ranked list of cross-repo actions (block items first). Call out each failed-to-report repo by name. ` +
    `Keep it tight — this is a triage signal, not an essay.`,
  { label: 'synthesize', phase: 'Synthesize' },
)

return { audited: clean.length, of: TARGETS.length, missing, tiers: requested, fleetSize: REPOS.length, report }

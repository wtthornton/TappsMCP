export const meta = {
  name: 'remove-ralph',
  description: 'Remove the Ralph loop from each fleet repo in parallel (branch→delete→settings-surgery→PR), then verify each is clean',
  phases: [
    { title: 'Remove', detail: 'one agent per repo: branch, delete artifacts, clean settings.json, open PR' },
    { title: 'Verify', detail: 'confirm each repo is ralph-free and settings.json parses' },
  ],
}

// Run from the orchestrator session (Ralph's guards are inert there). Repos are
// independent dirs, so no worktree isolation is needed — parallel is safe.
// settingsHooks = expected count of .ralph/hooks/ entries to strip from settings.json.
const REPOS = [
  { name: 'AgentForge',      path: '/home/wtthornton/code/AgentForge',   settingsHooks: 10, extra: ['scripts/ralph-fix-team-injection.sh'] },
  { name: 'NLTlabsPE',       path: '/home/wtthornton/code/NLTlabsPE',    settingsHooks: 8,  extra: [] },
  { name: 'NewCompanyIdeas', path: '/home/wtthornton/NewCompanyIdeas',   settingsHooks: 0,  extra: [] },
  { name: 'ReportLab',       path: '/home/wtthornton/code/ReportLab',    settingsHooks: 0,  extra: [] },
]

const REMOVE_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['repo', 'branch', 'removed', 'settingsValid', 'nonRalphHooksKept', 'prUrl'],
  properties: {
    repo: { type: 'string' },
    branch: { type: 'string' },
    removed: { type: 'array', items: { type: 'string' }, description: 'paths deleted' },
    settingsValid: { type: 'boolean', description: 'python3 -m json.tool exited 0' },
    nonRalphHooksKept: { type: 'array', items: { type: 'string' }, description: 'surviving hook names' },
    prUrl: { type: 'string', description: 'PR URL, or "none (untracked-only)"' },
    notes: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['repo', 'clean', 'remaining'],
  properties: {
    repo: { type: 'string' },
    clean: { type: 'boolean', description: 'no .ralph/.ralphrc/ralph* agents remain AND settings.json parses' },
    remaining: { type: 'array', items: { type: 'string' }, description: 'any ralph artifacts still present' },
  },
}

// Coverage guard: a repo whose stage-1 or stage-2 agent() call fails outright resolves
// falsy and is silently dropped by pipeline()'s Promise.allSettled-style collection —
// `.filter(Boolean)` then `.every()` over the SURVIVORS can be vacuously true even though
// a repo was never cleaned/verified. Compare against REPOS.length so a drop can't pass.
// Pure (no workflow-harness globals) so scripts/test-remove-ralph-summary.js can extract
// and unit-test it in isolation — see check-fleet-sync.js for the same slice-and-eval idiom.
function summarize(results, repoCount) {
  const done = results.filter(Boolean)
  const skipped = repoCount - done.length
  return {
    repos: done,
    skipped,
    allClean: skipped === 0 && done.every((r) => r.verify && r.verify.clean),
    prs: done.map((r) => r.prUrl).filter((u) => u && u !== 'none (untracked-only)'),
  }
}

// Budget guard — refuse to start a parallel mutation sweep without headroom.
if (budget.total && budget.remaining() < 40_000) {
  log(`insufficient budget (${budget.remaining()} left) for parallel removal — aborting`)
  return { aborted: true, reason: 'budget' }
}

phase('Remove')
const results = await pipeline(
  REPOS,
  // Stage 1 — remove + PR (one repo per agent; receives the repo as the item)
  (r) =>
    agent(
      `In ${r.path}: \n` +
        `1. git branch chore/remove-ralph-loop.\n` +
        `2. Delete (if present): .ralphrc, .ralph/, .claude/skills/ralph-workflow/, every .claude/agents/ralph*.md` +
        (r.extra.length ? `, ${r.extra.join(', ')}` : '') + `.\n` +
        `3. In .claude/settings.json remove ONLY hook entries whose command/statusMessage references .ralph/hooks/ ` +
        `(expect ${r.settingsHooks}). Preserve every tapps-*, linear-sdlc-*, observe, and memory hook. ` +
        `Drop any matcher object left with an empty hooks array. Validate: python3 -m json.tool .claude/settings.json >/dev/null (must exit 0).\n` +
        `4. ReportLab special-case: if 'git ls-files .ralph' is empty, just delete locally and set prUrl="none (untracked-only)" — no branch/PR.\n` +
        `5. Otherwise: git add -A; commit 'chore: remove Ralph autonomous loop' with trailer ` +
        `'Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>'; push the branch; gh pr create (do NOT merge).\n` +
        `Return the structured result.`,
      { label: `remove:${r.name}`, phase: 'Remove', schema: REMOVE_SCHEMA },
    ),
  // Stage 2 — verify (no barrier; each repo verifies as soon as its removal lands)
  (res, r) =>
    agent(
      `Verify ${r.path} is Ralph-free: grep for .ralph, .ralphrc, and .claude/agents/ralph* (expect none), ` +
        `and run python3 -m json.tool .claude/settings.json (expect exit 0). Report clean + any remaining artifacts.`,
      { label: `verify:${r.name}`, phase: 'Verify', schema: VERIFY_SCHEMA },
    ).then((v) => ({ ...res, verify: v })),
)

return summarize(results, REPOS.length)

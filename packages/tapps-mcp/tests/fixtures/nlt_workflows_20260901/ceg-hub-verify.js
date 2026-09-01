export const meta = {
  name: 'ceg-hub-verify',
  description: 'CEG hub rebuild: verify every VAL with a fresh-context refuter carrying a negative control (tiered by proof shape), then gate the merge on an opus/xhigh artifact-identity read of the owner-facing pages',
  whenToUse: 'Sub-goal 7 of prompts/ceg-hub-rebuild-owner-showcase.md, after Lane H opens its PR',
  phases: [
    { title: 'Verify', detail: 'one fresh-context verifier per VAL; closed → haiku/low, comparative → sonnet/medium, open → opus/high' },
    { title: 'Gate', detail: 'opus/xhigh artifact identity on each served page — merging publishes to a paying client' },
  ],
}

// args = {
//   repo?: string, worktree?: string,
//   baseline: { tests: number, packFiles: number, routes: number },   // MEASURED in sub-goal 0
//   vals: [{ id, kind: 'closed'|'comparative'|'open', assertion, proofCommand, negativeControl, artifactPath? }],
//   identityPages: string[],
//   context?: string,   // known open findings (e.g. "TAP-6860: …") — verifiers list them as "known:", never re-derive
// }
// `args` must be a real JSON object — prose here yields `undefined` in every prompt.

const REPO = args?.repo ?? '/home/wtthornton/code/CuttingEdgeGraphix'
const WORKTREE = args?.worktree ?? '/tmp/ceg-wt-hub'
const PYTEST = '.venv/bin/pytest'
const baseline = args?.baseline ?? {}
const vals = Array.isArray(args?.vals) ? args.vals : []
const pages = Array.isArray(args?.identityPages) ? args.identityPages : []

// identityOnly: re-run just the Gate phase (e.g. identity round N after the VAL rows already hold on record).
// The caller owns the claim that the VALs are green — say where that evidence lives in args.valsEvidence.
const identityOnly = !!args?.identityOnly
if (identityOnly && !args?.valsEvidence) return { error: 'identityOnly needs args.valsEvidence — name the record the VAL verdicts live in' }
if (!vals.length && !identityOnly) return { error: 'args.vals is empty — pass the VAL rows to verify' }
// Floors gate the Verify phase only. identityOnly skips Verify, so demanding a baseline there would ask the
// caller to paste numbers that gate nothing — an invitation to fabricate a floor to get past a guard.
if (!identityOnly && (!baseline.tests || !baseline.packFiles || !baseline.routes)) {
  return { error: 'args.baseline.{tests,packFiles,routes} missing — floors must be MEASURED in sub-goal 0, never assumed' }
}
if (budget.total && budget.remaining() < 60_000) {
  log(`insufficient budget (${budget.remaining()} left) — aborting`)
  return { aborted: true, reason: 'budget' }
}

const VERDICT = {
  type: 'object',
  required: ['id', 'verdict', 'observed_output', 'negative_control_result', 'green_by_suppression', 'refutation'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'RED'] },
    observed_output: { type: 'string', description: 'verbatim stdout. EMPTY IS A FAIL — the verifier reasoned instead of running.' },
    negative_control_result: { type: 'string', enum: ['FAILED_AS_EXPECTED', 'DID_NOT_FAIL', 'NOT_RUN'] },
    green_by_suppression: { type: 'boolean', description: 'true when the proof went green by deleting what it measures' },
    refutation: { type: 'string' },
    successor_hint: { type: 'string' },
  },
}

const IDENTITY = {
  type: 'object',
  required: ['artifact', 'is_the_thing_asked_for', 'answer_in_words', 'contradictions', 'blocks_merge'],
  properties: {
    artifact: { type: 'string' },
    is_the_thing_asked_for: { type: 'boolean' },
    answer_in_words: { type: 'string', description: 'what the verifier SAW — audience, content, disclosure — not whether a gate passed' },
    contradictions: { type: 'array', items: { type: 'string' }, description: 'counts/prices/statuses that disagree with index.html or heroes.html' },
    blocks_merge: { type: 'boolean' },
  },
}

const TIER = {
  closed: { model: 'haiku', effort: 'low' },
  comparative: { model: 'sonnet', effort: 'medium' },
  open: { model: 'opus', effort: 'high' },
}

phase('Verify')
if (identityOnly) log(`identityOnly: skipping Verify — VAL evidence on record at ${args.valsEvidence}`)
const verdicts = identityOnly ? [] : await parallel(vals.map(v => () =>
  agent(
    `You are an INDEPENDENT verifier. You did NOT write this change. REFUTE the claim; do not confirm it.\n` +
      `Repo worktree: ${WORKTREE} (read-only). Live host: https://cegmerch.nltlabs.ai — every fetch uses ?cb=$RANDOM and reports cf-cache-status; a HIT is not evidence about the origin.\n` +
      `VAL ${v.id}: ${v.assertion}\n` +
      `Run this exact proof command and paste what it printed: ${v.proofCommand}\n` +
      `Then run the NEGATIVE CONTROL and confirm it FAILS: ${v.negativeControl}\n` +
      `A proof that passes on both the real artifact AND the deliberately-broken one proves nothing — report DID_NOT_FAIL and treat the VAL as UNVERIFIED.\n` +
      `Floors (must not shrink): tests >= ${baseline.tests} passed, pack files >= ${baseline.packFiles}, served routes >= ${baseline.routes}.\n` +
      `Env quirks: ${PYTEST} not bare pytest; WebStoreDNA tools run via 'uv run --project /home/wtthornton/code/WebStoreDNA'. Never print a token or credential; probe with grep -c only.\n` +
      `Could this proof have gone green because something was DELETED or a served file was marked assume-unchanged? Set green_by_suppression accordingly.\n` +
      `Default to RED on any doubt. Report gaps; do NOT implement fixes.`,
    { label: `verify:${v.id}`, phase: 'Verify', schema: VERDICT, agentType: 'general-purpose', ...(TIER[v.kind] ?? TIER.open) }
  )
))

const results = verdicts.filter(Boolean)
const dropped = vals.length - results.length
if (dropped) log(`${dropped} verifier(s) returned null — those VALs are unknown, not green`)
const hollow = results.filter(r => !r.observed_output?.trim())
if (hollow.length) log(`${hollow.length} verdict(s) with EMPTY observed_output — forced RED`)
const vacuous = results.filter(r => r.negative_control_result === 'DID_NOT_FAIL')
if (vacuous.length) log(`${vacuous.length} non-discriminating proof(s) — UNVERIFIED`)
const suppressed = results.filter(r => r.green_by_suppression)
if (suppressed.length) log(`${suppressed.length} green-by-suppression flag(s) — treated as RED`)

const green = results.filter(r =>
  r.verdict === 'GREEN' && r.observed_output?.trim() &&
  r.negative_control_result === 'FAILED_AS_EXPECTED' && !r.green_by_suppression)
const allGreen = identityOnly || green.length === vals.length

phase('Gate')
// Consequence overrides proof shape: merging publishes to a paying client's hub.
const identity = allGreen && pages.length
  ? await parallel(pages.map(p => () =>
      agent(
        `Open ${p} in ${WORKTREE} and READ IT as the CEG shop owner would (read-only). Also open docs/client/index.html and docs/client/heroes.html for cross-checks.\n` +
          `A passing gate says the file is well-formed. It does NOT say it is the thing asked for. Answer in words:\n` +
          `- Is the page addressed to the shop owner (not to shoppers, not NLT selling merch)?\n` +
          `- Does it show what the program promised for this page (packet intact / identity + Brass Edge AS A PROPOSAL + 16 merch lines / lookbook on real blanks with disclosure on every render / before-after pairs with honest status chips)?\n` +
          `- Do counts, prices, product statuses and the tagline agree with index.html and heroes.html? List every contradiction.\n` +
          `- Is any Class-C file, held SKU presented as live, dead auth link, or credential visible?\n` +
          (args?.context ? `Known open findings, already filed — still LIST them if you see them, prefixed "known:" so they can be separated from new ones: ${args.context}\n` : '') +
          `If what you see contradicts the program's claims, set blocks_merge true and say why.`,
        { label: `identity:${p.split('/').pop()}`, phase: 'Gate', schema: IDENTITY, agentType: 'general-purpose', model: 'opus', effort: 'xhigh' }
      )
    ))
  : []

const identityResults = identity.filter(Boolean)
const identityBlocks = identityResults.filter(r => r.blocks_merge || !r.is_the_thing_asked_for || (r.contradictions?.length ?? 0) > 0)

return {
  summary: {
    requested: vals.length, verified: results.length, green: green.length,
    red: results.length - green.length, hollow: hollow.length, vacuous: vacuous.length,
    suppressed: suppressed.length, dropped, identityBlocks: identityBlocks.length,
  },
  // Conjunctive on purpose: every VAL green with a discriminating proof, no suppression,
  // every page identified as the thing asked for with zero contradictions.
  merge_authorized: allGreen && identityBlocks.length === 0 && dropped === 0 && identityResults.length === pages.length,
  verdicts: results,
  identity: identityResults,
  spent_tokens: budget.spent(),
}

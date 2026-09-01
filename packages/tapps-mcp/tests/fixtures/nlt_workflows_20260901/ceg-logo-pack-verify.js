export const meta = {
  name: 'ceg-logo-pack-verify',
  description: 'CEG Wave 2: rebuild the logo pack (ico frames, CMYK, clear-space sheet, style-guide colour), verify each VAL with a fresh-context refuter carrying a negative control, then gate the merge on an opus artifact-identity read',
  whenToUse: 'Sub-goals 4-5 of prompts/ceg-handoff-close-and-drift-guard.md, after Wave 1 has merged',
  phases: [
    { title: 'Build', detail: 'one coupled execution lane in an isolated worktree — the pack regenerates as a unit' },
    { title: 'Verify', detail: 'one fresh-context verifier per VAL; closed VALs sonnet/medium, open VALs opus/high' },
    { title: 'Gate', detail: 'opus/xhigh artifact identity — merging publishes to a paying client, so consequence sets the tier' },
  ],
}

// args = {
//   repo?: string,                 // default below
//   worktree?: string,             // isolated tree for the build lane
//   baseline: { tests: number, packFiles: number },   // must-not-shrink floors, MEASURED not assumed
//   vals: [{ id, assertion, proofCommand, negativeControl, kind: 'closed'|'open', artifactPath? }],
//   budget?: number,
// }
// `args` must be a real JSON object — passing prose here yields `undefined` in every
// prompt and well-behaved verifiers correctly return RED for ~0 useful work.

const REPO = args?.repo ?? '/home/wtthornton/code/CuttingEdgeGraphix'
const WORKTREE = args?.worktree ?? '/tmp/ceg-wt-logo'
const PYTEST = '.venv/bin/pytest' // NOT bare `pytest` — the venv is python3.14 and holds cairosvg/PIL
const TRAILER = 'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>'

const baseline = args?.baseline ?? {}
const vals = Array.isArray(args?.vals) ? args.vals : []

if (!vals.length) return { error: 'args.vals is empty — pass the VAL rows this wave must turn green' }
if (!baseline.tests || !baseline.packFiles) {
  return { error: 'args.baseline.{tests,packFiles} missing — the must-not-shrink floors must be MEASURED in sub-goal 0, never assumed from the prompt' }
}
if (budget.total && budget.remaining() < 80_000) {
  log(`insufficient budget (${budget.remaining()} left) for build + ${vals.length} verifiers + gate — aborting`)
  return { aborted: true, reason: 'budget' }
}

const BUILD = {
  type: 'object',
  required: ['branch', 'filesChanged', 'testsPassed', 'testCount', 'packFileCount', 'prUrl', 'handMadeNotRegenerable'],
  properties: {
    branch: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    testsPassed: { type: 'boolean' },
    testCount: { type: 'integer', description: 'passed count from the pytest summary line' },
    packFileCount: { type: 'integer', description: 'find assets/logo-pack -type f | wc -l' },
    prUrl: { type: 'string', description: 'the open PR URL, or "blocked: <reason>"' },
    handMadeNotRegenerable: {
      type: 'array', items: { type: 'string' },
      description: 'files the rebuild script does NOT produce — documented, never silently dropped',
    },
    notes: { type: 'string' },
  },
}

const VERDICT = {
  type: 'object',
  required: ['id', 'verdict', 'observed_output', 'negative_control_result', 'green_by_suppression', 'refutation'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'RED'] },
    observed_output: {
      type: 'string',
      description: 'verbatim stdout the verifier saw. EMPTY IS A FAIL — it means the verifier reasoned instead of running.',
    },
    negative_control_result: { type: 'string', enum: ['FAILED_AS_EXPECTED', 'DID_NOT_FAIL', 'NOT_RUN'] },
    green_by_suppression: {
      type: 'boolean',
      description: 'true when the proof went green by deleting what it measures (test removed, file dropped, assertion weakened)',
    },
    refutation: { type: 'string', description: 'why RED, or the strongest attack that still did not refute GREEN' },
    successor_hint: { type: 'string', description: 'the named next fix if RED; empty if GREEN' },
  },
}

const IDENTITY = {
  type: 'object',
  required: ['artifact', 'is_the_thing_asked_for', 'answer_in_words', 'blocks_merge'],
  properties: {
    artifact: { type: 'string' },
    is_the_thing_asked_for: { type: 'boolean' },
    answer_in_words: { type: 'string', description: 'what the verifier actually SAW, described — not whether a gate passed' },
    blocks_merge: { type: 'boolean' },
  },
}

phase('Build')
const build = await agent(
  `In a git worktree of ${REPO} at ${WORKTREE} (create it; never edit the primary checkout — a sibling session shares that index), close the CEG logo-pack findings as ONE coupled change:\n` +
    `- Multi-frame .ico (16/32/48/128/256). rebuild_logo_pack.py:576 passes the 16px image as the save base, so Pillow silently drops every larger size. Look up Pillow's ICO save / sizes= semantics with tapps_lookup_docs BEFORE writing the fix.\n` +
    `- Author a 16px-specific HINTED mark variant (widened counter, thickened blade). The mark currently fuses into a blob at 16px. If it cannot be made legible without changing the mark's geometry, STOP and report — changing the mark amends ADR-0001 and is not this lane's call.\n` +
    `- Add a CMYK print lane (US Web Coated (SWOP) v2). All 13 EPS currently use setrgbcolor. Look up the conversion path before writing it; a colour transform written from memory lints clean and separates wrong on a press.\n` +
    `- Redraw preview/ceg-clearspace-spec.png so it SHOWS the margin (a dimensioned annotation, not just a caption saying "(shown)"), and state minimums in inches/mm as well as px — this client is a print and embroidery shop.\n` +
    `- Record #A56BE1 in docs/BRAND-STYLE-GUIDE.md as the on-dark violet. ADR-0001 already names it; the guide is the stale artifact, so fix the guide, NOT the SVGs.\n` +
    `- Extend tests/: assert the .ico frame count and a pack inventory. The suite is green today precisely because it asserts geometry and contrast but never existence — that is why the broken .ico shipped.\n` +
    `RULES: no green-by-suppression — never delete a test, drop a file, or weaken an assertion to pass. Root-cause only.\n` +
    `Run ${PYTEST} tests/ -q (NOT bare pytest). Report the passed count and \`find assets/logo-pack -type f | wc -l\`.\n` +
    `Floors that must NOT shrink: tests >= ${baseline.tests}, pack files >= ${baseline.packFiles}.\n` +
    `Commit with trailer '${TRAILER}'. Open a PR with gh pr create. DO NOT MERGE — the merge is gated downstream.`,
  { label: 'build:logo-pack', phase: 'Build', schema: BUILD, agentType: 'general-purpose', model: 'opus', effort: 'high' }
)

if (!build || build.prUrl?.startsWith('blocked')) {
  return { aborted: true, reason: 'build lane blocked', build }
}

const shrank = []
if (build.testCount < baseline.tests) shrank.push(`tests ${build.testCount} < ${baseline.tests}`)
if (build.packFileCount < baseline.packFiles) shrank.push(`pack files ${build.packFileCount} < ${baseline.packFiles}`)
if (shrank.length) {
  log(`MUST-NOT-SHRINK VIOLATED: ${shrank.join(' · ')} — this is green-by-deletion, not progress`)
  return { aborted: true, reason: 'count shrank', shrank, build }
}

phase('Verify')
const verdicts = await parallel(vals.map(v => () =>
  agent(
    `You are an INDEPENDENT verifier. You did NOT write this change. Your job is to REFUTE the claim, not confirm it.\n` +
      `Repo worktree: ${WORKTREE} (read-only — do not edit).\n` +
      `VAL ${v.id}: ${v.assertion}\n` +
      `Run this exact proof command and paste what it actually printed: ${v.proofCommand}\n` +
      `Then run the NEGATIVE CONTROL and confirm it FAILS: ${v.negativeControl}\n` +
      `A proof command that passes on both the real artifact AND the deliberately-broken one proves nothing — report negative_control_result: DID_NOT_FAIL and treat the VAL as UNVERIFIED.\n` +
      `Environment quirks: use ${PYTEST}, not bare pytest. Never print a token or credential; probe with grep -c only.\n` +
      `Also answer: could this proof have gone green because something was DELETED rather than fixed? Set green_by_suppression accordingly.\n` +
      `Default to RED on any doubt. Report gaps; do NOT implement fixes.`,
    {
      label: `verify:${v.id}`,
      phase: 'Verify',
      schema: VERDICT,
      agentType: 'general-purpose',
      model: v.kind === 'open' ? 'opus' : 'sonnet',
      effort: v.kind === 'open' ? 'high' : 'medium',
    }
  )
))

const results = verdicts.filter(Boolean)
const dropped = vals.length - results.length
if (dropped) log(`${dropped} verifier(s) returned null — those VALs are NOT verified, they are unknown`)

// An empty observed_output means the verifier reasoned about plausibility instead of
// running the command — the exact failure an independent pass exists to eliminate.
const hollow = results.filter(r => !r.observed_output || !r.observed_output.trim())
if (hollow.length) log(`${hollow.length} verdict(s) had an EMPTY observed_output — forcing to RED`)

const vacuous = results.filter(r => r.negative_control_result === 'DID_NOT_FAIL')
if (vacuous.length) log(`${vacuous.length} verdict(s) had a non-discriminating proof (negative control did not fail) — UNVERIFIED, not GREEN`)

const suppressed = results.filter(r => r.green_by_suppression)
if (suppressed.length) log(`${suppressed.length} verdict(s) flagged green-by-suppression — treated as RED`)

const green = results.filter(r =>
  r.verdict === 'GREEN' &&
  r.observed_output?.trim() &&
  r.negative_control_result === 'FAILED_AS_EXPECTED' &&
  !r.green_by_suppression
)
const allGreen = green.length === vals.length

phase('Gate')
// Consequence overrides proof shape: merging publishes to a paying client's review site,
// so this is opus/xhigh even though several underlying proofs are one-line exit codes.
const artifacts = vals.filter(v => v.artifactPath)
const identity = allGreen && artifacts.length
  ? await parallel(artifacts.map(v => () =>
      agent(
        `Open ${v.artifactPath} in ${WORKTREE} and LOOK AT IT (read-only). It is an artifact a paying client will see.\n` +
          `Context: ${v.assertion}\n` +
          `A passing gate tells you the file is well-formed. It does NOT tell you the file is the thing that was asked for. ` +
          `Answer in words what you actually see: is the 16px mark legible as a severed C with an open counter? Does the ` +
          `clear-space sheet actually DRAW the margin it describes, with a physical minimum a print shop could use? ` +
          `If what you see contradicts what the change claims, set blocks_merge true and say why.`,
        { label: `identity:${v.id}`, phase: 'Gate', schema: IDENTITY, agentType: 'general-purpose', model: 'opus', effort: 'xhigh' }
      )
    ))
  : []

const identityResults = identity.filter(Boolean)
const identityBlocks = identityResults.filter(r => r.blocks_merge || !r.is_the_thing_asked_for)

return {
  summary: {
    requested: vals.length,
    verified: results.length,
    green: green.length,
    red: results.length - green.length,
    hollow: hollow.length,
    vacuous: vacuous.length,
    suppressed: suppressed.length,
    dropped,
    identityBlocks: identityBlocks.length,
  },
  // The driver merges ONLY on this flag. It is deliberately conjunctive: every VAL green
  // with a discriminating proof, no suppression, and no identity objection.
  merge_authorized: allGreen && identityBlocks.length === 0 && dropped === 0,
  build,
  verdicts: results,
  identity: identityResults,
  spent_tokens: budget.spent(),
}

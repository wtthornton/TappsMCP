export const meta = {
  name: 'tmcp-handoff-verify',
  description: 'Handoff slots + overwrite guard (tapps-mcp): verify every VAL with a fresh-context refuter carrying a negative control (tiered by proof shape), then gate the merge on an opus artifact-identity read of the emitted skill bodies and the rollout runbook',
  whenToUse: 'WAVE 3/4 of prompts/tmcp-handoff-slots-program.md, after SG-6 lands and no write lane is live',
  phases: [
    { title: 'Verify', detail: 'one fresh-context verifier per VAL, each running BOTH controls; deterministic → haiku/low, comparative → sonnet/medium, semantic → opus/high' },
    { title: 'Gate', detail: 'opus artifact identity + the PR\'s own CI by name and state + merge authorization — merging changes the MCP fleet every session in the workspace shares' },
  ],
}

// args = {
//   worktree: string,                                   // the SG-0 worktree, off origin/master
//   pr: string|number,                                  // the PR this gate authorizes — its OWN CI is read by name and state
//   baseline: { tests: number, testIdsPath: string },   // MEASURED on origin/master in sub-goal 0
//   vals: [{ id, kind: 'deterministic'|'comparative'|'semantic', assertion, proofCommand, negativeControl, positiveControl }],
//   identityArtifacts: string[],                        // emitted skill bodies + rollout runbook
// }
// `args` must be a real JSON object — prose here yields `undefined` in every prompt.

const WORKTREE = args?.worktree
const PR = args?.pr
const baseline = args?.baseline ?? {}
const vals = Array.isArray(args?.vals) ? args.vals : []
const artifacts = Array.isArray(args?.identityArtifacts) ? args.identityArtifacts : []

if (!WORKTREE) return { error: 'args.worktree missing — the verifiers must read the lane worktree, not the primary checkout (which is not on master)' }
if (!vals.length) return { error: 'args.vals is empty — pass the VAL rows from the program prompt' }
if (!PR) return { error: 'args.pr missing — VAL-10 gates a merge, and local evidence is coverage complete with respect to the wrong universe. Without the PR number the PR\'s own CI cannot be read by name and state.' }
if (!baseline.tests || !baseline.testIdsPath) {
  return { error: 'args.baseline.{tests,testIdsPath} missing — the floor must be MEASURED on origin/master in sub-goal 0, before any lane wrote. A post-lane baseline measures nothing.' }
}
const uncontrolled = vals.filter(v => !v.negativeControl || !v.positiveControl)
if (uncontrolled.length) {
  return { error: `vals missing a control: ${uncontrolled.map(v => v.id).join(', ')}. Every proof needs BOTH — one that must fail on a broken input and one that must pass on a known-good one. A check that fires on everything is as useless as one that fires on nothing, and a selector matching zero targets prints what a clean result prints.` }
}
if (budget.total && budget.remaining() < 60_000) {
  log(`insufficient budget (${budget.remaining()} left) — aborting`)
  return { aborted: true, reason: 'budget' }
}

const VERDICT = {
  type: 'object',
  required: ['id', 'verdict', 'observed_output', 'measurements', 'negative_control_result', 'positive_control_result', 'green_by_suppression', 'refutation'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'RED'] },
    observed_output: { type: 'string', description: 'verbatim stdout. EMPTY IS A FAIL — it means the verifier reasoned about plausibility instead of running the command.' },
    // Keyed pairs, never two parallel arrays: a files array beside a counts array is where a
    // cheap-tier verifier mis-zipped per-file counts against the wrong files. Every number real,
    // every filename real, the prose perfect, the pairing wrong — and invisible.
    measurements: { type: 'object', additionalProperties: { type: 'number' }, description: 'every number this proof produced, as {file_or_key: count}. One key per measured artifact. Emit {} only if the proof produced no numbers.' },
    negative_control_result: { type: 'string', enum: ['FAILED_AS_EXPECTED', 'DID_NOT_FAIL', 'NOT_RUN'] },
    positive_control_result: { type: 'string', enum: ['PASSED_AS_EXPECTED', 'DID_NOT_PASS', 'NOT_RUN'], description: 'a check that cannot pass is as broken as one that cannot fail — a pathspec or -k selector matching zero targets prints what a clean result prints' },
    green_by_suppression: { type: 'boolean', description: 'true when the proof went green because a test, an assertion, or the measured file was deleted or weakened' },
    refutation: { type: 'string', description: 'the strongest case that this VAL is NOT actually satisfied' },
    successor_hint: { type: 'string' },
  },
}

const IDENTITY = {
  type: 'object',
  required: ['artifact', 'is_the_thing_asked_for', 'answer_in_words', 'contradictions', 'blocks_merge'],
  properties: {
    artifact: { type: 'string' },
    is_the_thing_asked_for: { type: 'boolean' },
    answer_in_words: { type: 'string', description: 'what the verifier SAW when it read the artifact — not whether a gate passed' },
    contradictions: { type: 'array', items: { type: 'string' }, description: 'statements that disagree with the design spec or with each other' },
    blocks_merge: { type: 'boolean' },
  },
}

const TIER = {
  deterministic: { model: 'haiku', effort: 'low' },
  comparative: { model: 'sonnet', effort: 'medium' },
  semantic: { model: 'opus', effort: 'high' },
}

// Environment quirks every verifier needs, or it will run the wrong interpreter against the
// wrong tree and report a confident result about neither.
const ENV = [
  `Worktree (read-only): ${WORKTREE}. The PRIMARY tapps-mcp checkout is on a FEATURE branch, not master — never read it.`,
  `Run python/pytest as: uv run --project ${WORKTREE} pytest ...  — the primary .venv's editable install resolves to the wrong tree inside a worktree.`,
  `The default branch is 'master', not 'main'.`,
  `Re-anchor by symbol or content, never by the line numbers quoted in the spec — they drift with any intervening merge. If an anchor does not resolve, that is a RED, not a rounding error.`,
  `Before trusting any "tree is clean" claim: git ls-files -v | grep '^[a-z]'  (assume-unchanged files diverge from HEAD while status reports clean).`,
  `Never echo an env var value; probe existence with grep -c only.`,
].join('\n')

phase('Verify')
const verdicts = await parallel(vals.map(v => () =>
  agent(
    `You are an INDEPENDENT verifier. You did NOT write this change. Your job is to REFUTE the claim, not confirm it.\n\n` +
      `${ENV}\n\n` +
      `VAL ${v.id}: ${v.assertion}\n` +
      `Run this exact proof command and paste verbatim what it printed:\n  ${v.proofCommand}\n` +
      `Then run the NEGATIVE CONTROL and confirm it FAILS:\n  ${v.negativeControl}\n` +
      `A proof that passes on both the real artifact AND the deliberately-broken one proves nothing — report DID_NOT_FAIL and treat the VAL as UNVERIFIED.\n` +
      `Then run the POSITIVE CONTROL and confirm it PASSES:\n  ${v.positiveControl}\n` +
      `A proof that fires on nothing is as useless as one that fires on everything — a grep, pathspec, or -k selector that silently matches ZERO targets prints exactly what a clean result prints. If the positive control does not pass, report DID_NOT_PASS and treat the VAL as UNVERIFIED regardless of what the main proof printed.\n\n` +
      `Report EVERY number this proof produced in 'measurements' as a keyed {file_or_key: count} object — the count beside its own filename. Do NOT return a list of files alongside a list of counts; that pairing desynchronizes silently and reads perfectly when it is wrong.\n\n` +
      `Floor that must not shrink: >= ${baseline.tests} tests collected, and every test id in ${baseline.testIdsPath} still present (renames only count if the change declares them old -> new).\n` +
      `Ask explicitly: could this have gone green because a test was deleted, skipped, xfailed, an assertion weakened, a linter silenced with # noqa or # type: ignore, or the measured file removed? Set green_by_suppression accordingly — an honestly-passing proof can still be suppression.\n\n` +
      `Default to RED on any doubt. Report gaps; do NOT implement fixes.`,
    { label: `verify:${v.id}`, phase: 'Verify', schema: VERDICT, agentType: 'general-purpose', ...(TIER[v.kind] ?? TIER.semantic) }
  )
))

const results = verdicts.filter(Boolean)
const dropped = vals.length - results.length
if (dropped) log(`${dropped} verifier(s) returned null — those VALs are UNKNOWN, not green`)
const hollow = results.filter(r => !r.observed_output?.trim())
if (hollow.length) log(`${hollow.length} verdict(s) with EMPTY observed_output — forced RED`)
const vacuous = results.filter(r => r.negative_control_result === 'DID_NOT_FAIL')
if (vacuous.length) log(`${vacuous.length} non-discriminating proof(s) — UNVERIFIED`)
const inert = results.filter(r => r.positive_control_result !== 'PASSED_AS_EXPECTED')
if (inert.length) log(`${inert.length} proof(s) whose positive control did not pass — the instrument may fire on nothing — UNVERIFIED`)
const suppressed = results.filter(r => r.green_by_suppression)
if (suppressed.length) log(`${suppressed.length} green-by-suppression flag(s) — treated as RED`)

const green = results.filter(r =>
  r.verdict === 'GREEN' && r.observed_output?.trim() &&
  r.negative_control_result === 'FAILED_AS_EXPECTED' &&
  r.positive_control_result === 'PASSED_AS_EXPECTED' && !r.green_by_suppression)
const allGreen = green.length === vals.length

phase('Gate')
// Consequence overrides proof shape: this merge changes the six-server MCP fleet that every
// session in the workspace shares, and the skill bodies are upgrade-policy overwrite — a wrong
// edit location looks shipped and is silently erased on the next tapps_upgrade.
const identity = allGreen && artifacts.length
  ? await parallel(artifacts.map(a => () =>
      agent(
        `Open ${a} in ${WORKTREE} and READ IT as its actual audience would (read-only). Cross-check against the design spec the program was built from.\n\n` +
          `${ENV}\n\n` +
          `A passing gate says the file is well-formed. It does NOT say it is the thing that was asked for. Answer in words:\n` +
          `- For an emitted skill body: does the text it produces describe the tool/CLI surface that ACTUALLY exists after this change (slot / owner / force params, 'handoff list'), and does it instruct the reader to LIST slots and ASK when more than one fresh handoff exists — never to silently pick one?\n` +
          `- Does it still contain any claim that --file selects the write destination? That was the misleading row this change exists to fix.\n` +
          `- For the rollout runbook: is the rollback target DERIVED LIVE from the running unit, or is it a recorded sha copied from somewhere? A recorded sha is a blocking defect.\n` +
          `- Does every statement agree with the others and with the spec? List every contradiction.\n` +
          `- Is any edit sitting under a consumer repo's .claude/skills/ path instead of upstream in pipeline/platform_skills.py? That is a blocking defect: it looks shipped and is erased by the next tapps_upgrade.\n\n` +
          `If what you see contradicts the program's claims, set blocks_merge true and say why.`,
        { label: `identity:${a.split('/').pop()}`, phase: 'Gate', schema: IDENTITY, agentType: 'general-purpose', model: 'opus', effort: 'high' }
      )
    ))
  : []

// VAL-10's only view of the universe outside this worktree. Three consecutive fresh-context opus
// verifiers have returned PASS on exhaustive LOCAL evidence while CI sat independently red —
// coverage complete with respect to the wrong universe.
const CI = {
  type: 'object',
  required: ['checks', 'all_passing', 'blocks_merge', 'raw_output'],
  properties: {
    raw_output: { type: 'string', description: 'verbatim `gh pr checks` stdout. EMPTY IS A FAIL.' },
    checks: {
      type: 'array',
      description: 'one entry per check, BY NAME AND STATE. An empty array blocks the merge.',
      items: {
        type: 'object',
        required: ['name', 'state'],
        properties: { name: { type: 'string' }, state: { type: 'string' } },
      },
    },
    all_passing: { type: 'boolean' },
    blocks_merge: { type: 'boolean' },
  },
}

const ci = allGreen
  ? await agent(
      `Read the CI state of PR ${PR} and report it, read-only. Do NOT merge, approve, or re-run anything.\n\n` +
        `${ENV}\n\n` +
        `Run exactly:  gh pr checks ${PR}\n` +
        `Paste its stdout VERBATIM into raw_output, and list EVERY check BY NAME AND STATE in 'checks'.\n\n` +
        `Rules, all blocking:\n` +
        `- ANY check in a non-pass state (failure, cancelled, timed_out, action_required, pending, skipped-when-required) => all_passing false, blocks_merge true.\n` +
        `- ZERO checks reported is blocks_merge TRUE, never a pass. It means no CI is wired to this PR, which is the one condition local evidence can never distinguish from green. Do not read an empty list or a non-zero exit as "nothing to report".\n` +
        `- If gh errors or the PR does not resolve, that is blocks_merge true with the error in raw_output — an error string must never read as a clean result.\n` +
        `- For any check that has a job command, re-run THAT command as read out of .github/workflows/ in ${WORKTREE}, never a local approximation, and report the disagreement if it differs.`,
      { label: `gate:ci-pr-${PR}`, phase: 'Gate', schema: CI, agentType: 'general-purpose', model: 'opus', effort: 'high' }
    )
  : null

const ciBlocks = !ci || ci.blocks_merge || !ci.all_passing || !(ci.checks?.length > 0) || !ci.raw_output?.trim()
if (allGreen && ciBlocks) log(`CI gate blocks the merge (checks reported: ${ci?.checks?.length ?? 'none — verifier returned null'})`)

const identityResults = identity.filter(Boolean)
const identityBlocks = identityResults.filter(r => r.blocks_merge || !r.is_the_thing_asked_for || (r.contradictions?.length ?? 0) > 0)

return {
  summary: {
    requested: vals.length, verified: results.length, green: green.length,
    red: results.length - green.length, hollow: hollow.length, vacuous: vacuous.length,
    inert: inert.length, suppressed: suppressed.length, dropped,
    identityBlocks: identityBlocks.length, ciChecks: ci?.checks?.length ?? 0, ciBlocks,
  },
  // Conjunctive on purpose: every VAL green with a proof that discriminates in BOTH directions,
  // no suppression, no dropped verifier, every human-read artifact identified as the thing that
  // was asked for, and the PR's own CI green with at least one check actually reported.
  merge_authorized: allGreen && !ciBlocks && identityBlocks.length === 0 && dropped === 0 && identityResults.length === artifacts.length,
  verdicts: results,
  identity: identityResults,
  ci,
  spent_tokens: budget.spent(),
}

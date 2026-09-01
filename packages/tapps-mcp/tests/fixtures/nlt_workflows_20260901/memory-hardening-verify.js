export const meta = {
  name: 'memory-hardening-verify',
  description: 'Independent, per-VAL adversarial verification for the memory-hardening program (creator ≠ verifier; closed VALs on sonnet/medium, open VALs on opus/high)',
  whenToUse: 'After a lane PR merges or a Wave-3 data pass applies; pass the VAL rows it claims as args.vals',
  phases: [
    { title: 'Verify', detail: 'one fresh-context verifier per VAL, refuting the proof with the negative control' },
    { title: 'Identity', detail: 'human-facing artifacts opened and described in words' },
  ],
}

// args = { vals: [{ id, assertion, proofCommands: [..], expectedArtifact, anchors: [..],
//                   paths: ['authoring','runtime'], negativeControl, kind: 'closed'|'open',
//                   artifactPath?: string }] , budget?: number }
// Closed VALs (line counts, wire keys, exit codes) → sonnet/medium. Open VALs
// (behavioral, "did the loop actually close") → opus/high. Never let a closed-tier
// verdict gate an ACCEPT relay — the driver re-derives from observed_output.

const VERDICT = {
  type: 'object',
  required: ['id', 'verdict', 'observed_output', 'negative_control_result', 'refutation', 'paths_checked'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['GREEN', 'RED'] },
    observed_output: { type: 'string', description: 'verbatim stdout/psql/curl output the verifier saw for the proof command' },
    negative_control_result: { type: 'string', enum: ['FAILED_AS_EXPECTED', 'DID_NOT_FAIL', 'NOT_RUN'] },
    refutation: { type: 'string', description: 'why RED, or the strongest attack that still did not refute GREEN' },
    paths_checked: { type: 'array', items: { type: 'string', enum: ['authoring', 'runtime', 'fixture', 'repo'] } },
    successor_hint: { type: 'string', description: 'named specific next fix if RED; empty if GREEN' },
  },
}

const IDENTITY = {
  type: 'object',
  required: ['artifact', 'is_the_thing_asked_for', 'accounting_balances', 'answer_in_words'],
  properties: {
    artifact: { type: 'string' },
    is_the_thing_asked_for: { type: 'boolean' },
    accounting_balances: { type: 'boolean', description: 'rows_before == rows_after + archived + moved' },
    answer_in_words: { type: 'string' },
  },
}

const vals = Array.isArray(args?.vals) ? args.vals : []
if (!vals.length) return { error: 'args.vals is empty — pass the VAL rows the merged PR or pass claims' }

const HERMETIC = [
  'HERMETIC RULES (SC-13): run any probe that can resolve project settings under a tmp project root',
  '(cwd=tmp + explicit project_root). Dry-run first where the tool offers it. Hash .tapps-mcp/ and the',
  'live metrics dir before and after; report any change. Never write to the live brain: reads only,',
  'or fixture DB only. Redact any token-like string from quoted output.',
  '',
  'A FIXTURE DATABASE IS NOT ISOLATION — NEVER CREATE ONE ON THE LIVE CLUSTER. Do NOT run',
  'CREATE DATABASE against tapps-brain-db (or any live Postgres) and do NOT apply schema/migrations',
  'there. Postgres ROLES, and their passwords, are CLUSTER-GLOBAL: tapps-brain\'s migration path',
  '(docker/migrate-entrypoint.sh steps 3-4) does ALTER ROLE tapps_runtime WITH LOGIN PASSWORD',
  '<value from its own env>, so applying migrations for a throwaway database silently rotates the',
  'LIVE brain credential and takes brain writes down cluster-wide. This is not hypothetical: it',
  'caused an 18-minute write outage on 2026-08-28 (12:44:41Z-13:03Z, 71 PoolTimeout /',
  '"password authentication failed for user tapps_runtime" lines), and dropping the fixture database',
  'afterwards does NOT undo it, because the role outlives the database.',
  'If you need a real Postgres for behavioural proof, start a SEPARATE throwaway container on its own',
  'cluster (e.g. `docker run --rm -d -e POSTGRES_PASSWORD=... -p 0:5432 pgvector/pgvector:pg16` or the',
  'image the repo pins), point the tool at THAT DSN, and remove the container when done. Prefer',
  'sqlite/in-process fixtures or the repo\'s own test harness where they can carry the proof.',
  'If you cannot get an isolated cluster, report the VAL as BLOCKED and say so — never fall back to',
  'the live one. Read-only SELECTs against the live database remain fine and are encouraged.',
  '',
  'NO DDL AND NO ROLE STATEMENTS AGAINST A LIVE CLUSTER, EVER — not CREATE/ALTER/DROP ROLE, not',
  'CREATE/DROP DATABASE, not GRANT, not a migration, not "just for a moment". The 2026-08-28 outage',
  'was not a subtle migration side effect: a verifier ran, verbatim,',
  'ALTER ROLE tapps_runtime WITH PASSWORD \'fixturepw\' against tapps-brain-db while setting up a',
  'fixture. It then noticed ("ALTER ROLE changed a live credential. Restoring it now.") and attempted',
  'a restore from a saved file — and the restore did not reinstate a working value, so writes stayed',
  'down for 18 minutes anyway. Take the lesson: intending to put it back is NOT a mitigation, because',
  'you cannot verify the restore against a credential you never knew. Set up fixtures on a container',
  'you started and will delete, where a wrong password harms nothing.',
].join(' ')

function verifyPrompt(v) {
  return [
    `You are an independent verifier for validation assertion ${v.id}. You did NOT produce the change.`,
    `Your job is to REFUTE the claim that it holds. Default to RED on any doubt. Grade the ARTIFACT, not the run.`,
    ``,
    `ASSERTION: ${v.assertion}`,
    `PROOF COMMANDS (run these exactly; quote the output verbatim):`,
    ...(v.proofCommands || []).map((c, i) => `  ${i + 1}. ${c}`),
    `EXPECTED ARTIFACT: ${v.expectedArtifact}`,
    `FILE:LINE ANCHORS: ${(v.anchors || []).join(' · ') || 'none given — say so'}`,
    `BRAIN PATHS TO CHECK: ${(v.paths || ['authoring']).join(', ')} — authoring = localhost:8080; runtime = docker exec agentforge-api curl http://tapps-brain-http:8080. Auth: AF_BRAIN_AUTH_TOKEN from the agentforge-api container env. A brain VAL is GREEN only if BOTH paths agree.`,
    `NEGATIVE CONTROL (must FAIL, or the check is vacuous): ${v.negativeControl || 'none supplied — mark NOT_RUN and say the check may be vacuous'}`,
    ``,
    HERMETIC,
    ``,
    `Techniques you must attempt where applicable: run the proof on the pre-change tree (detached worktree of the base SHA) to prove it fails there;`,
    `if the assertion is "X ran", read audit_log not status columns; if a grep proves absence, first run it against a commit known to contain the symbol;`,
    `if a count is asserted, run with no LIMIT/maxfail truncation; if a wire field is asserted, print the raw key not a defaulted read.`,
    `Return ONLY the structured verdict.`,
  ].join('\n')
}

phase('Verify')
const verdicts = await parallel(vals.map(v => () =>
  agent(verifyPrompt(v), {
    label: `verify:${v.id}`,
    phase: 'Verify',
    schema: VERDICT,
    agentType: 'general-purpose',
    model: v.kind === 'open' ? 'opus' : 'sonnet',
    effort: v.kind === 'open' ? 'high' : 'medium',
  })
))

const results = verdicts.filter(Boolean)
const dropped = vals.length - results.length
if (dropped) log(`${dropped} verifier(s) returned null (skipped or terminal error) — those VALs are NOT verified`)

phase('Identity')
const artifacts = vals.filter(v => v.artifactPath)
const identity = artifacts.length
  ? await parallel(artifacts.map(v => () =>
      agent(
        `Open ${v.artifactPath} (read-only). It is a human-facing artifact for ${v.id}: ${v.assertion}. ` +
        `Answer in words: is this the set of rows/changes the operator expects? Does the accounting balance ` +
        `(rows_before == rows_after + archived + moved)? Quote the numbers you used. Do not edit anything.`,
        { label: `identity:${v.id}`, phase: 'Identity', schema: IDENTITY, agentType: 'Explore', model: 'sonnet', effort: 'medium' }
      )
    ))
  : []

const green = results.filter(r => r.verdict === 'GREEN' && r.negative_control_result !== 'DID_NOT_FAIL')
const vacuous = results.filter(r => r.verdict === 'GREEN' && r.negative_control_result === 'DID_NOT_FAIL')
if (vacuous.length) log(`${vacuous.length} GREEN verdict(s) had a negative control that did not fail — treat as UNVERIFIED, not GREEN`)

return {
  summary: { requested: vals.length, verified: results.length, green: green.length, red: results.filter(r => r.verdict === 'RED').length, vacuous: vacuous.length, dropped },
  verdicts: results,
  identity: identity.filter(Boolean),
  spent_tokens: budget.spent(),
}

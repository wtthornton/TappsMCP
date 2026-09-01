export const meta = {
  name: 'licensed-oracle-sweeps',
  description: 'Read-only sweeps for the two systemic shapes the licensed-oracle program exposed: contract restatement, and failure values hidden inside a valid output_schema enum',
  whenToUse: 'SG-6 of prompts/licensed-oracle-aftermath-program.md. Read-only — files nothing itself; returns findings for the driver to file via the linear-issue skill.',
  phases: [
    { title: 'Sweep', detail: 'one Explore agent per surface, both shapes in parallel' },
    { title: 'Refute', detail: 'adversarial verify of each candidate finding' },
    { title: 'Synthesize', detail: 'dedupe and rank what survived' },
  ],
}

// Every agent here is read-only: agentType Explore cannot write, so the tool boundary
// enforces it rather than the prose. Nothing in this workflow files a Linear issue --
// a dispatched agent cannot reach the Linear plugin anyway, and the driver owns writes.

const FINDING_SCHEMA = {
  type: 'object',
  required: ['surface', 'findings'],
  properties: {
    surface: { type: 'string' },
    searched: { type: 'string', description: 'what was actually searched -- paths, globs, greps. Required so "none found" is auditable.' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['shape', 'file', 'claim', 'evidence'],
        properties: {
          shape: { enum: ['restatement', 'silent-valid-enum', 'fallback-only-golden-case'] },
          file: { type: 'string', description: 'repo-relative path, with :LINE when known' },
          claim: { type: 'string', description: 'one sentence: what is restated or what failure value is legal' },
          authority: { type: 'string', description: 'the component that actually DECIDES this, i.e. what should be derived from' },
          evidence: { type: 'string', description: 'literal quoted text from the file -- not a summary' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['real', 'observed_output', 'reasoning'],
  properties: {
    real: { type: 'boolean', description: 'false = refuted. Default false when uncertain.' },
    observed_output: { type: 'string', description: 'the literal text read from the file. EMPTY IS A FAIL -- it means you reasoned instead of reading.' },
    reasoning: { type: 'string' },
    already_derived: { type: 'boolean', description: 'true when the artifact actually derives or checks the value, so the finding is wrong' },
  },
}

// Restatement surfaces: an artifact that RESTATES a sibling's contract instead of deriving
// it or adding a cheap sync-check. The licensed-oracle genes were this shape and it cost a
// ~70% request-malformation rate.
const RESTATEMENT_SURFACES = [
  { key: 'reportlab-briefs', prompt: 'In /home/wtthornton/code/ReportLab, find every brief or volume doc that states a fact about a SIBLING repo (tool counts, integration lists, API shapes, capability claims) as hand-authored prose rather than deriving it at build time or guarding it with a sync-check. For each, name the component that actually decides that fact. Quote the literal restated sentence.' },
  { key: 'render-yaml', prompt: 'Across the fleet (see /home/wtthornton/code/nlt-orchestrator/fleet.paths.json for paths), find every render.yaml or deploy manifest whose declared services/env restate what the live Render or compose services actually are, with no check that fails when they diverge. Quote the declaration.' },
  { key: 'claude-scaffolding', prompt: 'Compare the per-repo .claude/ scaffolding copies (rules, skills, hooks) across 3-4 fleet repos. Find content duplicated verbatim across repos with no generator and no drift-check, where divergence would be silent. Quote one duplicated block and name the repos.' },
  { key: 'af-library-genes', prompt: 'In /home/wtthornton/code/AgentForge/library, find every gene whose prose RESTATES a consumer API request or response shape (a JSON body, a field list, an endpoint contract) instead of referencing a schema. Literal "..." ellipses in an example payload are the strongest tell. Quote the prose.' },
]

// Silent-valid-enum surfaces: an output_schema that admits a value MEANING failure, so a
// failed call yields a schema-valid object and every gate passes. Plus genes whose only
// golden_case exercises the FALLBACK rather than a successful call.
const ENUM_SURFACES = [
  { key: 'af-library-schemas', prompt: 'In /home/wtthornton/code/AgentForge/library, read every agent/gene output_schema. Find each one whose enum admits a value that MEANS the operation failed or returned nothing (blocked, unavailable, error, insufficient_input, unknown, skipped). For each, state whether anything downstream distinguishes it from success. Quote the enum.' },
  { key: 'af-library-goldens', prompt: 'In /home/wtthornton/code/AgentForge/library, find every gene whose golden_cases contain ONLY cases that exercise a fallback/degraded path (empty input, missing gateway, no credentials) and none that exercise a successful call. Quote the golden_cases block and the gene name.' },
  { key: 'consumer-workflows', prompt: 'In /home/wtthornton/code/nlt-ideas-scout and /home/wtthornton/code/AgentForge, read every published workflow YAML under agentforge/projects/*/workflows/ and library/*/workflows/. Find nodes whose output_schema admits a failure-meaning value, where the workflow has no telemetry or gate distinguishing it from success. Quote the node.' },
]

phase('Sweep')
log(`sweeping ${RESTATEMENT_SURFACES.length} restatement surfaces + ${ENUM_SURFACES.length} enum surfaces`)

const ALL = [
  ...RESTATEMENT_SURFACES.map((s) => ({ ...s, kind: 'restatement' })),
  ...ENUM_SURFACES.map((s) => ({ ...s, kind: 'enum' })),
]

// pipeline, not parallel: each surface's findings go straight into refutation as soon as
// that surface returns. No barrier -- surface A can be in Refute while surface B still reads.
const swept = await pipeline(
  ALL,
  (s) =>
    agent(
      `${s.prompt}\n\nRead-only. Report ONLY what you can quote literally from a file. If you find nothing, say so and record exactly what you searched -- an unaudited "none found" is worthless. Do not file anything anywhere.`,
      { label: `sweep:${s.key}`, phase: 'Sweep', schema: FINDING_SCHEMA, model: 'haiku', effort: 'low' },
    ),
  (result, original) => {
    if (!result || !result.findings || result.findings.length === 0) {
      return { surface: original.key, kind: original.kind, searched: result?.searched || 'unreported', verified: [] }
    }
    return parallel(
      result.findings.map((f) => () =>
        agent(
          `Adversarially REFUTE this claimed finding. Open the file yourself and read it.\n\n` +
            `File: ${f.file}\nShape: ${f.shape}\nClaim: ${f.claim}\nClaimed evidence: ${f.evidence}\n\n` +
            `Refute it if: the artifact actually derives or checks the value rather than restating it; ` +
            `a sync-check or generator already exists; the quoted evidence does not say what the claim says it says ` +
            `(a citation is a pointer, not an argument -- state in one sentence what the cited text actually proves, ` +
            `and if that sentence is not the claim, the finding is refuted); or the file does not contain the quoted text at all.\n\n` +
            `Default to real=false when uncertain. observed_output must be the literal text you read.`,
          { label: `refute:${f.file}`, phase: 'Refute', schema: VERDICT_SCHEMA, model: 'sonnet', effort: 'medium' },
        ).then((v) => ({ finding: f, verdict: v })),
      ),
    ).then((verdicts) => ({
      surface: original.key,
      kind: original.kind,
      searched: result.searched || 'unreported',
      verified: verdicts.filter(Boolean),
    }))
  },
)

const rows = swept.filter(Boolean)
const confirmed = rows.flatMap((r) =>
  (r.verified || [])
    .filter((v) => v.verdict && v.verdict.real === true && (v.verdict.observed_output || '').trim() !== '')
    .map((v) => ({ ...v.finding, surface: r.surface, kind: r.kind, observed_output: v.verdict.observed_output })),
)

// An empty observed_output is a FAIL per the guardrail: it means the verifier reasoned
// about plausibility instead of opening the file. Those are dropped above, and counted here
// so a silent drop cannot masquerade as "nothing found".
const droppedForNoEvidence = rows.flatMap((r) =>
  (r.verified || []).filter((v) => v.verdict && v.verdict.real === true && (v.verdict.observed_output || '').trim() === ''),
).length

log(`confirmed ${confirmed.length}; dropped ${droppedForNoEvidence} for empty observed_output`)

phase('Synthesize')
const synthesis = await agent(
  `Here are adversarially-confirmed findings from two fleet sweeps.\n\n` +
    `RESTATEMENT = an artifact restating a sibling's contract instead of deriving it or guarding it with a check.\n` +
    `SILENT-VALID-ENUM = an output_schema admitting a value that means failure, so a failed call is schema-valid and every gate passes.\n\n` +
    `${JSON.stringify(confirmed, null, 1)}\n\n` +
    `Dedupe (the same file may appear under both shapes). Rank by blast radius: how many consumers ` +
    `would silently get a wrong answer, and whether anything downstream would ever notice. ` +
    `For each, propose the CHEAPEST check that would make the divergence fail loudly -- follow ` +
    `nlt-orchestrator's scripts/check-fleet-sync.js as the house pattern: it does not prevent ` +
    `duplication, it makes duplication fail. Prefer one check covering several findings over one per finding. ` +
    `Return a ranked list ready to become Linear issues; do not write anything.`,
  { label: 'synthesize', phase: 'Synthesize', model: 'opus', effort: 'high' },
)

return {
  confirmed_count: confirmed.length,
  dropped_for_no_evidence: droppedForNoEvidence,
  surfaces_with_nothing: rows.filter((r) => (r.verified || []).length === 0).map((r) => ({ surface: r.surface, searched: r.searched })),
  confirmed,
  synthesis,
}

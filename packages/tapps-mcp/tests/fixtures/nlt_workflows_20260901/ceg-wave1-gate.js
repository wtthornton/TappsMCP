export const meta = {
  name: 'ceg-wave1-gate',
  description: 'GATE 1 of the CEG close-out (TAP-6820): build an integration tree of both Wave-1 PRs, run cross-file consistency checks, then an opus/xhigh artifact-identity read — is this what we would send a paying client. Returns merge_authorized.',
  whenToUse: 'After both Wave-1 lanes have open PRs and their per-lane deterministic verifiers passed',
  phases: [
    { title: 'Integrate', detail: 'scratch worktree at origin/main + merge both PR branches; cross-file greps; build the owner zip' },
    { title: 'Identity', detail: 'opus/xhigh: open the artifacts and answer in words — consequence sets the tier, the merge publishes to a paying client' },
  ],
}

// args = { branchA: string, branchB: string, budget?: number }
const REPO = '/home/wtthornton/code/CuttingEdgeGraphix'
const SCRATCH = '/tmp/ceg-wave1-integration'
const branchA = args?.branchA ?? 'lane/ceg-packet-blockers'
const branchB = args?.branchB ?? 'lane/ceg-site-tagline-crop'

const INTEGRATE = {
  type: 'object',
  required: ['merged_clean', 'zip_built', 'link_walk_unresolved', 'cross_file_counts_consistent', 'observed_output'],
  properties: {
    merged_clean: { type: 'boolean', description: 'both branches merged onto origin/main with zero conflicts' },
    zip_built: { type: 'boolean' },
    zip_bytes: { type: 'integer' },
    link_walk_unresolved: { type: 'integer', description: 'relative hrefs/srcs in the packed index.html+heroes.html that do not resolve inside the zip tree' },
    cross_file_counts_consistent: { type: 'boolean', description: 'no product-count claim anywhere in docs/client/ contradicts the 3-product roster' },
    operator_paths: { type: 'integer', description: 'grep -rEc "(/home/[a-z]+|~/)" docs/client/ on the integrated tree' },
    observed_output: { type: 'string', description: 'the literal command outputs, labeled — empty is a FAIL' },
    notes: { type: 'string' },
  },
}

const IDENTITY = {
  type: 'object',
  required: ['is_the_thing_asked_for', 'answer_in_words', 'blocks_merge'],
  properties: {
    is_the_thing_asked_for: { type: 'boolean' },
    answer_in_words: { type: 'string', description: 'what was actually seen in each artifact, described concretely' },
    blocks_merge: { type: 'boolean' },
    objections: { type: 'array', items: { type: 'string' } },
  },
}

phase('Integrate')
const integ = await agent(
  `Build a Wave-1 integration tree and prove its consistency. Commands, not judgement.\n` +
    `1. rm -rf ${SCRATCH}; git -C ${REPO} worktree remove --force ${SCRATCH} 2>/dev/null; git -C ${REPO} fetch origin; ` +
    `git -C ${REPO} worktree add ${SCRATCH} origin/main --detach\n` +
    `2. cd ${SCRATCH} && git merge --no-ff ${branchA} -m integ-A && git merge --no-ff ${branchB} -m integ-B — report merged_clean=false on ANY conflict and stop.\n` +
    `3. Build the owner zip with the tree's own script: bash scripts/pack-client-review.sh (read the script first to find its output location; run it from ${SCRATCH}).\n` +
    `4. Link-walk: extract every relative href/src from the packed index.html and heroes.html and stat each inside the zip tree; count unresolved.\n` +
    `5. Cross-file counts: grep -rniE '(three|four|five|six|[0-9]+) products' docs/client/*.md docs/client/*.html — paste all hits; consistent means every hit agrees with the 3-product roster (koozie, tee, cap).\n` +
    `6. Operator paths: grep -rEc '(/home/[a-z]+|~/)' docs/client/ ; true\n` +
    `7. Cornhole: grep -rci cornhole docs/operator/REVIEW-MESSAGE.md ; true (expect 0)\n` +
    `NEVER print any line containing _auth= — counts only. Paste every command's literal output into observed_output. Leave ${SCRATCH} in place for the next stage.`,
  { label: 'integrate', phase: 'Integrate', schema: INTEGRATE, agentType: 'general-purpose', model: 'sonnet', effort: 'medium' }
)

if (!integ || !integ.merged_clean || !integ.observed_output?.trim()) {
  return { merge_authorized: false, reason: 'integration failed or unproven', integ }
}
if (integ.link_walk_unresolved > 0 || !integ.cross_file_counts_consistent || integ.operator_paths > 0) {
  return { merge_authorized: false, reason: 'integrated tree fails a deterministic floor', integ }
}

phase('Identity')
// Consequence overrides shape: this verdict gates a publish to a paying client's site.
const identity = await agent(
  `You are the final gate before a merge that PUBLISHES to a paying client's review site (cegmerch.nltlabs.ai). ` +
    `Open the integrated tree at ${SCRATCH} (read-only) and judge the ARTIFACTS, not the diffs:\n` +
    `1. Read docs/client/index.html end to end as the shop owner would (a non-technical print-shop owner in Mountain Home, Idaho). ` +
    `Is the tagline presented as decided ("Put your name on it.")? Does the store section read honestly (three products, services alongside)? ` +
    `Does anything contradict anything else on the page?\n` +
    `2. Read docs/operator/REVIEW-PACKET.md and docs/operator/OWNER-SITTING.md the same way (they moved out of docs/client on purpose — confirm nothing under docs/client links to them): is the 12-hour expiry on the recommended option, ` +
    `is the posting-agreement question present and clear, is the next-SKU recommendation visibly conditional on it, do the dates read current?\n` +
    `3. List the built zip's contents (the Integrate stage built it): would the owner following the packet's instructions hit anything missing?\n` +
    `4. Read docs/client/before-after.html as the owner. Count the cards (expect 46) and state the live / held / concept / render-pending breakdown per section. ` +
    `Are the three held cornhole designs presented for his COMMENT (not as rejects, not as relist-scheduled, the word "withdrawn" absent)? Is the Elk & Mountain board the first cornhole card and shown as a fresh restyle of his own board? ` +
    `Do signs/banners sit under "drawn from scratch" with the phone number 208-599-0540 visible in the renders (open two at 100%)? Does the "Shop swag" group read as concepts for him to pick, not a catalogue? ` +
    `Does every card end with what we want from him? Are renders disclosed as renders and befores as his photos/artwork? Is any render-pending card honest about WHY (magnet, stacked-block tee, idaho plate, flag-wedding)? Spot-check eight image paths resolve; ` +
    `then check docs/client/assets/after and docs/client/assets/renders-swag contain NO file whose sidecar/manifest verdict is redo/failed (served-but-unlinked is still published).\n` +
    `5. The plan PDF (expect v1.6 in its text via pdftotext): confirm it records the approved tagline, the one-cornhole-story, dates that read current (1 Sep 2026), ` +
    `and no claim of three live cornhole sets with "a real photo of your work". Confirm the packet's cited hash matches the shipped file.\n` +
    `6. Prices: does the page say plainly which prices are the owner's (koozie $9, PRD) and which are our proposals pending his confirmation (tee $28, cap $32), and is there a question asking him to confirm them?\n` +
    `6b. If docs/client/brand.html exists: read it as the owner. Does the colour ladder show 1-, 2- and 3-colour lockups on light AND dark (six images)? ` +
    `Is the 2-colour lockup stated plainly as the identity that stays, and Brass Edge presented as a PROPOSAL needing his yes — never as adopted? ` +
    `Are the reasons in shop-floor voice with the registration (1.17 mm) and per-process cost numbers present? Do the 16 merch lines read as concepts for him to pick, with a working pick mechanic? ` +
    `Is anything addressed to shoppers or phrased as NLT selling merch (it must not be)?\n` +
    `6c. Read docs/client/lookbook.html as the owner: one card per accepted render of the 16 merch lines on CEG blanks, each disclosed as a computer-generated render, ` +
    `the pick mechanic working and consistent with brand.html's, no line presented as listed or for sale, no NLT-facing copy beyond the shared "Private review · from NLT Labs" eyebrow.\n` +
    `6d. The frame around every page: open index, heroes, imagery, before-after, imagery-concepts, brand and lookbook — does each carry the 2-colour lockup top-left ` +
    `(assets/brand/ceg-lockup-fullcolor.svg, linking to index.html) and the same 7-link nav with no .md links? Render index.html and before-after.html headless at 390 px wide ` +
    `(google-chrome --headless=new --screenshot) and LOOK: does the lockup overlap the nav or title, is anything clipped? Say what you saw.\n` +
    `7. The one question that matters: knowing the full pre-handoff review context, is this the packet, page, gallery, brand page and lookbook we would be proud to put in front of ` +
    `the shop owner tomorrow morning? A passing grep is not an answer — answer in words, naming what you saw.\n` +
    `If anything would embarrass us in front of the client, set blocks_merge=true and name it in objections. ` +
    `This is the SEND gate: it decides whether the operator sends the email, not whether code merges.`,
  { label: 'identity', phase: 'Identity', schema: IDENTITY, agentType: 'general-purpose', model: 'opus', effort: 'xhigh' }
)

const ok = !!identity && identity.is_the_thing_asked_for && !identity.blocks_merge
return {
  merge_authorized: ok,
  integ,
  identity,
  spent_tokens: budget.spent(),
}

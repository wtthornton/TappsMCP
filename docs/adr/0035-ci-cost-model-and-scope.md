# 35. CI cost model: free by visibility, guarded by assertion

Date: 2026-08-05

## Status

Accepted.

## Context

A review of this repo's CI/CD started from the premise that GitHub Actions was a
cost to be reduced. Measurement did not support it.

TappsMCP is a **public** repository. Standard GitHub-hosted runners are free and
unmetered on public repositories — this survived the January 2026 Actions
repricing, which cut larger-runner rates but left the public-repo exemption in
place. Every job in this repo runs on `ubuntu-latest`. Over a 30-day sample the
repo used 150 workflow runs / 177 wall-minutes, all of it free. Cache (622 MB)
and artifacts (20 MB) are likewise unbilled on public repos.

Two costs had already been optimised against on the assumption that Actions
minutes were scarce here:

- `brain-contract.yml` had its scheduled runs removed "to save Actions minutes".
- `codeql-analysis.yml` was set to `disabled_manually` and ran zero times in 30
  days, while the workflow file stayed in the tree — so the repo advertised
  security scanning it did not perform.

Both traded away real signal for savings that were always $0. Meanwhile the
genuine gap was coverage, not cost: CI ran `validate-changed --quick` over the
files a PR touched plus three targeted test modules, and `.githooks/pre-push`
runs a five-test smoke gate. Nothing ran the ~10,800-test suite. Twenty-five
real failures had accumulated on `master` undetected, spanning the brain tool
snapshot, the pre-push brain floor, the platform skill registry, the
`validate_changed` judge path, and the PyInstaller spec.

Recurring shape across those failures: a value duplicated as a literal in a test
while the real value moved elsewhere. The brain floor drifted 3.18.0 → 3.24.0 →
3.28.0; the skill count drifted 17 → 24 → 26 in two separate files; the consumer
audit stamp was pinned to a released version. Each was a test asserting a
constant the project had already abandoned.

## Decision

**1. Treat repository visibility as the cost model, and assert it.**

CI cost here is $0 because the repo is public and every runner is standard — not
because of workflow count, trigger filters, or schedule frequency. Optimising
those for cost is not warranted and costs signal. `scripts/ci_cost_guard.py`
fails the build when a workflow adopts a runner that is billable even on a
public repo (larger runners, runner groups), and emits a warning when the
repository is private, because that single change converts every job to metered
minutes.

**2. Restore security scanning.** CodeQL is re-enabled on `codeql-action@v4`
with `build-mode: none` (Python is interpreted; the old `autobuild` step was a
slow no-op) and the `security-extended` query suite rather than
`security-and-quality`, whose quality half duplicates ruff, pylint, and mypy.
A weekly scheduled scan on the default branch supplies the Security-tab
baseline, since PR runs only annotate the diff. All free.

**3. Do not gate the full regression suite on PRs yet.** A `tests.yml` job
invoking `scripts/run-regression.sh` was built and run against CI four times.
It failed every time, and never twice on the same tests — brain-bridge
flywheel tests, then `TestTappsChecklist`, then `test_contract_finish_gate`.

The names moved because the cause is one class, not one bug: a substantial
number of unit tests perform real subprocess, network, or repository-wide I/O.
They pass on a developer machine, where a brain answers in milliseconds and
`time.monotonic()` reflects days of uptime. On a clean 4-core runner they hang
and hit the 60s per-test timeout. Four causes were found and fixed —
oversubscribed xdist workers, a test asserting staleness against a
boot-relative clock, a full-repo AST scan on every `tapps_checklist` call, and
a brain URL inherited from this repo's own config — and a fifth surfaced each
time.

Landing the gate red would have been worse than not landing it: a permanently
failing check trains everyone to ignore the check. The gate is deferred until
the I/O-in-unit-tests debt is paid, which is work of its own scale rather than
a step within this one. What did land are the four fixes above and the
`REGRESSION_WORKERS` cap, so the suite is closer to CI-ready than it was.

**4. A gate must be order-independent to be trustworthy.** Two failures were
not stale expectations but genuine cross-test leaks, and both were fixed at the
source rather than pinned around:

- TAP-5442 replaces `server_memory_tools._params_project_id` globally the first
  time a brain bridge is built, and nothing undid it. Whether a later test saw
  the settings-tenant fallback depended on collection order. The patch is now
  reversible (`uninstall_memory_project_id_patch`) and restored by the conftest
  cache-reset registry in both packages.
- `--json` CLI assertions parsed `result.output`, which has interleaved stderr
  since Click 8.2, so any log record corrupted the parse. They now read
  `result.stdout`. The CLI was already correct — JSON on stdout, logs on stderr.

The suite is green under randomised ordering (`pytest-randomly`, seed printed on
every run), which is retained precisely because it is what surfaced these.

**5. Derive drifting constants; do not duplicate them.** Where a test asserted a
literal that lives somewhere else, the test now reads the real source: the brain
floor is parsed from `.githooks/pre-push`, skill counts come from the registry,
the consumer-audit stamp from `_package_version()`. The one constant that stays
hardcoded is `_ADR_MINIMUM_FLOOR`, which encodes the ADR-0033 policy floor the
hook must never regress below — a policy value, not a mirror of state.

## Consequences

- CI cost remains $0 and is now enforced rather than assumed. A PR introducing a
  larger runner fails with an explicit message instead of silently starting a
  bill.
- Making this repository private is a deliberate, visible cost decision: the
  guard warns and names the scheduled workflows that would begin billing.
- **The coverage gap this ADR opened with is still open.** CI continues to run
  only `validate-changed` on touched files plus targeted modules; nothing runs
  the full suite. That is the honest state, and it is the top follow-up.
- The blocker is now identified and measurable rather than suspected: unit
  tests that reach the network, spawn subprocesses, or scan the whole
  repository. Each is individually cheap to fix; there are enough of them that
  the sweep is its own work item. `.claude/rules/test-quality.md` already
  forbids the pattern for new tests, so the debt is bounded.
- Repo-wide `mypy --strict` is still not gated; `validate-changed` type-checks
  only files a PR touches. Closing that is separate work with its own error
  surface.
- ADR-0013's and ADR-0033's floors are now enforced by a test that reads the
  hook, so the next floor bump cannot leave the suite asserting a stale value.

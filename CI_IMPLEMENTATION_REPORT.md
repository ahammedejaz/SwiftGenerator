# CI implementation report

**Date:** 2026-08-16 · **Branch:** `feat/github-actions-ci` · **PR:**
[#5](https://github.com/ahammedejaz/SwiftGenerator/pull/5)

No financial-message specification was modified. No MT or MX message was added.
`sese.020/027/030/031` untouched. Two application-adjacent changes were made, both because
CI exposed a genuine defect — see §1.

---

## 1 · Audit findings

The repository had **no `.github/` directory at all**. That is the gap
[V0_1_0_RELEASE_READINESS_REPORT.md](V0_1_0_RELEASE_READINESS_REPORT.md) §18 named as the top
next step: PR #2 merged with `gh pr checks` reporting *"no checks reported"*, and the
clean-clone defect that broke `make migrate` for every new developer reached `main` because
no automated environment ever started from nothing.

Seven findings shaped the design:

| # | Finding | Consequence |
|---|---|---|
| 1 | `make audit` already exists and runs `pip-audit` + `npm audit --omit=dev`; `pip-audit` is pinned in `requirements-dev.txt` | Use the target rather than duplicating it in YAML |
| 2 | `make install` installs the Playwright browser but **not** its OS libraries — deliberately, since `--with-deps` needs sudo | CI must add that step; a developer machine must not |
| 3 | `reuseExistingServer: true` in both webServer entries | Harmless on a fresh runner, but Priority 3 asks for impossible, not unlikely |
| 4 | `reporter: "list"` produces no HTML report | Nothing to upload on failure |
| 5 | `webServer.timeout: 30_000` | A cold Next compile on a shared runner can exceed it |
| 6 | `make install` calls `python3.13` by name | Pin behind a variable rather than assume |
| 7 | Bare `git diff --check` compares worktree to index | Always clean on a runner: a no-op dressed as a check |

### Two genuine defects CI exposed

**`lxml 6.0.2` carried PYSEC-2026-87** (two entries), fixed in 6.1.0. `make audit` failed the
moment it was wired up. Bumped to `6.1.1`. The only thing lxml does here is compile and run
the derived XSD; the MX generation suite passes and a direct check confirms the schema layer
still rejects an element outside the configured subset.

**A timing-dependent e2e assertion failed on the very first CI run.**
`settlement-processing.spec.ts` asserted `getByRole("heading", { name: "MT530" })`, and that
page's own `<h1>` is *"Cancellation, MT530 priority, and cancel/rebook"*. Once the generated
message renders there are two matching headings and strict mode trips; before it renders
there is one and the assertion passes. **It passed on every laptop and failed on the first
shared runner**, which renders more slowly.

This is the second occurrence — the identical defect was fixed in `penalties.spec.ts` for
MT537, and the gotcha written then said to use `exact` and `level`. `corporate-actions.spec.ts`
has the same fragile pattern for five message codes; no collision on that page today, pinned
so a reworded heading cannot quietly create one. `AGENTS.md` gotcha 22 now records that it
happened twice and that CI is what caught it.

## 2 · Workflow design

`.github/workflows/ci.yml`. One workflow, five jobs, no reusable workflows, no matrices, no
custom actions, no containers inside containers.

**The Makefile is the source of truth.** Every job runs a `make` target, so CI and a laptop
cannot verify different things and reproducing a failure means running the same command. The
YAML adds only what a runner needs that a laptop does not:

- the browser's **OS libraries** (`npx playwright install --with-deps chromium`), which need
  sudo and would be wrong to run on a developer's machine;
- an explicit **base ref** for `git diff --check`, so it checks the pull request's range
  instead of the always-clean worktree-versus-index comparison.

## 3 · Jobs

| Job name | Runs | Duration |
|---|---|---|
| **Required Checks** | `make install` → `make check` → `make secret-scan` → `git diff --check <base>...HEAD` | 2m 2s |
| **Clean Clone** | assert no local state → `make install` → `make migrate` → `make check` | 1m 50s |
| **Browser E2E** | `make install` → browser OS libs → `make e2e` | 5m 3s |
| **Docker** | `docker compose config --quiet` → `docker compose build` | 1m 33s |
| **Security Audit** | `make audit` | 1m 11s |

`make check` covers ruff, ESLint, mypy `--strict`, `tsc --noEmit`, the backend suite, the
coverage gate and the demo-pack gate — the repository-generated-file checks included.

`Clean Clone` asserts up front that `.env`, `backend/.venv`, `frontend/node_modules`,
`backend/data` and `frontend/.next` are all absent, and fails with a GitHub error annotation
if any is present. Without that assertion the job could pass while proving nothing.

## 4 · Trigger rules

```yaml
on:
  pull_request: { branches: [main] }
  push:         { branches: [main] }
  workflow_dispatch:
```

All five jobs run on all three triggers. Playwright and Docker were measured before being
left on pull requests: 5m and 1m 33s respectively, which is well inside a reasonable feedback
loop, so both run on PRs as well as `main`.

**Concurrency**

```yaml
group: ${{ github.workflow }}-${{ github.ref }}
cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

Scoped by ref, so unrelated branches are never touched. Cancellation is limited to pull
requests: cancelling an in-progress `main` run would leave the default branch with no
verified result.

**Verified with real evidence.** Pushing `cb284e1` while the run for `b65e562` was in
progress produced exactly the specified behaviour:

| Run | SHA | Conclusion |
|---|---|---|
| 31942022509 | `b65e562` | **cancelled** |
| 31942042130 | `cb284e1` | success — authoritative |

## 5 · Dependency and cache strategy

`actions/setup-python@v5` with `cache: pip` keyed on `backend/requirements-dev.txt`;
`actions/setup-node@v4` with `cache: npm` keyed on `frontend/package-lock.json`. Nothing else
is cached — no database, no `.env`, no credentials, no generated messages, no application
state.

**`Clean Clone` deliberately has no cache.** A cached wheel would hide exactly the class of
defect that motivated the job: `lxml-stubs==0.6.0`, a pin that did not exist upstream and
broke `make install` for everyone who had never run it. Speed is not the point of that job,
and it still finishes in under two minutes.

Caching therefore affects speed only. The one job whose correctness depends on resolving
dependencies afresh does not use it.

## 6 · Security handling

| Control | Where |
|---|---|
| `make secret-scan` | Required Checks — deterministic and repository-local |
| `make audit` (`pip-audit`, `npm audit --omit=dev`) | Security Audit |
| `permissions: contents: read` | Workflow-level; the token can do nothing but check out code |
| No secrets referenced | No `secrets.*` expression appears anywhere in the workflow |
| No `.env` created or uploaded | None of the jobs writes one; none exists to upload |

**`Security Audit` is deliberately not part of Required Checks.** It asks the world whether a
dependency has a newly published advisory, so it can turn red overnight for a reason nobody's
change caused. A required gate should fail only for something in the diff. Promote it to
required once the team is happy to treat a new CVE as merge-blocking — the trade-off is
explicit rather than accidental.

## 7 · Clean-clone verification

The job proves a new developer can start from git-tracked files alone. Evidence from the
successful run:

```
No .env, virtualenv, node_modules, database or build cache. Starting from git alone.
…
Running upgrade 20260805_0006 -> 20260816_0007, Add the Financial Message Studio recent-messages table.
…
757 passed, 27 skipped, 1 deselected in 13.48s
```

`make migrate` succeeding from an empty state is the specific thing that failed before the
`ensure_database_directory` fix, which is why this job exists. No fake credentials are
created and no API key is required; AI stays optional.

## 8 · Playwright handling

- `make e2e` owns both server lifecycles. CI starts nothing itself.
- `reuseExistingServer` is now `!process.env.CI`, so **a run can never adopt a process it did
  not start** and report green for somebody else's server.
- `npx playwright install --with-deps chromium` installs the OS libraries. Only chromium —
  that is the single project the config declares.
- The webServer timeout rises to 180s on CI; a cold Next compile on a shared runner is
  slower than on a laptop.
- On CI an HTML report is produced alongside the list reporter, and `screenshot:
  "only-on-failure"` joins the existing `trace: "retain-on-failure"`.

**Artifacts upload on failure only** (`if: failure()`), 7-day retention:
`frontend/playwright-report/` and `frontend/test-results/`. Verified working — the first,
failing run uploaded a 2.29 MB `playwright-report` artifact containing the report, the trace
and the failure screenshot.

Everything those can contain is the synthetic demonstration data already committed under
`demo/`: no `.env` is created in CI, the database is in-memory, and no credential reaches
those paths.

## 9 · Docker verification

`docker compose config --quiet` then `docker compose build`. Nothing is tagged, pushed, run
or logged into. The job verifies reproducible image construction only, and completes in
1m 33s.

## 10 · Actual GitHub Actions results

**Authoritative run** (head of the branch, `72459a6`):
<https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942423127> — **success, 5/5**

| Job | Result |
|---|---|
| Required Checks | ✅ 1m 55s |
| Clean Clone | ✅ 1m 59s |
| Browser E2E | ✅ 5m 26s |
| Docker | ✅ 1m 36s |
| Security Audit | ✅ 59s |

**Previous green run** (`cb284e1`), kept for its per-job links:
<https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130> — **success**

| Job | Result | Link |
|---|---|---|
| Required Checks | ✅ 2m 2s | [job](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130/job/95152563387) |
| Clean Clone | ✅ 1m 50s | [job](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130/job/95152563363) |
| Browser E2E | ✅ 5m 3s | [job](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130/job/95152563362) |
| Docker | ✅ 1m 33s | [job](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130/job/95152563358) |
| Security Audit | ✅ 1m 11s | [job](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942042130/job/95152563443) |

**Earlier runs, kept because they are the evidence:**

| Run | SHA | Result | Why it matters |
|---|---|---|---|
| [31941598188](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31941598188) | `1e0ca84` | 4/5 — Browser E2E failed | CI found a real timing-dependent test defect on its first run, and the failure artifact uploaded correctly |
| [31942022509](https://github.com/ahammedejaz/SwiftGenerator/actions/runs/31942022509) | `b65e562` | cancelled | Superseded by a newer commit — concurrency working as specified |

CI **started automatically** on the pull request; no manual dispatch was needed.

## 11 · Files changed

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | **New.** The whole pipeline |
| `frontend/playwright.config.ts` | `reuseExistingServer: !process.env.CI`; HTML reporter and longer webServer timeout on CI; `screenshot: "only-on-failure"` |
| `frontend/tests/e2e/settlement-processing.spec.ts` | The heading assertion CI exposed |
| `frontend/tests/e2e/corporate-actions.spec.ts` | Same fragile pattern, pinned before it bites |
| `backend/requirements.txt` | `lxml` 6.0.2 → 6.1.1 (PYSEC-2026-87) |
| `Makefile` | `PYTHON ?= python3.13`, so the interpreter can be named differently without duplicating the recipe |
| `AGENTS.md` | New §11 *Continuous integration*; gotcha 22 updated with the second occurrence |
| `docs/testing.md` | Points at CI and at how to reproduce a job |
| `CI_IMPLEMENTATION_REPORT.md` | This document |

## 12 · Remaining limitations

- **Branch protection is not configured.** Changing protection settings was explicitly out of
  scope. **`CI / Required Checks` is the check to mark as required for `main`** — that job
  name is deliberately stable, and renaming it would silently disable the gate. Until it is
  marked required, CI reports but does not block.
- **`Security Audit` does not block merges** by design (§6). A newly published advisory turns
  it red without anything in the diff having changed.
- **One runner OS, one Python and one Node version.** `ubuntu-latest`, Python 3.13, Node 22 —
  matching what the repository targets. No matrix; the tool is not distributed to other
  platforms, and a matrix would multiply cost for a claim nobody is making. macOS and Windows
  remain unverified by CI.
- **`pip-audit` and `npm audit` need network access**, so the Security Audit job can fail for
  reasons outside the repository.
- **Docker images are built, not run.** The job proves construction, not that the composed
  stack serves traffic; that check is manual and recorded in
  [V0_1_0_RELEASE_READINESS_REPORT.md](V0_1_0_RELEASE_READINESS_REPORT.md) §5.
- **No deployment, release automation or image publishing.** Deliberately out of scope.

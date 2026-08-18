# Message Diff Implementation Report

**Date:** 2026-08-16 · **Base:** `21e5f4b` ·
**Scope:** an original-versus-regenerated comparison for both MT and MX imports, plus the
clean-machine verification that came with it.

No MT or MX specification was invented, expanded or "corrected". `sese.020/027/030/031`
remain `UNVERIFIED` and were not touched. No model is involved in the comparison, and none
could be: a diff a tester is expected to trust has to be reproducible.

---

## 1. Audit findings

`AGENTS.md` and `mt-import-and-coverage-hardening-report.md` were read first and the
documented state reproduced exactly: **697 backend tests, 50 browser tests, coverage
current**. `AGENTS.md` §15 already listed this work as recommended next item 5, in the same
words the brief used.

**Eight things the audit and the verification turned up that were not in the brief.** The
first three came from building a clean clone rather than reading about one; the last two
from running the suites repeatedly instead of once, and chasing the intermittent failures
to their causes rather than re-running until they passed:

1. **`make install` had never worked on a clean machine.** `backend/requirements-dev.txt`
   pinned `lxml-stubs==0.6.0`, which **does not exist** — the latest release is `0.5.1`,
   which is what every working checkout actually had installed. Any new laptop failed at
   `pip install`. Found by building a clean clone rather than by reading.
2. **Nothing installed the browser the tests drive.** `npm ci` installs the Playwright
   *package*; the browser is a separate download. `make e2e` therefore failed on a machine
   that had never run Playwright before.
3. **A committed lockfile carried a high-severity advisory** — `nanoid <3.3.18`
   (GHSA-2v37-7h3g-55p8), a build-time transitive dependency of `postcss`.
4. **The API & Automation screen's "Every endpoint" panel listed 14 of 18.** A list that
   claims completeness and quietly is not is worse than one that admits it is a selection,
   because nobody re-checks the first kind. Now complete, and a test keeps it that way.
5. **The browser suite had grown past the demonstration rate limit**, so a test unrelated to
   throttling could fail with a 429.
6. **`next dev` replaced this repository's `AGENTS.md` with nine lines of its own
   boilerplate** when `frontend/AGENTS.md` was transiently absent. Recovered, and recorded.
7. **The in-memory database was being used unsafely from several threads at once.**
   Concurrent requests could get an error — or, worse, **another request's result**. The
   most serious finding in this work. See §8.
8. **The browser could not reliably reach the backend.** The app called
   `http://localhost:8000` while the backend binds `127.0.0.1`; a dual-stack machine
   resolves `localhost` to `::1` first, so requests occasionally died with
   `ECONNREFUSED ::1:8000`. That reaches `fetch()` as a bare network error and reads as
   *"the studio API could not be reached"* — a developer would conclude their backend had
   crashed. See §8.

All eight are fixed. See §7 and §8.

---

## 2. What was built

### The comparison — `backend/app/studio/diff.py`

The design problem here is not producing a diff. It is stopping a tester from reading an
**expected** difference as a fault. A regenerated message almost always differs from the one
that was pasted, and almost always for a reason that does not matter. A comparison that
presents all of them equally teaches the tester to ignore the panel, which costs more than
having no panel at all.

So every difference carries a reason, in the product's own words:

| Reason | Shown as | Counted as | Meaning |
|---|---|---|---|
| `USER_EDIT` | You changed this | expected | A value the caller edited. |
| `NORMALISATION` | Written the studio's way | expected | Same meaning — specification field order, indentation, a header rebuilt from the client profile. |
| `NOT_REPRODUCED` | Never generated | expected | Block 5 trailers, user-header fields the studio does not emit, the MX `Sgntr`. Interface- and network-generated. **Never an application error.** |
| `IMPORT_DROPPED` | Could not be imported | **dropped** | Outside the configured subset. Reported at import, absent from the result. |
| `UNEXPLAINED` | Unexplained | **unexplained** | None of the above fitted. |

`UNEXPLAINED` is the point. Anything the studio cannot account for is labelled as such
rather than given a comfortable-sounding default — a difference quietly filed as
"normalisation" would hide exactly the case the comparison exists to surface. It is also the
only figure a pipeline should assert on.

### Two comparison bases, because the formats mean different things by "the same message"

**`FIN_LINES`** — MT is compared line for line on the FIN text exactly as rendered. Nothing
is normalised away first, because in FIN the line structure *is* the message.

**`CANONICAL_XML`** — MX is compared on meaning. Both sides are re-serialised into one
deterministic form first, so indentation, attribute order, self-closing style, whitespace-only
text and redundant namespace declarations cannot appear as differences. Element *order* is
preserved, because in ISO 20022 that is part of the message rather than a presentation choice.

Each canonical line keeps its element path, which is how a difference gets named in business
language: the tester sees *Transaction Identification*, not `<TxId>`.

### Comparing like with like

Somebody who pasted a bare `Document` has not *removed* a business application header, and
somebody who pasted a text block has not removed Blocks 1 and 2. Comparing either against the
full wrapped output would bury the real differences under the wrapper, so the comparison
picks matching sides and says which in words — *"the document, without its business
application header"*.

### API first

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/messages/diff` | Regenerate from these values and compare with a message you already have. Returns the message *and* the attributed comparison. |
| `POST /api/v1/messages/import` | Unchanged, but every response now carries `diff` — the faithfulness comparison, answering "did importing lose anything?" without a second call. |

The diff endpoint re-reads the original server-side to work out which values the caller
changed, so attribution needs nothing extra from the caller. It regenerates through
`_generate` — the same call `generate` makes, not a lookalike, so the two cannot drift. A
message whose format disagrees with the supplied values is refused (422) rather than
compared.

`_read_existing` was extracted so import and diff read a message through exactly the same
code. That matters more here than anywhere: the diff endpoint's whole job is to compare what
was read with what was written.

### In the browser — `frontend/components/studio/MessageDiff.tsx`

A **unified** diff, not side-by-side: FIN lines and ISO 20022 elements are long, and two
columns at 390px would mean reading each at half width.

The verdict comes first, in one sentence a tester can stop reading after:

- *The regenerated message is identical* — nothing was lost or rewritten.
- *Every difference is accounted for* — "None of them is a fault."
- *One part of the original could not be imported* — amber.
- *N differences could not be explained* — red, and the only one that means anything.

Then the lines, each with a reason chip and the business field name. Actions: **Show only
changes** (on by default), **Copy regenerated**, **Download regenerated**, **Return to edit**.

It appears on the Create Message proof step whenever a message was imported, and on Validate
after checking an existing message. It is **not** rendered when generating from scratch —
there is nothing to compare against, and an empty comparison panel is a dead end.

---

## 3. Supported inputs and behaviours

| Requirement | How it is met |
|---|---|
| Show original, regenerated, and a diff | Unified diff with both texts per changed line, plus copy/download of the regenerated message |
| Highlight added, removed, changed | `ADDED` / `REMOVED` / `CHANGED`, in colour **and** in words (`sr-only` labels), so nothing depends on colour alone |
| MT preserves FIN line structure | `FIN_LINES` basis compares raw lines; a test asserts the rendered lines are exactly the message's own |
| MX compares meaning, not whitespace | `CANONICAL_XML`; four formatting manglings are asserted to produce *no* difference |
| Show only changes | On by default; unchecking shows the whole message |
| Copy / download regenerated | Both present; download names the file from the scenario reference |
| Return to edit | Returns to the data-entry step. **Omitted on Validate**, where there is no form to return to — a button that only hid the result would be a dead end |
| Explain each difference | Five reasons, each with a one-sentence explanation and a "What the reasons mean" list under the diff |
| Never treat network trailers as errors | `NOT_REPRODUCED` counts as `expected`; `dropped` and `unexplained` stay at zero. Asserted in both the backend and browser suites |
| No LLM call | `difflib` and string comparison only. Determinism asserted |
| Simple enough to understand instantly | Verdict sentence first, five plain-English reasons, one table |
| API support first | Endpoint, then types, then client, then component |

---

## 4. Bounded work — a defect found while testing

A near-1 MB paste of unmatched lines took **over two minutes**. `SequenceMatcher` was not
the problem — it handles 8,000 lines in a millisecond. The cost was attribution: every
removed line scanned every reported import issue, which is quadratic. At 35,000 lines that
is a denial-of-service vector on an endpoint that is open in development.

Rather than degrade the comparison silently, it now refuses to produce one nobody could
read:

- **`MAX_DIFF_LINES = 3,000`** per side
- **`MAX_ATTRIBUTED_ISSUES = 200`**

Beyond either, `comparable` is `false`, `lines` is empty, `notComparedReason` says why, and
`summary.identical` still answers the question that actually matters. **Over two minutes →
0.22 seconds.**

Both bounds sit far above anything the studio itself can generate: `FieldInput.occurrence`
caps at 100, so the largest producible MT537 is 313 lines. A test pins that.

The browser renders this case explicitly. The first attempt showed a **green tick** above
"The regenerated message is not the same as the one you imported" — reassurance the studio
had not earned. Caught by looking at the screenshot; the verdict is now amber.

---

## 5. Files changed

**New for the comparison (4)**

```
backend/app/studio/diff.py                    593   the comparison and its attribution
backend/tests/studio/test_message_diff.py     524   50 tests, mostly about attribution
frontend/components/studio/MessageDiff.tsx    340   the panel a tester reads
frontend/tests/e2e/message-diff.spec.ts       229   11 browser journeys
```

**Modified**

| File | Change |
|---|---|
| `backend/app/studio/models.py` | `DiffKind`, `DiffReason`, `DiffBasis`, `DiffLine`, `DiffSummary`, `MessageDiff`, `DiffRequest`, `DiffResult`; `ImportResult.diff` |
| `backend/app/studio/routes.py` | `POST /messages/diff`; `_read_existing` and `_merge_import_issues` shared with import |
| `backend/requirements-dev.txt` | `lxml-stubs` `0.6.0` → `0.5.1` — the pin did not exist |
| `backend/tests/conftest.py` | the backend suite no longer shares the demonstration rate limit |
| `frontend/playwright.config.ts` | the browser suite no longer shares it either; every URL is an address, not `localhost` |
| `frontend/lib/api-client.ts` | the API base is `127.0.0.1`, so no name resolution is involved |
| `backend/app/config.py`, `app/main.py` | `FRONTEND_ORIGIN` accepts a comma-separated list; both spellings allowed by default |
| `docker-compose.yml`, `.env.example`, `docs/configuration.md` | the same two settings |
| `frontend/tests/e2e/bulk.spec.ts` | the one spec that hardcoded `localhost:8000` |
| `backend/tests/studio/test_studio_api.py` | asserts the Automation page lists every endpoint |
| `Makefile` | `make install` also installs the browser Playwright drives |
| `frontend/package-lock.json` | `nanoid` → 3.3.18 (GHSA-2v37-7h3g-55p8) |
| `frontend/lib/studio-types.ts`, `studio-api.ts` | the diff contract and `diffMessage()` |
| `frontend/components/studio/CreateMessage.tsx` | keeps the pasted text, calls diff after generating, renders the panel |
| `frontend/components/studio/ValidateStudio.tsx` | shows the comparison after checking an existing message |
| `frontend/components/studio/Automation.tsx` | the endpoint listed |
| `backend/tests/security/test_cors_and_throttling.py` | both spellings of the local origin are accepted |
| `backend/app/persistence/database.py` | the in-memory engine is safe to use concurrently |
| `backend/tests/unit/test_database_concurrency.py` | *(new)* eight threads, no cross-thread bleed |
| `README.md`, `AGENTS.md`, `docs/*` | see §6 |

---

## 6. Documentation

Beyond documenting the comparison, the audit turned up documentation that had gone stale
and is now corrected:

| Document | Was | Now |
|---|---|---|
| `README.md` | "19 message types… 3 MX types" | 23 types; 3 settlement + 4 lifecycle MX; import and the comparison described |
| `docs/testing.md` | "453 automated tests. 417 backend, 36 in a real browser" | 813 tests: 752 backend, 61 browser; per-folder counts corrected; both new specs listed |
| `docs/limitations.md` | "19 message types", "38 samples" | 23 types, 46 samples; the diff limitation removed; the size bound added |
| `docs/how-messages-are-built.md` | "38 samples across 19 message types" | 46 across 23 |
| `docs/for-manual-testers.md` | — | a section on importing and reading the comparison, with the reason table |
| `docs/for-automation-testers.md` | — | the endpoint, the response shape, and which figure to assert on |
| `AGENTS.md` | 697/50 tests, 17 endpoints | 752/61, 18 endpoints, `diff.py` in the file map, eight new gotchas, next-work updated |

---

## 7. Runs on a clean machine — verified, not assumed

The brief asked for a tool that works on any laptop, so the claim was tested rather than
believed. A copy containing exactly what git tracks — **no `.env`, no virtualenv, no
`node_modules`, no API keys** — was built from scratch:

```
make install ... ✅  (was: failed at pip install — lxml-stubs==0.6.0 does not exist)
make check ..... ✅  752 passed, 27 skipped · lint, typecheck and coverage gate clean
make e2e ....... ✅  61 passed
```

Run twice: once to find the two setup defects, and again from a fresh copy after fixing them
to confirm the whole sequence works first time. `make install` previously failed at
`pip install` on **any** machine, and `make e2e` failed on any machine that had never run
Playwright before.

What this proves and what it does not: no dependency on this checkout's `.env`, virtualenv,
`node_modules` or Playwright cache. It does not prove independence from macOS, this Python
patch release or this Node version — see §12.

---

## 8. Tests and exact results

```
make check
  ruff check app tests ......................... All checks passed
  eslint ....................................... clean
  mypy app ..................................... no issues in 128 source files
  tsc --noEmit ................................. clean
  pytest ....................................... 752 passed, 27 skipped, 1 deselected  (5.1s)
  coverage gate ................................ docs/generated/message-coverage.md is current

make e2e ....................................... 61 passed  (1.3m)
make secret-scan ............................... no secret-shaped strings in tracked files
make coverage .................................. current
docker compose build ........................... backend Built, frontend Built
docker compose config --quiet .................. ok
git diff --check ............................... clean
npm audit --omit=dev ........................... found 0 vulnerabilities
alembic upgrade / downgrade base / upgrade ..... clean on a fresh database
clean clone: install -> check -> e2e ........... all green
```

**Backend 697 → 752 (+55). Browser 50 → 61 (+11).**

| Suite | Result |
|---|---|
| `test_message_diff.py` | 50 passed |
| `test_mt_import.py` | 133 passed, 18 skipped |
| `test_mx_import.py` | 57 passed, 5 skipped |
| `test_coverage_and_sources.py` | 38 passed |

### One test-infrastructure defect

Adding 50 backend tests produced **13 failures in files that have nothing to do with the
diff** — all `429 RATE_LIMIT_EXCEEDED`. The demonstration throttle is per process and a
suite shares one, so whether a run passed depended on how many requests it happened to make.
`tests/conftest.py` raises the ambient limit.

`playwright.config.ts` was given the same treatment, not because the browser suite had been
observed to trip it — the failure there turned out to be the networking defect below — but
because it is now the same size and the same wall is in front of it.

The throttle is still tested either way: `tests/security/test_cors_and_throttling.py`
installs its own limiter, which is the only place the limit is the subject rather than the
scenery.

### The intermittent failures were two real defects, not flaky tests

A test that fails one run in three and passes in isolation is easy to shrug at. Both causes
here were real, and one of them could return the wrong data to a user.

#### The database was not safe to use concurrently

Different tests failed on different runs — `bulk.spec.ts`, then `ai-efficiency.spec.ts` —
which is the signature of something under the tests rather than in them. The full server log
gave it away:

```
sqlalchemy.exc.InterfaceError: (sqlite3.InterfaceError) bad parameter or other API misuse
[SQL: SELECT count(ai_result_cache.id), coalesce(sum(ai_result_cache.hit_count), ?) ...]
```

An in-memory SQLite database lives inside its connection, so every thread must share one —
and the engine used `StaticPool`, which hands that single connection to every caller at the
same time. `check_same_thread=False`, which the configuration needs, removes the guard that
would have complained. FastAPI runs sync endpoints in a threadpool, so requests genuinely
overlap.

Reproduced deterministically with eight threads, and the result was worse than an error:

```
MultipleResultsFound: Multiple rows were found when exactly one was required
NoResultFound: No row was found when one was required
```

on a query that can only ever return one row — **threads reading each other's result sets**.
For a tool whose job is to hand a tester *their* message, that is a correctness bug, not a
flake.

`sqlite://` now uses `QueuePool` with `pool_size=1, max_overflow=0`: one connection, and the
pool blocks the second caller until the first gives it back. The same hammer test then ran
3,200 concurrent operations with zero failures, and the in-memory database survived.
`tests/unit/test_database_concurrency.py` fails if `StaticPool` is ever put back — verified
by putting it back.

Scope: `sqlite://` is what the test suites and the e2e stack use. Local development uses a
file-backed SQLite database and production uses PostgreSQL; both give each thread its own
connection and were never affected.

#### The browser could not reliably reach the backend

One Advanced-screen spec, `bulk.spec.ts`, failed about one run in three and passed in
isolation every time. The page said *"Report retrieval failed."* — the frontend's message for
a **network** failure rather than an HTTP error, which was the clue.

The backend was not at fault: 25 consecutive bulk-generate-then-fetch-metadata cycles
against it all returned 200. Driving the same journey in a browser loop surfaced the actual
error:

```
apiRequestContext.get: connect ECONNREFUSED ::1:8000
```

The app called `http://localhost:8000`; `make backend` and `playwright.config.ts` bind
`127.0.0.1`. On a dual-stack machine `localhost` resolves to `::1` first, and the fallback to
IPv4 usually — but not always — wins. Nothing about it is specific to the tests: **a
developer running the app locally would see the same occasional "the studio API could not be
reached", and conclude their backend had crashed.**

`--host ::` is not the fix: macOS binds it IPv6-*only*, so `127.0.0.1` then fails instead.
Matching the address is. `NEXT_PUBLIC_API_BASE_URL`, `playwright.config.ts` and the one spec
that hardcoded a URL now all use `127.0.0.1`, and `FRONTEND_ORIGIN` accepts both spellings so
a tester who opens `127.0.0.1:3000` is not refused by CORS for not choosing `localhost:3000`.

#### Stability, proved rather than assumed

Neither fix is worth anything unasserted, so both suites were run repeatedly afterwards
rather than once:

```
backend  752 passed, 27 skipped   ×3 consecutive, identical
browser   61 passed               ×5 consecutive
```

One run in the middle of that sequence failed, and the cause is worth recording because it
is the same class of mistake as the ones above: **I ran `npm run build` in the directory the
test suite's dev server was serving from**, which took the servers down mid-run. Runs after
that were done without touching the repository. A test result gathered while editing the
thing under test is not a result.

### Two further environment defects, both self-inflicted and both worth recording

**A hand-started backend gets reused.** Two Advanced-screen specs failed on one run and
passed on the next. A backend I had started by hand was still on port 8000, and Playwright's
`reuseExistingServer` took it — but `playwright.config.ts` passes `DATA_ENCRYPTION_KEY` and
`SESSION_HMAC_SECRET` that a hand-started server does not have. Not a regression; the gotcha
in `AGENTS.md` has been sharpened to name the real cause, and `docs/testing.md` warns about it.

**`next dev` replaced `AGENTS.md`.** Next's `generate-agent-files.js` writes an agent file,
walking up to the project root when it cannot find one — and it *replaces* rather than
merges. With `frontend/AGENTS.md` transiently absent during the clean-clone work, it reduced
this repository's 548-line `AGENTS.md` to nine lines of its own boilerplate. Recovered from
the index, `frontend/AGENTS.md` restored so Next has its own target again, and verified: a
`next dev` cycle now leaves the root file byte-identical. Recorded as a gotcha, because the
next person to delete that file will not expect this.

**Two `make e2e` loops at once deadlock on the ports.** Both reuse whatever is on 8000 and
3000 (`reuseExistingServer: true`), so neither finishes. Obvious in hindsight, invisible at
the time: the symptom is a run that simply never produces output. Run one suite at a time.

---

## 9. Browser verification

Walked in Chromium at 1440×1100 and 390×844. **Zero console errors, zero failed requests,
0px horizontal overflow.** Twelve screenshots covering: an identical round trip, a user edit,
the whole message with *Show only changes* off, a network trailer, dropped content, a
reformatted ISO 20022 document, an MX edit, the Validate screen, the oversize case, and the
panel alone at both widths.

Two defects found by looking rather than by testing:

1. **A green tick above "the regenerated message is not the same as the one you imported."**
   The verdict only escalated on unexplained or dropped differences, both zero in the
   uncomparable case. Now amber.
2. **"Return to edit" on the Validate screen had nothing to return to** — it only hid the
   result. The action is now optional and omitted there.

---

## 10. Remaining external blockers

Unchanged by this work, and none worked around.

1. **Licensed ISO 20022 message-definition reports.** `sese.020.001.08`, `sese.027.001.08`,
   `sese.030.001.10`, `sese.031.001.09` still carry `UNVERIFIED` as their first limitation.
   Still the single largest outstanding risk.
2. **Official ISO 20022 XSDs** — absent; MX validation remains `SUBSET_DERIVED`.
3. **Licensed SWIFT MT specification** — coverage remains a repository-configured subset.
4. **`22F::SETR` placement** — still needs an authoritative source rather than a guess.
5. **Client MyStandards profiles** and **production connector contracts** — absent.
6. **Shared rate-limiter and circuit-breaker state** needs Redis or equivalent.

---

## 11. Updated recommended next work

1. **Reconcile the four lifecycle specifications** against an authoritative
   message-definition report.
2. **Import a licensed MT specification.** Still the only thing that changes what the
   platform may claim.
3. **Drop official ISO 20022 XSDs in.** One folder, no code.
4. **Fix `22F::SETR` placement** once an authoritative source exists.
5. **Shared rate-limiter and circuit-breaker state** before running more than one instance.
6. **Production OIDC/SAML adapter.** The boundary exists; the adapter does not.

---

## 12. What this leaves unproven

Honesty about the verification itself, not only about the messages:

- **The comparison's attribution is heuristic where it has to be.** A difference is matched
  to an import issue by content, because the parser numbers lines within the text block it
  was given and not within the whole FIN message. It is right for every case in the test
  suite, and `UNEXPLAINED` exists precisely so a case it cannot place is visible rather than
  mislabelled.
- **The 3,000-line bound was chosen, not derived.** It sits about ten times above the
  largest message the studio can produce, which is the argument for it. A configuration that
  raises `FieldInput.occurrence` past 100 would need it revisited.
- **The concurrency fix serialises rather than parallelises.** One in-memory connection with
  a queue in front of it is correct, not fast; under real load that configuration would be a
  bottleneck. It is a test and demonstration configuration, and production uses PostgreSQL.
- **The clean-machine check ran on this machine.** It proves no dependency on this
  checkout's `.env`, virtualenv or `node_modules`; it does not prove independence from
  macOS, this Python patch release, or this Node version.

---

## 13. Invariants checked

| Invariant | How it was kept |
|---|---|
| A message = specification + values | The comparison reads the specification's own display names; no message name appears in `diff.py` |
| Prefer configuration over code | No new configuration was needed, and none was invented |
| UI, JSON API and Excel share one path | `/messages/diff` regenerates through `_generate`, the same call `generate` makes |
| MT and MX rendering stay separate | Two comparison bases, chosen by format; neither touches the other's renderer |
| Never invent interface/network values | Trailers, user-header fields and `Sgntr` are shown as **never generated** and are never counted as faults |
| AI does intent interpretation only | The comparison is `difflib` and string comparison. Determinism asserted by a test |
| Honest `PARTIAL` reporting | Untouched. `UNEXPLAINED` exists so the comparison stays honest about what it does not know |
| No UI capability without an API equivalent | Endpoint first, then types, then client, then component; listed on the Automation page |
| Errors name the business field | Every diff line resolves to a display name — *Transaction Identification*, not `<TxId>` |

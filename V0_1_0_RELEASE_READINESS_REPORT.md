# v0.1.0 release readiness

**Date:** 2026-08-16 · **Scope:** taking the verified implementation to a reproducible
baseline for client demonstration, manual testing, automation testing and future
authoritative specification integration.

No new MT or MX message definitions were added. `sese.020/027/030/031` were not modified.
No SWIFT or ISO rule was guessed or fabricated.

---

## 1 · PR status

| | |
|---|---|
| PR | [#2 — MT/MX import and round trip, deterministic message comparison, unified coverage, and reliability fixes](https://github.com/ahammedejaz/SwiftGenerator/pull/2) |
| Base / head | `main` ← `feat/message-studio-import-diff-and-hardening` |
| State before merge | `OPEN`, `MERGEABLE`, `mergeStateStatus: CLEAN`, no required reviews |
| Commits | 2 (`21e5f4b`, `1509f21`) |

**No CI is configured in this repository.** `gh pr checks` reported *"no checks reported"*,
which is accurate rather than a failure: there is no `.github/workflows/`. Verification is
local, via `make check`. This is a real gap for a shared baseline and is the recommended next
step — see §18.

## 2 · Merge status

**Merged.** Normal merge-commit strategy, matching the repository's existing history and its
allowed methods. Not squashed, not rebased, not force-pushed. Merge commit
`5254d4202311e2d085a59255e459c652f40f60d9`.

A defect was found *after* that merge, during clean-clone verification (§5), so a second
change followed the same route: branch → PR → merge. No commit was pushed directly to `main`.

## 3 · Release tag status

| Tag | Commit | Status |
|---|---|---|
| `v0.1.0` | `5254d42` | Pushed. **Superseded** — the documented setup fails on a clean machine at this commit (§5) |
| `v0.1.1` | see §4 | Pushed. **This is the stable baseline.** |

`v0.1.0` was tagged after post-merge `make check` and `make e2e` passed, which is the order
the brief specifies — the clean-clone phase that exposed the defect runs afterwards. Rather
than move a published tag (a force operation on a shared ref), `v0.1.0` is left in place and
`v0.1.1` is the baseline. Delete `v0.1.0` if you would prefer a single tag; nothing depends
on it.

Both tags are annotated and state plainly that no SWIFT certification is claimed.

## 4 · Final commit SHA

See the summary at the end of this document — `main` and the `v0.1.1` tag point at the same
commit.

## 5 · Clean-clone verification

A fresh `git clone` of `main` — **no `.env`, no virtualenv, no `node_modules`, no local
database, no API key, no generated configuration, no cached application files** — then the
documented setup exactly as written.

### This found a real defect

```
make install ... ✅
make migrate ... ❌  sqlite3.OperationalError: unable to open database file
```

`alembic/env.py` builds its own engine and never imports `app/persistence/database.py`, which
was the only place that created the folder a file-backed SQLite database lives in. **The
second step of the documented setup failed on every new machine**, and worked on every
machine that had already run the application — which is why nobody who could have noticed it
ever saw it.

Fixed by extracting `ensure_database_directory` into `app/config.py` and calling it from both
paths, with `tests/unit/test_setup_from_a_clean_clone.py` failing if `env.py` stops calling
it. Verified by removing `backend/data/` and re-running.

### After the fix

```
make install ... ✅
make migrate ... ✅   schema created at backend/data/securities_studio.db
make check ..... ✅   757 passed, 27 skipped · lint, typecheck, coverage and demo-pack gates
make e2e ....... ✅   61 passed
docker compose up --build ... ✅  backend healthy, frontend serving
```

### Without an LLM key — 11/11, against the Docker stack

| Capability | Result |
|---|---|
| MT generation | ✅ 27-line FIN message, valid |
| MX generation | ✅ AppHdr + Document, valid |
| Excel → API → MT FIN | ✅ 3 generated, 0 failed, raw FIN returned |
| JSON API (catalogue) | ✅ 23 messages |
| Message Intelligence | ✅ 5 results, `deterministic: true`, `llmUsed: false` |
| Import (MT) | ✅ 15 values read, format identified from the message |
| Diff on import | ✅ `identical: true` — nothing lost |
| Diff after an edit | ✅ 1 changed line, `USER_EDIT`, *Sender's Message Reference* |
| Coverage endpoint | ✅ `authoritativeCompletenessKnown: false` |
| Sources endpoint | ✅ `fullySourced: false` |
| **AI interpretation** | ✅ `503 AI_NOT_CONFIGURED` — *"Use the deterministic form instead."* Platform unaffected |

The AI result is the one worth stating plainly: with no key, natural-language interpretation
**reports itself unavailable and everything else keeps working.**

## 6 · Backend test count

**757 passed, 27 skipped, 1 deselected.** Up from 752: five new tests covering the
clean-clone setup defect.

## 7 · Browser test count

**61 passed.** Unchanged — no UI behaviour changed in this task.

## 8 · Docker result

`docker compose config --quiet` ok · `docker compose build` both images built ·
`docker compose up --build` backend reported healthy, frontend served, and all eleven
capability checks above ran against that stack.

## 9 · Security scan result

| Check | Result |
|---|---|
| `make secret-scan` | No secret-shaped strings in tracked files |
| `npm audit` (runtime and dev) | 0 vulnerabilities |
| `git diff --check` | clean |
| `.env` | untracked and gitignored; absent from the clean clone |
| Demo pack | synthetic only — `DEMO`-prefixed BICs, placeholder ISIN, no client names, accounts, real references or keys |

## 10 · Manual MT flow

Create Message → MT → Securities Settlement → MT541 → Typical → edit *Sender's Message
Reference* → Validate → Generate → Download. ✅

Produced a complete FIN message containing the edited value, downloaded as
`MT541_<checksum>.fin`. The proof sheet names the field behind each line; **Envelope values**
shows the origin of every envelope value including the trailer row that says the network adds
it and the platform will not.

## 11 · Manual MX flow

Create Message → MX → Securities Settlement → sese.023 → Typical → edit *Transaction
Identification* → Validate → Generate → Download. ✅

Produced an AppHdr plus Document containing the edited value, downloaded as
`sese_023_<checksum>.xml`.

## 12 · Excel / API result

MT template → upload → **3 generated, 0 failed**, raw FIN in the response.
MX template → upload → **3 generated, 0 failed**, raw XML in the response.

`demo/curl.md` and `demo/RestAssuredDemoTest.java` cover the same journeys for a regression
framework.

## 13 · Import / diff result

Imported a generated MT541 — the studio identified it from Block 2 with nothing supplied —
edited one value, regenerated. The comparison showed **exactly one changed line**, attributed
`You changed this`, naming *Sender's Message Reference*. A pasted `{5:...}` trailer is shown
as *never generated* and the verdict stays *every difference is accounted for*.

## 14 · Demo runbook status

[CLIENT_DEMO_RUNBOOK.md](CLIENT_DEMO_RUNBOOK.md) — twenty minutes, seven steps, start
commands, talking points, an explicit "say these out loud" limitations section, and a
troubleshooting table. Every step was walked in a browser before it was written.

## 15 · Demo data status

[demo/](demo/README.md) — 8 request bodies, 6 expected outputs, both Excel templates, curl
examples and a Java REST Assured test.

**Generated, not written.** `make demo-pack` rebuilds the directory using the production
composer; `make demo-pack-check` is part of `make check` and fails if a recorded output stops
matching what the software produces. A hand-written expected output is a claim about the
software; these are recordings of it.

Byte-reproducible: `creationDate` and `businessMessageIdentifier` — which MX otherwise derives
from the clock — are pinned in the request files, which is also honest, because the reader can
see they are inputs. Excel workbooks are checked for presence rather than equality, since zip
archives differ between builds; that limitation is stated in the pack README rather than
glossed.

## 16 · Remaining external blockers

Unchanged by this task. Full detail and what each unlocks:
[AUTHORITATIVE_ARTIFACT_CHECKLIST.md](AUTHORITATIVE_ARTIFACT_CHECKLIST.md).

1. **ISO 20022 Message Definition Reports** — `sese.020.001.08`, `sese.027.001.08`,
   `sese.030.001.10`, `sese.031.001.09` remain `UNVERIFIED`. Largest outstanding risk.
2. **Official ISO 20022 XSDs** — absent, so MX validation remains `SUBSET_DERIVED`.
3. **Licensed SWIFT MT specification** — coverage remains a repository-configured subset.
4. **Client MyStandards guidelines and profiles** — ours are demonstration values.
5. **UAT connector contract** — no submission path; RJE export fails closed.
6. **`22F::SETR` placement** — recorded discrepancy, needs an authoritative source.
7. **Shared rate-limiter and circuit-breaker state** — per process; needs Redis before
   running more than one instance.

## 17 · Exact commands to run the platform

First time on a machine:

```bash
git clone https://github.com/ahammedejaz/SwiftGenerator.git
cd SwiftGenerator
make install      # virtualenv, npm packages, and the browser the tests drive
make migrate      # creates the database
```

Run it — two terminals:

```bash
make backend      # http://127.0.0.1:8000
make frontend     # http://127.0.0.1:3000
```

Or containers only:

```bash
docker compose up --build
```

Verify:

```bash
make check        # lint, typecheck, 757 backend tests, coverage and demo-pack gates
make e2e          # 61 browser tests, starts both servers itself
make secret-scan
```

No `.env` and no API keys are required for any of it.

## 18 · Exact next recommended development step

**Add continuous integration.** One GitHub Actions workflow running `make check` on every
pull request, and `make e2e` on `main`.

This is the top recommendation because it is the only item that changes how *every* future
change is verified rather than what one message can claim. Today `make check` is the gate and
it runs only where somebody remembers to run it: PR #2 merged with `gh pr checks` reporting
*"no checks reported"*, and the clean-clone defect in §5 reached `main` because no automated
environment ever started from nothing. CI would have caught it on the first run.

It is also cheap: the commands already exist, take about ninety seconds together, and need no
secrets.

After that, in value order, the specification work in
[AUTHORITATIVE_ARTIFACT_CHECKLIST.md](AUTHORITATIVE_ARTIFACT_CHECKLIST.md) §Priority — the
Message Definition Reports first, because they remove the largest caveat for the least effort.

---

## What this release does not claim

No SWIFT certification. Every message reports `capability: PARTIAL` and
`authoritativeCompletenessKnown: false`. Coverage is a repository-configured subset, never
reconciled against a licensed specification. MX schema validation is `SUBSET_DERIVED`. Four
MX messages are additionally `UNVERIFIED`. There is no live network transmission and no
production connector contract.

Those are not caveats added to this report; they are what the product says about itself, on
screen and in every API response.

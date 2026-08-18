# Phase 0/1 Pre-Merge Documentation and Honesty Audit (PR #9)

Point-in-time audit run on `feat/specification-engine-foundation` before merging PR #9.
No product features were added; every change is a documentation correction, an honesty
correction to wording or a default, or a regression test pinning those corrections.

## Actual test counts (measured on the branch)

| Suite | Count |
|---|---|
| Backend (pytest) | **1,036 passed**, 23 skipped (optional dependencies), 1 deselected (live AI) — 1,060 collected |
| Browser (Playwright) | **73 tests** in 14 files |

Per backend folder (collected): studio 693 · unit 193 · api 63 · spec_engine 36 (40 after
this audit) · knowledge 17 · golden 17 · workflows 16 · specifications 13 · security 9 ·
samples 2.

## Contradictions found and corrected

1. **`docs/limitations.md` said the cancellation/modification lifecycle was "Not
   implemented at all".** False — `sese.020`, `sese.027`, `sese.030` and `sese.031` are
   configured, generatable, validating and round-tripping end to end (registry verified
   on the branch; covered by the Playwright lifecycle spec), and README.md already listed
   them as generatable. Their true status is **implemented but UNVERIFIED**: version
   numbers, root element names and element sets were modelled on the repository's ISO
   20022 idioms, not reconciled against an authoritative message-definition report. The
   per-message limits table now states exactly that; the "not implemented" list is
   reduced to `pacs.*`, `camt.*`, `semt.*`. (AGENTS.md §14 and the registry's own
   `limitations` blocks were already correct; limitations.md was the outlier.)
2. **Stale test counts.** `docs/testing.md` claimed "813 automated tests, 752 backend,
   61 browser" with a folder table from two engagements ago; `docs/limitations.md`
   repeated the 813 figure. Both now carry the measured numbers above, and the testing
   folder table and Playwright spec table were rebuilt (adding `spec_engine/`,
   `specifications/` counts and `mt-authoring.spec.ts`).
3. **OFFICIAL provenance wording converted a declaration into a compliance claim** in
   three places: AGENTS.md §8 and the schema-source tables in ARCHITECTURE.md and
   how-messages-are-built.md all said `OFFICIAL` proves "real conformance", and
   authoritative-sources.md said "schema conformance becomes a real claim". All four now
   state the invariant: validation proves conformance **to the schema the operator
   supplied**; the platform cannot verify the file is the genuine ISO artifact, and
   `OFFICIAL` records the operator's declaration, not a verification the platform
   performed. The runtime detail string in `app/studio/mx/xsd.py` now reads "Validated
   against the operator-supplied official schema …".
4. **The compiler's `--source-type` default silently declared `OFFICIAL_ISO_20022_XSD`.**
   That converted omission into an official claim. The default is now
   `OPERATOR_SUPPLIED_XSD` (which claims nothing); declaring a source official requires
   passing `--source-type OFFICIAL_ISO_20022_XSD` explicitly. CLI help and
   `docs/specification-pack-format.md` state this.

No other contradictions were found between the registry, the capability dimensions, the
coverage report, limitations.md and AGENTS.md: the "not implemented" lists in AGENTS.md
§14 and README.md were already correct, the generated coverage document is current
(`make coverage` gate), and the historical figures in the Phase 0/1 plan and report
(e.g. "986 backend tests" as the *pre-change baseline*) are accurate as written.

## Lifecycle-message status (verified against the running registry)

`sese.020.001.08`, `sese.027.001.08`, `sese.030.001.10`, `sese.031.001.09`: present in
`config/mx/`, generatable through every surface, each carrying an explicit `UNVERIFIED`
limitation in its own specification. They are **not unimplemented**; they are
**unreconciled**.

## OFFICIAL provenance behaviour (verified and pinned)

The application can know a schema arrived through the official drop location and that
the operator declared it official. It cannot independently prove authenticity. Verified
behaviour: the declaration influences only structure *provenance*; it upgrades none of
`businessRules`, `marketPractice`, `clientProfile`, `externalValidation`; and no surface
(pack YAML, capability summary, gate output, compiler findings) produces "SWIFT
compliant", "ISO compliant", "certified" or "production ready".

## Tests added

`backend/tests/spec_engine/test_provenance_honesty.py` (4 tests):

- declaring a source official upgrades only structure provenance — the other four
  dimensions stay `NOT_CONFIGURED` / `NOT_RUN`
- no forbidden wording on any surface of the official path
- the compiler default records `OPERATOR_SUPPLIED_XSD`, never an official claim
- the OFFICIAL validation detail names the operator, pinned at source level

Backend suite after the audit: **1,040 passed** (1,036 + 4).

## Verification on the audited tree

`make check` · `make e2e` (73/73) · `make coverage` · `make demo-pack-check` ·
`make secret-scan` · `git diff --check` — results recorded in the PR conversation; all
pass, and PR #9 CI ran green on the final SHA (see below).

## Files corrected

`docs/limitations.md`, `docs/testing.md`, `docs/AGENTS.md`, `docs/ARCHITECTURE.md`,
`docs/how-messages-are-built.md`, `docs/authoritative-sources.md`,
`docs/specification-pack-format.md`, `app/studio/mx/xsd.py` (wording),
`app/spec_engine/pipeline.py` + `__main__.py` (default), plus the new test file and this
report.

## Final state

- Final commit SHA: recorded in the PR (this audit's commit is the PR head).
- PR #9: **open, not merged** — the user decides after reviewing.
- CI: all five jobs green on the final head (run linked from the PR checks page).

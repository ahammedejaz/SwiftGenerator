# MT standards upgrades

Use this procedure when moving the MT Prowide structural evidence lock from one standards
release stream to another.

## When to Upgrade

Upgrade only when one of these is true:

- Swift's official Standards Release page says the new MT release is live.
- A maintainer deliberately opens a future-release analysis branch and labels every output
  as future/test evidence.
- A dependency-security or reproducibility issue requires a pinned Prowide patch version
  in the same live release stream.

Do not upgrade because Maven metadata has a newer value.

## Procedure

1. Verify Swift's official Standards Release page and record the exact live date.
2. Verify Prowide's primary sources: repository, download docs, Maven Central package and
   Maven metadata.
3. Create a new lock file under `backend/config/`.
4. Download the new core jar, source jar and Java probe dependencies into `build/`.
5. Compute SHA-256 for every artifact and record Maven SHA-1 where available.
6. Run `make mt-prowide-extract` with the new lock and fixture path.
7. Run `make mt-prowide-reports-write`.
8. Review `docs/generated/mt-prowide-structure-diff.md`.
9. Run `make verify-prowide-mt-source`.
10. Run the full repository verification gates.
11. Update [mt-source-versioning.md](mt-source-versioning.md), this document and the
    Phase report.

## Review Rules

The reviewer should inspect these changes together:

- the lock file
- the JSON fixture
- `docs/generated/mt-prowide-structure-diff.md`
- `docs/generated/mt-importer-compatibility.md`
- `docs/generated/mt-multicategory-coverage.md`
- `docs/generated/message-coverage.md`

Expected changes include new candidate messages, removed candidate messages, moved
sequence nesting, new field groups and changed global field patterns.

Unexpected changes include:

- candidate messages becoming active
- `backend/config/specifications/` changes without a separate reviewed promotion
- `backend/config/knowledge/` changes without source-backed review
- any runtime package importing `app.spec_engine.mt_prowide`
- a claim that Prowide evidence proves Swift conformance

## Promotion Is Separate

An upgrade may reveal that a configured row differs from the Prowide-derived structure. Do
not fix that by changing the runtime manifest in the same step unless the source and review
scope explicitly include runtime reconciliation.

Runtime promotion or correction requires its own evidence-backed change:

- update the MT manifest and knowledge records
- update samples and golden fixtures if output changes
- update validation and parser behavior where needed
- update coverage and limitations
- run `make check`, `make e2e`, `make demo-pack-check`, `make secret-scan` and Docker
  verification

## Failure Handling

If fixture comparison fails, inspect the fresh extraction in `build/mt-prowide-candidates/`
and decide whether the change is expected for the new lock.

If the Java probe fails, do not work around it with partial data. The reflected global
field definitions and MT541 parser proof are part of the acceptance gate.

If Swift's live date and Prowide's version stream disagree, keep the current live lock and
document the newer artifact as future/test only.

## Post-Upgrade Claims

After a successful upgrade, the repository may claim only this:

> The committed MT Prowide fixture was reproduced from a pinned Prowide artifact and
> compared with the existing configured MT subset.

It still may not claim Swift certification, Swift network validation, market-practice
coverage, client-rule coverage or ISO 15022 completeness.

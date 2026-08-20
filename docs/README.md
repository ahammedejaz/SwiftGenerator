# Documentation

**Start here:** [../README.md](../README.md) — what this is and how to run it.

If you have never opened this repo before, read the root README first and then pick a
row from the table below based on why you are here.

---

## By what you are trying to do

| I want to… | Read |
|---|---|
| Make a message in the browser | [for-manual-testers.md](for-manual-testers.md) |
| Call it from a test suite or CI | [for-automation-testers.md](for-automation-testers.md) |
| Understand MT and MX formats | [how-messages-are-built.md](how-messages-are-built.md) |
| Understand the codebase | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Read a per-service tour | [../backend/README.md](../backend/README.md) · [../frontend/README.md](../frontend/README.md) |
| Change the code | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Configure it for a client | [configuration.md](configuration.md) |
| Import a licensed specification, schema or client guideline | [authoritative-sources.md](authoritative-sources.md) |
| Review MT Prowide structural evidence | [mt-structure-importer.md](mt-structure-importer.md) |
| Ingest MT semantic rule sources | [mt-semantic-rule-ingestion.md](mt-semantic-rule-ingestion.md) |
| Read a SWIFT Message Reference Guide as evidence | [mt-real-semantic-phase-05b.md](mt-real-semantic-phase-05b.md) |
| Understand occurrence-scoped rule evaluation | [rule-occurrence-semantics.md](rule-occurrence-semantics.md) |
| Demo the platform to a client | [CLIENT_DEMO_RUNBOOK.md](CLIENT_DEMO_RUNBOOK.md) |
| Know what to ask a client for | [AUTHORITATIVE_ARTIFACT_CHECKLIST.md](AUTHORITATIVE_ARTIFACT_CHECKLIST.md) |
| Know what is and is not supported | [limitations.md](limitations.md) |
| Know what the AI does | [ai-assistance.md](ai-assistance.md) |
| Review the security posture | [security.md](security.md) |
| Run or add tests | [testing.md](testing.md) |
| Run Phase 5C internal UAT | [testing/phase-05c-internal-uat-checklist.md](testing/phase-05c-internal-uat-checklist.md) |
| Use the lifecycle / corporate-action screens | [advanced-workflows.md](advanced-workflows.md) |
| See the design decisions behind the UI | [DESIGN.md](DESIGN.md) |
| See who this is for and why | [PRODUCT.md](PRODUCT.md) |
| Read historical reports of past work | [history/README.md](history/README.md) |
| See instructions written for AI coding tools | [AGENTS.md](AGENTS.md) |

---

## Where the docs live

```
<repo root>
├── README.md                          quick start, screens overview, everyday commands
│
├── backend/README.md                  backend tour (module map, entry points)
├── backend/config/README.md           configuration is the source of truth — how it's organised
│
├── frontend/README.md                 frontend tour (routes, components, state)
├── frontend/AGENTS.md · frontend/CLAUDE.md   Next-generated notices for AI tools
│
├── demo/README.md                     the synthetic demo pack, and how it is generated
├── demo/curl.md                       copy-paste curl for every demo endpoint
│
└── docs/                              all longer-form documentation
    ├── README.md                      ← you are here
    │
    │   Project orientation
    ├── ARCHITECTURE.md                how the pieces fit together
    ├── DESIGN.md                      why the UI looks the way it does
    ├── PRODUCT.md                     who uses this and why
    ├── CONTRIBUTING.md                pre-push checklist for code changes
    ├── AGENTS.md                      dense factual index maintained for AI coding tools
    ├── CLIENT_DEMO_RUNBOOK.md         twenty-minute demo script
    ├── AUTHORITATIVE_ARTIFACT_CHECKLIST.md   what to ask a client for
    │
    │   Task-oriented guides
    ├── for-manual-testers.md          walk-through for a person with no SWIFT knowledge
    ├── for-automation-testers.md      the JSON API, Excel templates, service authentication
    ├── how-messages-are-built.md      MT (ISO 15022) and MX (ISO 20022) format primer
    ├── advanced-workflows.md          settlement lifecycle, corporate actions, penalties
    ├── configuration.md               environment variables and their defaults
    ├── authoritative-sources.md       how to install a licensed specification or schema
    ├── specification-engine.md        compile an ISO 20022 schema into a specification pack
    ├── specification-pack-format.md   what a pack contains and what it may claim
    ├── specification-engine-plan.md   the phased architecture programme (Phases 0–7)
    ├── specification-rule-engine.md   business rules as reviewed, evidence-backed configuration
    ├── rule-pack-format.md            what a rule pack contains and what it may claim
    ├── rule-occurrence-semantics.md   `rule-dsl/2` occurrence identity and scoped evaluation
    ├── rule-source-handling.md        licensed source documents, and what may be committed
    ├── specification-rule-engine-plan.md   the Phase 2 architecture plan
    ├── mt-structure-importer.md       Prowide-derived MT structure evidence, build-time only
    ├── mt-semantic-rule-ingestion.md  MT semantic rule ingestion foundation
    ├── mt-real-semantic-phase-05b.md  reading a SWIFT Message Reference Guide as evidence
    ├── mt-semantic-source-handling.md MT semantic source metadata and privacy gate
    ├── mt-structure-importer-plan.md  the Phase 4 implementation plan
    ├── mt-source-versioning.md        live release and Prowide lock policy
    ├── mt-standards-upgrades.md       procedure for SRU/standards upgrades
    ├── ai-assistance.md               what the AI layer does (and does not)
    ├── security.md                    threat model and controls
    ├── testing.md                     run tests, add tests, the CI gate
    ├── testing/                       concise manual UAT checklists
    ├── limitations.md                 explicit non-guarantees
    │
    │   Machine-generated
    ├── generated/
    │   └── message-coverage.md        every configured message, measured — regenerate via `make coverage-write`
    │
    │   Point-in-time reports (not current-state docs)
    └── history/
        └── README.md                  reading order for the reports
```

---

## Generated

| File | Regenerate with |
|---|---|
| [generated/message-coverage.md](generated/message-coverage.md) | `make coverage-write` |
| [generated/mt-importer-compatibility.md](generated/mt-importer-compatibility.md) | `make mt-prowide-reports-write` |
| [generated/mt-multicategory-coverage.md](generated/mt-multicategory-coverage.md) | `make mt-prowide-reports-write` |
| [generated/mt-prowide-structure-diff.md](generated/mt-prowide-structure-diff.md) | `make mt-prowide-reports-write` |
| [generated/mt-semantic-readiness.md](generated/mt-semantic-readiness.md) | `make mt-rule-readiness-write` |
| [generated/mt-semantic-source-readiness.md](generated/mt-semantic-source-readiness.md) | `make mt-rule-readiness-write` |
| [generated/mt540-mt541-sr2026-rule-fidelity.md](generated/mt540-mt541-sr2026-rule-fidelity.md) | `make mt-mrg-reports-write` |
| [generated/mt540-sr2026-rule-review.md](generated/mt540-sr2026-rule-review.md) | `make mt-mrg-reports-write` |
| [generated/mt541-sr2026-rule-review.md](generated/mt541-sr2026-rule-review.md) | `make mt-mrg-reports-write` |
| [generated/mt-sr2026-semantic-readiness.md](generated/mt-sr2026-semantic-readiness.md) | `make mt-mrg-reports-write` |

Do not edit generated files by hand. `make coverage` fails the build if message coverage
is stale. It covers every configured message in both formats, and every figure in it is
measured from the real component rather than read from a flag. `GET /api/v1/coverage`
serves the same data. `make mt-prowide-check` fails the build if the Prowide-generated
reports are stale. `make mt-rule-check` fails the build if the MT semantic readiness
reports or synthetic MT corpus drift. `make mt-mrg-check` fails if the SR2026 MT540/MT541
Message Reference Guide fixture or generated reviewer reports drift.

[authoritative-sources.md](authoritative-sources.md) is the procedure for importing a
licensed specification, schema or client guideline — where each one goes and what it
changes. `GET /api/v1/sources` reports which are present.

---

## Historical reports

Point-in-time records of a piece of work. **Useful history, not a description of how
things work today.** Each report was correct on the day it was written; today's behaviour
is described by the guides above and by the code.

See [history/README.md](history/README.md) for a reading order and one-line summary of
each report.

Earlier plan and report pairs were removed to keep the repository readable. They remain in
git history at the first commit.

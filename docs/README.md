# Documentation

**Start here:** [../README.md](../README.md) — what this is and how to run it.

---

## By what you are trying to do

| I want to… | Read |
|---|---|
| Make a message in the browser | [for-manual-testers.md](for-manual-testers.md) |
| Call it from a test suite or CI | [for-automation-testers.md](for-automation-testers.md) |
| Understand MT and MX formats | [how-messages-are-built.md](how-messages-are-built.md) |
| Understand the codebase | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Change the code | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| Configure it for a client | [configuration.md](configuration.md) |
| Import a licensed specification, schema or client guideline | [authoritative-sources.md](authoritative-sources.md) |
| Demo the platform to a client | [../CLIENT_DEMO_RUNBOOK.md](../CLIENT_DEMO_RUNBOOK.md) |
| Know what to ask a client for | [../AUTHORITATIVE_ARTIFACT_CHECKLIST.md](../AUTHORITATIVE_ARTIFACT_CHECKLIST.md) |
| Know what is and is not supported | [limitations.md](limitations.md) |
| Know what the AI does | [ai-assistance.md](ai-assistance.md) |
| Review the security posture | [security.md](security.md) |
| Run or add tests | [testing.md](testing.md) |
| Use the lifecycle / corporate-action screens | [advanced-workflows.md](advanced-workflows.md) |
| See the design decisions behind the UI | [../DESIGN.md](../DESIGN.md) |
| See who this is for and why | [../PRODUCT.md](../PRODUCT.md) |

## Generated

| File | Regenerate with |
|---|---|
| [generated/message-coverage.md](generated/message-coverage.md) | `make coverage-write` |

Do not edit it by hand. `make coverage` fails the build if it is stale. It covers every
configured message in both formats, and every figure in it is measured from the real
component rather than read from a flag. `GET /api/v1/coverage` serves the same data.

[authoritative-sources.md](authoritative-sources.md) is the procedure for importing a
licensed specification, schema or client guideline — where each one goes and what it
changes. `GET /api/v1/sources` reports which are present.

## Reports

Point-in-time records of a piece of work. Useful history, not a description of how things
work today.

| File | What it is |
|---|---|
| [reports/overnight-brief.md](reports/overnight-brief.md) | The brief that commissioned the MT/MX studio work |
| [reports/overnight-audit-and-plan.md](reports/overnight-audit-and-plan.md) | The audit of the repository and the plan that followed |
| [reports/overnight-implementation-report.md](reports/overnight-implementation-report.md) | What was actually built, tested and left undone |
| [../AUTONOMOUS_CONTINUATION_REPORT.md](../AUTONOMOUS_CONTINUATION_REPORT.md) | MX import, the cancellation lifecycle, and a CORS defect |
| [../MT_IMPORT_AND_COVERAGE_HARDENING_REPORT.md](../MT_IMPORT_AND_COVERAGE_HARDENING_REPORT.md) | MT import, unified coverage, authoritative-source drop points |
| [../MESSAGE_DIFF_IMPLEMENTATION_REPORT.md](../MESSAGE_DIFF_IMPLEMENTATION_REPORT.md) | Original versus regenerated, and the clean-machine verification |
| [../V0_1_0_RELEASE_READINESS_REPORT.md](../V0_1_0_RELEASE_READINESS_REPORT.md) | What was verified for the v0.1.0 baseline |

Earlier plan and report pairs were removed to keep the repository readable. They remain in
git history at the first commit.

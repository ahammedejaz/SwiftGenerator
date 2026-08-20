# Historical reports

Point-in-time records of work that has already been done. **They are not a description of
how the code works today** — they describe how it looked and what was verified on the day
they were written.

If you are trying to understand the current system, start with the docs one level up
([`../README.md`](../README.md)) or [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

If you are trying to understand *how the system reached its current shape* — what problems
were found, what was fixed, what was measured — read the reports below in chronological
order.

---

## Reading order

The reports were all written during the initial construction of Financial Message Studio
(mid-August 2026). They fit together like this:

```
overnight-brief          → what was commissioned
overnight-audit-and-plan → the audit of the empty repository and the plan that followed
overnight-implementation-report → what the plan actually produced
     │
     ├─ message-diff-implementation-report    → original-vs-regenerated comparison added
     │
     ├─ mt-authoring-ux-correctness-plan      → UX correctness gap found
     │  └─ mt-authoring-ux-correctness-report → …and closed
     │
     ├─ autonomous-continuation-report        → MX import + cancellation lifecycle
     │
     ├─ mt-import-and-coverage-hardening-report → MT import + unified coverage
     │
     ├─ v0-1-0-release-readiness-report       → what was verified for v0.1.0
     │
     ├─ ci-implementation-report              → GitHub Actions pipeline set up
     │
     └─ specification-engine-phase-04-report  → Prowide-derived MT structure evidence
        └─ specification-engine-phase-04b-report → all-category MT source discovery
```

---

## Files

| File | What it recorded |
|---|---|
| [overnight-brief.md](overnight-brief.md) | The brief that commissioned the studio work. |
| [overnight-audit-and-plan.md](overnight-audit-and-plan.md) | Baseline audit of the pre-studio repository and the implementation plan. |
| [overnight-implementation-report.md](overnight-implementation-report.md) | What was actually built, tested, and left undone. |
| [message-diff-implementation-report.md](message-diff-implementation-report.md) | Adding the "original vs regenerated" comparison. |
| [mt-authoring-ux-correctness-plan.md](mt-authoring-ux-correctness-plan.md) | Plan to fix four accepted-but-wrong MT inputs. |
| [mt-authoring-ux-correctness-report.md](mt-authoring-ux-correctness-report.md) | Execution of that plan. |
| [autonomous-continuation-report.md](autonomous-continuation-report.md) | MX import, cancellation lifecycle, and a CORS defect. |
| [mt-import-and-coverage-hardening-report.md](mt-import-and-coverage-hardening-report.md) | MT import, unified coverage reporting, authoritative-source drop points. |
| [v0-1-0-release-readiness-report.md](v0-1-0-release-readiness-report.md) | What was verified for the v0.1.0 baseline. |
| [ci-implementation-report.md](ci-implementation-report.md) | The GitHub Actions pipeline and the two defects it found. |
| [specification-engine-phase-04-report.md](specification-engine-phase-04-report.md) | Prowide-derived MT structure evidence, source locks, reports and verification. |
| [specification-engine-phase-04b-report.md](specification-engine-phase-04b-report.md) | All-category Prowide MT source discovery, inert candidate analysis and authoring-readiness blockers. |
| [specification-engine-phase-05a-report.md](specification-engine-phase-05a-report.md) | The MT semantic-rule ingestion foundation: source metadata, privacy gating and canonical references. |
| [specification-engine-phase-05b-report.md](specification-engine-phase-05b-report.md) | Reading real SWIFT SR2026 MT540/MT541 Message Reference Guides as evidence, and refusing to activate any of it. |

---

## Why these were kept

Each report captures a **before/after** that would otherwise vanish from git history the
moment a file is re-touched:

- The *specific defects found and fixed* — which recur elsewhere and are easy to
  reintroduce.
- The *tests and checks that were run* to prove a change worked — a template for future
  verification.
- The *measurement basis* for coverage and completeness claims — so no one has to guess
  what "23 message types" meant on a given date.

They are safe to read out of order, but the diagram at the top explains what each one
depends on.

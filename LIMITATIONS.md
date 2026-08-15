# Limitations

- The repository contains 200 configured source-bounded rows, not an authorised complete current
  ISO 15022/SWIFT Standards specification. All 16 target messages remain `PARTIAL`; none is marked
  `PRODUCTION_CAPABLE` or externally validated.
- There is no SWIFT certification, live SWIFT network session, signing/authentication, institution
  connector, or production ACK/NAK. Download-only is operational; mock UAT is explicitly test-only.
- MT530 is limited to configured processing changes. It cannot amend core trade/event data.
- MT537 authoring supports the configured penalty structure but not the complete Statement of
  Pending Transactions catalogue. Amounts are user-entered; no approved penalty calculator exists.
- Corporate actions enable only a partial DVOP event profile. Other event types are catalogue-only
  until authorised event profiles and rules are imported.
- Dynamic forms, optional fields, repeatable sequences, parser, validator, and samples cover the
  configured rows only. Unknown imported fields are preserved as unsupported findings, not validated.
- The secure generic builder is expert sequence-oriented. Beginner business-question modes remain
  the existing configured workflows rather than a complete business-mode form for every target row.
- Raw import/round-trip is exposed by API; the secure builder does not yet provide a full visual
  original-versus-recomposed diff or editable unsupported-field preservation workspace.
- RJE output is fail-closed pending an authorised client interchange contract. Validation evidence
  is HTML/JSON, not PDF. Nested multi-sheet secure real-data bulk authoring is not implemented; the
  existing bounded Excel workflows remain configured-subset test utilities.
- The OIDC/SAML boundary exists, but no production identity-provider adapter or credentials are
  included. Development login is forbidden in production.
- PostgreSQL runtime support and migrations exist, but deployment HA, RLS, backup/restore, KMS/HSM,
  secure purge, SIEM/DLP, and operational key rotation are not complete.
- External validation accepts uploaded, checksum-correlated evidence. No MyStandards, Alliance, or
  vendor validation API contract is claimed.
- OpenRouter models are optional fallible interpreters. They receive minimal tokenised text and
  never compose, validate, approve, or submit messages. Live synthetic evaluation is point-in-time
  engineering evidence, not certification.
- Rate limiting, AI circuit state, L1 cache, telemetry percentiles, and daily budgets are process
  local. Distributed deployments need shared controls.
- Playwright covers critical UI flows, not every browser, accessibility, visual-regression, or
  destructive operational scenario.

See [MESSAGE_COVERAGE_REPORT.md](MESSAGE_COVERAGE_REPORT.md) and
[CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md](CLIENT_USABLE_SWIFT_PLATFORM_REPORT.md) for exact evidence.

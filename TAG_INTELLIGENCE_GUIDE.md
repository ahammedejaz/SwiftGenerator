# Tag Intelligence Guide

## Purpose

The Tag Intelligence Centre is the authoritative explanation layer for fields emitted by the configured demonstration composers. Normal list, detail, search, dependency, and profile-overlay operations are deterministic and do not call an LLM.

Coverage is startup-validated: a composer field signature cannot be enabled without a verified knowledge record containing business meaning, technical meaning, purpose, business question, presence, format, provenance, and version.

## PSET example

`PSET` means Place of Settlement. It identifies the requested settlement location or venue; depending on the message, option, market practice, and selected rule profile, the approved representation may identify a CSD, settlement institution, country, or another configured place-of-settlement form. It is not a generic counterparty account. The application presents the exact message/profile rule and its relationships to settlement parties such as `DEAG` and `REAG`; it does not generalise one message rule to all messages.

## Storage and provenance

Knowledge files live under `backend/config/knowledge`. Records use strict schemas, stable internal source references, standards-release labels, review status, reviewer, review date, and knowledge version. They contain concise derived metadata—not copied handbook pages—and do not imply certification.

Enabled records must be `VERIFIED` and originate from one of the allowed source categories. Duplicate IDs, unknown signatures/options/messages, broken dependencies, unverified sources, and profile overlays that broaden or weaken base rules fail startup validation.

## Adding a tag

1. Verify the field against an authorised source.
2. Add its exact `(message type, sequence path, tag option, qualifier)` signature to the owning module’s allowlist.
3. Add a complete versioned knowledge record with concise derived text and provenance.
4. Add dependencies only when the relationship is verified.
5. Add a client overlay only when it narrows options/codes or strengthens presence.
6. Run `make test`, including the coverage and knowledge-loader tests.

The LLM may simplify, translate, compare, or conversationally explain supplied verified records. It may not invent a definition, option, code, condition, or source. Missing records return: “This tag is not yet covered by the verified knowledge profile.”

## APIs

- `GET /api/knowledge/messages`
- `GET /api/knowledge/messages/{messageType}`
- `GET /api/knowledge/tags`
- `GET /api/knowledge/tags/{knowledgeId}`
- `GET /api/knowledge/search?q=...`
- `POST /api/knowledge/explain`
- `GET /api/knowledge/dependencies/{knowledgeId}`

No endpoint reproduces authorised documentation or claims official validation.

## Specification and sample integration

Each of the 200 configured knowledge records compiles to one stable form/composer/parser/validator
row. Message- and sequence-specific PSET records are not reused blindly. Annotated sample lines
link directly to the exact record, and every draft field exposes its source/provenance. Coverage is
checked by `make coverage`; 100% knowledge coverage means 100% of the configured subset, not the
unknown authoritative denominator.

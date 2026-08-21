# Message conversion

Conversion is a business-semantic transformation, not a tag-to-XPath rewrite. The first
runtime supports MT to MX through versioned Mapping Packs under `backend/config/mappings/`.
It does not claim general reversibility.

## Mapping Pack contract

A pack names exact source and target format, message, lane and release/version. It records
source type/reference/checksum, review state, reviewer, production eligibility and limits.
It also pins deterministic checksums of the source and target Structure Pack projections;
conversion refuses an evidence or structure checksum mismatch. A `CANDIDATE` pack cannot
execute, and only `REVIEWED` provenance may be marked production eligible.
Rules use a closed vocabulary: `DIRECT`, `TRANSFORM`, `CONDITIONAL`, `ONE_TO_MANY`,
`MANY_TO_ONE`, `NOT_REPRESENTED`, and `TARGET_REQUIRED_MISSING`. Transforms are named,
deterministic functions; there is no `eval`.

The small semantic vocabulary covers transaction reference, dates, instrument, quantity,
settlement amount/currency, place of settlement, agents, transaction/payment/movement type
and safekeeping account. It is intentionally not a financial ontology.

## Authority

This repository contains no approved real MT-to-MX mapping evidence. The bundled MT541 to
`sese.023.001.11` pack is `SYNTHETIC_TEST_ONLY`, `productionEligible: false`, and based on a
committed synthetic fixture. Normal requests return `BLOCKED_BY_MAPPING_EVIDENCE`. A caller
must explicitly set `allowSyntheticPreview: true` to demonstrate mechanics. This never
changes the pack's authority label.

Install a real pack only after an authorized mapping specification has been reviewed. RAG
or a model may propose a candidate, but a candidate remains `REVIEW_REQUIRED` and cannot
activate itself.

## Workflow and API

1. Parse raw MT with the ordinary import parser, or accept canonical MT fields.
2. Resolve an exact Mapping Pack and validate every source/target reference against the
   real specs.
3. Apply deterministic rules into target canonical values.
4. Report mapped, derived, user-supplied, missing and not-represented fields plus every
   transform and the pack provenance.
5. Return `NEEDS_INPUT` for required target data the source does not establish.
6. When complete, call ordinary `StudioService.generate(persist=false)` and return XML only
   if its target validation passes.

Discovery:

```http
GET /api/v1/messages/MT541/conversion-targets?sourceFormat=MT
```

Conversion:

```json
POST /api/v1/messages/convert
{
  "sourceFormat": "MT",
  "sourceMessage": "MT541",
  "rawMessage": "{4:\n...\n-}",
  "targetFormat": "MX",
  "targetMessage": "sese.023",
  "targetVersion": "sese.023.001.11",
  "allowSyntheticPreview": true
}
```

`/convert` provides the same workflow. A generated/imported MT also offers **Convert to MX**.
Excel conversion is possible later because the engine accepts and returns canonical values;
no Excel conversion UI is claimed today.

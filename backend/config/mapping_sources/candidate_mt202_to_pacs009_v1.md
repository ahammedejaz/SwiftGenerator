# Candidate mapping evidence — MT202 (SR2026) to pacs.009.001.13

This is the evidence record of a **candidate** Mapping Pack. It is not a SWIFT, CBPR+ or
ISO 20022 translation rule set and it is not reviewed.

## What the knowledge base establishes

- `SWIFT-MT-SR2026-MT205-MRG`, page 4, Scope: the category 2 financial-institution
  transfers (MT 200, 201, 202, 203, 205) and the ISO 20022 Financial Institution Credit
  Transfer are named as equivalents. This establishes the *target relationship* for MT202.
- `ISO20022-XSD-pacs.009.001.13`: the Financial Institution Credit Transfer message
  definition the knowledge base holds (root `FICdtTrf`).

## What it does not establish

No document in the knowledge base states a field-level mapping. Every rule in the pack is a
candidate drawn from the *definitions* of the fields it cites — the MT202 field
specifications (`SWIFT-MT-SR2026-MT202-MRG`, pages 5–18) and the element names of the
pacs.009 schema — and is marked `CANDIDATE_PREVIEW`: it executes only behind the explicit
preview opt-in, is labelled a candidate in every response, and is never production eligible.

## Conventions the pack records as limitations

- A SWIFT `YYMMDD` value date is read as `20YY-MM-DD`.
- `NbOfTxs` is set to `1` because one MT202 carries one transaction.
- `SttlmMtd` and `CreDtTm` are not in an MT202 and are surfaced as `NEEDS_INPUT`.
- Only party option A (BIC) is carried; options B and D are reported as not represented.

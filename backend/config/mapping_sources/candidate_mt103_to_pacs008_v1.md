# Candidate mapping evidence — MT103 (SR2026) to pacs.008.001.14

This is the evidence record of a **candidate** Mapping Pack. It is not a SWIFT, CBPR+ or
ISO 20022 translation rule set and it is not reviewed.

## What the knowledge base establishes

- `SWIFT-MT-SR2026-MT103-MRG`, page 4: the guide states the message is converted to its
  ISO 20022 equivalent over InterAct FINplus. It does not name the equivalent.
- `ISO20022-XSD-pacs.008.001.14`: the only customer credit transfer message definition the
  knowledge base holds (`FIToFICustomerCreditTransferV14`, root `FIToFICstmrCdtTrf`).

The relationship is therefore a **name correspondence** between the two documents' titles,
not a documented equivalence.

## What it does not establish

No document in the knowledge base states a field-level mapping. Every rule is a candidate
drawn from the definitions of the fields it cites (`SWIFT-MT-SR2026-MT103-MRG`, pages
14–40) and the element names of the pacs.008 schema, marked `CANDIDATE_PREVIEW`.

## Conventions the pack records as limitations

- A SWIFT `YYMMDD` value date is read as `20YY-MM-DD`.
- A SWIFT `d` decimal is rewritten with a full stop, and a trailing separator is
  dropped (`1000,` → `1000`). The number itself is unchanged; only the separator is,
  because the two standards spell it differently. Carrying the SWIFT spelling through
  produces a value the ISO 20022 decimal datatype rejects.
- `71A` codes are mapped to `ChrgBr` by their definitions (`BEN`→`CRED`, `OUR`→`DEBT`,
  `SHA`→`SHAR`); the correspondence is a candidate, not a published table.
- `NbOfTxs` is set to `1`; `SttlmMtd` and `CreDtTm` are surfaced as `NEEDS_INPUT`.
- Only party option A (BIC) is carried for agents; the customer options F and K and the
  no-letter option are reported as not represented.

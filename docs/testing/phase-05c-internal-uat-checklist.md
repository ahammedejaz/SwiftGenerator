# Phase 5C Internal UAT Checklist

Use this for current-live application UAT after Phase 5C. It checks that existing message
workflows still work and that SR2026 candidate rules remain isolated. It is not a SWIFT
certification checklist and does not approve any SR2026 C-rule.

## Setup

- Start the backend and frontend with `make backend` and `make frontend`.
- Use `BASE_DEMO_V1` unless a step explicitly asks for another profile.
- Treat "Ready to generate" as the expected valid state.

## MT540 Typical Sample

- Open Create Message.
- Select `MT` and `MT540`.
- Load `Typical Sample`.
- Validate, then generate.
- Confirm Block 4 and FIN outputs are present.
- Import the generated FIN message.
- Regenerate from the imported values and confirm the comparison is identical or has only
  expected differences.

## MT541 Typical Sample

- Select `MT` and `MT541`.
- Load `Typical Sample`.
- Confirm the sample includes `PSET` as a party field and a safekeeping account.
- Validate, then generate Block 4 and FIN.
- Import the generated FIN message and regenerate it.
- Confirm no SR2026 `REVIEW_REQUIRED` candidate rule appears as a tester-facing validation
  error.

## Guided Mode

- Open Guided.
- Use the default receive-against-payment style prompt.
- Generate MT541.
- Confirm the message reaches "Ready to generate" and shows FIN output.

## Expert Mode

- Open Expert.
- Select MT541.
- Load a sample or enter the common trade fields.
- Switch values without losing them.
- Confirm controlled fields use selectors rather than free text where code lists exist.

## Invalid Then Corrected ISIN

- In an MT541 flow, change the ISIN to an invalid value.
- Confirm validation names the Financial Instrument Identification field.
- Correct it to a valid sample ISIN.
- Confirm the error clears and the message generates.

## Validate Screen

- Generate an MT541 FIN message.
- Paste it into Validate.
- Confirm validation succeeds and import/comparison details are readable.

## Excel

- Download the MT template.
- Upload it unchanged.
- Confirm all included scenarios generate with zero failures.
- Repeat with the MX template.

## Existing MX Message

- Select `MX` and `sese.023`.
- Load `Typical Sample`.
- Validate and generate.
- Confirm XML contains both AppHdr and Document.
- Import the generated XML and regenerate it.

## Message Intelligence

- Search for `PSET`.
- Confirm MT and MX results are shown without any AI/model-call indication.
- Search for nonsense text and confirm the empty state is readable.

## Expected Decision

Internal UAT is ready to proceed when all steps above pass, no page shows horizontal scroll
on desktop or phone width, and no SR2026 candidate rule is visible in normal validation.

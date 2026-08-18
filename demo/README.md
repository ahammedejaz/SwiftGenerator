# Demonstration pack

Synthetic inputs, the messages they produce, and working examples in curl and Java. Enough
to show the platform to somebody in ten minutes, and enough for an automation tester to copy
into a real framework.

The runbook that uses this pack is [../docs/CLIENT_DEMO_RUNBOOK.md](../docs/CLIENT_DEMO_RUNBOOK.md).

## What is here

| Path | What it is |
|---|---|
| `requests/*-generate.json` | Request bodies for `POST /api/v1/messages/generate` |
| `requests/MT541-import.json` | An existing FIN message, for `POST /api/v1/messages/import` |
| `requests/MT541-diff.json` | The same message plus one edited value, for `POST /api/v1/messages/diff` |
| `expected/*.fin`, `expected/*.xml` | What those requests produce, byte for byte |
| `excel/demo-MT.xlsx`, `excel/demo-MX.xlsx` | The Excel templates, ready to upload |
| `curl.md` | Copy-paste examples for every endpoint in the demo |
| `RestAssuredDemoTest.java` | The same three journeys as a Java regression test |

## Everything here is generated, not written

`make demo-pack` rebuilds the whole directory using the **production composer** — the same
code path the browser, the JSON API and the Excel importer use. `make demo-pack-check`, which
`make check` runs, fails if the recorded output stops matching what the software produces.

That matters more than it sounds. A hand-written "expected output" is a *claim* about the
software; these files are a *recording* of it. If the composer changes, the pack changes in
the same commit or the build fails.

Two values are pinned in the MX request files so the pack is byte-reproducible: `creationDate`
and `businessMessageIdentifier`, which the studio otherwise derives from the clock. Seeing
them as inputs is also honest — the reader can tell they are supplied, not invented.

Excel workbooks are zip archives whose bytes differ between builds even when the content is
identical, so those two files are checked for presence rather than for equality.

## Nothing here is real

Every value is synthetic demonstration data from `backend/config/profiles/` and the sample
library:

- BICs are `DEMOGB2LXXX` / `DEMOUS33XXX` — the `DEMO` prefix is not an allocated institution.
- The account is `SAFE0000001`, the ISIN `XS0000000009`, references `TESTREF001` and
  similar. The ISIN is structurally valid and carries a correct ISO 6166 check digit; it
  is synthetic and is not registered with any numbering agency.
- Session `0001` and sequence `000001` are configured demonstration interface values.

There are no client names, no real accounts or transaction references, no API keys, and no
live network values. Block 5 trailers and the MX `Sgntr` element are **never** generated at
all — a messaging interface and the network produce those, and the studio refuses to invent
them. You will see them reported as *never generated* in the comparison.

## Honest scope

These messages are generated against a **repository-configured subset**, not a licensed
specification. Every message reports `capability: PARTIAL` and
`authoritativeCompletenessKnown: false`. Do not present this pack as evidence of SWIFT or ISO
20022 conformance — [../docs/limitations.md](../docs/limitations.md) is the full statement.

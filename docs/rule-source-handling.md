# Handling business-rule source documents

Message definition reports, message usage guides, market-practice documentation and client
guidelines are the evidence business rules are derived from. Most of them carry
redistribution restrictions. This page is about keeping that straight.

The rule is short:

> **A source document is not a rule pack.** The document stays with the operator; only
> permitted derived metadata is committed.

## The drop directory

`backend/config/rule_sources/`, overridable with `RULE_SOURCE_DIRECTORY` so a drop can sit
outside the checkout entirely. It holds `sources.yaml` — the manifest — and the documents
beside it.

`.gitignore` tracks only this repository's own synthetic fixtures:

```gitignore
backend/config/rule_sources/*
!backend/config/rule_sources/README.md
!backend/config/rule_sources/sources.yaml
!backend/config/rule_sources/synthetic-*.md
```

Drop a licensed PDF in and `git status` stays silent. This mirrors
`backend/config/mx/xsd/official/*.xsd`, which does the same for schemas.

## Declaring a source

```yaml
sources:
  - sourceId: ISO-SESE-023-MUG-2026          # stable, upper-case, hyphenated
    sourceType: OFFICIAL_ISO_20022_MESSAGE_USAGE_GUIDE
    title: …
    version: '2026'
    sourceLocation: sese-023-mug-2026.txt    # a file name, never a path
    adapter: TEXT                            # optional; inferred from the suffix
    sourceChecksum: sha256:…                 # recorded after the first ingest
    marketIdentifier: null
    clientIdentifier: null
    redistribution:
      sourceMayBeCommitted: false
      excerptsMayBeCommitted: false
```

`sourceType` is one of `SYNTHETIC_FIXTURE`, `OPERATOR_SUPPLIED_GUIDELINE`,
`OPERATOR_SUPPLIED_MARKET_PRACTICE`, `OPERATOR_SUPPLIED_CLIENT_GUIDELINE`,
`OFFICIAL_ISO_20022_MESSAGE_DEFINITION_REPORT`,
`OFFICIAL_ISO_20022_MESSAGE_USAGE_GUIDE`.

**It is a declaration, not a verification.** The platform can know a file arrived through
the configured directory and that the operator labelled it; it cannot prove the file is the
genuine licensed artifact. Nothing in the tooling, the documentation or the UI converts
that label into a compliance claim — the same invariant that governs
[schema provenance](authoritative-sources.md).

### Redistribution

Both flags default to `false`. **Silence is not permission**: a source whose licence has
not been considered is treated as one that may not be redistributed, so no excerpt is ever
written into a pack by accident.

The tool makes no legal determination. The operator declares the policy and the tool
honours it. Where excerpts may not be committed, a rule's evidence carries `sourceId`,
`sourceLocation`, `segmentId`, `sourceChecksum`, `segmentHash`, `excerptHash`, the heading
and the line range — enough for a reviewer to open their own copy at the right place, and
to prove the passage they are reading is the one that produced the rule.

## Ingesting

```bash
make rule-source-ingest SOURCE_ID=SYNTH-DEMO-MARKET-V1
```

prints the checksum, the adapter and every segment with its heading and line range. Record
the checksum in the manifest: a later ingest of changed bytes then fails with
`SOURCE_HASH_MISMATCH` instead of quietly deriving rules from a different document.

### What is refused

| Finding | When |
|---|---|
| `SOURCE_OUTSIDE_DROP_DIRECTORY` | a location resolving outside the directory, symlinks included |
| `SOURCE_TOO_LARGE` | over 4 MB |
| `SOURCE_FORMAT_UNSUPPORTED` | a file type with no adapter |
| `SOURCE_UNREADABLE` | not UTF-8, unparseable, or missing |
| `SOURCE_EXTRACTION_UNUSABLE` | garbled text, almost no prose, or an image-only PDF |
| `SOURCE_HASH_MISMATCH` | the bytes changed under a recorded checksum |

Rules are never derived from garbled extraction.

## Supported formats

`.txt`, `.md`, and `.html` (tags stripped deterministically, `script`/`style` removed, no
network, no DTD).

**PDF is a seam, not an implementation.** `pypdf` is deliberately not a dependency of this
repository: a PDF parser is a real attack surface, and every licensed document that would
justify it is one CI can never see. The adapter exists and reports
`SOURCE_FORMAT_UNSUPPORTED` when no extractor is installed. Convert first —

```bash
pdftotext -layout guide.pdf guide.txt
```

— which also gives you a text file you can checksum, read and diff. Installing `pypdf`
locally enables the adapter directly; even then, extraction is text-layer only, page
numbers are preserved, and an image-only document is refused rather than guessed at.

## Segmentation

Deterministic and LLM-free. Text is normalised (line endings, trailing whitespace, tabs,
NFC, runs of blank lines), split on blank lines with a heading stack, and merged up to
2,000 characters without crossing a heading or a page boundary.

`segmentId` is `{sourceId}#S{ordinal:04d}`; `segmentHash` is over the segment's text.

Ordinal identities are stable for an *unchanged* source but shift when text is inserted
earlier in the document. That is why evidence records **both** the ordinal and the content
hash, and why a changed source checksum invalidates every extraction-cache entry for it.
Content-addressed identities were considered and rejected: they would leave a reviewer
unable to read the document in order.

A marker heading (`#`, or a Setext underline) is peeled even when body text follows it. A
*numbered* heading is only recognised when it stands alone in its block — "2 Shares must be
delivered" looks exactly like "4.1 Payment", and quietly deleting a sentence would be far
worse than missing a heading.

## Privacy

Client guideline documents may be confidential. Before any model call the configured
provider must be the authorised one, and data-collection denial and zero-data-retention
routing apply from the same settings the runtime uses. Raw segments are never logged, never
emitted in telemetry, and never placed in a cache key or a file name — the extraction cache
is keyed on hashes and version identifiers only.

## What is committed

For each rule derived from a source, the committed pack carries the source's identity,
version, location, checksum and — only where the operator permitted it — a short excerpt
capped at 400 characters. Nothing else of the document leaves the operator's machine.

The synthetic documents in this repository are its own, which is why they are committed and
why their excerpts appear in the demo packs. They describe a market and a client that do
not exist.

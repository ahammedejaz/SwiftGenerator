# Business-rule source documents

The drop directory for the documents rules are derived from. `sources.yaml` declares each
one; the documents themselves sit beside it.

**Only synthetic material is committed here.** Message definition reports, message usage
guides, market-practice documentation and client guidelines normally carry redistribution
restrictions, so an operator drops them in locally and `.gitignore` keeps them out of the
repository — the same arrangement `config/mx/xsd/official/` uses for schemas. What may be
committed is the *derived* rule pack: identity, location, checksums and, only where the
operator declares excerpts redistributable, a short excerpt for a reviewer's convenience.

`sourceType` is an operator **declaration**. The platform can know a file arrived through
this directory and that someone labelled it; it cannot prove the file is the genuine
licensed artifact, and nothing in the tooling converts that label into a compliance claim.

Point `RULE_SOURCE_DIRECTORY` elsewhere to use a drop directory outside the checkout.

    python -m app.rule_engine ingest SYNTH-DEMO-MARKET-V1 --stamp

MT semantic-rule sources also declare `standardsRelease`, optional category/message scope
and two explicit external-model approval flags. Non-synthetic text is not sent to an
extraction model unless both `sourceAllowsExternalModelProcessing` and
`providerApprovedForSourceClassification` are true.

    python -m app.rule_engine ingest SYNTH-MT-SEMANTIC-V1 --stamp

## SWIFT Message Reference Guides

`mt-mrg-sources.yaml` is a second, separate declaration for SWIFT MyStandards MT Message
Reference Guides. It lives here because it is metadata about business-rule sources, but the
guides themselves are read from their own drop directory — `MT_MRG_SOURCE_DIRECTORY`,
default `swiftKnowledgeBase/` beside the checkout — which `.gitignore` excludes.

The declaration is committed and carries the SHA-256 of the exact bytes the derived rule
candidates were read from, so a re-exported or swapped guide is refused rather than silently
re-read. Redistribution and external model processing are both withheld: the guides' own
Legal Notices restrict disclosure outside the licensee's organisation.

    make mt-mrg-inspect
    make mt-mrg-extract

Reading a PDF needs `pypdf`, which this repository deliberately does not depend on:

    backend/.venv/bin/pip install pypdf

See [../../../docs/rule-source-handling.md](../../../docs/rule-source-handling.md),
[../../../docs/mt-semantic-source-handling.md](../../../docs/mt-semantic-source-handling.md)
and [../../../docs/mt-real-semantic-phase-05b.md](../../../docs/mt-real-semantic-phase-05b.md).

# MT Semantic Source Handling

MT semantic rule sources are handled by the existing rule-source system with additional
metadata that keeps source authority, privacy and runtime activation separate.

## Source classes

The manifest accepts these MT semantic source declarations:

```yaml
sourceType: OPERATOR_SUPPLIED_MT_GUIDE
sourceType: OPERATOR_SUPPLIED_MYSTANDARDS_EXPORT
sourceType: OPERATOR_SUPPLIED_INTERNAL_RULE_SOURCE
sourceType: OPERATOR_SUPPLIED_CLIENT_GUIDELINE
sourceType: OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL
sourceType: OFFICIAL_ISO_15022_DOCUMENTATION
```

`sourceType` is an operator declaration. The platform can know which file it read from the
configured source directory and what label the operator gave it. It cannot prove the file
is genuine SWIFT, ISO, MyStandards, market or client material.

## MT metadata

An MT semantic source should declare:

```yaml
standardsRelease: SR2025
applicableMessageCategories: [5]
messageIdentifiers: [MT541]
sourceAllowsExternalModelProcessing: false
providerApprovedForSourceClassification: false
```

The first three fields describe scope. The last two fields are a privacy gate.

Non-synthetic source text is never sent to an extraction model unless both
`sourceAllowsExternalModelProcessing` and
`providerApprovedForSourceClassification` are explicitly `true`. Unknown means blocked.
Local ingestion and segmentation still work, so a reviewer can checksum and inspect the
source without a provider call.

Synthetic fixtures are repository-owned and may opt into model processing for tests.

## Supported formats

The source adapters are shared with the Phase 2 rule engine:

- `.txt`
- `.text`
- `.md`
- `.markdown`
- `.html`
- `.htm`
- `.pdf` with text-layer extraction only when an optional local extractor is installed

Scanned PDF/OCR handling is outside Phase 5A.

## Current repository state

Generated source readiness is committed at
[generated/mt-semantic-source-readiness.md](generated/mt-semantic-source-readiness.md).
At the time of this phase:

```text
REAL_MT_SEMANTIC_SOURCE_AVAILABLE = NO
SYNTHETIC_MT_SOURCE_AVAILABLE = YES
```

The committed synthetic fixture is `SYNTH-MT-SEMANTIC-V1`; it is invented material and not
derived from SWIFT, ISO, MyStandards, a market guide, a custodian guide or a client
profile.

## Git policy

Raw non-synthetic sources should live in `backend/config/rule_sources/` or an override
directory pointed to by `RULE_SOURCE_DIRECTORY`, but they remain ignored. Commit only:

- manifest metadata that can be shared;
- derived reviewed Rule Packs;
- short excerpts only when the operator explicitly allowed excerpts to be committed.

Never commit restricted source documents, source archives, downloaded artifacts, provider
credentials or temporary extraction output.

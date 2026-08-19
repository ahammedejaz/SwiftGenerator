# The Specification Engine

How a message definition becomes part of this platform without application development.

```
Source schema (ISO 20022 .xsd, plus its local bundle)
        │   make spec-compile SOURCE=…            ← offline, developer-run
   Specification compiler (app/spec_engine)
        │   deterministic YAML — same bytes for the same source
   Specification pack (one file, the existing config/mx format)
        │   review → commit → PR → CI             ← never runtime self-modification
   MxRegistry (unchanged)
        │
   catalogue · Guided/Expert UI · Excel · JSON API · samples ·
   Message Intelligence · parser · coverage
```

The running application never compiles a schema. It loads packs the way it always loaded
configuration; a pack becomes active by being committed (or by pointing
`MX_SPECIFICATION_DIRECTORY` at a directory that contains it).

## Commands

```bash
# Compile a schema and run every gate over the result
make spec-compile SOURCE=path/to/sese.023.001.11.xsd OUT=backend/config/mx

# Prove an existing pack against its source schema
make spec-validate PACK=backend/config/mx/sese.023.001.11.yaml SOURCE=path/to/schema.xsd

# Resolve logical message IDs from the official ISO catalogue into a metadata manifest
make mx-source-discover LOGICAL="pacs.008 pain.001 camt.053" OUT=backend/config/mx/xsd/sources/catalogue-snapshot.yaml

# Fetch one official catalogue artifact into a local source cache
make mx-source-fetch URL=https://www.iso20022.org/... OUT=backend/config/mx/xsd/sources \
  EXPECTED_MESSAGE_DEFINITION=pacs.008.001.14

# Acquire every XSD listed in, or resolvable from, a metadata manifest
make mx-source-acquire MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot.yaml \
  SOURCES=backend/config/mx/xsd/sources \
  OUT=backend/config/mx/xsd/sources/catalogue-snapshot-acquired.yaml

# Compile and gate every manifest entry whose raw source is present locally
make mx-scaleout MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot.yaml SOURCES=backend/config/mx/xsd/sources OUT=build/mx-candidates REPORT=build/mx-scaleout.md

# What changed between two pack versions (for standards-release upgrades)
make spec-diff BEFORE=old.yaml AFTER=new.yaml

# The CLI underneath, with more options (--root, --bundle, --source-type, inspect)
cd backend && .venv/bin/python -m app.spec_engine --help
```

`mx-source-discover`, `mx-source-fetch` and `mx-source-acquire` are developer/operator
commands. They accept only HTTPS `iso20022.org` URLs for remote structural authority, and
they reject cross-domain redirects or HTTP downgrade. The fetcher accepts
`application/octet-stream` only after safe XML parsing proves the body is an `xs:schema`
whose `targetNamespace` matches the expected exact message definition. Raw source bodies
are kept in the ignored source cache; the committed manifest records safe metadata such as
logical message, exact message definition, catalogue state, source location, checksums when
available and redistribution status.

## The gates

`spec-compile … --validate` and `spec-validate` run six gates, each through the same code
path the platform uses at runtime:

1. **registry load** — the ordinary `MxRegistry` accepts the pack.
2. **sample derivation** — every mandatory leaf has a deterministic example derived from
   the schema's own facets.
3. **compose** — the ordinary `MxGenerator` builds the document and its own validation
   passes.
4. **source-XSD validation** — the composed document is valid against the **source**
   schema. Validating only against the pack's derived schema would prove nothing but
   self-consistency.
5. **invalid variants rejected** — deliberately broken documents (missing mandatory
   element, wrong order, bad enumeration, bad datatype) are *rejected* by the source
   schema, proving the gate can fail.
6. **round trip** — the ordinary parser reads the document back and recomposition is
   canonically identical.

## What a compiled pack claims — and what it does not

A compiled pack's capability dimensions read:

```
structure:          COMPILED_FROM_SCHEMA
businessRules:      NOT_CONFIGURED
marketPractice:     NOT_CONFIGURED
clientProfile:      NOT_CONFIGURED
externalValidation: NOT_RUN
```

XSD validation proves structure. It does not prove business rules, market practice,
client conformance or anything the words "SWIFT compliant" would imply. Whether the
source file was the official ISO artifact is recorded as provenance
(`source.sourceType`, `source.sourceChecksum`) — an operator's declaration, deliberately
not a capability claim.

## Presentation is mechanical until reviewed

Compiled packs get deterministic labels (`SttlmDt` → "Settlement Date" via camelCase
splitting and the published ISO 20022 abbreviations). Business meaning, questions and
common mistakes are absent until a reviewer writes them — missing presentation never
blocks compilation, generation or validation, and Message Intelligence reports the
technical facts it does have rather than inventing prose.

## Unsupported constructs fail loudly

Anything outside the supported XSD subset produces a named finding
(`XSD_UNSUPPORTED_CONSTRUCT`, `XSD_TYPE_UNRESOLVED`, `XSD_ROOT_AMBIGUOUS` …) — an error
when a valid message could not be generated without the construct, a warning plus a
recorded pack limitation when omitting it merely narrows the subset (optional
attributes, `xs:any` supplementary content, unbounded repetition capped at 1000).
Nothing is ever silently flattened.

## Security

Schemas are untrusted XML. The loader refuses any DOCTYPE (which removes XXE and
entity-expansion attacks in one move), blocks network schemaLocations, resolves
includes/imports only inside the explicit bundle directory (symlinks included), caps
file and bundle sizes, and reports structured findings instead of stack traces. Nothing
in a source artifact is ever executed. See `tests/spec_engine/test_xsd_loader_security.py`.

## Licensing

Official ISO 20022 schemas, MDRs and market-practice guidelines may carry redistribution
restrictions. The engine separates the **source artifact** (never embedded in a pack;
referenced by sha256 checksum), the **generated structural metadata** (the pack — commit
it only where redistribution of the derived description is permitted; that call belongs
to the operator, not this tool), and the **redistribution status** (recorded in
provenance). CI relies only on synthetic fixtures under `backend/tests/fixtures/xsd/`.

## Roadmap context

This is Phases 0–1 of the programme in
[specification-engine-plan.md](specification-engine-plan.md): dynamic registry, dimensional
capability model, and the MX structure compiler. Rule extraction with evidence (Phase 2),
market-practice overlays, the Prowide-derived MT importer (Phase 4) and the Specification
Factory (Phase 6) are designed there and deliberately not built yet.

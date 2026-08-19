# MX source bundles

This directory is an ignored cache/drop point for Phase 3 ISO 20022 source artifacts.

Use it for legitimately obtained source bundles only:

- official ISO 20022 catalogue downloads from `iso20022.org`;
- operator-supplied local ISO 20022 artifacts;
- previously reviewed local source bundles.

Raw source files stay untracked by default. A metadata-only manifest may be committed when
it contains only safe identifiers, URLs, checksums, source declarations and redistribution
status. `UNKNOWN` redistribution means the raw source must not be committed and generated
derived metadata needs an operator decision before it is committed.

Typical flow:

```bash
make mx-source-discover LOGICAL="pacs.008 pain.001 camt.053" OUT=backend/config/mx/xsd/sources/catalogue-snapshot.yaml
make mx-source-fetch URL=https://www.iso20022.org/... OUT=backend/config/mx/xsd/sources
make mx-source-inspect MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot.yaml
make mx-scaleout MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot.yaml SOURCES=backend/config/mx/xsd/sources OUT=build/mx-candidates REPORT=build/mx-scaleout.md
```

The runtime never reads this directory unless an operator points configuration at reviewed
generated packs. Source acquisition and compilation are developer/build-time operations.

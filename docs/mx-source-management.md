# MX Source Management

MX source acquisition is developer/operator tooling only. The running application never
fetches ISO pages, downloads XSDs or compiles schemas.

## Source Authorities

Accepted structural sources are:

- official `https://www.iso20022.org/` catalogue XSD downloads;
- operator-supplied local XSD files;
- reviewed local source bundles.

Random mirrors, package registries, blog posts and generated schemas are not structural
authority.

## Raw Source Cache

Raw source files belong in the ignored cache:

```bash
backend/config/mx/xsd/sources/
```

The directory commits only `README.md` and metadata manifests. Raw `*.xsd` files are
ignored because downloadable does not mean redistributable.

## Manifest Semantics

`logicalMessage` is not a runtime identity. Exact message-definition IDs are.

For current catalogue entries, the manifest records every observed current definition:

```yaml
logicalMessage: sese.023
currentDefinitions:
  - sese.023.001.13
  - sese.023.002.11
```

Do not choose the highest numeric version unless the ISO catalogue explicitly establishes a
replacement relationship. Parallel `.001` and `.002` branches may both be current.

## Acquisition

Discover metadata from the official catalogue:

```bash
make mx-source-discover LOGICAL="pacs.008 camt.053 sese.023 seev.031" \
  OUT=backend/config/mx/xsd/sources/catalogue-snapshot.yaml
```

Acquire raw XSDs into the ignored cache:

```bash
make mx-source-acquire \
  MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot.yaml \
  SOURCES=backend/config/mx/xsd/sources \
  OUT=backend/config/mx/xsd/sources/catalogue-snapshot-acquired.yaml
```

If a manifest entry has no `xsdUrl`, acquisition re-reads that entry's official
`sourceUrl`, resolves the exact message-definition row and then downloads the XSD link.

## Fetch Safety

The downloader accepts `application/octet-stream` only when all source checks pass:

- initial, redirect and final URLs are HTTPS `iso20022.org`;
- the body is within the configured XSD size limit;
- XML parsing is safe and forbids DOCTYPE/entity declarations;
- the root is `xs:schema`;
- `targetNamespace` matches the exact message definition;
- any expected checksum matches.

Checksums are recorded as `sha256:<hex>` after successful acquisition.

## Scale-Out

Compile and gate candidates outside installed configuration:

```bash
make mx-scaleout \
  MANIFEST=backend/config/mx/xsd/sources/catalogue-snapshot-acquired.yaml \
  SOURCES=backend/config/mx/xsd/sources \
  OUT=build/mx-candidates \
  REPORT=build/mx-scaleout.md
```

Generated candidate packs remain outside Git until redistribution of derived metadata is
explicitly approved.

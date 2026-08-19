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
build/mx-real-sources/
```

The directory commits only `README.md` and metadata manifests. Raw `*.xsd` files are
ignored because downloadable does not mean redistributable. The `build/mx-real-sources/`
cache is fully ignored and is intended for live verification runs.

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

Message-set bundle acquisition is attempted before individual XSD fallback when a manifest
contains `messageSets` entries:

```yaml
messageSets:
  - messageSetName: Payments Clearing and Settlement
    messageSetSourcePage: https://www.iso20022.org/iso-20022-message-definitions?search=Pacs.008
    messageSetDownloadUrl: https://www.iso20022.org/message-set/1249/download
    redistributionStatus: UNKNOWN
    rawSourceCommitted: false
```

Discover current message-set download links from ISO catalogue HTML:

```bash
make mx-message-set-discover FAMILY=pacs
```

Fetch and safely index a reviewed official message-set ZIP:

```bash
make mx-message-set-fetch \
  URL=https://www.iso20022.org/message-set/1249/download \
  OUT=backend/config/mx/xsd/sources \
  MESSAGE_SET_NAME="Payments Clearing and Settlement"
```

Inspect an operator-supplied local ZIP already placed in the ignored cache:

```bash
make mx-message-set-inspect \
  BUNDLE=backend/config/mx/xsd/sources/bundles/payments-clearing-and-settlement.zip \
  SOURCES=backend/config/mx/xsd/sources \
  MESSAGE_SET_NAME="Payments Clearing and Settlement"
```

The live network verifier is separate from normal CI:

```bash
make verify-real-iso-sources \
  OUT=build/mx-real-sources/acquired-manifest.yaml
```

That target runs in bundle-only mode so a temporary ISO outage does not turn into many
per-message fallback requests.

## Fetch Safety

The downloader accepts `application/octet-stream` only when all source checks pass:

- initial, redirect and final URLs are HTTPS `iso20022.org`;
- the body is within the configured XSD size limit;
- XML parsing is safe and forbids DOCTYPE/entity declarations;
- the root is `xs:schema`;
- `targetNamespace` matches the exact message definition;
- any expected checksum matches.

Checksums are recorded as `sha256:<hex>` after successful acquisition.

## Bundle Safety

Message-set ZIP archives are treated as untrusted. The safe loader enforces:

- HTTPS-only `iso20022.org` initial, redirect and final URLs;
- maximum archive download size, member count, individual member size and total expansion;
- compression-ratio checks for zip-bomb resistance;
- rejection of path traversal, `..`, absolute paths and Windows drive paths;
- rejection of symlinks, non-regular entries and nested archives;
- rejection of duplicate archive filenames;
- safe XML parsing for `.xsd` candidates with DOCTYPE/entity declarations forbidden;
- `xs:schema` root and ISO `targetNamespace` inspection before identity is trusted;
- rejection when filename message ID and namespace message ID disagree.

Only validated XSD bytes are materialised from the ZIP, using exact
`<messageDefinition>.xsd` filenames. The local bundle index records exact ID,
targetNamespace, source filename, source checksum, bundle checksum, message set, authority
and redistribution status; it never stores raw source content.

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

## Operator-Supplied Extracted Message Sets

When an operator has already downloaded and extracted an official ISO message-set archive
outside the repository, copy only the XSD files needed for local verification into the
ignored cache, for example:

```bash
mkdir -p build/mx-real-sources
cp /path/to/extracted-message-set/*.xsd build/mx-real-sources/
```

Record safe metadata only in `backend/config/mx/xsd/sources/*.yaml`: exact message
definition, target-namespace-derived checksum, authority declaration, `UNKNOWN`
redistribution status and `rawSourceCommitted: false`. The Payments operator manifest is:

```text
backend/config/mx/xsd/sources/payments-operator-supplied-2026-08-20.yaml
```

Run the real-source batch without committing generated packs:

```bash
make mx-scaleout \
  MANIFEST=backend/config/mx/xsd/sources/payments-operator-supplied-2026-08-20.yaml \
  SOURCES=build/mx-real-sources \
  OUT=build/mx-real-candidates \
  REPORT=build/mx-real-candidates/payments-scaleout-report.md
```

`build/mx-real-sources/` and `build/mx-real-candidates/` are ignored. Raw XSD files,
message-set ZIPs, MDR/MUG documents and generated real candidate packs must not be staged
unless redistribution of that exact artifact class has been explicitly established.

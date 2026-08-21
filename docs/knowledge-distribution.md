# Knowledge distribution

## Audit and decision

The operator folder audited on 21 August 2026 contained 164 files (163 active PDF/XSD
sources plus `.DS_Store`), about 36 MB. Repository documentation identifies the SWIFT MRGs
as licensed, and no explicit redistribution authorization was present for the raw PDF/XSD
set. The files are therefore `RESTRICTED` or `UNKNOWN`; both remain untracked.

Git LFS is not used. LFS changes storage mechanics, not redistribution rights. The chosen
mode is **secure bootstrap**: configured messages work with no bundle, and an authorized
operator may fetch/copy one separately.

## Secure bootstrap

Set exactly one source plus its approved checksum:

```bash
KNOWLEDGE_BUNDLE_URL=https://approved.example/knowledge.zip \
KNOWLEDGE_BUNDLE_SHA256=<64-hex-digest> \
make knowledge-fetch
```

or:

```bash
KNOWLEDGE_BUNDLE_PATH=/secure/drop/knowledge.tar.gz \
KNOWLEDGE_BUNDLE_SHA256=<64-hex-digest> \
make knowledge-fetch
```

URLs must be HTTPS, including redirects. Local input must be a regular non-symlink file.
The checksum is mandatory. Extraction rejects absolute/traversal paths, links, devices,
duplicate writes, excessive file counts and excessive uncompressed size. Credentials are
not accepted as committed configuration; use a short-lived approved URL or organization
connector.

HTTPS downloads resume into a checksum-keyed ignored cache under
`build/knowledge-bundles/`. A completed cache entry is reused only after its checksum is
verified. `KNOWLEDGE_BUNDLE_CACHE` can relocate that cache; cache paths may not be symlinks.

The default destination is ignored `swiftKnowledgeBase/`. Then run `make knowledge-sync`.
`make quickstart` performs fetch and sync when the bundle environment variables are present.

Do not commit raw bundles, extracted sources, the SQLite index, vectors, source cache or
compiled local packs. Only content-free manifests/reports with redistribution status and
checksums may be considered for review.

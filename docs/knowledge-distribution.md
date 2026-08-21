# Knowledge distribution

## Decision (superseded on 2026-08-21)

The audit of 2026-08-21 recorded the operator folder at 164 files, about 36 MB, and — with
no explicit redistribution authorisation at the time — kept it untracked behind a secure
bootstrap. The operator has since **explicitly authorised the knowledge-base content for
this internal, non-distributed project**, and the source tree is now committed through Git
LFS. The current contract is [knowledge-repository.md](knowledge-repository.md):

```bash
git clone https://github.com/ahammedejaz/SwiftGenerator.git && cd SwiftGenerator
git lfs pull
make quickstart
```

Git LFS changes storage mechanics, not rights; the authorisation is what changed. The
secure bootstrap below remains for an operator who cannot reach the repository's LFS
store, and `make quickstart` uses it only when the bundle variables are set and the
committed tree is absent.

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

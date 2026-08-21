# The knowledge repository

The authorised knowledge base travels with the repository. This page is the contract for
what is committed, how it is carried, how a clone proves it arrived intact, and what never
enters Git.

## Decision

The operator explicitly authorised the knowledge-base content for this **internal**
project; the application is not distributed publicly. On that authority the source tree
under `swiftKnowledgeBase/` is committed through **Git LFS**, so a new authorised developer
gets code, sources, deterministic metadata and a working application from:

```bash
git clone https://github.com/ahammedejaz/SwiftGenerator.git
cd SwiftGenerator
git lfs pull
make quickstart
```

The earlier secure-bootstrap path (`make knowledge-fetch` with a checksummed bundle) is
kept for an operator who cannot reach the repository's LFS store; `quickstart` uses it only
when the bundle variables are set and the committed tree is absent.

## What is committed

| Path | Carried as | Content |
|---|---|---|
| `swiftKnowledgeBase/MT/*.pdf` | Git LFS | 156 SWIFT MyStandards MT Message Reference Guides, Standards MT November 2026 (SR2026) |
| `swiftKnowledgeBase/MX/*.xsd` | Git LFS | 8 ISO 20022 `pacs` schemas |
| `swiftKnowledgeBase/source-manifest.json` | plain text | every file's relative path, byte size, SHA-256 and the identity the knowledge base read from its content |
| `.gitattributes` | plain text | the LFS rules: `swiftKnowledgeBase/**/*.pdf`, `*.xsd`, `*.zip`, `*.docx`, `*.xlsx` |

Measured on 2026-08-21: 164 files, 38,423,389 bytes. `docs/generated/` carries only
derived metadata (counts, hashes, page numbers, dispositions) — no sentence of any guide.

## What is never committed

- `build/knowledge/` — `knowledge.sqlite3` (segments, FTS index, vectors, sample cache),
  `packs/` (compiled Structure Packs), `source-cache/` (extracted text, XSD copies).
- `build/knowledge-e2e/` and every `build/knowledge-*/`.
- `.env`, credentials, browser state, session cookies, the operator's scratch files beside
  the sources (`.DS_Store`, `*.tmp`, lock files are ignored inside `swiftKnowledgeBase/`).

Everything under `build/` regenerates through `make knowledge-sync`; nothing in it is
needed to review the repository.

## The manifest

`swiftKnowledgeBase/source-manifest.json` (schema `knowledge-source-manifest/1`) is written
from a synced knowledge database:

```bash
make knowledge-manifest-write     # python -m app.knowledge_base manifest --write
```

and verified on any clone:

```bash
make knowledge-verify             # presence, real bytes (not LFS pointers), sizes, hashes,
                                  # nothing unlisted
make knowledge-verify-identity    # additionally re-reads each file's identity (local; slow)
```

A pointer file left behind by a checkout without the LFS client is a named failure
(`LFS_POINTER_NOT_FETCHED: … run git lfs pull`), never a source the sync would try to read.
Identity in the manifest comes from the knowledge base's content identification, not from
the file name: a renamed copy is the same source.

## Quickstart and the sync

`make quickstart` (`scripts/quickstart.sh`):

1. Requires Docker + Compose and OpenSSL; creates `.env` from the example and generates
   the local secrets.
2. If `swiftKnowledgeBase/source-manifest.json` exists: fetches LFS content when pointer
   files are found (`git lfs pull`), refuses with `LFS_POINTER_NOT_FETCHED` if they remain,
   sets `KNOWLEDGE_MODE=local` unless the operator chose otherwise.
3. Starts the containers and waits for backend readiness. The configured lane is usable
   now.
4. Verifies the mounted sources against the manifest, then runs `knowledge sync` **in the
   background** (`/app/data/knowledge-sync.log`). The first parse of ~160 standards
   documents takes minutes; the knowledge-preview lane appears when it finishes. Later
   syncs are incremental (unchanged checksums are skipped). Without embedding credentials
   the index is lexical, which is enough for the preview lane, the structures and the rule
   reader; embeddings are added later only where policy allows.

The container mounts `./swiftKnowledgeBase` read-only at `/app/knowledge-sources`; the
database and compiled packs live in the `studio-data` volume, not in the image and not in
Git.

## Re-reading without re-parsing

The sync keeps each PDF's page-marked text in the ignored source cache
(`build/knowledge/source-cache/mrg-text/<sha256>.txt`). A re-index reads the cache instead
of the PDF, the MRG rule reader consumes it directly, and
`make knowledge-rebuild-structures` re-reads every guide's structural artifact and
recompiles every Structure Pack in seconds — the development loop for the compiler and the
reader.

## CI

Only the **Clean Clone** job checks out with `lfs: true` and runs `make knowledge-verify`:
that job's claim is exactly "a fresh clone is sufficient", and it now proves the knowledge
base arrived as real bytes. Every other job keeps the default pointer-only checkout —
nothing they run opens a source, and the manifest test skips by name
(`Git LFS content not fetched on this checkout`) rather than passing silently.

## Security notes

- The secret scan (`make secret-scan`) runs over `git ls-files` with `grep -I`, so the
  binaries are skipped and a pointer file's text matches none of its patterns.
- Source text still never leaves the machine unless both policy gates allow it
  ([knowledge-source-handling.md](knowledge-source-handling.md)); committing the files
  changes where they are stored, not what may be sent to a model.
- The guides remain licensed material under the MyStandards Terms of Use; the repository is
  private and internal, and the operator's authorisation is recorded in this page and in
  the engagement report.

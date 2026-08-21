# Knowledge sources: the operator's guide

How to give the studio a new authoritative document, what happens to it, what may leave
the machine, and what never enters Git. The architecture behind this is in
[universal-financial-message-rag.md](universal-financial-message-rag.md).

## 1. What goes in

| Input | Recognised as | Used for |
|---|---|---|
| SWIFT MyStandards MT Message Reference Guide (PDF) | `MRG`, identity from the cover page | Search, citations, MT structure (qualifier tables, codes, formats), future Rule Pack candidates |
| ISO 20022 schema (`.xsd`) | `XSD`, identity from `targetNamespace` | Search, MX structure pack compiled through the six gates |
| Notes, usage guides (`.md`, `.txt`, `.markdown`, `.html`, `.htm`) | `NOTE` / `USAGE_GUIDE`, bound to the dominant message identifier | Search and citations |
| `.xml` | Read as an XSD when it declares one; otherwise indexed as text | Search |
| `.zip` | Expanded into the source cache; members handled by their own suffix | As above |

Anything else is skipped and reported as `UNSUPPORTED_EXTENSION` (the `.yaml` manifest in
`build/mx-real-sources` is the example on the measured run). Dot-files are ignored and
symlinks are never followed.

## 2. Where it goes

`KNOWLEDGE_SOURCE_DIR` names one or more roots, comma-separated, relative to the project
root or absolute. The default is `swiftKnowledgeBase`. Discovery is recursive, so
sub-folders by family or by release are fine — and preferable to a flat drop, because one
root that recurses beats a list of roots that has to be edited every time a folder appears:

```
swiftKnowledgeBase/MT/    MT Message Reference Guides (PDF)
swiftKnowledgeBase/MX/    ISO 20022 schemas (.xsd)
```

Add a folder beside those and the next sync indexes it with no configuration change. A
source is keyed by its content hash, not its path, so **moving a file between folders
keeps its index entry, its segments and its vectors**; only the recorded relative path
changes, and the run reports it as unchanged.

Name every root you want indexed in a single value: anything outside the roots of the
current run is tombstoned, so narrowing the list silently drops what a previous run had
indexed (§9).

Everything derived lands under the ignored `build/knowledge/` tree:

```
build/knowledge/knowledge.sqlite3   sources, segments, FTS, vectors, sample cache, metrics
build/knowledge/source-cache/       ZIP members and cached XSD bytes, by content hash
build/knowledge/packs/mt/           compiled MT Structure Packs (<MT>-<release>.yaml)
build/knowledge/packs/mx/           compiled MX packs beside their source XSD
build/knowledge/source-manifest.json
```

`KNOWLEDGE_DB_PATH`, `KNOWLEDGE_PACK_DIR` and `KNOWLEDGE_SOURCE_CACHE_DIR` move these.

## 3. ZIP safety

A ZIP is opened only within limits, and each refusal is reported by code:

| Refusal | Code |
|---|---|
| Uncompressed total above `KNOWLEDGE_MAX_ZIP_TOTAL_BYTES` (default 256 MiB) | `ZIP_TOO_LARGE` |
| Compression ratio above 100:1 (`MAX_ZIP_RATIO`) | `ZIP_RATIO_EXCEEDED` |
| A member above `KNOWLEDGE_MAX_ZIP_MEMBER_BYTES` (default 64 MiB) | `ZIP_MEMBER_TOO_LARGE` |
| A member path with `..`, an absolute path or an empty part (zip-slip) | `ZIP_UNSAFE_MEMBER` |
| A symlink member | `ZIP_SYMLINK_MEMBER` |
| A ZIP inside a ZIP | `ZIP_NESTED_NOT_EXPANDED` |

A single file above `KNOWLEDGE_MAX_SOURCE_BYTES` (default 64 MiB) is skipped the same way.
Members are extracted into `source-cache/<hash16>/`, never next to the source.

## 4. Identity and classification

Identity is read from the content, so a renamed file keeps its identity and two copies of
the same bytes are one source:

- **MRG** → `SWIFT-MT-<release>-<MT>-MRG`, e.g. `SWIFT-MT-SR2026-MT541-MRG`. The release
  comes from the cover date through `release_for_cover` (a November cover is the following
  year's release).
- **XSD** → `ISO20022-XSD-<version>`, e.g. `ISO20022-XSD-pacs.008.001.14`.
- **Note** → `<format>-DOC-<message>[-<release>]-<hash10>` when one identifier dominates the
  body: it must appear at least twice and at least twice as often as the runner-up, and
  when both MT and ISO identifiers appear one family must outnumber the other 2:1.
  Otherwise `UNIDENTIFIED-<hash10>`: still indexed and searchable, bound to no message.

Classification decides policy. A body that contains the line
`KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE` is a synthetic fixture owned by this
repository (the test corpus under `backend/tests/fixtures/knowledge/` uses it). An MRG is
`OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL`; an XSD is `OPERATOR_SUPPLIED_XSD`; a note is
`OPERATOR_SUPPLIED_DOCUMENT`; anything unreadable enough to have no identity is
`LICENSED_UNKNOWN`. There is no way to declare a licensed document synthetic from its file
name.

## 5. Licensing and privacy

The default is conservative and two gates must agree before any licensed text leaves the
machine:

```
KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED=false       # global gate for embeddings
KNOWLEDGE_EXTERNAL_LLM_ALLOWED=false             # global gate for prompt evidence text
KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS=SYNTHETIC_FIXTURE   # per-classification list
```

`policy_for(classification, settings)` allows a `SYNTHETIC_FIXTURE` unconditionally. For
every other classification the global gate must be `true` **and** the classification must
be listed. A configured embedding deployment or chat deployment is never permission: on
the measured run the deployment probe passed and all 23 licensed sources were still
`EMBEDDING_BLOCKED`, which is the intended state.

To widen it deliberately — for instance, after confirming with the licence holder that
operator-supplied XSDs may be embedded — set both:

```
KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED=true
KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS=SYNTHETIC_FIXTURE,OPERATOR_SUPPLIED_XSD
```

and run `make knowledge-sync`; only the newly allowed sources are embedded. What this
means: segment text of those sources is sent to the configured provider for embedding,
and (with the LLM gate) quoted inside prompts. Blocked sources still work for lexical
search and still produce citations; their text is simply withheld from the model and
from the API's snippet field.

What is stored and where:

| Data | Location | In Git? |
|---|---|---|
| Source bytes | The operator's folder; ZIP members in `source-cache/` | Never |
| Segment text, page numbers, sections, checksums | `knowledge.sqlite3` | Never |
| Embedding vectors | `knowledge.sqlite3` | Never |
| Compiled packs | `build/knowledge/packs/` | Never |
| Counts, identifiers, checksum prefixes, readiness | `docs/generated/*.md` | Yes — no text |
| Synthetic fixtures | `backend/tests/fixtures/knowledge/` | Yes |

The status and telemetry endpoints report provider *names*, deployment *configured:
yes/no* and dimensions; never a key, never an endpoint.

## 6. Commands

| Command | What it does |
|---|---|
| `make knowledge-sync` | discover → identify → index → embed (policy permitting) → compile structures, incrementally; writes the manifest |
| `make knowledge-status` | The same view as `GET /api/v1/knowledge/status` plus a structure summary |
| `make knowledge-reindex` | Re-parses every source even when its hash is unchanged (`sync --reindex`) |
| `make knowledge-clean-cache` | Removes `source-cache/` and `packs/`; never a source. `--database` also removes the DB |
| `make knowledge-reports-write` | Writes the three reports under `docs/generated/` |
| `make knowledge-reports-check` | Fails when the committed reports differ from the database |
| `make knowledge-check` | Offline retrieval evaluation on the synthetic fixtures (part of `make check`) |
| `make knowledge-dev` | Incremental sync, then the backend in `KNOWLEDGE_MODE=local_uat` |
| `make probe-embeddings` | One synthetic-text request to the configured embedding deployment |
| `make test-live-rag` | The retrieval evaluation with the real deployment on the synthetic corpus |

All of them honour `KNOWLEDGE_SOURCE_DIR=…` on the command line. `sync --no-embed` skips
embedding; `sync --reports` writes the reports in the same run.

### Incremental behaviour

| Situation | What happens |
|---|---|
| Unchanged file | Hash matches; not re-read; segments and structures reused (`documentsUnchanged`, `structuresReused`) |
| Changed file | Re-parsed; old segments replaced; previous checksum tombstoned (`sourcesDeleted` counts it) |
| Deleted file | Tombstoned; segments, vectors and its catalogue entries disappear |
| Unreadable file | `documentsFailed` with `KNOWLEDGE_SOURCE_UNREADABLE` and a reason (encrypted PDF, no pages); the run continues |
| Unsupported file | `documentsUnsupported` with `UNSUPPORTED_EXTENSION` |
| Interrupted run | Marked `INTERRUPTED`; the next run resumes where it stopped |
| Sync during use | Readers keep working (WAL, read-only connections); the API reloads the preview registries when the sync finishes |

The measured numbers: a fresh full run over 23 sources (1,525 pages, 4,663 segments, 293
structures) takes about 20–40 s; an unchanged rescan parses 0 and reuses 293 structures in
0.4 s; `--reindex` re-parses everything in about 27 s.

## 7. Adding another MT guide

1. Copy the PDF into the MT folder: `swiftKnowledgeBase/MT/SR_2026_MT535.pdf` (the name
   does not matter; the cover page does).
2. `make knowledge-sync` (or press **Sync** on `/knowledge-base` when the backend runs in
   `local_uat`). The run reports `documentsParsed: 1` and a new source id such as
   `SWIFT-MT-SR2026-MT535-MRG`.
3. `make knowledge-status` shows the source, its page and segment counts, its policy
   (`BLOCKED` unless you widened it) and the structure line for `MT535 SR2026`.
4. The catalogue (`GET /api/v1/catalogue`, the Create Message search, the Excel preview
   template list) now lists `MT535 · SR2026 · future release, test preview` with one of:
   - `GENERATION_READY` — the MRG's Format Specification, qualifier tables and codes were
     read, reconciled with the Prowide SR2025 evidence where it exists, and the compiled pack
     passed every gate. Generate, samples, Excel, import and the AI sample path all work in
     `lane=KNOWLEDGE_PREVIEW`.
   - `STRUCTURE_VERIFIED` — the pack generates and validates but does not parse back
     identically (`ROUND_TRIP_FAILED`). Search and citations work; generation is refused.
   - `STRUCTURE_AVAILABLE` — typically `QUALIFIER_EVIDENCE_MISSING` when a qualifier table
     could not be read, `FORMAT_FIDELITY_PARTIAL` for a format the notation compiler cannot
     render faithfully, or `SEQUENCE_OMITTED_CODE_UNKNOWN:<path>` when a sequence's block
     code was not found. The readiness report names the row.
   - `KNOWLEDGE_ONLY` — the document is searchable but no structure could be compiled
     (`STRUCTURE_SOURCE_MISSING`).
5. `make knowledge-reports-write` and commit the three reports if you want the repository's
   record to reflect the new state. No Python, YAML or TypeScript changes are involved; the
   Phase 6 proof of this used the SR2026 MRGs for MT537, MT540, MT541, MT543–MT549 and
   MT564–MT567, all of which reached `GENERATION_READY` without message-specific code.

A guide for a message the configured lane already serves in the same current-live release
is *shadowed* in the catalogue (the reviewed pack is the authority); a future-release guide
for such a message is listed as its own entry — MT541 SR2026 beside configured MT541.

## 8. Adding another MX schema

1. Copy the schema into the MX folder: `swiftKnowledgeBase/MX/camt.053.001.13.xsd` (or a
   ZIP of schemas).
2. `make knowledge-sync`, or press **Sync Knowledge Base** on `/knowledge-base` when the
   backend runs in `local_uat`. The run reports the new `ISO20022-XSD-camt.053.001.13` source
   and `structuresCompiled: 1`.
3. The structure is `GENERATION_READY` when the six gates pass — registry load, sample,
   compose, validation against the supplied XSD itself, rejection of invalid variants, round
   trip — which is what happened for all eight pacs schemas on the measured run. A schema
   that fails a gate is listed with the failing gate and the blocker.
4. Address the message by its full version in the preview lane:
   `GET /api/v1/messages/camt.053.001.13/spec?format=MX&lane=KNOWLEDGE_PREVIEW`. Generated
   documents are validated against the supplied XSD at runtime, not only at compile time.

## 9. Troubleshooting

| Symptom | Meaning | What to do |
|---|---|---|
| `UNSUPPORTED_EXTENSION` in `failures` | The suffix is not in the supported set | Convert or leave it; it is harmless |
| `KNOWLEDGE_SOURCE_UNREADABLE` (encrypted PDF / no pages) | The PDF could not be read | Supply an unencrypted copy |
| `KNOWLEDGE_SOURCE_UNSUPPORTED` | Readable bytes in a format the identifier does not handle | Supply PDF, XSD or text |
| Source state `EMBEDDING_BLOCKED`, `embeddingBlockedSegments > 0` | Policy, not an error; lexical search works | Leave it, or widen the policy deliberately (§5) |
| `semanticReason: EMBEDDING_PROVIDER_UNAVAILABLE` | No deployment configured or `EMBEDDING_PROVIDER=disabled` | Set `EMBEDDINGS_DEPLOYMENT` with the endpoint and key; `make probe-embeddings` |
| `EMBEDDING_AUTHENTICATION_FAILED` / `EMBEDDING_RATE_LIMITED` | The provider refused | Check the deployment name; rate limits are retried with backoff then reported |
| `loadErrors` in status | A compiled pack could not be loaded by the preview registry | `make knowledge-reindex`; the gate detail names the pack |
| `UNIDENTIFIED-…` source | No dominant message identifier in a note | Name the message clearly in the body, or accept it as searchable-only |
| "Knowledge Base has not been indexed yet" | No database | `make knowledge-sync`; configured messages work meanwhile |
| Page says `Mode: disabled` / `Not indexed` right after a successful sync, and the catalogue lists only the configured messages | The **server** process has no `KNOWLEDGE_MODE`. The Make targets export `local` for themselves; `make backend`, `make dev` and `scripts/start-dev.sh` do not, so the server falls back to the `disabled` default and `_preview_entries()` returns nothing however complete the database is | Put `KNOWLEDGE_MODE=local_uat` in the project-root `.env` so the CLI and the server read the same value, then restart the backend — or start it with `make knowledge-dev` |
| Widening the policy in §5 changes nothing; sources stay `EMBEDDING_BLOCKED` | The policy is resolved once, at parse time, and stored on the source row. An incremental sync skips an unchanged hash before it re-derives anything | `make knowledge-reindex`, not `make knowledge-sync` |
| Sources that were indexed before are suddenly `sourcesDeleted` and their catalogue entries are gone | The run used a narrower `KNOWLEDGE_SOURCE_DIR` than the one that indexed them; anything outside the roots of the current run is tombstoned | List every root at once, e.g. `KNOWLEDGE_SOURCE_DIR=swiftKnowledgeBase,build/mx-real-sources` |
| Structures reused after a compiler change | Reuse is keyed on `PACK_COMPILER_VERSION` | Bump the version (done for `/2`) or `make knowledge-clean-cache` then sync |

## 10. Git hygiene

The authorised source tree is committed through Git LFS (see
[knowledge-repository.md](knowledge-repository.md)); what stays out of Git is everything
derived from it. Before committing, this must print nothing:

```bash
git ls-files | grep -Ei '\.(sqlite3?)$|^build/'
git ls-files swiftKnowledgeBase | grep -vE '\.(pdf|xsd|zip|json)$'
```

and `make knowledge-verify` must pass on the checkout. `.env`, credentials, browser state
and the operator's scratch files never enter Git; `make secret-scan` and the `.gitignore`
entries enforce it.

## Where this lives

```
backend/app/knowledge_base/discovery.py     roots, suffixes, ZIP limits, hashing
backend/app/knowledge_base/identify.py      identity, classification, dominance rule
backend/app/knowledge_base/policy.py        policy_for, policy_statement
backend/app/knowledge_base/index.py         incremental sync, tombstones, manifest
backend/app/knowledge_base/__main__.py      sync / status / clean-cache / probe-embeddings / evaluate-rag / reports
backend/app/knowledge_base/paths.py         KNOWLEDGE_* path resolution
backend/tests/fixtures/knowledge/           the synthetic corpus (MT999 SR2026/SR2027 guides, MT998 note, test.001 XSD)
Makefile                                    knowledge-* targets
.env.example                                every KNOWLEDGE_* and EMBEDDING_* name
```

## Limitations

- Identity depends on a readable cover page (MRG) or `targetNamespace` (XSD); a scanned PDF
  without a text layer is `KNOWLEDGE_SOURCE_UNREADABLE`.
- Only MT MRGs of the MyStandards layout the Phase 5B reader understands yield structure;
  other MT documents are indexed for search only.
- Tables the PDF reader cannot reconstruct are recorded as partial; the affected pages are
  listed on the source and the structure reports `QUALIFIER_EVIDENCE_MISSING` or
  `FORMAT_FIDELITY_PARTIAL` rather than guessing.
- Policy is per classification, not per document; there is no per-file allow list.
- Release lanes come from the recorded `RELEASE_LANES` table; a release outside it is
  `UNKNOWN` and is neither current-live nor future-test.

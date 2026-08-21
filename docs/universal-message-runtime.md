# Universal message runtime

The runtime has two explicit lanes and one generation service.

| Lane | Source | Authority | How selected |
|---|---|---|---|
| `CONFIGURED` | committed MT/MX specification packs | repository-configured subset | default |
| `KNOWLEDGE_PREVIEW` | local Structure Packs compiled from operator sources | structure only unless separately reviewed rules exist | caller must name lane and release |

Both lanes resolve a `MessageSpec`, accept canonical values, and enter `StudioService`.
That service remains the only owner of composition, layered validation, FIN/AppHdr output,
XML well-formedness, XSD validation, checksums, persistence and provenance. Knowledge and
AI code cannot render or validate a message.

## Catalogue startup

`GET /api/v1/catalogue?includePreview=false` is the startup projection. It reads only the
committed registries, returns an ETag, and never opens the knowledge database or calls an
AI/embedding provider. Create Message renders it first and requests the default complete
catalogue in the background. A shared browser single-flight cache prevents React remounts
and route changes from duplicating calls.

The complete projection and serialized response are cached in process. Knowledge sync and
preview reload invalidate both caches. MX paths use an index, and sample-cache availability
is read in one SQLite query rather than one connection per message.

## Dynamic structure boundary

Knowledge sync may compile MT structures from pinned Prowide structural evidence plus a
source guide, and MX structures from XSDs. A structure becomes generation-ready only after
load, sample, composition, validation, rejection and round-trip gates pass. A searchable
source without those proofs remains `KNOWLEDGE_ONLY` or `STRUCTURE_AVAILABLE` and is never
offered as generatable.

JSON generation and Excel already consume the same catalogue/spec/service contracts, so a
new generation-ready pack needs no message-specific controller or spreadsheet code. Preview
requests must include `lane: KNOWLEDGE_PREVIEW` and the exact release/version.

## Readiness

- `/api/health/live` proves only that the process answers.
- `/api/health/ready` checks the database and configured MT/MX registries.
- Knowledge, AI and embeddings are reported separately as optional states.

Create Message waits only for the configured catalogue. An unavailable optional service
cannot prevent deterministic configured-message work.

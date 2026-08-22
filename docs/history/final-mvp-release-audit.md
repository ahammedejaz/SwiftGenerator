# Final MVP release audit

Every route, endpoint, engine, cache, database and boundary of the Financial Message
Studio, with a verdict. Measured on branch `feat/final-mvp-release-hardening` at
`d19835a`, base main `e8a77f8`, on 2026-08-22, with the committed Git-LFS knowledge base
present and AI credentials configured. `NOT_APPLICABLE` means the item does not exist in
this product, not that it was skipped.

Verdicts: **PASS** · **FAIL** · **PARTIAL** (works, with a stated boundary) ·
**NOT_APPLICABLE**.

---

## 1. Browser routes

| Route | Verdict | Evidence |
|---|---|---|
| `/` Create Message | PASS | Format → area → message → sample → edit → validate → generate walked on `127.0.0.1` and `localhost`; 496 catalogue entries load configured-first then enrich |
| `/excel` Bulk / Excel | PASS | Both templates download; both upload and generate 3/3 scenarios; preview-lane template picker present |
| `/intelligence` Message Intelligence | PASS | Deterministic search over MT tags and MX elements; "Ask the indexed source material" answers with citations |
| `/validate` Validate | PASS | Field data and pasted message, both modes |
| `/automation` API & Automation | PASS | curl, Java/REST Assured, Python and JavaScript snippets; Swagger UI and `openapi.json` linked |
| `/convert` Convert Message | PASS | Fixed this engagement — see §7 |
| `/recent` Recent Messages | PASS | 50 most recent, both formats, reopenable |
| `/ai-efficiency` AI & Knowledge Usage | PASS | Operations, calls, tokens, cache-hit rate, RAG queries, retrieved sections, embedding state |
| `/knowledge-base` Knowledge Base | PASS | 164 sources, 16,656 segments and embeddings, 489 structures, last run, policy statement |
| `/advanced` and the legacy screens | PASS | Reachable from the shell; unchanged |
| Dead links or empty screens | PASS | None found |
| Refresh-required behaviour | PASS | None found; every route renders on direct URL, refresh, back and forward |
| Mobile (390 × 844) | PASS | `studio-screens.spec.ts` "works on a phone" and "never scrolls the page sideways" |
| Application console errors | PASS | **0** across the whole walk; the only exceptions come from a browser extension (gotcha 58) |

## 2. `/api/v1` endpoints

| Endpoint | Verdict | Note |
|---|---|---|
| `GET /catalogue` | PASS | 496 entries: 481 MT + 15 MX; lane, release, readiness, blockers |
| `GET /coverage`, `GET /sources` | PASS | Measured from the components, never declared |
| `GET /messages/{m}/spec` | PASS | Now also carries `formatNotation` |
| `GET /messages/{m}/samples`, `/samples/{variant}` | PASS | Preview lane offers MINIMAL and FULL; TYPICAL is the AI path |
| `POST /messages/validate` | PASS | Nine or ten layers, reported individually |
| `POST /messages/generate` | PASS | 57 of 57 generation paths exercised, all valid |
| `POST /messages/import` | PASS | MT FIN, MT Block 4, MX, both lanes; every round trip `identical` with 0 unexplained |
| `POST /messages/diff` | PASS | Every difference attributed |
| `POST /messages/convert` | PASS | Fixed this engagement — see §7 |
| `GET /messages/{s}/conversion-targets` | PASS | Evidence class and convertibility on every target |
| `GET /templates/{format}.xlsx` | PASS | MT 34 KB, MX 21 KB, preview-lane variant 12 KB |
| `POST /messages/generate-from-excel` | PASS | 3/3 scenarios per format |
| `GET /messages/recent`, `/id/{id}`, `/download/{output}`, `/evidence.zip` | PASS | Download and a valid ZIP |
| `GET /intelligence/search`, `/field` | PASS | Deterministic; no model call |
| `GET /knowledge/status`, `/messages`, `/messages/{m}/status`, `/sources`, `/telemetry` | PASS | |
| `POST /knowledge/search` | PASS | `HYBRID` retrieval on this machine (embeddings permitted by the operator) |
| `POST /knowledge/sync` | PASS | 404 outside `KNOWLEDGE_MODE=local_uat`, by design (gotcha 55) |
| `POST /ai/samples`, `/messages/identify`, `/messages/prepare`, `/test-data/generate`, `/presentation`, `/ask`, `/releases/compare` | PASS | All answer; cache reports HIT with 0 model calls on repeat |
| HTTP error contract | PASS | Every 4xx is `{error:{code,message,details,requestId}}`; no stack trace; no 5xx in any probe |

## 3. Message engines

| Component | Verdict | Note |
|---|---|---|
| MT resolver / validator / composer | PASS | 16 configured + 465 preview entries |
| MT parser (import) | PASS | The exact inverse; runs the real `plan_sequences` |
| FIN envelope | PASS | Fails closed rather than inventing session/sequence numbers |
| MX resolver / validator / composer | PASS | 7 configured + 8 preview |
| MX parser (import) | PASS | Refuses nested repeats rather than collapsing them |
| XSD validation | PASS | Operator-supplied schemas where present, else `SUBSET_DERIVED` |
| AppHdr consistency | PASS | |
| Excel template builder and parser | PASS | Same composer as the UI and the API |
| Round trip `Compose(Parse(Compose(v)))` | PASS | Asserted for every configured sample and all golden fixtures |
| Occurrence model (`plan_sequences`) | PASS | One definition, shared by composer and parser |

## 4. Structure coverage

| Item | Verdict | Value |
|---|---|---|
| MT catalogue entries | PASS | 481 (16 configured, 465 preview) |
| Generation-ready entries | PASS | 424 |
| Distinct MT types | PASS | 271 |
| Types with a ready structure | PARTIAL | 258 / 271 |
| SR2026 ready | PASS | 210 / 210 |
| SR2025 ready | PARTIAL | 198 / 255 |
| MX generation-ready | PASS | 15 / 15 |
| Universal generation matrix | PASS | 408 / 408 preview structures |
| 13 blocked MT types | EXTERNAL_AUTHORITY_REQUIRED | §9 |

## 5. Semantic rules

| Item | Verdict | Value |
|---|---|---|
| Guides read | PASS | 156 (0 unreadable) |
| Rules discovered | PASS | 911, one disposition each |
| Exact | PASS | 345 |
| Partial (weaker than source) | PASS | 115 |
| Unsupported, with a recorded reason | PARTIAL | 451 |
| Review-required candidates | PASS | 460 |
| Reviewed / runtime activations | PASS | 0 / 0 — the gate holds |
| Reviewer packages | PASS | 156, one per message, with rule id, page, AST and residual |
| Rule evaluation determinism | PASS | `make mt-mrg-evaluate` 29/29 |
| SR2026 leaking into SR2025 | PASS | None; the lane is a recorded constant, never a clock comparison |

## 6. Mapping and conversion

| Item | Verdict | Note |
|---|---|---|
| Mapping engine | PASS | Declarative packs, exact resolution, checksum-gated |
| Evidence classes | PASS | Five, never relabelled |
| `SOURCE_BACKED` packs | EXTERNAL_AUTHORITY_REQUIRED | **0** — the corpus holds no field-level mapping material |
| `NAME_CORRESPONDENCE` / `TARGET_RELATIONSHIP_ONLY` / `SYNTHETIC` | PASS | 1 / 1 / 1 |
| Preview opt-in before a non-production pack executes | PASS | Explicit checkbox, per conversion |
| Occurrence-aware references | PASS | Pack refs carry sequence and occurrence through the canonical model |
| `NEEDS_INPUT` rather than invention | PASS | Asserted; every prompt now carries a question |
| MT103 → pacs.008 | PASS | READY, XSD accepted (was: never completed) |
| MT202 → pacs.009 | PASS | READY, XSD accepted |
| MT541 → sese.023 | PASS | READY, XSD accepted |
| Structure-checksum gate | PASS | Refuses a pack whose specification moved; `packs --refresh-checksums` is the fix |

## 7. Defects found and fixed this engagement

| # | Severity | Defect | Verdict now |
|---|---|---|---|
| 1 | BLOCKING | `127.0.0.1:3000` never hydrated; Create Message loaded for ever, no API request made | PASS |
| 2 | BLOCKING | Convert Message refused every candidate conversion; `targetLane` omitted | PASS |
| 3 | BLOCKING | MT103 → pacs.008 unreachable: SWIFT decimal comma into an ISO decimal; `SYN` currency | PASS |
| 4 | HIGH | 599 preview rows downgraded from `CURRENCY`/`DATETIME` to plain text | PASS |
| 5 | HIGH | Conversion asked for missing data with an empty question | PASS |
| 6 | MEDIUM | Raw Prowide notation as the "expected format"; dead currency box on composite amounts | PASS |
| 7 | LOW | Knowledge sync counted its own manifest as an unsupported source | PASS |

## 8. AI, RAG and caches

| Item | Verdict | Note |
|---|---|---|
| Embeddings | PASS | `azure_openai`, 3,072 dimensions, 16,656 vectors |
| Retrieval | PASS | `HYBRID` on this machine; lexical-only under the default policy |
| RAG answer quality | PASS | Source-aware, release-aware, cited, `SUPPORTED` verdict |
| AI Typical Sample | PASS | Validated by the deterministic engine before it reaches the form |
| Sample cache | PASS | Repeat call reports `Cache: HIT — 0 model calls` |
| Cache invalidation | PASS | Key spans structure checksum, rule packs, prompt, schema, provider, model, lane, release |
| Deterministic endpoints make 0 model calls | PASS | Asserted by test and by the Playwright network watch |
| LLM writing FIN or XML | PASS | Impossible — the composer is the only writer |
| Prompt injection from source text | PASS | Fenced, closed response schema |
| AI failure fallback | PASS | `test_degraded_mode.py`: deterministic seed, never an error screen |
| RAG / embedding failure fallback | PASS | Generation, validation and the catalogue unaffected |
| Knowledge database missing | PASS | Studio keeps working; status endpoint answers |
| Telemetry contains no secrets or source text | PASS | Content-free ledger |

## 9. External capability boundaries — not defects

| Boundary | Class |
|---|---|
| 13 MT system message types (MT021, 023, 035, 043, 048, 049, 056, 063, 074, 090, 092, 094, 096) have no deterministic structure evidence in any supplied release | EXTERNAL_AUTHORITY_REQUIRED |
| 451 of 911 Network Validated Rules have no sound weaker-or-equal expression | EXTERNAL_AUTHORITY_REQUIRED |
| No Mapping Pack is `SOURCE_BACKED` | EXTERNAL_AUTHORITY_REQUIRED |
| The four `sese` lifecycle specifications remain `UNVERIFIED` | EXTERNAL_AUTHORITY_REQUIRED |
| XSD is `SUBSET_DERIVED` unless the operator supplies the official schema | EXTERNAL_AUTHORITY_REQUIRED |
| No SWIFT certification, no live network, no conformance claim | EXTERNAL_AUTHORITY_REQUIRED |
| Import cannot represent a repeatable block nested inside another; detected and refused | FUTURE_ENHANCEMENT |
| Rate limiter, AI circuit breaker and L1 cache are per process | FUTURE_ENHANCEMENT |
| No production identity-provider adapter, KMS/HSM or penetration test | FUTURE_ENHANCEMENT |

## 10. Security

| Item | Verdict |
|---|---|
| `make secret-scan` | PASS |
| No `.env`, credential, session state, knowledge database, vector cache, AI cache or browser profile tracked | PASS |
| Automation key comparison (`hmac.compare_digest`, never echoed) | PASS |
| `/api/v1` open only in `development`/`test`; 503 elsewhere until keys exist | PASS |
| Source-document handling: no symlink following, ZIP byte and ratio limits, never writes an original | PASS |
| XSD external-entity handling | PASS |
| Path traversal on downloads and evidence ZIP | PASS |
| Excel formula injection | PASS |
| HTML and XML escaping | PASS |
| Cross-message, cross-release and cross-lane leakage | PASS |
| CORS ordering and preflight exemption | PASS |
| `make audit` (`pip-audit`, `npm audit --omit=dev`) | PASS |

## 11. Build, packaging and release

| Item | Verdict |
|---|---|
| `make check` (13 sub-targets) | PASS |
| Backend suite | PASS — 1,639 passed, 27 skipped, 6 deselected |
| `ruff` / `mypy --strict` (238 files) | PASS |
| `eslint` / `tsc --noEmit` / `next build` | PASS |
| Playwright | PASS — 98 / 98 |
| `docker compose config` / `build` | PASS |
| `docker compose up` runtime | PASS — backend healthy, frontend serving, MT and MX generated in-container |
| Clean clone in a separate directory, no `.env`, no keys | PASS — install → migrate → knowledge-verify 164/164 → check → e2e |
| `git diff --check` | PASS |
| Git LFS knowledge base | PASS — 164 / 164 verified, real bytes |
| CI, six jobs on the exact head | PASS |

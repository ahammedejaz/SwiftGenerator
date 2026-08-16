# Overnight Platform Audit and Implementation Plan

**Date:** 2026-08-16
**Scope:** Full-repository audit of the AI-assisted financial messaging platform, followed by an
autonomous implementation plan for the highest-value pending capabilities.
**Baseline:** 257 backend tests green, `git` repository initialised with **no commits yet**
(entire tree is staged/untracked).

---

## 1. Current repository status

| Area | State |
|---|---|
| Backend | FastAPI + SQLAlchemy + Alembic, Python 3.13 venv at `backend/.venv`, 18,419 LOC across 108 modules |
| Frontend | Next.js 16 / React 19 / Tailwind 4, 3,942 LOC, 17 routes, 22 components |
| Tests | 257 backend tests pass (`pytest -q`), 9 Playwright specs, golden files for 17 MT messages |
| Migrations | 6 Alembic revisions, all applied cleanly |
| Docker | `docker-compose.yml` + `docker-compose.production.yml`, both backend and frontend Dockerfiles present |
| Git | **No commits.** `main` branch exists but is empty. 267 paths staged/untracked |
| Docs | 30 Markdown documents at root — heavily overlapping, several superseded |
| Secrets | `.env` contains a live `OPENROUTER_API_KEY`; `.gitignore` correctly excludes `.env` |

---

## 2. Current architecture

```
frontend (Next.js, 17 routes)
   │  fetch → NEXT_PUBLIC_API_BASE_URL
   ▼
FastAPI app/main.py
   ├── app/api/routes.py            (public, unauthenticated demo API — 60+ endpoints)
   └── app/authoring/routes.py      (session-authenticated, CSRF, RBAC, tenant-scoped drafts)

Domain
   app/domain/models.py             SettlementScenario — a *fixed business shape*
   app/domain/validation/engine.py  scenario-level rules
   app/composers/*                  9 hand-written MT composers (scenario → text)
   app/specifications/registry.py   spec registry (sequences + ordered field rows)
   app/knowledge/loader.py          Tag Intelligence knowledge base (1,719 YAML lines)
   app/authoring/composer.py        generic spec-driven Block 4 composer  ← strongest asset
   app/profiles/loader.py           client profiles (2)
   app/agents/*                     OpenRouter LLM + cache + telemetry + circuit breaker
   app/bulk/service.py              scenario-row Excel import
   app/samples/service.py           composer-generated annotated samples
```

---

## 3. What is working (do not break)

1. **Deterministic MT Block 4 composition** for 17 message types (MT530/537/540–548/564–568),
   validated by golden files.
2. **`app/authoring/composer.py` — the generic specification-driven composer.** It renders Block 4
   from `(specification, sequence instances, field rows + values)`, enforces sequence cardinality,
   parent/child nesting, `insertAfterTag` placement, field ordering by `row_number`, controlled-code
   checks and per-tag format regexes. This is the correct foundation for tag-level input and is
   currently reachable **only** through the authenticated draft workflow.
3. **Specification registry** — sequences and ordered, addressable field rows
   (`MT541-A-20C-SEME`) derived from the knowledge base.
4. **Tag Intelligence knowledge base** — business meaning, technical meaning, why-used, presence,
   conditions, format explanation, synthetic examples, dependencies, common mistakes, source
   provenance. Fully deterministic, **no LLM call**.
5. **AI subsystem** — OpenRouter client, HMAC-keyed exact-match cache, telemetry (tokens, cost,
   latency, calls-avoided), circuit breaker, budgets, privacy enforcement, deterministic fallback.
6. **Security** — session HMAC cookies, CSRF, RBAC, tenant isolation, field-level encryption,
   safe-error envelope, rate limiting, request-size caps, safe logging.
7. **Lifecycle correlation** — MT541 → MT548 → MT545 with correlation validation.
8. **Bulk Excel (scenario-level)** with evidence ZIP, per-row validation JSON and summary workbook.

---

## 4. What is broken

| # | Finding | Evidence |
|---|---|---|
| B1 | **The primary generation API emits a fabricated FIN envelope.** `POST /api/messages/generate` returns `{1:DEMONSTRATION}` / `{2:MT541}` / `{4:…-}`. `{1:DEMONSTRATION}` is not a valid Basic Header and `{2:MT541}` is not a valid Application Header. | `app/composers/dvp_instruction.py:47`, verified live against a running server |
| B2 | Every hand-written composer repeats the same fake header lines. | `composers/*.py` (9 files) |
| B3 | The **real** FIN envelope builder exists but is unreachable from the main flow — it lives behind `POST /api/messages/{draftId}/exports/fin`, requiring login, CSRF, a draft, and manually typed session/sequence numbers. | `app/authoring/service.py:259` |
| B4 | `frontend/data/reports/*.zip` — 18 generated artefacts committed into the working tree. `.gitignore` covers `frontend/data/` but the files predate it and are untracked clutter. | `ls frontend/data/reports` |
| B5 | `backend/.mypy_cache`, `.ruff_cache`, `tsconfig.tsbuildinfo`, `.DS_Store` present in the tree. | `find` |
| B6 | No git history at all — nothing is recoverable, nothing is reviewable. | `git log` → *"does not have any commits yet"* |

---

## 5. What is partially implemented

- **MX / ISO 20022: entirely absent.** No XML, no namespaces, no AppHdr, no XSD, no `sese.*`.
  `MessageType` is a closed enum of 16 MT types.
- **Excel automation** is scenario-shaped (one row = one message, 28 business columns), not
  tag-level. Automation testers cannot express `Sequence/Tag/Qualifier/Value` and cannot express
  repeating sequence occurrences.
- **Output modes**: Block 4 and FIN exist only in the authoring service; the public API returns one
  `rawMessage` string with no output-mode choice, no checksum, no canonical JSON.
- **Samples**: one "golden path" variant per message type. No minimal / typical / full variants.
- **Message Intelligence**: MT tags only, and the search endpoint is `/api/knowledge/search`
  under the name *Tag Intelligence*.

---

## 6. What is demo-only

- `{1:DEMONSTRATION}` header literal.
- `SYNTH/` prefix hard-coded onto every `95R` party value in the settlement composers.
- `POST /api/demo/reset` seeding a fixed lifecycle.
- Profiles named `BASE_DEMO_V1` / `BFS_CLIENT_DEMO_V1` with `status: DEMO`.
- `DEMO_PHRASE` pre-filled in the guided generator.
- The dashboard advertises 13 workflows, several of which are demo narratives rather than tasks.

---

## 7. MT coverage

| Message | Composer | Golden test | Spec rows | Generatable from public API |
|---|---|---|---|---|
| MT530 | yes | yes | 7 | via `/api/settlement/commands` |
| MT537 | yes | yes | 19 | via `/api/penalties/generate` |
| MT540/541/542/543 | yes | yes | 14–15 | yes (`/api/messages/generate`) |
| MT544–MT547 | yes | yes | 13–14 | only as a lifecycle response |
| MT548 | yes | yes | 9 | only as a lifecycle response |
| MT564–MT568 | yes | yes | 10–22 | via `/api/corporate-actions/*` |

**Domain-rule gap (documented, not silently fixed):** the configured subset renders
`:22F::SETR//BUY` in Sequence B and `:22F::SETR//RECE` in Sequence E. In the authoritative ISO 15022
Category 5 format `22F::SETR` appears in Sequence E only, and receive/deliver direction is implied
by the message type. Correcting this requires an authoritative format import; it is recorded in
`LIMITATIONS.md` and surfaced in the API as a domain-rule gap rather than being invented here.

## 8. MX coverage

**Zero.** This is the single largest functional gap against the brief.

## 9. Excel / API coverage

| Capability | State |
|---|---|
| MT scenario-level Excel template + upload | works |
| MT **tag-level** Excel | missing |
| MX element-level Excel | missing |
| `POST /api/v1/messages/generate` JSON contract | missing (only scenario-shaped `/api/messages/generate`) |
| Automation authentication | missing (either fully open demo API or interactive cookie session) |
| Machine-readable validation with `ruleId`/`severity`/`suggestion` | present in `ValidationFinding` — good, reuse it |
| OpenAPI | auto-generated by FastAPI at `/docs` |

## 10. UI/UX problems

1. **13 top-level workflow cards.** A manual tester cannot tell where to start.
2. There is **no single "Create Message" flow**. Message creation is split across
   `/guided`, `/expert`, `/message-builder`, `/lifecycle`, `/settlement-processing`,
   `/penalties`, `/corporate-actions` — seven entry points for one job.
3. The guided flow **opens with a free-text box and an LLM call** — an unnecessary AI dependency
   for a tester who already knows they want an MT541.
4. Format (MT vs MX) is never a user-visible concept.
5. No progressive disclosure: field sets are all-or-nothing; there is no
   `+ Add Optional Field` and no `+ Add Another` for repeatable sequences.
6. No per-field information affordance in the builder — Tag Intelligence lives on a separate page.
7. Validation output is a raw findings list with `ruleId` and `technicalExplanation` exposed first.
8. Downloads require the authenticated draft flow.
9. Header/footer carry three paragraphs of legal disclaimer above the fold.

## 11. Security gaps

| # | Gap | Action |
|---|---|---|
| S1 | `.env` holds a live OpenRouter key on disk; correctly gitignored, but must be verified never committed | Add a pre-commit secret scan + `make secret-scan` |
| S2 | No automation/service authentication model — `/api` is wide open in development | Add `X-API-Key` service authentication, required outside development, keys only from environment |
| S3 | `AI_MODE=required` means a fresh clone with no key produces a hard failure on the guided flow | Default deterministic; AI strictly optional |
| S4 | 18 report ZIPs sitting in the working tree | Remove, keep `.gitignore` rule |
| S5 | No secret scan in the toolchain | Add |

## 12. Validation gaps

- MT: no FIN envelope validation (block presence, address format, message-type consistency).
- MX: none at all.
- The public API's validation surface is scenario-level; there is no tag-level or element-level
  validation endpoint that automation can call before generating.

## 13. Download / output gaps

- No Block-4-only vs FIN choice on the public API.
- No canonical JSON output.
- No checksum on the public API response.
- No MX XML / AppHdr / evidence ZIP.
- No download endpoint that does not require a session.

## 14. Test gaps

No tests exist for: FIN envelope construction, output modes, tag-level generation, MX anything,
tag-level Excel, the automation API, service authentication, or the new UI.

---

## 15. Recommended simplified target architecture

Additive. The existing domain, composers, knowledge base and authoring stack stay exactly where
they are; a new **Studio** layer sits on top and becomes the single entry point for both humans
and automation.

```
        UI (6 nav items)            Automation (REST / Excel / curl / REST Assured)
                │                                    │
                └──────────────┬─────────────────────┘
                               ▼
                      FastAPI  /api/v1/*
                               │
                    ┌──────────┴───────────┐
                    ▼                      ▼
              Input Adapters          AI Assistant
              ├─ JSON field rows      └─ intent interpretation only
              ├─ Excel (MT tags)         (never rendering/validation)
              └─ Excel (MX XPaths)
                    │
                    ▼
            Canonical Field Map   {rowId | xpath → value, occurrence}
                    │
                    ▼
            Message Specification    MT: specifications/registry
                    │                MX: studio/mx/registry (new)
           ┌────────┴────────┐
           ▼                 ▼
      MT Composer        MX Composer
   (authoring/composer,  (new, namespace + order aware)
    reused as-is)
           │                 │
           ▼                 ▼
      MT Validator       MX Validator
   (+ FIN envelope)      (+ XSD + AppHdr/Document consistency)
           └────────┬────────┘
                    ▼
              Output Service
              ├─ MT: BLOCK4 | FIN | TXT | CANONICAL_JSON
              ├─ MX: XML | APPHDR | DOCUMENT | CANONICAL_JSON
              └─ validation JSON/HTML, evidence ZIP
```

No microservices, no Kafka, no Kubernetes, no new abstraction layers.

---

## 16. Exact implementation priorities

| P | Item |
|---|---|
| **P1** | This audit + plan (this file) |
| **P2** | Studio catalogue + canonical field-map model + `/api/v1` skeleton + service auth |
| **P3** | **MT: proper configured FIN envelope.** Profile-driven Blocks 1/2/3/5, five-way field origin classification, no fabricated network values, output modes `BLOCK4 / FIN / TXT / CANONICAL_JSON`. Rock-solid MT541 |
| **P4** | **MX vertical slice: `sese.023`** — spec model, YAML spec, namespace-aware composer, AppHdr (`head.001.001.03`), validator, XSD hook, downloads |
| **P5** | **Excel → API → FIN/XML** — tag-level MT template, XPath-level MX template, `generate-from-excel`, multi-scenario, row-level errors |
| **P6** | **Message Intelligence** — unified MT tag + MX element search, deterministic, no LLM |
| **P7** | **UI rebuild** — 6 nav items, 6-step Create Message wizard, guided/expert modes, per-field info, plain-English validation, downloads |
| **P8** | Samples (minimal/typical/full), downloads, evidence ZIP |
| **P9** | Tests: backend unit/API, Playwright, lint, typecheck, build, migrations, Docker, secret scan |
| **P10** | `sese.024`, `sese.025` if the architecture holds |
| **P11** | Final report, git history, PR |

---

## 17. Files expected to change

**New — backend**
```
app/studio/__init__.py            app/studio/catalogue.py       app/studio/models.py
app/studio/service.py             app/studio/routes.py          app/studio/security.py
app/studio/mt/__init__.py         app/studio/mt/fin.py          app/studio/mt/generator.py
app/studio/mx/__init__.py         app/studio/mx/models.py       app/studio/mx/registry.py
app/studio/mx/composer.py         app/studio/mx/validator.py    app/studio/mx/apphdr.py
app/studio/mx/xsd.py              app/studio/mx/samples.py
app/studio/excel/__init__.py      app/studio/excel/mt.py        app/studio/excel/mx.py
app/studio/intelligence.py        app/studio/samples.py         app/studio/store.py
config/mx/sese.023.001.11.yaml    config/mx/sese.024.001.13.yaml
config/mx/sese.025.001.12.yaml    config/mx/head.001.001.03.yaml
alembic/versions/*_studio_messages.py
```

**Modified — backend**
```
app/main.py                 register studio router
app/config.py               FIN + automation-auth + MX settings
config/profiles/*.yaml      finEnvelope block
requirements.txt            + lxml
```

**New — frontend**
```
app/create/page.tsx         app/excel/page.tsx        app/intelligence/page.tsx
app/validate/page.tsx       app/automation/page.tsx   app/recent/page.tsx
app/advanced/page.tsx
components/studio/*         lib/studio-api.ts         lib/studio-types.ts
tests/e2e/studio-*.spec.ts
```

**Modified — frontend**: `app/layout.tsx`, `app/page.tsx`, `app/globals.css`.

## 18. Database changes

One additive, non-destructive migration creating `studio_messages`
(`id`, `created_at`, `format`, `message_type`, `profile_id`, `profile_version`, `scenario_id`,
`valid`, `error_count`, `warning_count`, `checksum`, `output_json`, `input_json`, `source`).
No existing table is altered or dropped.

## 19. API changes

Additive under `/api/v1`. Nothing existing is removed or renamed.

```
GET  /api/v1/catalogue
GET  /api/v1/messages/{messageType}/spec
GET  /api/v1/messages/{messageType}/samples[/{variant}]
POST /api/v1/messages/validate
POST /api/v1/messages/generate
POST /api/v1/messages/generate-from-excel
GET  /api/v1/templates/{format}.xlsx
GET  /api/v1/intelligence/search?q=
GET  /api/v1/intelligence/{elementId}
GET  /api/v1/messages/recent
GET  /api/v1/messages/{messageId}
GET  /api/v1/messages/{messageId}/download/{output}
```

## 20. UI changes

Primary navigation reduced from 13 cards to **6**: Create Message · Bulk / Excel ·
Message Intelligence · Validate Message · API & Automation · Recent Messages.
The 13 existing screens remain reachable from a single **Advanced** page so no working
functionality is destroyed.

## 21. Risks

| Risk | Mitigation |
|---|---|
| Inventing ISO 20022 structure | Configured subset, `authoritativeCompletenessKnown: false`, source flagged `CONFIGURED_SUBSET_REQUIRES_VERIFICATION`, surfaced in API + UI + LIMITATIONS |
| Official ISO 20022 XSDs not in repo | Derive a subset XSD from the configured spec (real libxml2 validation, honestly labelled `SUBSET_DERIVED`); prefer any official XSD dropped into `config/mx/xsd/official/` and report which was used |
| Fabricating FIN network values | Session/sequence are **profile-configured** and classified `PROFILE_CONFIGURED`; absent config → FIN output fails closed with a named error. Block 5 (MAC/CHK) never emitted unless profile-configured |
| Breaking the 257 green tests | Purely additive backend layer; full suite re-run after every phase |
| Scope overrun | Priority order is strict; MX depth is capped at three messages |
| `lxml` build failure on a clean machine | Wheels exist for macOS/Linux/Windows on Python 3.12–3.13; XSD validation degrades to `SKIPPED_NO_PARSER` if the import fails, everything else still works |

## 22. Acceptance criteria

The 50 criteria in §21 of the brief are adopted verbatim as the definition of done and are
re-tested and reported item-by-item in `OVERNIGHT_PLATFORM_IMPLEMENTATION_REPORT.md`.

---

## 23. Self-review of this plan

**Is the plan too ambitious?**
The MX portion is the risk. Mitigation: `sese.023` is a hard commitment; `sese.024`/`sese.025`
are explicitly P10 and will be dropped rather than half-built. The MT/Excel/API/UI work is
mostly *exposure and simplification* of assets that already exist and are already tested.

**Does anything duplicate working functionality?**
Initially yes — a first draft had a new MT composer. Corrected: the studio **reuses**
`app/authoring/composer.py` and `app/specifications/registry.py` unchanged. The nine
scenario composers are also kept; the studio adds a second, tag-level door into the same
specification, and the FIN envelope is applied as a wrapper rather than being re-implemented.

**Can any architecture be simplified?**
Yes, and the plan was cut three times:
- dropped a planned "MX canonical domain model" — the element-path map *is* the canonical model;
- dropped a planned MX-specific validation engine — one validator with pluggable checks;
- dropped a separate automation gateway service — one `X-API-Key` dependency on one router.

**Does every proposed feature add measurable user value?**
Re-checked. Two items were removed for failing this test: a real-time WebSocket validation
channel, and an MX↔MT translation engine (interesting, unrequested, and impossible to do
honestly without authoritative mapping tables).

**Can a manual tester understand the resulting UI?**
The wizard is linear and never shows more than one decision at a time. Field labels are
business names from the knowledge base, not tags. Tags are shown as secondary metadata.
Validation is stated as *"Ready to generate"* or *"N issues need attention"*.

**Can an automation tester consume the same functionality by API?**
Yes, and by construction: the UI calls exactly the same `/api/v1` endpoints. There is no
UI-only capability.

**Are MT and MX treated correctly and separately?**
Yes. `format` is a first-class discriminator from the catalogue down. MT produces FIN blocks and
never XML; MX produces AppHdr + Document and is structurally prevented from emitting FIN blocks.
The two have separate specs, composers, validators, Excel templates and sample sets, joined only
at the catalogue and the output envelope.

**Correction applied to the plan:** the original ordering put the UI before the API. That would
have forced UI rework once the automation contract settled. Reordered so the API contract lands
first and the UI is written against the final contract.

# Backend

The FastAPI service that generates, validates and imports SWIFT MT and MX messages.

**If you just want to run it:** `make backend` from the repository root, then
`http://localhost:8000/docs` for the auto-generated OpenAPI browser.

**If you want to understand the whole system:** read the root
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) first. This README is the local map — where each
subdirectory lives and what it owns — and assumes you already know the mental model
described there.

---

## Language, versions, and tooling

- **Python 3.13** (a `.venv/` at the top of this folder holds the interpreter)
- **FastAPI** for the HTTP surface, **Starlette** middleware, **Pydantic v2** models
- **SQLAlchemy 2** ORM · **Alembic** migrations · **SQLite** locally, **PostgreSQL** in prod
- **pytest** for tests · **ruff** for lint · **mypy --strict** for typing
- **libxml2** (via `lxml`) for XSD validation of MX messages
- **openpyxl** for the Excel importer

Every one of these is invoked via a `make` target at the repository root; you almost never
run the underlying command yourself. See the root [../README.md](../README.md) and
[../docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md).

---

## Directory map

```
backend/
├── alembic/                database migrations (one file per version)
│   ├── env.py              alembic entry — also ensures the SQLite folder exists
│   └── versions/           timestamped migration scripts
├── alembic.ini             alembic configuration
├── app/                    all runtime code
│   ├── main.py             FastAPI app factory · middleware · lifespan · routers
│   ├── config.py           Pydantic `Settings` (env-driven) · production invariants
│   ├── agents/             optional AI layer (OpenRouter, cache, circuit breaker)
│   ├── api/                the /api HTTP routes (predates the studio; still in service)
│   ├── authoring/          Block 4 composer, tenant-scoped drafts, RBAC
│   ├── bulk/               Excel workbook generation and batched processing
│   ├── composers/          scenario-shaped composers (DVP, FOP, corporate actions, ...)
│   ├── demo/               reset service for the shipped demo pack
│   ├── domain/             pure data models · enums · deterministic validation engine
│   ├── event_profiles/     corporate-action event registry
│   ├── external_validation/  boundary for third-party validators (stubbed)
│   ├── knowledge/          per-tag MT metadata · code lists · presentation rules
│   ├── knowledge_base/     local evidence index · retrieval · privacy-safe telemetry
│   ├── mapping/            exact Mapping Packs · deterministic conversion · loss reports
│   ├── persistence/        SQLAlchemy models · repositories · database factory
│   ├── profiles/           client-profile loader (envelope values, currencies, ...)
│   ├── raw/                subset MT parser used by the older validate-raw endpoint
│   ├── samples/            MINIMAL / TYPICAL / FULL sample generation
│   ├── security/           auth, encryption, rate limiting, security headers
│   ├── services/           orchestrating services (generation, lifecycle, workflows)
│   ├── specifications/     MT specification registry (loads YAML manifests)
│   ├── studio/             the current message studio — /api/v1 · MT + MX
│   │   ├── service.py      dispatch hub · six/nine validation layers · output selection
│   │   ├── routes.py       every /api/v1 endpoint
│   │   ├── models.py       request/response shapes
│   │   ├── mt/             MT (ISO 15022) generator · FIN envelope · parser
│   │   └── mx/             MX (ISO 20022) generator · registry · XSD · parser
│   └── workflows/          settlement, penalties, corporate-actions workflow services
├── config/                 the actual source of truth for messages (YAML)
│   ├── knowledge/          per-tag MT metadata + shared code lists
│   ├── specifications/     MT: sequence and row order per message
│   ├── mx/                 MX: element tree per message · optional official XSDs
│   ├── profiles/           client-profile definitions
│   ├── mappings/           reviewed/synthetic Mapping Packs
│   ├── mapping_sources/    mapping authority records and checksums
│   └── README.md           how the configuration is organised (start here)
├── data/                   the running SQLite database and any generated reports
├── evaluation/             benchmark datasets for the AI layer
├── tests/                  pytest suite (see below)
├── Dockerfile              production image
├── pyproject.toml          project metadata · ruff · mypy configuration
├── requirements.txt        runtime dependencies (pinned)
└── requirements-dev.txt    test/lint/type-check dependencies (pinned)
```

`config/` is the point of the whole product. See
[`config/README.md`](config/README.md) — most changes to what a message looks like are one
YAML edit in that folder, not a code change here.

---

## The entry point

`app/main.py` is small and worth reading top-to-bottom. It does four things:

1. Loads `Settings` from environment variables (`config.py`).
2. Builds a `lifespan` context manager that creates the database schema on startup and
   wires the optional AI service.
3. Registers middleware in a specific order — see the note below about CORS.
4. Registers the routers under `/api`, `/authoring` and `/api/v1`.

**The middleware order matters.** Starlette treats the last `add_middleware()` call as the
*outermost* layer. CORS is registered last on purpose so short-circuit responses (400,
413, 429) still reach the browser with the right `Access-Control-Allow-Origin` header. If
you reorder it you will find yourself debugging a "backend is down" error against a
backend that is running fine. The regression is guarded by
`tests/security/test_cors_and_throttling.py`.

---

## Two API surfaces

| Prefix | For | Auth |
|---|---|---|
| `/api/v1` | The **studio** — everything the current UI uses; the automation contract | `X-API-Key` header in production; open in `development`/`test` |
| `/api` | Legacy scenario-shaped endpoints; also authoring, workflows, AI health | Session cookie + CSRF; RBAC via roles |

Both are exposed by the same FastAPI app. New functionality goes on `/api/v1`. The `/api`
surface still serves the Advanced screens (lifecycle, penalties, corporate actions) and
is not being deleted.

The `/authoring` prefix is a third router: the maker-checker drafts flow, tenant-scoped
and encrypted at rest. Most contributors will never touch it.

---

## A request, end to end

```
POST /api/v1/messages/generate                app/studio/routes.py
              │
       StudioService.generate()               app/studio/service.py
              │
     ┌────────┴────────┐
     │                 │
  MT branch         MX branch
   resolve           resolve                  address → specification row
   validate          validate                 six / nine layers, reported individually
   compose           compose                  written in specification order
   FIN envelope      AppHdr + wrapper
                     XSD (libxml2)
     └────────┬────────┘
        GenerateResult                        message · validation · checksum · origins
              │
       studio_messages table                  optional; trims itself
```

Read [`app/studio/service.py`](app/studio/service.py) alongside this diagram — it is the
"room behind the three doors" that the architecture doc describes.

---

## Configuration and secrets

Every runtime setting lives in `app/config.py` as a Pydantic field with a validator.

- No `.env` is required for a clean clone. Every AI feature is off by default.
- In production (`APP_ENV=production`), a set of invariants is enforced at startup:
  PostgreSQL required, OIDC required, HMAC secret required for AI caching, ...
- **Secrets never appear in a response, a log line, or the source.** The environment is
  the only channel.

The full list of variables and their defaults is in
[../docs/configuration.md](../docs/configuration.md).

---

## Database and migrations

- Development uses SQLite at `data/securities_studio.db`.
- Production requires PostgreSQL — enforced in `config.py`.
- Migrations live in `alembic/versions/`. Never edit an existing migration once it has
  shipped; add a new one.
- `alembic/env.py` calls `ensure_database_directory` so `make migrate` works on a clean
  clone. If you delete that call, `tests/unit/test_setup_from_a_clean_clone.py` fails.
- Concurrency subtlety worth knowing about: `sqlite://` uses `QueuePool(pool_size=1,
  max_overflow=0)` — SQLite is single-writer and FastAPI runs sync endpoints in a
  threadpool. Guarded by `tests/unit/test_database_concurrency.py`.

---

## Tests

```
tests/
├── api/                          HTTP-level tests for the legacy /api surface
├── domain/                       unit tests for the pure data / validation core
├── golden/                       byte-for-byte MT regression fixtures
│   └── expected/*.txt            golden output; a change here needs a reason in the commit
├── security/                     CORS, throttling, encryption, headers
├── studio/                       tests for /api/v1 (generation, import, diff, ...)
└── unit/                         low-level components (identifiers, database, setup)
```

Run everything:

```
make test        # backend only, ~3 seconds
make check       # lint + typecheck + tests + coverage gate — run before every push
```

Targeted:

```
cd backend && .venv/bin/pytest tests/studio -q
cd backend && .venv/bin/pytest -k "fin_envelope" -q
```

Test names read as behaviour, not implementation, and assert on `ruleId` rather than
prose. The whole suite is designed to run without mocks — SQLite in memory, no network,
no LLM.

---

## Adding things

Most changes are **not code changes**. See
[../docs/ARCHITECTURE.md § Adding things](../docs/ARCHITECTURE.md#adding-things) for the full list;
the summary is:

| Task | Where |
|---|---|
| Add a field to an MT message | `config/knowledge/*.yaml` |
| Add or change a code list | `config/knowledge/code_lists.yaml` |
| Add an MX message | one file in `config/mx/` |
| Add a client profile | one file in `config/profiles/` |
| Add a validation rule | `MtGenerator._business_rules` or `MxGenerator._business_rules` (prefer YAML rules) |
| Add an output format | `OutputMode` → produce in `StudioService` → extension in `routes.OUTPUT_FILE_TYPES` |
| Add an endpoint | `app/studio/routes.py`, then update the frontend `studio-types.ts` and `studio-api.ts` |

---

## Where to read next

- [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — how the whole system fits together
- [config/README.md](config/README.md) — the configuration layout
- [../docs/configuration.md](../docs/configuration.md) — every environment variable
- [../docs/authoritative-sources.md](../docs/authoritative-sources.md) — installing a
  licensed spec or schema
- [../docs/AGENTS.md](../docs/AGENTS.md) — dense factual index maintained for AI coding tools;
  useful to humans too

# Configuration

Everything that changes behaviour without changing code.

---

## Environment variables

Copy `.env.example` to `.env` and edit. **Every secret is empty in the example and must
stay empty there** — `.env` is gitignored, `.env.example` is not.

Nothing below is required to run the tool locally. The defaults work.

### The ones you might actually change

| Variable | Default | What it does |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test` or `production`. Production enforces PostgreSQL, real authentication and secure cookies. |
| `DATABASE_URL` | `sqlite:///./data/securities_studio.db` | Where data lives. Production must be PostgreSQL. |
| `FRONTEND_ORIGIN` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed CORS origins, comma-separated. Both spellings of the same machine, so a tester who opens one is not refused for not choosing the other. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Where the browser looks for the API. An address, not `localhost`: a browser resolves `localhost` to `::1` first on a dual-stack machine, and the backend binds `127.0.0.1`. |
| `AUTOMATION_API_KEYS` | *(empty)* | Comma-separated service keys for `/api/v1`. Empty leaves the API open in development and closed elsewhere. Minimum 24 characters each. |
| `AI_PROVIDER` | `openrouter` | Set to `disabled` to switch the model off entirely. Nothing that makes a message depends on it. |
| `OPENROUTER_API_KEY` | *(empty)* | Only needed for the natural-language interpretation feature. |

### Limits

| Variable | Default | Guards against |
|---|---|---|
| `MAX_UPLOAD_BYTES` | `5242880` | Oversized workbook uploads |
| `MAX_REQUEST_BYTES` | `6291456` | Oversized request bodies |
| `MAX_BULK_ROWS` | `1000` | Runaway spreadsheets |
| `MAX_EXCEL_SCENARIOS` | `200` | One upload asking for too many messages |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `600` | General flooding |
| `AI_RATE_LIMIT_REQUESTS_PER_MINUTE` | `30` | Runaway model spend |

### Secrets

All optional locally; all must be set from a secret manager in production.

| Variable | Needed for | Rule |
|---|---|---|
| `SESSION_HMAC_SECRET` | Interactive login | ≥ 32 characters |
| `DATA_ENCRYPTION_KEY` | Encrypted drafts | base64 of exactly 32 bytes |
| `AI_CACHE_HMAC_SECRET` | The AI cache | ≥ 32 characters |
| `AUTOMATION_API_KEYS` | The automation API | ≥ 24 characters per key |

Generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"          # HMAC secret / API key
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"   # encryption key
```

`app/config.py` validates all of these at startup and refuses to boot on a bad value,
rather than failing later in a confusing place.

### The organisation AI endpoint (Phase 6)

An Azure OpenAI resource or any OpenAI-compatible server. Only the **origin** of the
endpoint is used; its path and query are ignored, except that an `api-version` query is
kept for the legacy deployment-scoped Azure surface. Each of the first three accepts an
older spelling as an alias, so an existing `.env` need not be renamed. Values are never
printed, logged or returned by any endpoint.

| Variable | Alias | Default | What it does |
|---|---|---|---|
| `AI_ENDPOINT` | `ENDPOINT` | *(empty)* | `https://…` origin of the resource. Must be HTTPS. |
| `AI_API_KEY` | `API_KEY` | *(empty)* | The key. Secret. |
| `AI_CHAT_DEPLOYMENT` | `MODEL` | *(empty)* | Chat deployment (Azure) or model name used for AI authoring. |
| `AI_API_VERSION` | — | *(empty → endpoint query → `2024-10-21`)* | Azure `api-version`. |
| `AI_MAX_OUTPUT_TOKENS` | — | `2000` | Ceiling per structured completion. |
| `EMBEDDINGS_DEPLOYMENT` | — | *(empty)* | Embedding deployment or model name. |
| `EMBEDDING_PROVIDER` | — | `auto` | `auto`, `azure_openai`, `openai_compatible`, `fake`, `disabled`. `auto` becomes `azure_openai` when the endpoint host is Azure's, `openai_compatible` when an endpoint and key exist, `disabled` otherwise. `fake` is for tests and CI only. |
| `EMBEDDING_DIMENSIONS` | — | *(unset)* | Sent as `dimensions` when set; every stored vector is checked against it on read. |
| `EMBEDDING_BATCH_SIZE` | — | `64` | Segments per embedding request. |
| `EMBEDDING_TIMEOUT_SECONDS` | — | `30` | Per request. |
| `EMBEDDING_MAX_RETRIES` | — | `3` | On 408/409/425/429/5xx. |

`AI_PROVIDER` keeps its meaning for the settlement-intent screen and now also accepts
`azure_openai` and `openai_compatible`. The AI authoring paths use the organisation endpoint
when all three of endpoint, key and chat deployment are set, fall back to OpenRouter when
that is what is configured, and are otherwise disabled — in which case every AI operation
returns its deterministic seed. `AI_PROVIDER=disabled` switches all of it off.

### The local knowledge base (Phase 6)

Off unless asked for, so a production-style process never reads arbitrary workstation
files. Sources stay in the operator's folder; everything derived lands under the ignored
`build/knowledge/`. Paths are relative to the project root.

| Variable | Default | What it does |
|---|---|---|
| `KNOWLEDGE_MODE` | `disabled` | `disabled`, `local` or `local_uat`. `local_uat` additionally enables `POST /api/v1/knowledge/sync`; everywhere else that route answers 404. |
| `KNOWLEDGE_SOURCE_DIR` | `swiftKnowledgeBase` | Comma-separated roots `make knowledge-sync` walks, e.g. `swiftKnowledgeBase,build/mx-real-sources`. Symlinks are never followed. |
| `KNOWLEDGE_DB_PATH` | `build/knowledge/knowledge.sqlite3` | The index: sources, segments, FTS5, vectors, sample cache, compiled-structure table. |
| `KNOWLEDGE_PACK_DIR` | `build/knowledge/packs` | Where compiled preview Structure Packs are written. |
| `KNOWLEDGE_SOURCE_CACHE_DIR` | `build/knowledge/source-cache` | Extracted ZIP members and cached XSDs. |
| `KNOWLEDGE_AUTO_SYNC_ON_START` | `false` | Run an incremental sync when the backend starts. |
| `KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED` | `false` | Global gate: may a source's text be sent to the embedding endpoint? |
| `KNOWLEDGE_EXTERNAL_LLM_ALLOWED` | `false` | Global gate: may a source's text be quoted to the chat endpoint? |
| `KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS` | `SYNTHETIC_FIXTURE` | Comma-separated classifications the two gates apply to: `SYNTHETIC_FIXTURE`, `OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL`, `OPERATOR_SUPPLIED_XSD`, `OPERATOR_SUPPLIED_DOCUMENT`, `LICENSED_UNKNOWN`. A source leaves the machine only when its gate **and** its classification both say so. An API key is never permission. |
| `KNOWLEDGE_MAX_SOURCE_BYTES` | `67108864` | Largest single file read. |
| `KNOWLEDGE_MAX_ZIP_MEMBER_BYTES` | `67108864` | Largest member extracted from a ZIP. |
| `KNOWLEDGE_MAX_ZIP_TOTAL_BYTES` | `268435456` | Largest total extracted from one ZIP; a 100:1 ratio is refused too. |
| `KNOWLEDGE_CONTEXT_CHARS` | `6000` | Retrieved-evidence budget handed to a prompt. |
| `KNOWLEDGE_AI_MAX_BATCH` | `20` | Ceiling on `count` for one AI test-data request; a larger request is clamped, not refused. |
| `KNOWLEDGE_AI_MAX_REPAIR_ATTEMPTS` | `3` | How many times validator findings are fed back to the model before a sample is refused. |
| `KNOWLEDGE_AI_REVIEWER_MODE` | `false` | Declared, validated, and **not yet read by any code path**. Whether `REVIEW_REQUIRED` candidate rules may be considered for negative test data is decided per request by the `reviewerMode` field of `POST /api/v1/ai/test-data/generate`, and even then no candidate rule is installed for runtime evaluation. |
| `KNOWLEDGE_AI_PROVIDER` | `auto` | `auto`, `scripted`, `disabled`. `scripted` returns each operation's deterministic seed with no network call and is honoured in `development` and `test` only; the process refuses to start with it elsewhere. |

Names and defaults live in `.env.example`. `make knowledge-status` prints the effective
mode, roots, provider and policy without printing any value that is secret.

---

## Client profiles

A **profile** is one client's rules. It lives in `backend/config/profiles/*.yaml` and
controls what the tool will accept and what it puts in the envelope.

Two ship with the repository: `BASE_DEMO_V1` (permissive) and `BFS_CLIENT_DEMO_V1`
(stricter — 12-character references, USD and EUR only). Switching profile on the Create
Message screen changes what validates.

```yaml
profileId: BASE_DEMO_V1
name: Base Demo Profile
version: 1.0.0

allowedCurrencies: [USD, EUR, GBP]      # anything else is a validation error

validation:
  senderReference:
    maxLength: 16                        # a longer reference is rejected
    uppercase: true

# Configured FIN interface values. Everything here is supplied by whoever configures the
# profile, which is why the studio labels these PROFILE_CONFIGURED rather than inventing
# them. Session and sequence numbers are ordinarily allocated by a messaging interface;
# these are configured test-interface values.
finEnvelope:
  senderLogicalTerminal: DEMOGB2LAXXX    # 12 chars: 8 BIC + 1 terminal + 3 branch
  receiverAddress: DEMOUS33XXXX
  applicationId: F
  serviceId: "01"
  sessionNumber: "0001"
  sequenceNumber: "000001"
  priority: "N"                          # N normal, U urgent
  includeMessageUserReference: true
  trailerFields: {}                      # MAC, CHK, PDE are refused even if listed here

# ISO 20022 header and transport values. `wrapperElement` is the element that carries the
# AppHdr and the Document together — a client or market convention, not part of ISO 20022,
# which is why it is configured rather than assumed.
mxEnvelope:
  fromBic: DEMOGB2LXXX
  toBic: DEMOUS33XXX
  businessService: swift.demo.subset
  priority: NORM
  wrapperElement: BusinessMessage
```

### Adding a profile

Drop a new YAML file in the folder and restart. It appears in the profile list on every
screen and in `GET /api/v1/catalogue`.

**If you omit `finEnvelope`,** that profile cannot produce a complete FIN message. Block 4
still works; FIN output fails closed with an error naming what is missing. That is
intentional — the alternative is inventing an address.

**If you omit `mxEnvelope`,** MX output contains the Document only, with a warning saying
the AppHdr must be transported separately.

---

## Message specifications

| Folder | Holds |
|---|---|
| `backend/config/knowledge/` | MT: what each tag means, in business language |
| `backend/config/specifications/` | MT: which sequences and rows each message has |
| `backend/config/mx/` | MX: the complete element tree, one file per message |
| `backend/config/mx/xsd/official/` | Optional official ISO 20022 schemas |
| `swiftKnowledgeBase/` (ignored) | Authorised PDFs, XSDs and ZIPs for the knowledge base; indexed by `make knowledge-sync`, served in the `KNOWLEDGE_PREVIEW` lane, never committed |

These are the source of truth for the API, the UI, the Excel templates and Message
Intelligence at once. Editing one YAML file changes all four.

See [how-messages-are-built.md](how-messages-are-built.md) for the shape of these files,
and [ARCHITECTURE.md](ARCHITECTURE.md#adding-things) for how to add a message.

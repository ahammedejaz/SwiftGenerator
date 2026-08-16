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

These are the source of truth for the API, the UI, the Excel templates and Message
Intelligence at once. Editing one YAML file changes all four.

See [how-messages-are-built.md](how-messages-are-built.md) for the shape of these files,
and [../ARCHITECTURE.md](../ARCHITECTURE.md#adding-things) for how to add a message.

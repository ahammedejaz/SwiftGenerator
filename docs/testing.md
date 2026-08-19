# Testing

**1,354 automated tests.** 1,274 backend, 80 in a real browser (plus 23 backend tests that skip unless their optional dependency is configured, and 1 live-AI test that is deselected by default).

---

`make install` installs the browser Playwright drives, so a machine that has never run it
still gets `make e2e` working. Nothing else needs configuring: no `.env`, no API keys.

Every one of these also runs in GitHub Actions on each pull request and on each push to
`main` — see `.github/workflows/ci.yml`, or §11 of [AGENTS.md](AGENTS.md). Reproducing
a CI job means running the same make target.

## Run everything

```bash
make check     # lint + typecheck + backend tests — run this before you push
make e2e       # browser tests (starts both servers itself)
```

Individually:

```bash
make test        # pytest
make lint        # ruff + eslint
make typecheck   # mypy + tsc
make build       # production frontend build
make coverage    # regenerate docs/generated/message-coverage.md, fail if stale
```

## Run one thing

```bash
cd backend
.venv/bin/pytest tests/studio -q                              # the studio suite
.venv/bin/pytest tests/studio/test_mx_generation.py -q        # one file
.venv/bin/pytest -k "fin_envelope" -q                         # by name

cd frontend
npx playwright test studio-create                             # one spec
npx playwright test --headed                                  # watch it happen
npx playwright test --debug                                   # step through it
```

---

## What is covered

### Backend — `backend/tests/`

| Folder | Tests | Covers |
|---|---|---|
| `studio/` | 694 | FIN envelope, MT and MX generation, import, the comparison, coverage, Excel, capability dimensions, the `/api/v1` contract |
| `unit/` | 193 | Resolver, profiles, identifiers, validation, AI service, cache, telemetry, security |
| `api/` | 63 | The original scenario API, bulk, samples, security, lifecycle |
| `spec_engine/` | 40 | XSD loader security, the compiler, pack gates, structural diff, provenance honesty, the end-to-end pack integration |
| `rule_engine/` | 233 | The rule DSL and its semantics, reference resolution, every compiler refusal, layer narrowing and conflict, the review gate, source ingestion and segmentation, the extraction pipeline against scripted providers, the injection boundary, the evaluation corpus, and the synthetic end-to-end proof |
| `knowledge/` | 17 | The MT knowledge base |
| `golden/` | 17 | Byte-for-byte MT output regression |
| `workflows/` | 16 | Settlement processing, penalties, corporate actions |
| `specifications/` | 13 | The manifest-driven dynamic registry |
| `security/` | 9 | CORS, throttling, encryption |
| `samples/` | 2 | Sample coverage |

The studio suite is worth knowing in detail, because it encodes the rules that matter:

**`test_fin_envelope.py`** — the envelope is real and refuses to invent

- Block 1 is exactly 25 characters and correctly structured
- No `DEMONSTRATION` placeholder survives anywhere
- Block 3 appears only with a message user reference
- Block 5 is absent unless the profile configures a permitted trailer
- Every forbidden trailer tag (MAC, CHK, PDE, PDM, DLM, TNG, SYS) is refused, parametrised
- A missing session or sequence number **fails closed**
- A request may legitimately supply what the profile lacks
- Nothing the platform emits claims to be a network-generated value

**`test_mx_generation.py`** — the XML is right

- Namespace matches the message version
- Elements are written in specification order **even when the inputs are reversed**
- MX never emits FIN blocks; MT never emits XML
- Choice elements reject two branches
- Repeated blocks render distinct values per occurrence
- XSD catches out-of-order elements, missing required attributes, bad patterns and bad enums
- The AppHdr `MsgDefIdr` matches the document namespace
- No wrapper is invented when none is configured
- Every sample of every MX message validates

**`test_mt_generation.py`** — addressing and validation

- Fields resolve by row id, by sequence/tag/qualifier, and by sequence path or code
- Ambiguous, unknown and duplicate addresses each produce their own named error
- Errors name the *business* field, not the tag
- Profile rules differ correctly between profiles
- Every sample of every MT message generates a FIN message

**`test_excel_api.py`** — the spreadsheet path

- Templates carry three sheets and the right columns
- Format is detected from the columns
- Headers match case- and space-insensitively
- Excel date cells convert back to ISO text; numeric cells do not gain a decimal point
- One bad scenario fails alone
- Upload guards: extension, path traversal, size, and actual OOXML validity

**`test_studio_api.py`** — the contract

- Catalogue declares completeness honestly
- Validation returns actionable errors, never a bare boolean
- A field value cannot smuggle FIN block fragments
- Message Intelligence **makes no model call** — asserted by comparing AI interaction counts
- Downloads preserve the exact bytes
- Service authentication behaves correctly, and a rejection never hints at the key

### Frontend — `frontend/tests/e2e/`

| Spec | Covers |
|---|---|
| `studio-create.spec.ts` | The full manual journey for MT541 and sese.023, field explanations, progressive disclosure, plain-English validation, envelope origins, download |
| `mt-authoring.spec.ts` | ISIN entry, SETR semantics, settlement parties, dropdowns, Guided/Expert mode switching |
| `studio-import.spec.ts` | Importing MT and MX back into the builder, the message-type picker, refusals, the cancellation lifecycle |
| `message-diff.spec.ts` | Original versus regenerated: the verdict, every reason, show-only-changes, copy, download, return to edit, phone width |
| `rule-overlays.spec.ts` | Reviewed market and client rule packs: narrowing, which layer refused, the evidence behind Technical details, correcting a value, Message Intelligence, phone width |
| `studio-screens.spec.ts` | Excel round trip both formats, Intelligence search, Validate, Automation examples, Recent Messages, responsive behaviour, accessibility basics |
| `guided`, `bulk`, `lifecycle`, `penalties`, … | The pre-existing Advanced screens |

Three structural assertions worth keeping:

- **No page scrolls sideways** at any of the tested widths — checked by comparing
  `scrollWidth` to `clientWidth` on every route.
- **Message Intelligence issues no model request** — checked by watching network traffic.
- **A network-generated trailer is never presented as a fault** — the comparison must show
  it as expected, with the alarming counters at zero.

> Stop any backend or frontend you started by hand before running `make e2e`.
> `reuseExistingServer` will reuse it, and a hand-started backend has a different
> environment from the one the config provides.

---

## Golden files

`backend/tests/golden/expected/*.txt` are review-controlled MT outputs. Any composer change
that alters raw text fails a byte-for-byte comparison.

That is deliberate friction. If you meant to change the output, update the fixture in the
same commit and say why in the message. If you did not mean to, the test just caught a bug.

---

## Writing a test

**Name it after the behaviour, not the function.**

```python
def test_missing_session_number_fails_closed(profile: ClientProfile) -> None:
    configured = _without(profile, session_number=None)

    with pytest.raises(FinEnvelopeUnavailable) as raised:
        build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=configured)

    codes = {issue.rule_id for issue in raised.value.issues}
    assert "FIN_SESSION_NUMBER_NOT_SUPPLIED" in codes
```

Guidelines that have earned their place here:

- **Assert the rule id, not the prose.** Messages get reworded; rule ids are the contract.
- **Parametrise over a set rather than picking one member.** The forbidden-trailer test
  covers all seven tags, so adding an eighth to the set automatically tests it.
- **Prefer a real end-to-end assertion to a mock.** The tests generate real messages and
  parse them with a real XML parser. They are fast enough: the whole backend suite runs in
  about three seconds.
- **In Playwright, query by role and accessible name.** `getByRole("button", { name: … })`
  breaks when a control stops being reachable — which is the point.

---

## Live AI tests

Marked `live` and deselected by default.

```bash
make test-live-ai      # needs a real OPENROUTER_API_KEY and spends money
```

`make test` never calls a provider.

# Financial Message Studio

**It makes SWIFT messages so you can test with them.**

Banks talk to each other with standard messages. When you want to test a banking system,
you need to feed it one of those messages. Writing one by hand is painful and easy to get
wrong. This tool writes it for you, checks it, and hands it over.

You give it the business facts:

> Receive 1,000 units of ISIN XS0000000009 on 18 August, paying USD 25,000.

It gives you back a real message:

```
{1:F01DEMOGB2LAXXX0001000001}
{2:I541DEMOUS33XXXXN}
{4:
:16R:GENL
:20C::SEME//TESTREF001
:23G:NEWM
:16R:TRADDET
:98A::SETT//20260818
:35B:ISIN XS0000000009
...
-}
```

Two kinds of people use it, and both get the same thing:

| You are | You do this | You get |
|---|---|---|
| A **manual tester** | Open the app, pick a message, fill in the boxes, press Generate | A message you can copy or download |
| An **automation tester** | POST some JSON, or upload a spreadsheet | The same message, in the API response |

There is nothing the app can do that the API cannot. The app *is* an API client.

---

## Start it up

You need **Python 3.13**, **Node 22** and about two minutes.

```bash
git clone <this-repo>
cd SwiftGenerator

make install     # Python virtualenv, npm packages, and the browser the tests drive
make migrate     # creates the database
```

Then open two terminals:

```bash
make backend     # terminal 1 → http://localhost:8000
make frontend    # terminal 2 → http://localhost:3000
```

Open <http://localhost:3000> and you are looking at Create Message.

**No API keys are needed, and there is no `.env` to write.** The AI features are optional
and off by default; everything that makes a message is plain deterministic code. A clean
clone runs `make install`, `make check` and `make e2e` with nothing else configured — and
that is verified, not assumed.

### Or use Docker

```bash
docker compose up --build
```

Same two URLs. Nothing else to configure.

---

## What are MT and MX?

Two languages for the same conversation. Banks are slowly moving from the old one to the
new one, so this tool speaks both.

**MT** is the old one (formally: ISO 15022). It looks like a telegram. Everything is a
numbered tag on its own line, wrapped in five "blocks":

```
{1: who is sending }
{2: who is receiving, and what kind of message }
{3: optional extras }
{4: the actual content, as tags   ← this is the interesting part
-}
{5: trailer, added by the network }
```

**MX** is the new one (formally: ISO 20022). It is XML. Instead of `:98A::SETT//20260818`
you write `<SttlmDt><Dt><Dt>2026-08-18</Dt></Dt></SttlmDt>`. More verbose, but a computer
can check it against a schema.

An MX message comes in two parts: a **header** (`AppHdr` — who, to whom, when) and a
**document** (the content). This tool produces both.

You do not need to know any of this to use the tool. Every field is labelled in plain
business language, and there is an **ℹ** button next to each one that explains it.

---

## The six screens

| Screen | What it is for |
|---|---|
| **Create Message** | Make one message by hand. Six steps, one decision at a time. |
| **Bulk / Excel** | Keep many test scenarios in a spreadsheet, turn them all into messages at once. |
| **Message Intelligence** | Look anything up. Type `PSET` or `SttlmDt` and find out what it means. |
| **Validate** | Check data, or paste an existing MT or MX message, without generating anything. |
| **API & Automation** | Copy-paste-ready examples in curl, Java, Python and JavaScript. |
| **Recent Messages** | Everything you generated lately, ready to download again. |

There is also an **Advanced** page holding specialist workflows (settlement lifecycle,
corporate actions, penalties, the approval stack) and, since Phase 6, the **Knowledge
Base** screen — what is indexed, how ready each discovered message is, and search with
citations. You do not need any of it to make a message.

---

## What it supports today

**23 message types, all generatable end to end.**

- **16 MT types** — MT530, MT537, MT540–MT548, MT564–MT568
- **3 MX settlement types** — sese.023 (instruction), sese.024 (status),
  sese.025 (confirmation)
- **4 MX cancellation and modification types** — sese.020, sese.027, sese.030, sese.031

Every one of them has a working sample in up to three depths (minimal, typical, full), and
every sample is produced by the same code that produces your message — so a sample can never
show you something the tool would not actually generate.

**Every one of them also imports.** Paste a message you already have — a FIN message, an MT
text block, or an ISO 20022 document — and the tool reads it back into the form, so you can
change one value and generate it again. It then shows you exactly what differs between the
message you pasted and the one it built, and *why*: a value you changed, a field written in
specification order, or something a messaging interface supplies that the tool refuses to
invent.

### Beyond the configured 23: the knowledge base

If you hold authorised SWIFT Message Reference Guides or ISO 20022 schemas, drop them into
an ignored local folder (`swiftKnowledgeBase/`), run `make knowledge-sync`, and the studio
indexes them for search, lets a model draft samples grounded in them with page-level
citations, and — where deterministic structure evidence exists — generates test messages
for types nobody configured by hand, in a separate, clearly labelled **knowledge-preview
lane**. On the operator's folder that is 209 generation-ready message/release structures
beside the 23 configured ones; a message without structural evidence can be searched but
is never generated, and the readiness report names the exact blocker. Nothing licensed is
ever committed, and no source text leaves the machine unless you say so twice. See
[docs/universal-financial-message-rag.md](docs/universal-financial-message-rag.md) and
[docs/knowledge-source-handling.md](docs/knowledge-source-handling.md).

### An honest note about coverage

The message definitions in this repository are a **configured subset**, hand-built from
public review material. They are **not** the complete official standard, and nobody has
checked them against a licensed SWIFT or ISO 20022 specification.

The tool says so, everywhere: in the API (`authoritativeCompletenessKnown: false`), on
screen, and in [docs/limitations.md](docs/limitations.md). Use it for testing. Do not
treat it as a conformance authority.

The same honesty applies to values the tool refuses to invent. A real SWIFT interface
assigns session and sequence numbers; the network adds authentication trailers. This tool
will not make those up. If it cannot get one legitimately, it says why instead of guessing.

---

## Where to read next

Two audiences, in the order you should read.

**If you are using the tool:**

| If you want to… | Read |
|---|---|
| Make your first message | [docs/for-manual-testers.md](docs/for-manual-testers.md) |
| Call it from a test suite | [docs/for-automation-testers.md](docs/for-automation-testers.md) · [docs/automation-api.md](docs/automation-api.md) |
| Index your own guides and schemas | [docs/knowledge-source-handling.md](docs/knowledge-source-handling.md) |
| Let a model draft a sample from a business request | [docs/ai-assisted-authoring.md](docs/ai-assisted-authoring.md) |
| Run the Phase 6 manual checklist | [docs/testing/phase-06-universal-rag-uat-checklist.md](docs/testing/phase-06-universal-rag-uat-checklist.md) |
| Understand a message format | [docs/how-messages-are-built.md](docs/how-messages-are-built.md) |
| Know exactly what is and is not supported | [docs/limitations.md](docs/limitations.md) |
| Demo this to somebody in twenty minutes | [docs/CLIENT_DEMO_RUNBOOK.md](docs/CLIENT_DEMO_RUNBOOK.md) |

**If you are working on the code:**

| If you want to… | Read |
|---|---|
| Understand how the pieces fit together | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Understand the knowledge base and preview lane | [docs/universal-financial-message-rag.md](docs/universal-financial-message-rag.md) |
| Read what Phase 6 built and measured | [docs/history/specification-engine-phase-06-report.md](docs/history/specification-engine-phase-06-report.md) |
| Tour the backend service | [backend/README.md](backend/README.md) |
| Tour the frontend app | [frontend/README.md](frontend/README.md) |
| Know how a message is defined (the source of truth) | [backend/config/README.md](backend/config/README.md) |
| Change the code (pre-push checklist) | [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) |
| See the design decisions behind the UI | [docs/DESIGN.md](docs/DESIGN.md) |

**Everything else:** [docs/README.md](docs/README.md) is the full index — one row per
guide, organised by what you are trying to do. Historical reports (implementation
milestones, audits) live under [docs/history/](docs/history/README.md) and are labelled
as such; they describe how the code reached its current shape, not how it works today.

---

## Everyday commands

```bash
make install     # first-time setup
make migrate     # apply database migrations
make backend     # run the API on :8000
make frontend    # run the web app on :3000
make test        # backend tests
make e2e         # browser tests
make lint        # ruff + eslint
make typecheck   # mypy + tsc
make build       # production frontend build
make coverage       # fail if the message-coverage report is out of date
make coverage-write # regenerate it
make secret-scan    # no secret-shaped strings in tracked files
make knowledge-sync     # index swiftKnowledgeBase/ (add KNOWLEDGE_SOURCE_DIR=a,b for more roots)
make knowledge-status   # what is indexed, and the embedding/LLM policy in force
make knowledge-dev      # sync, then run the API in local UAT mode (enables the sync endpoint)
make knowledge-reports-write   # regenerate the three docs/generated knowledge reports
```

`make check` runs lint, typecheck, the full test suite, the coverage gate and the offline
knowledge-retrieval evaluation together — run it before you push. It needs no PDF, no
schema and no key.

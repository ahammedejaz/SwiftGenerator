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

## Quickstart

With Docker, Compose, OpenSSL and Git LFS installed, a fresh clone is three commands:

```bash
git clone <this-repo>
cd SwiftGenerator
git lfs pull
make quickstart
```

Open <http://localhost:3000> (or <http://127.0.0.1:3000> — both work). The command creates safe local secrets, builds both images,
runs migrations, starts the platform, waits for readiness, verifies the committed knowledge
base against its manifest and indexes it in the background. The 23 configured messages work
immediately; the knowledge-preview lane (hundreds of MT and MX structures compiled from the
committed SWIFT guides and ISO 20022 schemas) appears when the first sync finishes. AI
credentials are optional: without them, indexing is lexical and everything deterministic
still works.

```bash
make stop       # stop services, keep development data
make reset-dev  # stop services and remove the Docker data volume
```

For a local Python/Node developer environment:

```bash
make install
make migrate
make dev
```

Details, knowledge bootstrap and troubleshooting: [docs/quickstart.md](docs/quickstart.md).

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
| **Convert Message** | Map MT business values to MX through an explicit, provenance-bearing Mapping Pack. |

There is also an **Advanced** page holding specialist workflows (settlement lifecycle,
corporate actions, penalties, the approval stack) and the **Knowledge Base**, **Recent
Messages**, and **AI & Knowledge Usage** screens. You do not need any of them to make a
message.

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

The repository carries the authorised knowledge base (`swiftKnowledgeBase/`, through Git
LFS: 156 SWIFT SR2026 Message Reference Guides and 8 ISO 20022 `pacs` schemas). `make
knowledge-sync` indexes it for search, lets a model draft samples grounded in it with
page-level citations, and — where deterministic structure evidence exists — generates test
messages for types nobody configured by hand, in a separate, clearly labelled
**knowledge-preview lane**: 424 of 481 MT catalogue entries and all 15 MX entries were
generation-ready on 2026-08-21, every one proven through the same API matrix (sample,
FIN, import, round trip, Excel, JSON). A message without structural evidence can be
searched but is never generated, and the blocker report names the exact reason. No source
text leaves the machine unless you say so twice. See
[docs/universal-financial-message-rag.md](docs/universal-financial-message-rag.md) and
[docs/knowledge-source-handling.md](docs/knowledge-source-handling.md).

Raw source redistribution is not authorized by the repository, so no operator PDF/XSD is
committed. Approved organization bundles use checksum-gated `make knowledge-fetch`; see
[docs/knowledge-distribution.md](docs/knowledge-distribution.md).

### MT to MX conversion

Conversion is a deterministic business-semantic Mapping Pack workflow, not a syntax rename.
The included MT541 to sese.023 pack is conspicuously synthetic and disabled until a tester
opts into preview mode. No real source-backed conversion is claimed because no approved
mapping evidence is present. See [docs/message-conversion.md](docs/message-conversion.md).

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
| Inspect model, RAG, embedding and cache usage | [docs/ai-rag-observability.md](docs/ai-rag-observability.md) |
| Convert an MT to MX through a Mapping Pack | [docs/message-conversion.md](docs/message-conversion.md) |
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
make quickstart  # Docker build, migrate, start and readiness wait
make stop        # stop Docker services, retain data
make reset-dev   # stop Docker services and remove development data
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
make knowledge-verify   # the committed knowledge base is present, real bytes, and hashes as recorded
make knowledge-fetch    # install one approved checksum-pinned organisation bundle
make knowledge-status   # what is indexed, and the embedding/LLM policy in force
make knowledge-dev      # sync, then run the API in local UAT mode (enables the sync endpoint)
make knowledge-reports-write   # regenerate the three docs/generated knowledge reports
```

`make check` runs lint, typecheck, the full test suite, the coverage gate and the offline
knowledge-retrieval evaluation together — run it before you push. It needs no PDF, no
schema and no key.

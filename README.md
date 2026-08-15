# Financial Message Studio

**It makes SWIFT messages so you can test with them.**

Banks talk to each other with standard messages. When you want to test a banking system,
you need to feed it one of those messages. Writing one by hand is painful and easy to get
wrong. This tool writes it for you, checks it, and hands it over.

You give it the business facts:

> Receive 1,000 units of ISIN XS0000000001 on 18 August, paying USD 25,000.

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
:35B:ISIN XS0000000001
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

make install     # creates the Python virtualenv and installs npm packages
make migrate     # creates the database
```

Then open two terminals:

```bash
make backend     # terminal 1 → http://localhost:8000
make frontend    # terminal 2 → http://localhost:3000
```

Open <http://localhost:3000> and you are looking at Create Message.

**No API keys are needed.** The AI features are optional and off by default; everything
that makes a message is plain deterministic code.

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
| **Validate** | Check data, or an existing message, without generating anything. |
| **API & Automation** | Copy-paste-ready examples in curl, Java, Python and JavaScript. |
| **Recent Messages** | Everything you generated lately, ready to download again. |

There is also an **Advanced** page holding specialist workflows (settlement lifecycle,
corporate actions, penalties, the approval stack). You do not need any of it to make a
message.

---

## What it supports today

**19 message types, all generatable end to end.**

- **16 MT types** — MT530, MT537, MT540–MT548, MT564–MT568
- **3 MX types** — sese.023 (instruction), sese.024 (status), sese.025 (confirmation)

Every one of them has a working sample in three depths (minimal, typical, full), and every
sample is produced by the same code that produces your message — so a sample can never
show you something the tool would not actually generate.

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

| If you want to… | Read |
|---|---|
| Make your first message | [docs/for-manual-testers.md](docs/for-manual-testers.md) |
| Call it from a test suite | [docs/for-automation-testers.md](docs/for-automation-testers.md) |
| Understand how the code fits together | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Change the code | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Understand a message format | [docs/how-messages-are-built.md](docs/how-messages-are-built.md) |
| Know exactly what is and is not supported | [docs/limitations.md](docs/limitations.md) |
| See every doc | [docs/README.md](docs/README.md) |

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
make coverage    # regenerate the message-coverage report
```

`make check` runs lint, typecheck and the full test suite together — run it before you
push.

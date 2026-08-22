# Ten-minute demo

What to show, in what order, and what to say. Every step below was walked in a real browser
on 2026-08-22. Each one has a fallback that needs no live AI, so the demo never depends on
a provider being reachable.

**Before you start:** `make quickstart` (Docker), or `make dev` and open
<http://127.0.0.1:3000>. Stop any server you started by hand first.

---

## 0 · What this is (30 seconds)

> Two audiences, one code path. A tester who has never seen a SWIFT message uses a
> six-step wizard; an automation pipeline POSTs JSON or uploads a spreadsheet. The browser
> calls exactly the same `/api/v1` endpoints — there is no UI-only capability.

Do not say *certified*, *compliant* or *production ready*. Say **internal MVP / POC**.

## 1 · The catalogue (1 min)

Open **Create Message**. The two cards read **16 configured · 465 previews** for MT and
**7 configured · 8 previews** for MX.

> 481 MT catalogue entries, 424 of which generate. 271 distinct message types, 258 with a
> structure the platform will build from. Everything past the configured 16 is a
> *knowledge preview*: compiled from the standards documents the operator supplied, and
> labelled as such on every screen and every API response.

## 2 · MT103 with an AI sample (2 min)

Search `MT103` → choose the **SR2026 · future release, test preview** row.

Point at the banner: *Structure-backed test generation; complete semantic rules not
established. Structure from SWIFT MRG SR2026, Prowide SR2025 corroborated.*

> The product never overstates what it knows.

Click **AI Typical sample**. The strip reads **AI sample — cached · validated by the
deterministic engine · AI used 8 source sections · Cache: HIT — 0 model calls**.

> The model proposed values. The deterministic validator and composer decided. A repeat
> request makes no model call at all.

Scroll the form: every field explains itself in plain English — *"In order: a date
(YYMMDD), then a three-letter currency code, then an amount, written with a comma as the
decimal separator."* — with the SWIFT notation kept at the end for an expert.

**Fallback with no AI:** click **Load minimal valid sample** or **Full configured subset**
instead. Both are deterministic and always work.

## 3 · Generate (1 min)

**Generate message** → a complete FIN message, line-numbered, each line annotated with the
field it is. Show the tabs: Block 4 only, FIN message, Plain text, Canonical JSON. Show
**Copy** and **Download**.

Open **Envelope values**: *where each value came from, and what the platform deliberately
did not produce.*

> Interface-generated and network-generated values are never fabricated. If the envelope
> cannot be built honestly, generation fails with a named error rather than a plausible
> substitute.

## 4 · Convert to MX (2 min) — the headline

Click **Convert to MX** under the generated message.

The Convert screen carries the message over and names the mapping authority:
**CANDIDATE_PREVIEW**, *evidence: name correspondence — the two documents' titles
correspond; nothing relates them*, with both citations and every limitation listed.

> No pack here is source-backed, because no document in the corpus states a field-level
> mapping. The product says so rather than implying otherwise.

Tick the opt-in, **Preview conversion**. Read the report: **Mapped 4 · Derived 10 ·
Missing 3 · Not represented 12**.

Fill the three questions — *What is the End To End Identification?*, *Cre Date Tm*,
*Settlement Mtd* — then **Generate target**. It asks once more for the Creditor name.

> It will not invent a party. Missing data stays `NEEDS_INPUT` until someone supplies it.

Fill it, generate: a valid **pacs.008.001.14**, XSD accepted. Show the Canonical target
preview — every value labelled *Mapped*, *Derived* or *You supplied*.

**Other proofs, same flow:** MT202 → pacs.009, MT541 → sese.023.

## 5 · Message Intelligence and RAG (1½ min)

Open **Message Intelligence**, click the `PSET` chip.

> Deterministic dictionary search across both standards. No model call — a browser test
> watches the network to prove it.

Then **Ask about this field**: an answer from the indexed guides, marked **Supported by
the indexed source · 1 model call · 10 source sections**, quoting what the document
actually says.

**Fallback with no AI:** the deterministic panel above it is the whole card and needs
nothing.

## 6 · Guided and Expert on MT541 (1 min)

Search `MT541`, load the sample, show the sequence groups (GENL, TRADDET, FIAC, SETDET),
the party-option switcher, and the ISIN check-digit feedback.

> Field format and identifier quality are different claims and live in different validation
> layers, because the FIN network checks the format and does not compute the check digit.

## 7 · Excel and the API (1½ min)

**Bulk / Excel** → download the MT template → upload it back → 3 scenarios generated.

**API & Automation** → the same call in curl, Java/REST Assured, Python and JavaScript.

> The workbook, the JSON API and the browser produce byte-identical output for equivalent
> values, because all three call the same composer.

## 8 · AI & Knowledge Usage (30 seconds)

Operations today, model calls, tokens, cache-hit rate, RAG queries, retrieved sections,
embedding provider and dimensions, last sync.

> Content-free: identifiers and counters, never a prompt, a message value or source text.

## 9 · Knowledge Base (30 seconds)

164 sources, 16,656 segments and embeddings, 489 compiled structures, last run COMPLETED.

> The sources ship with the repository through Git LFS with a content manifest, so a new
> engineer clones and has the whole corpus. `make knowledge-verify` proves every file is
> present with the recorded hash.

## 10 · Close (30 seconds)

> No known blocking software defects. What remains is evidence: 13 FIN system message types
> whose only source states no Block 4 structure, 451 Network Validated Rules with no sound
> weaker-or-equal expression — every one recorded with its reason, none silently ignored,
> none active at runtime — and no authoritative MT↔MX field-level mapping material in the
> corpus. Those are capability boundaries, not bugs.

---

## Demo without AI at all

Set `AI_PROVIDER=disabled` and `KNOWLEDGE_AI_PROVIDER=disabled`. Steps 1, 3, 4, 6, 7, 9
and 10 are unchanged. Step 2 uses **Load minimal valid sample**; step 5 uses the
deterministic panel. Nothing shows an error screen — the AI entry points answer with their
deterministic seed.

## If something goes wrong

- **Create Message says "Loading configured messages…" for ever** — the backend is not on
  `:8000`. `curl http://127.0.0.1:8000/api/health`.
- **Convert refuses a pack** — the specification moved under it. Run
  `cd backend && .venv/bin/python -m app.mapping packs --check-checksums`.
- **The preview lane is empty** — `KNOWLEDGE_MODE` is unset, or the knowledge database is
  not on this machine. `make knowledge-status`.

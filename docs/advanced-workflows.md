# Advanced workflows

The specialist screens under **Advanced**. They predate the studio, they still work, and
**you do not need any of them to generate a message.**

They are one level down for a reason: a new tester should not have to choose between
thirteen things before understanding one.

---

## Message lifecycles

A real settlement is a conversation, not a single message. These screens run the whole
exchange and check that the parts link up correctly.

### Settlement lifecycle — `/lifecycle`

`MT541` (I instruct) → `MT548` (you tell me its status) → `MT545` (you confirm it settled).

Each response references the instruction it answers. The screen shows the timeline and
whether the correlation between them is valid.

### Settlement processing — `/settlement-processing`

What to do when an instruction needs to change after you sent it.

Some changes can be made directly; others require cancelling and re-booking. The tool
classifies a proposed change and tells you which:

| Classification | Meaning |
|---|---|
| `PROCESSING_DATA_MODIFICATION` | Change it directly (e.g. priority) |
| `CORE_BUSINESS_DATA_CHANGE` | Cancel and re-book |
| `CANCELLATION_ONLY` | Can only be cancelled |
| `UNSUPPORTED_MODIFICATION` | Not supported by the configured subset |

Also builds `MT530` (a processing command, e.g. change the priority) and runs a complete
cancel-and-rebook, showing the before and after values.

### Corporate actions — `/corporate-actions`

What happens when a company does something to its own shares — pays a dividend, offers
a choice between cash and stock.

`MT564` (here is an event and your options) → `MT565` (I choose option 1) → `MT567` (your
election is acknowledged) → `MT566` (here is what you got), with `MT568` for free-text
narrative.

Scope is one configured event type: Dividend With Options.

### Penalty statements — `/penalties`

When a settlement fails, the market charges a penalty. `MT537` reports them.

The screen builds a statement from supplied penalty amounts, grouped by currency and by
counterparty. It does **not** calculate penalties — rates and calculation rules are market
data this repository does not have.

---

## Authoring and operations

A heavier workflow for producing a message under control: encrypted drafts, roles, and
maker-checker approval.

### Secure message builder — `/message-builder`

Requires a login (development identities: author, reviewer, approver, submitter, auditor,
admin). Drafts are scoped to a tenant and encrypted at rest. Field values are masked from
roles that should not see them.

Draft → request review → approve → download or submit. The approver cannot be the author.

### Operations console — `/operations`

Validation levels, approval state, configured connectors and submission evidence.

**Submission is disabled by default and fails closed.** Sending a real message needs an
authorised connector, an approval policy and external validation evidence, all explicitly
configured. There is a `DOWNLOAD_ONLY` connector that does exactly what it says.

### Message catalogue — `/catalogue`

Capability and measured coverage per message type. Every message reads `PARTIAL`, and that
is honest: see [limitations.md](limitations.md).

### Annotated samples — `/samples`

Composer-generated samples with line-by-line annotations. Message Intelligence in the main
navigation largely replaces this.

---

## AI assistance

### Describe a scenario — `/guided`

Write a settlement in plain English and let the model propose the canonical fields. This is
the only screen where a model is called. See [ai-assistance.md](ai-assistance.md).

### Canonical field inspector — `/expert`

The canonical scenario, the deterministic tags and the raw message side by side. Useful for
understanding how a business fact becomes a tag.

### Tag Intelligence — `/knowledge`

The original MT-only knowledge browser. **Message Intelligence** in the main navigation
extends it to MX and is the better place to look things up.

### AI efficiency — `/ai-efficiency`

Live calls, cache hits, tokens, cost, latency, and how much was avoided.

---

## The older API

These screens use the original scenario-shaped API under `/api/*` — for example
`POST /api/messages/generate`, which takes a `SettlementScenario` object rather than
tag-level fields.

It still works and is still tested. **For new automation, use `/api/v1`** — see
[for-automation-testers.md](for-automation-testers.md). The `/api/v1` surface is
field-level, covers MT and MX equally, and is what the main screens use.

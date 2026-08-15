# Product context

> **How this was written.** The brief that commissioned this work explicitly forbade
> questions ("Do not ask me questions. Do not wait for approval."), so the usual interview
> was replaced by inference from that brief plus the existing codebase. Assumptions are
> labelled **[assumed]**. Correct any of them and the design decisions that depend on them
> should be revisited.

## What this is

**Financial Message Studio** — a tool for producing valid SWIFT MT (ISO 15022) and MX
(ISO 20022) financial messages for testing. You give it business or field-level data; it
gives you back a complete, validated message ready to send to a downstream test system.

It is not a SWIFT administration console, not a production messaging gateway, and it makes
no certification claim.

## Who uses it

**The manual tester.** Often has little or no SWIFT knowledge. Sits at a desk in an office,
daytime, on a laptop, usually with a ticket open in another window. They have been asked to
"produce an MT541 for this scenario" and they need to do it today, without training. Their
success is a downloaded message they can hand to the system under test.

Their real problem is not the tool — it is that ISO 15022 and ISO 20022 are opaque. Every
field label must earn its keep in business language, and every tag must be explainable in
one click without leaving the page.

**The automation tester.** Never opens the UI if they can help it. Keeps scenario data in a
spreadsheet or in code, and wants an HTTP call that turns it into a message. Their success
is a green pipeline. They need a stable contract, machine-readable validation, and no login
screen in the way.

**[assumed]** Both work inside a bank or a vendor serving one, on a corporate laptop, in a
Windows-or-macOS Chrome/Edge browser at desktop resolution. Mobile use is incidental —
someone checking a result on a phone, not composing on one.

## The two success criteria

The brief names these as the definition of done, so they are the product's spine:

1. A manual tester can understand and generate a message without training.
2. An automation tester can provide Excel, tag or element data through an API and receive a
   valid MT FIN or MX XML message ready for the downstream test system.

Everything else is subordinate. Where a design choice serves one of these and a convention
opposes it, the criterion wins.

## Product truth that constrains the design

- **The message is the deliverable.** Not the form, not the dashboard. The interface exists
  to produce an artifact and hand it over.
- **Honesty about coverage is a feature.** Message coverage is a configured subset, not the
  complete authoritative standard, and the platform says so rather than implying otherwise.
  The UI must carry that without shouting it on every screen.
- **Nothing is fabricated.** Values the messaging interface or the network allocates are
  never invented. Where the platform declines to produce something, it says why.
- **MT and MX are genuinely different.** MT produces FIN blocks; MX produces an AppHdr and a
  Document. They are never blended, and the interface must not imply they are the same thing
  with different syntax.
- **AI is optional and narrow.** It interprets natural-language intent. It never renders,
  validates or parses a message. A tester with no model access loses nothing essential.
- **The UI has no private capabilities.** Every screen calls the same `/api/v1` endpoints an
  automation tester calls.

## Constraints

- Next.js 16 / React 19 / Tailwind 4, talking to a FastAPI backend.
- Must run on any laptop after a clone and two commands — no network-dependent build step,
  no font CDN, no external asset host.
- The 13 pre-existing specialist screens (lifecycle, penalties, corporate actions, AI
  efficiency and so on) still work and must remain reachable. They are not the front door.

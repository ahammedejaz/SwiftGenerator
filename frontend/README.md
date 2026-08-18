# Frontend

The Next.js web app that turns the message studio into something a person can drive.

**If you just want to run it:** `make frontend` from the repository root (the backend
must be running too), then `http://localhost:3000`.

**If you want to understand the whole system:** read the root
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) and [../docs/DESIGN.md](../docs/DESIGN.md) first. This
README is the local map — routes, components, state, testing — and assumes you already
know why the app looks and behaves the way it does.

---

## Language, versions, and tooling

- **Node 22** · **Next.js 16** (App Router) · **React 19** · **Tailwind CSS 4**
- **TypeScript 5** in `strict` mode
- **Playwright** for end-to-end browser tests
- **ESLint** on `next/core-web-vitals` + TypeScript ruleset

There is **no CSS-in-JS**, no icon library, no state library, no data-fetching library.
The design tenet is that the app must build and run offline after a clean clone, and
every dependency is measured against that. See [../docs/DESIGN.md](../docs/DESIGN.md).

---

## Directory map

```
frontend/
├── app/                          Next.js App Router — one folder per route
│   ├── layout.tsx                root layout: <Chrome> wrapper, globals.css
│   ├── globals.css               Tailwind @theme custom properties (see DESIGN.md)
│   ├── page.tsx                  /                   → Create Message
│   ├── excel/page.tsx            /excel              → Bulk / Excel
│   ├── intelligence/page.tsx     /intelligence       → Message Intelligence
│   ├── validate/page.tsx         /validate           → Validate
│   ├── automation/page.tsx       /automation         → API & Automation
│   ├── recent/page.tsx           /recent             → Recent Messages
│   ├── advanced/page.tsx         /advanced           → grid of specialty screens
│   ├── guided/page.tsx           /guided             → "describe the settlement"
│   ├── expert/page.tsx           /expert             → deterministic inspector
│   ├── message-builder/page.tsx  /message-builder    → tenant-scoped drafts
│   ├── operations/page.tsx       /operations         → approvals, connectors
│   ├── catalogue/page.tsx        /catalogue          → capability matrix
│   ├── samples/page.tsx          /samples            → annotated samples
│   ├── knowledge/page.tsx        /knowledge          → MT tag intelligence
│   ├── ai-efficiency/page.tsx    /ai-efficiency      → live AI calls / cache / cost
│   ├── lifecycle/page.tsx        /lifecycle          → MT541 → MT548 → MT545 flows
│   ├── settlement-processing/page.tsx  /settlement-processing
│   ├── corporate-actions/page.tsx      /corporate-actions
│   ├── penalties/page.tsx              /penalties
│   └── reports/[reportId]/page.tsx     /reports/:id  → bulk-report viewer
│
├── components/
│   ├── studio/                   the six primary screens · the wizard vocabulary
│   ├── platform/                 authoring, operations, catalogue, annotated samples
│   ├── guided/                   the "plain English → scenario" screen
│   ├── expert/                   the deterministic inspector
│   ├── knowledge/                the MT knowledge browser (predates Intelligence)
│   ├── lifecycle/                settlement lifecycle correlation
│   ├── settlement-processing/    amendments, cancel/rebook
│   ├── corporate-actions/        MT564 / MT565 / MT567 / MT566 flow
│   ├── penalties/                MT537 penalty statement builder
│   ├── bulk/                     Excel-driven bulk generation
│   ├── ai/                       AI efficiency dashboards
│   ├── messages/                 shared message view components
│   └── reports/                  bulk-report viewer
│
├── lib/                          the only place that talks to the backend
│   ├── api-client.ts             low-level fetch — CSRF, credentials, error shape
│   ├── studio-api.ts             the typed `studioApi` client
│   ├── studio-types.ts           TypeScript mirror of the /api/v1 contract
│   ├── contracts.ts              types for the legacy /api scenario endpoints
│   └── identifiers.ts            ISIN / BIC live-feedback helpers (server still decides)
│
├── tests/e2e/                    Playwright specs — see the Testing section
│
├── next.config.ts                standalone build, no X-Powered-By header
├── tsconfig.json                 strict TypeScript
├── eslint.config.mjs             Next.js + TypeScript rules
├── postcss.config.mjs            @tailwindcss/postcss
├── playwright.config.ts          starts backend + frontend together for the test run
├── package.json                  dependencies and scripts
├── AGENTS.md                     Next-generated notice for AI tools (see below)
└── CLAUDE.md                     Next-generated notice for AI tools (see below)
```

---

## The screen you land on

The home page (`app/page.tsx`) renders `<CreateMessage />` directly — no separate landing
screen. This is deliberate: a new user is already on the task they came for. The old
front page (thirteen equal cards on a slate hero) is described in
[../docs/DESIGN.md](../docs/DESIGN.md) as the shape the current design deliberately refuses.

Six primary routes appear in the top nav (`components/studio/Chrome.tsx`):

| Route | What it is |
|---|---|
| **`/`** — Create Message | The six-step wizard: format → area → message → mode → data → result |
| **`/excel`** — Bulk / Excel | Upload a workbook, generate every scenario in it, download the pack |
| **`/intelligence`** — Message Intelligence | Look up an MT tag or MX element in plain English |
| **`/validate`** — Validate | Paste an existing message or JSON; validate without persisting |
| **`/automation`** — API & Automation | Copy-paste curl, Java, Python, JavaScript examples |
| **`/recent`** — Recent Messages | Everything generated lately; download by output mode |

An **Advanced** menu (`/advanced`) links to specialist screens: settlement lifecycle,
corporate actions, penalties, the maker-checker authoring stack, and dashboards.

---

## Two components carry the whole product

- **`components/studio/CreateMessage.tsx`** is the wizard. It is the largest file in the
  codebase for good reason: it owns the step machine, loads the specification and
  samples, tracks values, drives import/regenerate round-trips, and dispatches every API
  call. If you are trying to change *what happens* on the main screen, start here.

- **`components/studio/ProofSheet.tsx`** renders the generated message on the dark
  monospaced surface with a line-number gutter and margin annotations naming the
  business field each line came from. It is the thing the user came for; see
  [../docs/DESIGN.md § The idea: a proof sheet](../docs/DESIGN.md#the-idea-a-proof-sheet).

Supporting cast:

- `FieldEditor.tsx` — progressive disclosure of a message specification into form
  groups; hides optional fields behind "Add optional field".
- `FieldControl.tsx` — one control per `InputKind`; the browser never infers a control
  from the value.
- `ValidationPanel.tsx` — plain-English validation summary; individual layers reported
  separately.
- `MessageDiff.tsx` — the original-vs-regenerated comparison; every difference carries a
  reason.
- `ui.tsx` — the shared component vocabulary (Button, Panel, Badge, Labelled, ...).
- `Icon.tsx` — authored SVG icons; no icon fonts, no third-party sets.

---

## State and data flow

**There is no global state manager.** Every screen owns its own state via React hooks.
The Create Message wizard is linear — each step feeds the next — and cross-screen
sharing is uncommon. Imports hydrate a fresh form rather than reading a store.

Data comes in through exactly one door:

```
component/screen
     │
lib/studio-api.ts        the typed studioApi object — methods per endpoint
     │
lib/api-client.ts        the only place fetch() is called
     │
Python backend on 127.0.0.1:8000
```

**`localhost` is banned in this codebase.** On a dual-stack machine it resolves to `::1`
first, and the backend binds `127.0.0.1`. A one-in-three intermittent test failure was
traced to this exact quirk; see [../docs/AGENTS.md § 13 Gotchas](../docs/AGENTS.md#13-gotchas-discovered-the-hard-way)
item 21.

The API contract itself is authoritatively defined by
[`lib/studio-types.ts`](lib/studio-types.ts) and the backend must not disagree. Every
new endpoint or field requires updating both, plus `studio-api.ts`. There is no
generator: those three files are kept in step by hand.

---

## Styling

Tailwind 4, no config file — the theme lives in `app/globals.css` inside a `@theme`
block. Warm neutrals for input surfaces (`--color-paper`), a dark monospaced surface for
generated messages (`--color-proof`), cool indigo accent (`--color-accent`). Colour
choices are semantic, not decorative; see [../docs/DESIGN.md](../docs/DESIGN.md) for the full
palette and its rationale.

Rules the design system enforces:

- **Base styles go in `@layer base`.** An unlayered `button { color: inherit }` reset
  once killed every text-colour utility on every button. Regression documented in
  AGENTS.md gotcha 1.
- **`min-w-0` on every grid/flex child that can hold wide content.** A wide code block
  otherwise expands its track and scrolls the whole page sideways.

---

## Testing

Playwright end-to-end tests live in `tests/e2e/`. They run against **both** the frontend
dev server and a real backend — `playwright.config.ts` starts both. There are no
component-level unit tests; every behaviour is verified against the running product.

```
tests/e2e/
├── studio-create.spec.ts              the six-step wizard
├── studio-import.spec.ts              round-trip: generate → paste → import → regenerate
├── studio-screens.spec.ts             navigation, responsive, accessibility
├── message-diff.spec.ts               the original-vs-regenerated comparison
├── bulk.spec.ts                       Excel upload
├── guided.spec.ts                     "describe the settlement" flow
├── mt-authoring.spec.ts               ISIN, SETR, parties, dropdowns, mode switch
├── client-authoring.spec.ts           tenant-scoped drafts
├── knowledge.spec.ts                  MT tag intelligence
├── lifecycle.spec.ts                  correlated MT541 → MT548 → MT545
├── penalties.spec.ts                  MT537 penalty statements
├── corporate-actions.spec.ts          MT564 → MT565 → MT567 → MT566
├── settlement-processing.spec.ts      amendment classification
└── ai-efficiency.spec.ts              AI usage dashboard
```

Run them:

```
make e2e            # starts backend + frontend, runs Playwright, then stops both
```

Targeted:

```
cd frontend && npx playwright test studio-create --headed
```

Two things about how the specs are written:

- **Selectors are role-based, not `data-testid`.** `getByRole("button", { name: ... })`
  is preferred; it also verifies the element is accessible.
- **Assertions on a page's `<h2>` require `exact: true, level: 2`.** A loose
  `getByRole("heading", { name })` can pass on the page `<h1>`; a test that used the
  loose form has broken on the first CI run twice now (MT537, MT530).

---

## Notes about the AGENTS.md and CLAUDE.md files

- **`frontend/AGENTS.md`** is generated and written by `next dev` on every start-up. If
  the file is missing, Next walks up to the repository root and *replaces* the root
  `AGENTS.md` instead. Keep the frontend file committed; it is Next's target and it is
  what protects the root file from being overwritten with Next boilerplate. See
  [../docs/AGENTS.md § 13 Gotchas](../docs/AGENTS.md#13-gotchas-discovered-the-hard-way) item 19.
- **`frontend/CLAUDE.md`** is a one-line reference to `AGENTS.md` for tools that read
  the CLAUDE-specific file.

Do not treat either of these as authored documentation. The human-facing docs are the
root [../docs/AGENTS.md](../docs/AGENTS.md), this README, and the guides in
[../docs/](../docs/README.md).

---

## Adding a screen or feature

The invariant: **the UI gains no capability the API lacks.** In order:

1. Add the endpoint in the backend (`backend/app/studio/routes.py` or friends).
2. Update `lib/studio-types.ts` to reflect the new request/response shape.
3. Add the method to `lib/studio-api.ts`.
4. Only now build the component/route.
5. Add a Playwright spec that drives the whole flow through the browser.

Adding a new route:

1. Create `app/<route>/page.tsx` — one line, importing the component.
2. Create the component under `components/<area>/`.
3. If the route belongs in the top nav (six primary screens), also update
   `components/studio/Chrome.tsx`. Anything else lives under `/advanced`.

---

## Where to read next

- [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — how the whole system fits together
- [../docs/DESIGN.md](../docs/DESIGN.md) — the visual and interaction system, with the rules it
  enforces
- [../docs/for-manual-testers.md](../docs/for-manual-testers.md) — the wizard walked
  through from a user's viewpoint
- [../docs/AGENTS.md](../docs/AGENTS.md) — dense factual index; §5 has a per-file map

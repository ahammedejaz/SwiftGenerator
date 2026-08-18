# Design system — Financial Message Studio

Mode: **Operate.** The visitor is in a task. Scanability, consistency and the real usage
scene outrank expression. Brand lives in precise details.

This replaces the previous visual world (teal `#006D77`, Arial, thirteen equal cards on a
slate hero). That world was a generic dashboard: it told you nothing about what the product
makes, and its front page asked the user to choose between thirteen things before they had
understood one.

---

## The idea: a proof sheet

The product's whole purpose is to produce an exact machine-readable artifact. So the
interface is **warm paper around a dark proof**: everything you fill in sits on quiet,
slightly warm paper, and the generated message appears on a dark, monospaced proof surface
with line numbers and margin annotations — the way a typesetter's proof or a telex printout
looks.

Two consequences that are not decoration:

- The message output is visually the most important thing on any screen it appears on,
  because it is the thing the user came for.
- Paper and proof are read as *different kinds of thing*: one is editable human input, one
  is exact machine output. A user never has to wonder which they are looking at.

The warm neutrals against a cool indigo accent are the signature. Warm paper is unusual in
financial tooling, which defaults to cold slate, and it is the single cheapest way to make
this feel like a considered instrument rather than a CRUD admin.

---

## Color

Warm neutral scale, cool accent, conventional semantics. Restrained: accent is reserved for
primary action, current selection and state — never decoration.

```
--paper      #FAF9F6   page canvas
--panel      #FFFFFF   raised content surface
--rail       #F2F0EA   nav, toolbars, table headers, inactive tabs
--sunken     #F6F4EF   inset wells, read-only inputs

--ink        #1A1815   primary text          (14.9:1 on paper)
--ink-2      #5C574E   secondary text        (6.3:1 on paper — tinted from the paper hue)
--ink-3      #857F73   tertiary, placeholder (4.6:1 on paper)
--line       #E4E0D6   hairlines and borders
--line-2     #D2CCBE   emphasised borders

--accent     #2C3E8C   primary action, selection, focus  (8.7:1 on paper)
--accent-2   #1F2D68   accent hover/active
--accent-sk  #EAECF7   accent surface tint
--accent-lt  #8FA0E8   accent on the proof surface

--proof      #1B1A17   proof surface
--proof-ink  #EDEAE2   proof text            (12.8:1 on proof)
--proof-dim  #928C7F   proof gutter and annotation
--proof-line #2C2A26   proof hairlines

--ok         #2C6A4A   valid, generated
--ok-sk      #E8F1EB
--bad        #9E2B2B   error
--bad-sk     #F8EAEA
--warn       #8A6410   warning, partial
--warn-sk    #F7F0DE
```

**Rules**

- Secondary text is tinted from the paper hue, never neutral gray. `--ink-2` and `--ink-3`
  carry the same warmth as the canvas.
- Semantic colors mark state; they are never a surface for large areas.
- Inside the proof surface, the accent is `--accent-lt` — the same hue, relit for a dark
  ground.
- Mandatory / conditional / optional field presence is carried by a label, not by color
  alone. Color-blind users must lose nothing.

---

## Typography

One family. A tuned system sans, deliberately: the product must build and run offline after
a clone, and a font CDN or a build-time font download would break that. Operate mode permits
familiar sans defaults, and the identity is carried by color, surface and spacing instead.

```
--sans  ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial
--mono  ui-monospace, "SF Mono", "Cascadia Mono", "JetBrains Mono", Menlo, Consolas, monospace
```

Fixed rem scale at a 1.2 ratio — not fluid. Users view at a consistent DPI and a heading that
shrinks inside a panel looks worse, not better.

```
display  2.0rem / 1.15 / -0.02em / 600     page title
h2       1.375rem / 1.25 / -0.015em / 600  section
h3       1.0625rem / 1.35 / -0.01em / 600  panel / group
body     0.9375rem / 1.6 / 0               prose and field help
ui       0.875rem / 1.45 / 0               labels, buttons, table cells
micro    0.75rem / 1.4 / 0.02em / 500      meta, badges, gutters  (never below 12px)
code     0.8125rem / 1.55 / 0              proof surface, tags, XPaths
```

Monospace is used only for message text, tags, qualifiers, element paths and checksums —
things that are literally code, data or measurement. It is never a costume for "technical".

Prose measure stays 65–75ch. Data tables and the proof surface may run denser.

---

## Space and shape

4px base. `4 8 12 16 20 24 32 40 56 72`.

Tighter inside a group than between groups, and more space above a heading than below it —
a heading belongs to what follows it.

```
--r-sm 4px   inputs, badges, small controls
--r-md 8px   buttons, panels, cards
--r-lg 12px  the proof surface and page-level panels
```

No radius above 12px. Large radii read as consumer software; this is an instrument.

Depth is mostly a hairline. Shadows carry a real offset and a soft blur, never a zero-offset
halo:

```
--shadow-1  0 1px 2px rgba(26,24,21,.06), 0 1px 1px rgba(26,24,21,.04)
--shadow-2  0 4px 12px rgba(26,24,21,.08), 0 1px 3px rgba(26,24,21,.05)
--shadow-3  0 12px 32px rgba(26,24,21,.12), 0 2px 8px rgba(26,24,21,.06)
```

---

## Layout

Top bar, six items, no sidebar. Six fits a bar comfortably and leaves the full width for the
dense content this product actually shows: field lists, specification tables, XML.

Content column `max-width: 1200px`. The proof surface may run to `1400px` because message
lines are long and wrapping them costs comprehension.

Responsive behaviour is structural, not fluid type: the nav collapses to a scrollable row,
two-column layouts stack, tables scroll inside their own container. The page body never
scrolls sideways.

---

## Components

Every interactive component ships default, hover, focus-visible, active, disabled — and
loading and error where it can reach them.

- **Buttons.** One shape everywhere. `primary` (accent fill), `secondary` (panel + border),
  `quiet` (text only). Loading shows in the button, not as an overlay.
- **Inputs.** 1px `--line-2` border, 8px radius, `--panel` fill. Focus is a 2px accent ring
  offset by 2px — the same ring on every focusable element, including links and cards.
- **Field rows.** Business name first and largest. The tag or element path sits under it in
  mono at `micro`, secondary. A presence chip states Required / Conditional / Optional in
  words. An info control opens the explanation inline, never in a modal.
- **Panels.** `--panel` on `--paper`, 1px `--line`, `--r-lg`, `--shadow-1`. Never nested.
- **Proof surface.** `--proof` ground, mono, a line-number gutter in `--proof-dim`, and
  annotations in the right margin naming the business field a line came from.
- **Validation.** Stated in plain English first — "Ready to generate" or "3 issues need
  attention" — with each issue naming the field, the problem, what was expected and what to
  do. Rule ids are present but secondary; a manual tester should never have to read one.
- **Empty states** teach the screen. They say what the screen is for and offer the first
  action, never "No data".
- **Skeletons** for loading content. Spinners only inside a control the user just pressed.

Icons are authored SVG on a 20×20 grid, 1.5px stroke, `currentColor`, round caps. No emoji,
no glyph substitutes.

---

## Motion

150–220ms, `cubic-bezier(.2,.7,.3,1)`. Motion conveys state: a panel opening, a step
advancing, a result arriving. Nothing animates on page load; the user came to work.

The one authored moment is the **proof reveal** — when a message is generated the proof
surface wipes in from the top over 260ms while its content settles from a 4px offset. It
happens once, on the thing the user was waiting for, and it is the only place in the product
that draws attention to itself.

All of it is inside `prefers-reduced-motion: reduce`, which flattens everything to a 1ms
opacity change.

---

## Copy

The product's own language, not the standard's.

- Say "Settlement date", not "98A::SETT". The tag is metadata, shown alongside.
- Errors name the problem and the recovery: "MX uses YYYY-MM-DD, not the MT format YYYYMMDD.
  Try 2026-08-18." — never "Invalid format".
- Buttons name their action: "Generate message", "Download FIN", "Load a sample".
- Never "Oops" and never an exclamation mark.

---

## What this world refuses

Recorded so the next change does not quietly reintroduce them:

- A grid of same-size icon-heading-text cards as page structure. That was the old front page
  and it is why nobody knew where to start.
- Kickers and eyebrows above headings.
- Gradient text, decorative glass, colored left borders, hard offset shadows.
- Nested cards.
- A modal for anything that fits inline. Field explanations, validation and output are all
  inline.
- Monospace as decoration.
- Emoji as icons.

# Universal MT generation

How any MT message for which authorised structural evidence exists becomes a generation-
ready structure, what the gates prove, and exactly what still blocks the rest. The measured
state is in [generated/universal-mt-generation-coverage.md](generated/universal-mt-generation-coverage.md)
and [generated/mt-generation-blockers.md](generated/mt-generation-blockers.md).

## Evidence → structure → message

```
Prowide SR2025 model            SWIFT MRG Format Specifications (SR2026)
 sequences, nesting, repeats     sequences (16R-delimited or not), rows, options,
 field groups, option letters    qualifier tables, CODES blocks, FORMAT notations
 global field notations
            └──────────────┬──────────────┘
                   compile_mt_pack  (app/knowledge_base/structures/mt_pack.py)
                           ↓
              PackSequence / PackRow  — the structural IR
                           ↓
             mt-structure-pack/1 YAML  (build/knowledge/packs/mt/<MT>-<release>.yaml)
                           ↓
              load_mt_pack → MessageSpecification (the runtime type)
                           ↓
          validator · composer · FIN envelope · parser · Excel · JSON · AI samples
```

Nothing message-specific sits in that path. A new guide dropped into the knowledge base is
identified from its cover, read by the same reader and compiled by the same compiler; the
catalogue, the forms, the Excel template, the JSON API and the AI sample flow follow
without an endpoint, a list or a branch being touched.

## The structural IR

`PackSequence`: path, block code, parent, order, `minOccurs`/`maxOccurs`, `bracketed`
(delimited by `:16R:`/`:16S:` or not), leading tags (which tags open an unbracketed
occurrence when reading back), `insertAfterTag` (where a child sequence sits among its
parent's fields). `PackRow`: row id `MT-SEQ-TAG-QUAL[-n]`, tag, option letter, qualifier,
presence, format notation and its compiled pattern with fidelity, qualifier separator,
allowed codes (closed lists only), choice group, repetition, evidence origin and page.

Global field definitions (Prowide's 620 field classes: notation, components, generic
flag) stay separate from message use (the rows of one message in one release): `95a`'s
format is global; which qualifiers MT541 allows in `SETPRTY` is message use.

## What the universal-completion engagement made generic

| Gap | Generic fix | Where |
|---|---|---|
| Guides without `16R` sequences (flat MT103/MT940; MT101's A/B; MT300's `15A`-delimited A–F) compiled to no sequences | rows outside a sequence form an unbracketed `ROOT`; a sequence without a `16R` row is unbracketed and keyed by its path, with a cross-check against Prowide's delimiters (`SEQUENCE_DELIMITER_EVIDENCE_CONFLICT`) | `mt_pack._rows_from_mrg` |
| Multi-row repeat arrows (`---->` … `----|`) read as independent repetitive rows | a block of several rows becomes an implicit repetitive group (`_A`, `B1_A`); arrows nest (MT801) | `formatspec.parse_format_specification` |
| A misnumbered table row stalled the reader for the rest of the book (MT548) | `16R`/`16S` rows are complete one-line rows; other rows resynchronise within ±3 and record `ROW_NUMBER_RESYNC_…` | `formatspec` |
| Prose before the table swallowed row 1; wrapped format strings truncated; `No letter option` unparsed | shortest row tail wins; format fragments are re-joined; `No letter option` is the bare tag | `formatspec._split_row` |
| Covers with `(`, `,` or `MT n90` not identified; titles wrapped on the cover | cover regex widened; short wrapped lines joined; common-group guides compile one structure per Prowide member (`MT190`…`MT990`) | `document.identify`, `common_group.py` |
| Format grammar lacked groups, alternation and bounded repeats | `N*(…)`, `A\|B`, `[…]*N`, `n*Wc` | `swift_format` |
| Prowide-only macros (`<PARTYFLD-J>`, `<VAR-SEQU-n>`) | the guide's own FORMAT notation per option is the fallback; Prowide's macros (`<CUR>`, `<DATE4>`) keep precedence for their component meaning | `mt_pack._format_for` |
| Code lists merged across `22A`/`22C`; open lists ("may be used", "or bilaterally agreed") enforced; wide codes (`CREDIT`, `FIXEDFLOAT`) missed | specifications keyed by exact tag; open lists compile to no allowed set; codes are 2–12 characters or camel case; a list applies only to a single-token value | `formatspec._code_blocks`, `mt_pack` |
| Same tag twice in one sequence (MT011's `175`, MT360's `18A`, MT942's `34F`) unaddressable | ordinal-aware addressing: the n-th value at an address is the n-th row, in composer, parser, Excel and JSON | `parser._TextBlockReader`, `generator.resolve` |
| Nested unbracketed repeats (`_A1` inside `_A`) refused on import | the parser opens the parent occurrence implicitly; leading-tag candidates are ranked by structural nearness | `parser._implicit_parent`, `_implicit_target` |
| Mandatory sequences with only optional rows never materialised | the sample opens them with their first value-carrying row (gate and runtime samples alike) | `mt_pack.run_mt_gates`, `samples._initial_selection` |
| `64!h` and other fixed widths over-truncated | synthetic fill repeats to the width | `swift_format._fill` |

## The generation gate

A structure is `GENERATION_READY` only when, through the ordinary engine:

1. **LOAD** — the pack loads into a `MessageSpecification`.
2. **SAMPLE** — every mandatory row (and the opener of every mandatory sequence) gets a
   synthetic value from its own notation; a generic row without qualifier evidence stops
   here (`QUALIFIER_EVIDENCE_MISSING`).
3. **VALIDATE** — the deterministic validator reports no finding.
4. **COMPOSE** — Block 4 composes; the FIN envelope follows from profile data.
5. **PARSE** — the parser reads the composed message back without an issue.
6. **ROUND_TRIP** — `Compose(Parse(Compose(v))) == Compose(v)`.

Every gate is terminal and every finding is recorded on the structure (`gates`) and in the
catalogue (`blockers`). `GENERATION_READY` means structure-backed test generation; it does
not mean complete semantic rules, SWIFT certification or conformance.

## Measured result

| | Baseline (main `0bbd7d0`) | After |
|---|---|---|
| MT catalogue entries | 419 | 481 |
| Generation-ready entries | 250 (16 configured + 234 preview) | 424 (16 + 408) |
| SR2026 structures ready | 47 / 146 | 210 / 210 |
| SR2025 structures ready | 187 / 271 | 198 / 271 |
| Distinct MT types with a ready structure | 227 / 271 | 258 / 271 |
| API matrix (sample → FIN → import → round trip → Excel → JSON) | — | 408 / 408 |

The 481 entries are the 16 configured messages, the 271 Prowide SR2025 models (16 of them
shadowed by the configured lane and not listed), the 210 SR2026 guide-backed structures
(MT541 and the seven common-group guides included) and the guides identified since.

## What remains blocked, and why

| Root cause | Entries | Status |
|---|---:|---|
| `QUALIFIER_EVIDENCE_MISSING` | 35 | SR2025 Prowide-only structures of Category 3/5 messages whose mandatory fields are generic. Prowide records no qualifier legality; a Message Reference Guide does, and the SR2026 lane of every one of these messages is generation-ready. Using the SR2026 tables for the SR2025 lane would conflate releases, so it is not done. |
| `FORMAT_NOTATION_NOT_IN_SOURCE` | 17 | Category 0 and Category 6/8 messages whose only notation is a Prowide-internal macro (`<?>`, `{65x}n`, `<VAR-SEQU-n>`, `<CC>[14<DATE1>]`) and for which no guide exists in the knowledge base. A pattern would be an invention. |
| `PROWIDE_NO_BLOCK4_FIELDS` | 5 | MT035, MT043, MT048, MT049, MT096: Prowide models with no Block 4 field groups and no guide. |

Thirteen message types therefore have no generation-ready structure in either release; all
thirteen are FIN system or Category 0 messages for which the knowledge base holds no
authoritative structure beyond Prowide's empty or macro-only model.

## Known limitations of the runtime model

- A field marked repetitive inside one sequence occurrence renders once per occurrence;
  multi-row repeat blocks are sequences and repeat as units.
- Components (`50K`'s five lines, `61`'s ten subfields) are one canonical value validated
  by one pattern.
- SR2025 Prowide models and SR2026 guides are different releases; a reconciliation verdict
  is `RELEASE_CHANGE` or `SOURCE_MODEL_DIFFERENCE`, never resolved by guessing.

## Commands

```bash
make knowledge-sync                 # parse, segment, index, compile (incremental)
make knowledge-rebuild-structures   # re-read guide artifacts from cached text, recompile packs
make knowledge-reports-write        # docs/generated/{universal-message-readiness,knowledge-rag-coverage,
                                    #   ai-sample-readiness,universal-mt-generation-coverage,mt-generation-blockers}.md
KNOWLEDGE_MATRIX_DB=build/knowledge/knowledge.sqlite3 \
  backend/.venv/bin/pytest backend/tests/knowledge_base/test_universal_generation_matrix.py -k real_corpus -s
```

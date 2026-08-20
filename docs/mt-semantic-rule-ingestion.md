# MT Semantic Rule Ingestion

Phase 5A adds the MT foundation for semantic rule ingestion. It does not install a real MT
business-rule pack and it does not promote Prowide structural discovery into runtime
authority.

## What exists

The MT path now has:

- MT-aware source metadata: SRU, applicable MT categories, explicit message identifiers,
  redistribution policy and external-model approval flags.
- deterministic ingestion and segmentation through the existing rule-source pipeline;
- an extraction CLI path for `--format MT`;
- an offline scripted MT evaluation corpus;
- canonical MT structural-reference validation against the Phase 4B Prowide fixture;
- runtime Rule Pack compilation through the existing `FieldRef` row ids and triples;
- generated readiness reports:
  - [generated/mt-semantic-readiness.md](generated/mt-semantic-readiness.md)
  - [generated/mt-semantic-source-readiness.md](generated/mt-semantic-source-readiness.md)

The same review gate still applies: a candidate pack is inert until it is reviewed,
committed, merged and loaded at startup.

## What does not exist

No authorised MT semantic source is present in this repository. The only MT semantic
source committed here is `SYNTH-MT-SEMANTIC-V1`, a synthetic fixture invented for tests.

Therefore:

- no Phase 5A base-standard MT Rule Pack is installed;
- no real market-practice MT Rule Pack is installed;
- no real client-profile MT Rule Pack is installed;
- candidate MT rules do not appear in Create Message or Message Intelligence;
- normal FastAPI runtime does not import Prowide, Java, Maven or Gradle;
- no runtime MT structure is rewritten from Prowide evidence.

`REAL_MT_SEMANTIC_SOURCE_AVAILABLE = NO`

## Reference model

MT semantic source references are validated in two layers:

1. Prowide structural evidence proves that a source model, sequence and tag shape exists
   in the pinned SRU fixture.
2. The runtime Rule Pack still compiles against the installed MT row id or
   sequence/tag/qualifier triple already used by the existing rule engine.

For example, a source reference to MT541 settlement transaction type resolves as metadata:

```text
MT:SR2025:MT541:SETDET:22F:SETR
```

The active rule, if a reviewed pack is later installed, still addresses the runtime row:

```yaml
field: {format: MT, fieldId: MT541-E-22F-SETR}
```

The canonical `MT:...` reference is provenance. It is not a new runtime address and it
does not mutate the standards registry.

## What validation refuses

The MT semantic resolver raises named findings for unsafe or unsupported claims:

| Finding | Meaning |
|---|---|
| `MT_RULE_MESSAGE_NOT_FOUND` | no Prowide source model exists for that message |
| `MT_RULE_SRU_MISMATCH` | source SRU and structural fixture SRU differ |
| `MT_RULE_SEQUENCE_NOT_FOUND` | the named sequence was not observed |
| `MT_RULE_FIELD_NOT_FOUND` | the named tag was not observed in that sequence |
| `MT_RULE_OPTION_NOT_RESOLVED` | tag and option conflict |
| `MT_RULE_QUALIFIER_NOT_RESOLVED` | qualifier cannot become an installed runtime row |
| `MT_RULE_COMPONENT_NOT_FOUND` | component index is absent from global field reflection |
| `MT_RULE_REFERENCE_AMBIGUOUS` | the reference is not precise enough |

Global field reflection is used only for parser/component metadata. It does not establish
message-level requiredness, qualifier legality, code legality or cardinality.

## Commands

```bash
make mt-rule-source-ingest SOURCE_ID=SYNTH-MT-SEMANTIC-V1
make mt-rule-extract SOURCE_ID=SYNTH-MT-SEMANTIC-V1 MESSAGE=MT541
make evaluate-mt-rule-extraction
make mt-rule-readiness-write
make mt-rule-check
make test-live-mt-rule-extraction
```

`make mt-rule-check` is offline and costs nothing. `make test-live-mt-rule-extraction`
calls the configured provider and is a measurement, not a CI default.

## Boundary

Prowide remains build-time/offline structural evidence. It is not SWIFT certification,
not ISO 15022 completeness, not business-rule authority, not market-practice authority and
not client-profile authority.

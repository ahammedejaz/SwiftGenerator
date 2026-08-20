# Rule occurrence semantics

Occurrence-aware evaluation is an internal Rule Engine capability. It lets a declarative
rule say that an assertion is checked inside each occurrence of one repeatable structural
scope. It does not change the browser, Excel, JSON API, parser, composer, or normal public
input contracts.

## Occurrence identity

An occurrence identity is:

1. the sequence path;
2. the parent occurrence lineage;
3. the local one-based occurrence number.

For example, `P[1]/C[2]` and `P[2]/C[2]` are different identities even though both child
occurrences have local index `2`. A bare number is never a safe occurrence identity.

## Evaluation context

Old rule evaluation receives a value bag:

```text
field key -> values in occurrence order
```

That path remains valid and keeps its old global semantics.

Scoped evaluation may instead receive an internal `EvaluationContext`:

```text
global value bag
occurrence-indexed values
active occurrence, when evaluating inside a scope
```

The context is built by adapters such as the MT Message Reference Guide candidate
evaluator. Runtime studio requests can keep using the legacy bag until a reviewed rule pack
needs scoped runtime validation.

## DSL node

The scoped AST node is `forEachOccurrence`:

```json
{
  "forEachOccurrence": {
    "sequencePath": "E1",
    "assert": {
      "implies": {
        "if": {
          "field": {"format": "MT", "sequencePath": "E1", "tag": "95", "qualifier": "PSET"},
          "operator": "EXISTS"
        },
        "then": {
          "field": {"format": "MT", "sequencePath": "E1", "tag": "97", "qualifier": "SAFE"},
          "operator": "ABSENT"
        }
      }
    }
  }
}
```

The example is synthetic in shape; it shows the mechanism, not an approved runtime rule.

## Global versus scoped predicates

Outside `forEachOccurrence`, predicates behave exactly as before:

- `EXISTS` means at least one value exists anywhere in the message.
- `ABSENT` means no value exists anywhere in the message.
- `COUNT` counts all present values for the referenced field.

Inside `forEachOccurrence`, predicates read only values in the current occurrence of the
selected scope:

- `EXISTS` means the field exists in this occurrence.
- `ABSENT` means the field is absent in this occurrence.
- `COUNT` counts values in this occurrence.

Zero occurrences satisfy `forEachOccurrence`, matching ordinary universal semantics.

## Nested scopes

Nested scopes filter by lineage. If the active occurrence is `P[1]`, an inner
`forEachOccurrence` over `C` sees `P[1]/C[1]` and `P[1]/C[2]`, not `P[2]/C[1]`.

## Compiler behaviour

The compiler validates scoped rules before they can become candidates:

- the scope exists in the target structure;
- the scope is repeatable where scoped iteration is used;
- references inside the scoped assertion stay inside the selected scope;
- scoped AST requires the current DSL version;
- old unscoped packs continue to compile under their recorded versions.

Invalid scopes fail loudly with structured rule-engine findings. Rule packs still only
observe values; they cannot create sequences, fields, cardinality, options, or values.

## Findings

When a scoped assertion fails, validation issues may include additive occurrence metadata:

```json
{
  "sequencePath": "E1",
  "occurrence": 2,
  "path": "E1[2]",
  "lineage": ["E1[2]"]
}
```

Existing clients can ignore this field. The business message remains the rule finding
text; occurrence metadata is for navigation and reviewer diagnostics.

## Performance

Unscoped rules still use the original field-key lookup. Scoped rules reuse the same global
bag and add a one-time occurrence-indexed projection. Evaluation scans only occurrences for
the named scope.

## Security

Occurrence predicates are declarative data. Scope paths resolve through the structure
index. No XPath, Python `eval`, JavaScript, shell, template execution, dynamic import,
model call, or arbitrary object traversal is involved.

## Backward compatibility

`rule-engine/1` and `rule-dsl/1` reviewed packs remain supported. New scoped candidates use
`rule-engine/2` and `rule-dsl/2`. Existing normal MT/MX generation, validation, import,
Excel, and JSON API flows remain unchanged unless a reviewed scoped rule pack is installed
through the ordinary source-control process.

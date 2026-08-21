"""The specification rule engine: declarative business rules with traceable evidence.

Structure is one authority; business rules are another. This package owns the second.
A Rule Pack is versioned configuration — never Python — that says what a *valid use* of an
already-valid structure looks like, and every rule in it points at the source location that
established it.

Three invariants hold everywhere below:

1. Rule Packs read structure and never write it.
2. A model may propose a candidate; only a reviewed, source-controlled pack is ever loaded.
3. Runtime evaluation is pure and calls no model.
"""

from __future__ import annotations

#: Identifies the engine and its pack contract, the way ``spec-engine/1`` identifies the
#: structure compiler. Bump when the pack format or evaluation semantics change.
RULE_ENGINE_VERSION = "rule-engine/2"
SUPPORTED_RULE_ENGINE_VERSIONS = ("rule-engine/1", RULE_ENGINE_VERSION)

#: The declarative language version recorded in every compiled pack.
DSL_VERSION = "rule-dsl/3"
#: Occurrence scope arrived with rule-dsl/2; component extraction and allEqual with rule-dsl/3.
OCCURRENCE_DSL_VERSIONS = ("rule-dsl/2", DSL_VERSION)
SUPPORTED_DSL_VERSIONS = ("rule-dsl/1", "rule-dsl/2", DSL_VERSION)

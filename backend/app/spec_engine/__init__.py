"""The specification engine: compiles source schemas into specification packs.

Development-time tooling only. Nothing in the runtime request path imports this package;
the running application consumes the packs it emits — ordinary files in the MX
specification directory — through the unchanged registry.

    ISO 20022 XSD → xsd_loader → xsd_reader (IR) → mapper → emit → pack YAML

``python -m app.spec_engine --help`` is the front door.
"""

#: Names the compiler and its output contract. Bump when emitted packs change shape, so a
#: pack records which compiler produced it and a regeneration diff is explainable.
COMPILER_VERSION = "spec-engine/1"

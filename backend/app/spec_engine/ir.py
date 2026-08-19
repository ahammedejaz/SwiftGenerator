"""The compiler's intermediate representation — deliberately small.

The reader turns schema DOM into these shapes; the mapper turns them into the
repository's MX specification model. Nothing downstream touches lxml nodes, and nothing
here knows about YAML. Later phases (MDR metadata, market-practice overlays) enrich this
layer without either neighbour changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Facets:
    """Restriction facets exactly as the schema states them."""

    base: str  # xs:string / xs:decimal / xs:boolean / xs:date / xs:dateTime
    enumerations: tuple[str, ...] = ()
    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    length: int | None = None
    total_digits: int | None = None
    fraction_digits: int | None = None
    min_inclusive: str | None = None
    max_inclusive: str | None = None


@dataclass(frozen=True)
class SimpleTypeIR:
    name: str | None  # None for anonymous types
    facets: Facets


@dataclass(frozen=True)
class AttributeIR:
    name: str
    required: bool
    simple_type: SimpleTypeIR | None


@dataclass
class ElementIR:
    name: str
    min_occurs: int
    max_occurs: int | None  # None = unbounded
    #: Exactly one of the following three is set.
    simple_type: SimpleTypeIR | None = None
    complex_type: ComplexTypeIR | None = None
    type_ref: str | None = None  # QName, resolved by the reader before mapping


@dataclass
class ComplexTypeIR:
    name: str | None
    #: ``sequence`` or ``choice`` — the content model of the type.
    model: str = "sequence"
    children: list[ElementIR] = field(default_factory=list)
    attributes: list[AttributeIR] = field(default_factory=list)
    #: Simple content: the type extends a simple type and adds attributes (amounts).
    simple_content: SimpleTypeIR | None = None
    #: The type permits open XML content through xs:any. The mapper does not write open
    #: content; optional open-content branches are omitted with a visible limitation.
    open_content: bool = False


@dataclass
class SchemaIR:
    target_namespace: str
    source_files: tuple[str, ...]
    global_elements: dict[str, ElementIR] = field(default_factory=dict)
    complex_types: dict[str, ComplexTypeIR] = field(default_factory=dict)
    simple_types: dict[str, SimpleTypeIR] = field(default_factory=dict)

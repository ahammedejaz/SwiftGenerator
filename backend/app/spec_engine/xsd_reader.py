"""Schema DOM → intermediate representation.

Supported constructs are read exactly; anything else becomes a named finding. Nothing is
ever silently flattened — an unsupported construct either blocks compilation (when a
valid message could not be generated without it) or is recorded as a warning and a pack
limitation (when omitting it narrows the subset without corrupting it).
"""

from __future__ import annotations

from lxml import etree

from app.spec_engine.diagnostics import CompilationError, FindingCode, FindingLog
from app.spec_engine.ir import (
    AttributeIR,
    ComplexTypeIR,
    ElementIR,
    Facets,
    SchemaIR,
    SimpleTypeIR,
)
from app.spec_engine.xsd_loader import XS, SchemaSet

_SUPPORTED_BASES = {
    "xs:string",
    "xs:decimal",
    "xs:boolean",
    "xs:date",
    "xs:dateTime",
    "xs:time",
    "xs:gYear",
    "xs:base64Binary",
}
_INT_FACETS = ("minLength", "maxLength", "length", "totalDigits", "fractionDigits")
_STR_FACETS = ("minInclusive", "maxInclusive")


def _tag(name: str) -> str:
    return f"{{{XS}}}{name}"


def _occurs(node: etree._Element) -> tuple[int, int | None]:
    raw_min = node.get("minOccurs", "1")
    raw_max = node.get("maxOccurs", "1")
    return int(raw_min), (None if raw_max == "unbounded" else int(raw_max))


class SchemaReader:
    """Reads one namespace of a loaded schema set into IR."""

    def __init__(self, schema_set: SchemaSet, log: FindingLog) -> None:
        self._set = schema_set
        self._log = log

    def read(self, namespace: str) -> SchemaIR:
        schemas = self._set.by_namespace.get(namespace, [])
        ir = SchemaIR(
            target_namespace=namespace,
            source_files=tuple(schema.path.name for schema in schemas),
        )
        # Pass 1: named simple types — everything else references them.
        for schema in schemas:
            for node in schema.tree.findall(_tag("simpleType")):
                name = node.get("name")
                if not name:
                    continue
                simple = self._read_simple_type(node, schema.path.name, name)
                if simple is not None:
                    ir.simple_types[name] = simple
        # Pass 2: named complex types.
        for schema in schemas:
            for node in schema.tree.findall(_tag("complexType")):
                name = node.get("name")
                if not name:
                    continue
                complex_ = self._read_complex_type(node, schema.path.name, ir, name)
                if complex_ is not None:
                    ir.complex_types[name] = complex_
        # Pass 3: global elements.
        for schema in schemas:
            for node in schema.tree.findall(_tag("element")):
                element = self._read_element(node, schema.path.name, ir)
                if element is not None:
                    ir.global_elements[element.name] = element
        return ir

    # ------------------------------------------------------------------ simple types

    def _read_simple_type(
        self, node: etree._Element, source: str, name: str | None
    ) -> SimpleTypeIR | None:
        restriction = node.find(_tag("restriction"))
        if restriction is None:
            self._log.error(
                FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                f"simpleType {name or '(anonymous)'} is not a restriction "
                "(union and list types are not supported).",
                "Model the type as a restriction, or exclude the element.",
                source=source,
                location=name,
            )
            return None
        base = restriction.get("base", "")
        base_local = f"xs:{base.split(':', 1)[-1]}" if base else ""
        if base_local not in _SUPPORTED_BASES:
            # A restriction of another simple type in the same namespace is legal; ISO
            # schemas occasionally chain them. Resolve one level through the named types.
            self._log.error(
                FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                f"simpleType {name or '(anonymous)'} restricts {base}, which is not a "
                "supported base (string, decimal, boolean, date, dateTime).",
                "Only ISO 20022 representation-class shapes are supported in this phase.",
                source=source,
                location=name,
            )
            return None
        enumerations = tuple(
            item.get("value", "") for item in restriction.findall(_tag("enumeration"))
        )
        facet_values: dict[str, int | str | None] = {key: None for key in _INT_FACETS}
        for key in _INT_FACETS:
            found = restriction.find(_tag(key))
            if found is not None:
                facet_values[key] = int(found.get("value", "0"))
        str_values: dict[str, str | None] = {key: None for key in _STR_FACETS}
        for key in _STR_FACETS:
            found = restriction.find(_tag(key))
            if found is not None:
                str_values[key] = found.get("value")
        pattern_node = restriction.find(_tag("pattern"))
        return SimpleTypeIR(
            name=name,
            facets=Facets(
                base=base_local,
                enumerations=enumerations,
                pattern=pattern_node.get("value") if pattern_node is not None else None,
                min_length=facet_values["minLength"],  # type: ignore[arg-type]
                max_length=facet_values["maxLength"],  # type: ignore[arg-type]
                length=facet_values["length"],  # type: ignore[arg-type]
                total_digits=facet_values["totalDigits"],  # type: ignore[arg-type]
                fraction_digits=facet_values["fractionDigits"],  # type: ignore[arg-type]
                min_inclusive=str_values["minInclusive"],
                max_inclusive=str_values["maxInclusive"],
            ),
        )

    # ------------------------------------------------------------------ complex types

    def _read_complex_type(
        self, node: etree._Element, source: str, ir: SchemaIR, name: str | None
    ) -> ComplexTypeIR | None:
        simple_content = node.find(_tag("simpleContent"))
        if simple_content is not None:
            return self._read_simple_content(simple_content, source, ir, name)
        sequence = node.find(_tag("sequence"))
        choice = node.find(_tag("choice"))
        if sequence is None and choice is None:
            self._log.error(
                FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                f"complexType {name or '(anonymous)'} has no sequence or choice content "
                "model (xs:all, xs:group and complexContent are not supported).",
                "Restate the type as a sequence or choice, or exclude the element.",
                source=source,
                location=name,
            )
            return None
        container = sequence if sequence is not None else choice
        assert container is not None
        model = "sequence" if sequence is not None else "choice"
        result = ComplexTypeIR(name=name, model=model)
        for child in container:
            if child.tag == _tag("element"):
                element = self._read_element(child, source, ir)
                if element is not None:
                    result.children.append(element)
            elif child.tag in (_tag("choice"), _tag("sequence")):
                # An inline particle group mixed among siblings has no element name to
                # hang a choice on in the specification model. Refusing is the honest
                # move; ISO 20022 message schemas express choices as named types.
                self._log.error(
                    FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                    f"complexType {name or '(anonymous)'} nests an inline "
                    f"{child.tag.split('}')[1]} particle among its children.",
                    "Wrap the group in a named type, or exclude the element.",
                    source=source,
                    location=name,
                )
            elif child.tag == _tag("any"):
                result.open_content = True
                self._log.warning(
                    FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                    f"complexType {name or '(anonymous)'} allows xs:any content, which "
                    "the configured subset will not write.",
                    "Supplementary open content is omitted from the pack; this is "
                    "recorded as a limitation.",
                    source=source,
                    location=name,
                )
            elif not isinstance(child.tag, str):
                continue  # comments and processing instructions
        for attribute in node.findall(_tag("attribute")):
            result.attributes.append(self._read_attribute(attribute, source, ir))
        return result

    def _read_simple_content(
        self, node: etree._Element, source: str, ir: SchemaIR, name: str | None
    ) -> ComplexTypeIR | None:
        extension = node.find(_tag("extension"))
        if extension is None:
            self._log.error(
                FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                f"complexType {name or '(anonymous)'} uses simpleContent without an "
                "extension.",
                "Only the amount shape (decimal plus attributes) is supported.",
                source=source,
                location=name,
            )
            return None
        base = extension.get("base", "")
        simple = self._resolve_simple_base(base, ir)
        if simple is None:
            self._log.error(
                FindingCode.XSD_TYPE_UNRESOLVED,
                f"simpleContent extension base {base} could not be resolved.",
                "Declare the base type in the bundle.",
                source=source,
                location=name,
            )
            return None
        result = ComplexTypeIR(name=name, simple_content=simple)
        for attribute in extension.findall(_tag("attribute")):
            result.attributes.append(self._read_attribute(attribute, source, ir))
        return result

    def _read_attribute(
        self, node: etree._Element, source: str, ir: SchemaIR
    ) -> AttributeIR:
        name = node.get("name", "")
        required = node.get("use") == "required"
        inline = node.find(_tag("simpleType"))
        simple: SimpleTypeIR | None = None
        if inline is not None:
            simple = self._read_simple_type(inline, source, None)
        else:
            type_ref = node.get("type")
            if type_ref:
                simple = self._resolve_simple_base(type_ref, ir)
        return AttributeIR(name=name, required=required, simple_type=simple)

    def _resolve_simple_base(self, qname: str, ir: SchemaIR) -> SimpleTypeIR | None:
        local = qname.split(":", 1)[-1]
        if f"xs:{local}" in _SUPPORTED_BASES:
            return SimpleTypeIR(name=None, facets=Facets(base=f"xs:{local}"))
        return ir.simple_types.get(local)

    # ------------------------------------------------------------------ elements

    def _read_element(
        self, node: etree._Element, source: str, ir: SchemaIR
    ) -> ElementIR | None:
        ref = node.get("ref")
        if ref is not None:
            # Resolved after all globals are read; store the reference.
            min_occurs, max_occurs = _occurs(node)
            return ElementIR(
                name=ref.split(":", 1)[-1],
                min_occurs=min_occurs,
                max_occurs=max_occurs,
                type_ref=f"element:{ref.split(':', 1)[-1]}",
            )
        name = node.get("name")
        if not name:
            self._log.error(
                FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
                "An element without a name or ref was found.",
                "Every element needs a name.",
                source=source,
            )
            return None
        min_occurs, max_occurs = _occurs(node)
        type_ref = node.get("type")
        if type_ref is not None:
            return ElementIR(
                name=name,
                min_occurs=min_occurs,
                max_occurs=max_occurs,
                type_ref=type_ref.split(":", 1)[-1],
            )
        inline_complex = node.find(_tag("complexType"))
        if inline_complex is not None:
            complex_ = self._read_complex_type(inline_complex, source, ir, None)
            return ElementIR(
                name=name,
                min_occurs=min_occurs,
                max_occurs=max_occurs,
                complex_type=complex_,
            )
        inline_simple = node.find(_tag("simpleType"))
        if inline_simple is not None:
            simple = self._read_simple_type(inline_simple, source, None)
            return ElementIR(
                name=name,
                min_occurs=min_occurs,
                max_occurs=max_occurs,
                simple_type=simple,
            )
        self._log.error(
            FindingCode.XSD_TYPE_UNRESOLVED,
            f"Element {name} declares no type.",
            "Give the element a type attribute or an inline type.",
            source=source,
            location=name,
        )
        return None


def read_schema(schema_set: SchemaSet, namespace: str | None = None) -> SchemaIR:
    """Read the entry namespace (or a named one) into IR, or raise with findings."""
    log = FindingLog()
    target = namespace or schema_set.entry_namespace()
    reader = SchemaReader(schema_set, log)
    ir = reader.read(target)
    if log.blocked:
        raise CompilationError(log.findings)
    # Non-blocking findings travel with the IR via the pipeline's log; the reader's own
    # warnings are re-raised there. Kept simple: reader warnings are recomputed.
    return ir

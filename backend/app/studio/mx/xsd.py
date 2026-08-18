"""XSD validation for generated ISO 20022 documents.

Two schema sources are supported, and the one that was used is always reported:

``OFFICIAL``
    A schema the operator placed in ``config/mx/xsd/official/`` as the official ISO 20022
    artifact, named after the message version, for example ``sese.023.001.11.xsd``. When
    present it is preferred. ``OFFICIAL`` records where the file came from and the
    operator's declaration — the platform cannot verify the file is the genuine artifact.

``SUBSET_DERIVED``
    A schema generated from the repository's configured subset specification. This is a
    real XSD validated by libxml2 — it independently catches element order, cardinality,
    datatype and enumeration errors — but it describes the *configured subset*, not the
    complete official message definition. It must not be read as authoritative conformance.

If ``lxml`` is unavailable the layer reports ``SKIPPED`` rather than silently passing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from app.config import get_settings, source_path
from app.studio.models import IssueSeverity, Presence, ValidationIssue, ValidationLayer
from app.studio.mx.models import (
    MxDataType,
    MxElement,
    MxMessageSpec,
    MxRestriction,
    MxRestrictionBase,
)


def official_schema_directory() -> Path:
    """Where a licensed ISO 20022 schema is dropped in. Read per call, not cached at
    import, so pointing the setting at a drop directory needs no code change."""
    return source_path(get_settings().mx_official_xsd_directory, "mx", "xsd", "official")

XS = "http://www.w3.org/2001/XMLSchema"

#: Restrictions applied to each representation class in the derived schema.
SIMPLE_TYPES: dict[MxDataType, str] = {
    MxDataType.MAX16_TEXT: '<xs:restriction base="xs:string">'
    '<xs:minLength value="1"/><xs:maxLength value="16"/></xs:restriction>',
    MxDataType.MAX35_TEXT: '<xs:restriction base="xs:string">'
    '<xs:minLength value="1"/><xs:maxLength value="35"/></xs:restriction>',
    MxDataType.MAX70_TEXT: '<xs:restriction base="xs:string">'
    '<xs:minLength value="1"/><xs:maxLength value="70"/></xs:restriction>',
    MxDataType.MAX140_TEXT: '<xs:restriction base="xs:string">'
    '<xs:minLength value="1"/><xs:maxLength value="140"/></xs:restriction>',
    MxDataType.MAX350_TEXT: '<xs:restriction base="xs:string">'
    '<xs:minLength value="1"/><xs:maxLength value="350"/></xs:restriction>',
    MxDataType.EXACT4_ALPHANUMERIC: '<xs:restriction base="xs:string">'
    '<xs:pattern value="[A-Z0-9]{4}"/></xs:restriction>',
    MxDataType.ISIN: '<xs:restriction base="xs:string">'
    '<xs:pattern value="[A-Z]{2,2}[A-Z0-9]{9,9}[0-9]{1,1}"/></xs:restriction>',
    MxDataType.ANY_BIC: '<xs:restriction base="xs:string">'
    '<xs:pattern value="[A-Z0-9]{4,4}[A-Z]{2,2}[A-Z0-9]{2,2}([A-Z0-9]{3,3}){0,1}"/>'
    "</xs:restriction>",
    MxDataType.LEI: '<xs:restriction base="xs:string">'
    '<xs:pattern value="[A-Z0-9]{18,18}[0-9]{2,2}"/></xs:restriction>',
    MxDataType.ISO_DATE: '<xs:restriction base="xs:date"/>',
    MxDataType.ISO_DATE_TIME: '<xs:restriction base="xs:dateTime"/>',
    MxDataType.DECIMAL: '<xs:restriction base="xs:decimal">'
    '<xs:fractionDigits value="5"/><xs:totalDigits value="18"/></xs:restriction>',
    MxDataType.YES_NO: '<xs:restriction base="xs:boolean"/>',
}


_RESTRICTION_XSD_BASES = {
    MxRestrictionBase.TEXT: "xs:string",
    MxRestrictionBase.DECIMAL: "xs:decimal",
    MxRestrictionBase.DATE: "xs:date",
    MxRestrictionBase.DATE_TIME: "xs:dateTime",
    MxRestrictionBase.BOOLEAN: "xs:boolean",
}


def _restriction_xsd(restriction: MxRestriction) -> str:
    """Rebuild the source schema's facets so the derived XSD enforces the same rule."""
    facets: list[str] = []
    if restriction.pattern is not None:
        facets.append(f'<xs:pattern value="{escape(restriction.pattern, {chr(34): "&quot;"})}"/>')
    if restriction.length is not None:
        facets.append(f'<xs:length value="{restriction.length}"/>')
    if restriction.min_length is not None:
        facets.append(f'<xs:minLength value="{restriction.min_length}"/>')
    if restriction.max_length is not None:
        facets.append(f'<xs:maxLength value="{restriction.max_length}"/>')
    if restriction.total_digits is not None:
        facets.append(f'<xs:totalDigits value="{restriction.total_digits}"/>')
    if restriction.fraction_digits is not None:
        facets.append(f'<xs:fractionDigits value="{restriction.fraction_digits}"/>')
    if restriction.min_inclusive is not None:
        facets.append(f'<xs:minInclusive value="{restriction.min_inclusive}"/>')
    if restriction.max_inclusive is not None:
        facets.append(f'<xs:maxInclusive value="{restriction.max_inclusive}"/>')
    base = _RESTRICTION_XSD_BASES[restriction.base]
    return f'<xs:restriction base="{base}">{"".join(facets)}</xs:restriction>'


class SchemaSource(StrEnum):
    OFFICIAL = "OFFICIAL"
    SUBSET_DERIVED = "SUBSET_DERIVED"
    NONE = "NONE"


@dataclass(frozen=True)
class XsdOutcome:
    performed: bool
    passed: bool
    schema_source: SchemaSource
    detail: str
    issues: tuple[ValidationIssue, ...] = ()


def _type_name(path: tuple[str, ...]) -> str:
    return "T_" + "_".join(path)


def _emit(element: MxElement, path: tuple[str, ...], complex_types: list[str]) -> str:
    """Emit the inline declaration for ``element`` and register any complex type it needs."""
    occurs = ""
    if element.presence is not Presence.MANDATORY:
        occurs += ' minOccurs="0"'
    if element.max_occurs > 1:
        occurs += f' maxOccurs="{element.max_occurs}"'

    if element.is_leaf:
        data_type = element.data_type
        if data_type is None:
            generic = element.restriction
            assert generic is not None
            inline = f"<xs:simpleType>{_restriction_xsd(generic)}</xs:simpleType>"
            return f'<xs:element name="{element.name}"{occurs}>{inline}</xs:element>'
        if data_type is MxDataType.CODE:
            enumerations = "".join(
                f'<xs:enumeration value="{code}"/>' for code in element.codes
            )
            inline = (
                "<xs:simpleType>"
                f'<xs:restriction base="xs:string">{enumerations}</xs:restriction>'
                "</xs:simpleType>"
            )
            return f'<xs:element name="{element.name}"{occurs}>{inline}</xs:element>'
        if data_type is MxDataType.AMOUNT:
            name = _type_name((*path, element.name))
            complex_types.append(
                f'<xs:complexType name="{name}">'
                "<xs:simpleContent>"
                '<xs:extension base="xs:decimal">'
                '<xs:attribute name="Ccy" use="required">'
                "<xs:simpleType>"
                '<xs:restriction base="xs:string">'
                '<xs:pattern value="[A-Z]{3,3}"/>'
                "</xs:restriction>"
                "</xs:simpleType>"
                "</xs:attribute>"
                "</xs:extension>"
                "</xs:simpleContent>"
                "</xs:complexType>"
            )
            return f'<xs:element name="{element.name}" type="{name}"{occurs}/>'
        restriction = SIMPLE_TYPES[data_type]
        inline = f"<xs:simpleType>{restriction}</xs:simpleType>"
        return f'<xs:element name="{element.name}"{occurs}>{inline}</xs:element>'

    children = "".join(
        _emit(child, (*path, element.name), complex_types) for child in element.children
    )
    container = "xs:choice" if element.choice else "xs:sequence"
    inline = f"<xs:complexType><{container}>{children}</{container}></xs:complexType>"
    return f'<xs:element name="{element.name}"{occurs}>{inline}</xs:element>'


def derive_schema(spec: MxMessageSpec) -> str:
    """Generate an XSD describing the configured subset of ``spec``."""
    complex_types: list[str] = []
    body = "".join(
        _emit(element, (spec.message_root,), complex_types) for element in spec.structure
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<xs:schema xmlns:xs="{XS}" targetNamespace="{spec.namespace}" '
        f'xmlns="{spec.namespace}" elementFormDefault="qualified">'
        f'{"".join(complex_types)}'
        f'<xs:element name="{spec.document_element}">'
        "<xs:complexType><xs:sequence>"
        f'<xs:element name="{spec.message_root}">'
        f"<xs:complexType><xs:sequence>{body}</xs:sequence></xs:complexType>"
        "</xs:element>"
        "</xs:sequence></xs:complexType>"
        "</xs:element>"
        "</xs:schema>"
    )


def official_schema_path(spec: MxMessageSpec) -> Path | None:
    candidate = official_schema_directory() / f"{spec.version}.xsd"
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=32)
def _compiled(version: str, source: str, schema_text: str):  # type: ignore[no-untyped-def]
    from lxml import etree

    return etree.XMLSchema(etree.fromstring(schema_text.encode()))


#: Serialises validation against the cached schemas.
#:
#: `XMLSchema.validate()` writes its findings onto the schema object — `schema.error_log` is
#: instance state, and libxml2 keeps a validation context there too. Those objects are shared
#: by every caller through the cache above, and FastAPI runs sync endpoints in a threadpool,
#: so two requests validating at the same time interleave on one object: a verdict, or a list
#: of errors, can be attributed to the wrong document. For a tool whose whole job is telling a
#: tester what is wrong with *their* message, that is worse than being slow.
#:
#: Caught by CI, where a lifecycle test failed about one run in three with
#: "No matching global declaration available for the validation root" — an error belonging to
#: some other document's schema. It did not reproduce on macOS, whose lxml wheel bundles a
#: different libxml2; the mechanism is the same either way and does not depend on the
#: platform to be wrong.
#:
#: Compilation stays cached, which is the expensive part. Validating a settlement message
#: takes microseconds, so serialising it costs nothing measurable.
_VALIDATION_LOCK = threading.Lock()


def validate_document(spec: MxMessageSpec, document_xml: str) -> XsdOutcome:
    """Validate a standalone ``Document`` against the best schema available."""
    try:
        from lxml import etree
    except ImportError:
        return XsdOutcome(
            performed=False,
            passed=False,
            schema_source=SchemaSource.NONE,
            detail="XSD validation was skipped because lxml is not installed. "
            "Install lxml to enable schema validation.",
        )

    official = official_schema_path(spec)
    if official is not None:
        schema_text = official.read_text(encoding="utf-8")
        source = SchemaSource.OFFICIAL
        detail_prefix = (
            f"Validated against the operator-supplied official schema {official.name}."
        )
    else:
        schema_text = derive_schema(spec)
        source = SchemaSource.SUBSET_DERIVED
        detail_prefix = (
            "Validated against a schema derived from the repository's configured subset. "
            "This is not authoritative ISO 20022 conformance; place the official "
            f"{spec.version}.xsd in config/mx/xsd/official/ to validate against it."
        )

    try:
        schema = _compiled(spec.version, source.value, schema_text)
    except etree.XMLSchemaParseError as error:
        return XsdOutcome(
            performed=False,
            passed=False,
            schema_source=source,
            detail=f"The schema could not be compiled: {error}",
        )

    try:
        tree = etree.fromstring(document_xml.encode())
    except etree.XMLSyntaxError as error:
        return XsdOutcome(
            performed=True,
            passed=False,
            schema_source=source,
            detail=f"The document is not well-formed XML: {error}",
            issues=(
                ValidationIssue(
                    rule_id="MX_XML_NOT_WELL_FORMED",
                    severity=IssueSeverity.ERROR,
                    layer=ValidationLayer.XML_WELL_FORMED,
                    message=f"The generated XML is not well formed: {error}",
                    suggestion="This indicates a platform defect. Report the scenario.",
                ),
            ),
        )

    # The verdict and the error log are one atomic read: `validate()` writes the log onto
    # the shared schema object, so releasing the lock between them would let another thread
    # overwrite the findings before they are copied out.
    with _VALIDATION_LOCK:
        valid = schema.validate(tree)
        entries = [] if valid else list(schema.error_log)
    if valid:
        return XsdOutcome(
            performed=True, passed=True, schema_source=source, detail=detail_prefix
        )
    issues = tuple(
        ValidationIssue(
            rule_id="MX_XSD_INVALID",
            severity=IssueSeverity.ERROR,
            layer=ValidationLayer.XSD,
            location=entry.path,
            message=entry.message,
            suggestion="Correct the element highlighted by the schema error.",
        )
        for entry in entries
    )
    return XsdOutcome(
        performed=True,
        passed=False,
        schema_source=source,
        detail=f"{detail_prefix} {len(issues)} schema error(s) found.",
        issues=issues,
    )

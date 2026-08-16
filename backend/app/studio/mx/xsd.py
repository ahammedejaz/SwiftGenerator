"""XSD validation for generated ISO 20022 documents.

Two schema sources are supported, and the one that was used is always reported:

``OFFICIAL``
    An authoritative ISO 20022 schema placed in ``config/mx/xsd/official/``, named after
    the message version, for example ``sese.023.001.11.xsd``. When present it is preferred.

``SUBSET_DERIVED``
    A schema generated from the repository's configured subset specification. This is a
    real XSD validated by libxml2 — it independently catches element order, cardinality,
    datatype and enumeration errors — but it describes the *configured subset*, not the
    complete official message definition. It must not be read as authoritative conformance.

If ``lxml`` is unavailable the layer reports ``SKIPPED`` rather than silently passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from app.studio.models import IssueSeverity, Presence, ValidationIssue, ValidationLayer
from app.studio.mx.models import MxDataType, MxElement, MxMessageSpec

OFFICIAL_SCHEMA_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "config" / "mx" / "xsd" / "official"
)

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
        assert data_type is not None
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
    candidate = OFFICIAL_SCHEMA_DIRECTORY / f"{spec.version}.xsd"
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=32)
def _compiled(version: str, source: str, schema_text: str):  # type: ignore[no-untyped-def]
    from lxml import etree

    return etree.XMLSchema(etree.fromstring(schema_text.encode()))


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
        detail_prefix = f"Validated against the official schema {official.name}."
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

    if schema.validate(tree):
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
        for entry in schema.error_log
    )
    return XsdOutcome(
        performed=True,
        passed=False,
        schema_source=source,
        detail=f"{detail_prefix} {len(issues)} schema error(s) found.",
        issues=issues,
    )

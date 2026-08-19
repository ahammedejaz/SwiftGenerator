"""IR → the repository's MX specification model.

Structure facts come from the schema and only from the schema. Presentation is
mechanical and deterministic — camelCase splitting plus the published ISO 20022
abbreviation conventions — and has no authority over anything: a pack with ugly labels
still validates, generates and round-trips identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.spec_engine import COMPILER_VERSION
from app.spec_engine.diagnostics import FindingCode, FindingLog
from app.spec_engine.ir import ComplexTypeIR, ElementIR, Facets, SchemaIR, SimpleTypeIR
from app.spec_engine.patterns import sample_from_pattern

NAMESPACE_PREFIX = "urn:iso:std:iso:20022:tech:xsd:"
#: The specification model's ceiling for a repeatable element. An unbounded schema
#: cardinality compiles to this and is recorded as a pack limitation — an explicit,
#: visible authoring bound, never a silent flattening.
OCCURS_CEILING = 1_000
_RECURSION_LIMIT = 64

#: Representation classes the runtime already knows by name. Mapping by name keeps packs
#: idiomatic; the source-XSD gate proves the semantics agree, and the runtime's own rule
#: is never looser than the schema's because generation is validated against the source.
_KNOWN_DATA_TYPES = {
    "Max16Text",
    "Max35Text",
    "Max70Text",
    "Max140Text",
    "Max350Text",
    "Exact4AlphaNumericText",
    "ISINOct2015Identifier",
    "AnyBICDec2014Identifier",
    "LEIIdentifier",
    "ISODate",
    "ISODateTime",
    "DecimalNumber",
    "YesNoIndicator",
}

#: XSD built-in types an element may use directly (`type="xs:string"`).
_BUILTIN_BASES = {
    "string",
    "decimal",
    "boolean",
    "date",
    "dateTime",
    "time",
    "gYear",
    "base64Binary",
}

_BASE_TO_RESTRICTION = {
    "xs:string": "TEXT",
    "xs:decimal": "DECIMAL",
    "xs:date": "DATE",
    "xs:dateTime": "DATE_TIME",
    "xs:time": "TIME",
    "xs:gYear": "YEAR",
    "xs:base64Binary": "BINARY",
    "xs:boolean": "BOOLEAN",
}

#: Published ISO 20022 name-part abbreviations, expanded for display only. Deliberately
#: the common core rather than an attempt at completeness: an unexpanded token renders
#: as itself, which is honest and still readable.
_ABBREVIATIONS = {
    "Acct": "Account", "Adr": "Address", "Agt": "Agent", "Amt": "Amount",
    "Attrbts": "Attributes", "Bal": "Balance", "Cd": "Code", "Ccy": "Currency",
    "Chrgs": "Charges", "Clr": "Clearing", "Cdtr": "Creditor", "Conf": "Confirmation",
    "Ctct": "Contact", "Ctry": "Country", "Dbtr": "Debtor", "Dt": "Date",
    "Dtl": "Detail", "Dtls": "Details", "Desc": "Description", "Fin": "Financial",
    "Frgn": "Foreign", "Grp": "Group", "Hdr": "Header", "Id": "Identification",
    "Indctn": "Indication", "Instr": "Instruction", "Instrm": "Instrument",
    "Intrmy": "Intermediary", "Mkt": "Market", "Mvmnt": "Movement", "Nb": "Number",
    "Nm": "Name", "Ntfctn": "Notification", "Orgnl": "Original", "Othr": "Other",
    "Pmt": "Payment", "Prc": "Price", "Prcg": "Processing", "Prtry": "Proprietary",
    "Qty": "Quantity", "Rcvg": "Receiving", "Ref": "Reference", "Rltd": "Related",
    "Rsn": "Reason", "Scties": "Securities", "Sctiy": "Security", "Sfkpg": "Safekeeping",
    "Sts": "Status", "Sttlm": "Settlement", "Svcr": "Servicer", "Tp": "Type",
    "Tx": "Transaction", "Txs": "Transactions", "Vldtn": "Validation", "Val": "Value",
    "Vn": "Venue", "Xchg": "Exchange",
}

_CAMEL_SPLIT = re.compile(r"[A-Z][a-z0-9]*|[A-Z]+(?![a-z])|[a-z0-9]+")


def display_name(element_name: str) -> str:
    """Mechanical, deterministic label: camelCase split + abbreviation expansion."""
    tokens = _CAMEL_SPLIT.findall(element_name)
    expanded = [_ABBREVIATIONS.get(token, token) for token in tokens]
    label = " ".join(expanded)
    # The model requires two characters; a one-letter element keeps its name visible.
    return label if len(label) >= 2 else f"Element {element_name}"


@dataclass
class MappingContext:
    ir: SchemaIR
    log: FindingLog
    limitations: list[str] = field(default_factory=list)

    def limitation(self, text: str) -> None:
        if text not in self.limitations:
            self.limitations.append(text)


def _example_value(facets: Facets, context: MappingContext, path: str) -> str | None:
    if facets.enumerations:
        return facets.enumerations[0]
    if facets.base == "xs:date":
        return "2026-01-01"
    if facets.base == "xs:dateTime":
        return "2026-01-01T00:00:00Z"
    if facets.base == "xs:time":
        return "00:00:00Z"
    if facets.base == "xs:gYear":
        return "2026"
    if facets.base == "xs:base64Binary":
        return "U1lOVEhFVElD"
    if facets.base == "xs:boolean":
        return "true"
    if facets.base == "xs:decimal":
        if facets.min_inclusive is not None and not facets.min_inclusive.startswith("-"):
            return facets.min_inclusive
        return "1"
    # Text: a pattern knows best; otherwise the length facets do.
    if facets.pattern is not None:
        sample = sample_from_pattern(facets.pattern)
        if sample is None:
            context.log.warning(
                FindingCode.SAMPLE_VALUE_UNDERIVABLE,
                f"No deterministic sample could be derived for the pattern at {path}.",
                "Author an example for this element before relying on generated samples.",
                location=path,
            )
        return sample
    size = facets.length or facets.min_length or 1
    if facets.max_length is not None:
        size = min(size, facets.max_length)
    return "A" * max(size, 1)


def _restriction_payload(name: str | None, facets: Facets) -> dict[str, Any]:
    payload: dict[str, Any] = {"base": _BASE_TO_RESTRICTION[facets.base]}
    if name:
        payload["typeName"] = name
    for key, value in (
        ("pattern", facets.pattern),
        ("minLength", facets.min_length),
        ("maxLength", facets.max_length),
        ("length", facets.length),
        ("totalDigits", facets.total_digits),
        ("fractionDigits", facets.fraction_digits),
        ("minInclusive", facets.min_inclusive),
        ("maxInclusive", facets.max_inclusive),
    ):
        if value is not None:
            payload[key] = value
    return payload


def _leaf_payload(
    simple: SimpleTypeIR, context: MappingContext, path: str
) -> dict[str, Any]:
    facets = simple.facets
    if facets.enumerations:
        return {"dataType": "Code", "codes": list(facets.enumerations)}
    if simple.name in _KNOWN_DATA_TYPES:
        return {"dataType": simple.name}
    return {"restriction": _restriction_payload(simple.name, facets)}


def _amount_shape(complex_: ComplexTypeIR) -> bool:
    """The one attribute-bearing shape the runtime writes: decimal + required Ccy."""
    if complex_.simple_content is None:
        return False
    if complex_.simple_content.facets.base != "xs:decimal":
        return False
    required = [item for item in complex_.attributes if item.required]
    return len(required) == 1 and required[0].name == "Ccy"


def _resolve(element: ElementIR, context: MappingContext, path: str) -> ElementIR:
    """Resolve a type or element reference into a concrete element."""
    if element.type_ref is None:
        return element
    ref = element.type_ref
    if ref.startswith("element:"):
        target = context.ir.global_elements.get(ref.removeprefix("element:"))
        if target is None:
            context.log.error(
                FindingCode.XSD_TYPE_UNRESOLVED,
                f"Element reference {ref} at {path} names no global element.",
                "Declare the referenced element in the bundle.",
                location=path,
            )
            return element
        return ElementIR(
            name=element.name,
            min_occurs=element.min_occurs,
            max_occurs=element.max_occurs,
            simple_type=target.simple_type,
            complex_type=target.complex_type,
            type_ref=target.type_ref,
        )
    if ref in _BUILTIN_BASES:
        return ElementIR(
            name=element.name,
            min_occurs=element.min_occurs,
            max_occurs=element.max_occurs,
            simple_type=SimpleTypeIR(name=None, facets=Facets(base=f"xs:{ref}")),
        )
    if ref in context.ir.complex_types:
        return ElementIR(
            name=element.name,
            min_occurs=element.min_occurs,
            max_occurs=element.max_occurs,
            complex_type=context.ir.complex_types[ref],
        )
    if ref in context.ir.simple_types:
        return ElementIR(
            name=element.name,
            min_occurs=element.min_occurs,
            max_occurs=element.max_occurs,
            simple_type=context.ir.simple_types[ref],
        )
    context.log.error(
        FindingCode.XSD_TYPE_UNRESOLVED,
        f"Type {ref} at {path} is not declared in the bundle.",
        "Add the schema that declares the type, or correct the reference.",
        location=path,
    )
    return element


def _occurs_payload(
    element: ElementIR, context: MappingContext, path: str
) -> dict[str, Any] | None:
    if element.min_occurs > 1:
        context.log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path} requires minOccurs={element.min_occurs}; the specification model "
            "expresses presence as mandatory or optional only.",
            "Restate the element, or exclude the message.",
            location=path,
        )
        return None
    payload: dict[str, Any] = {}
    if element.min_occurs == 1:
        payload["presence"] = "MANDATORY"
    max_occurs = element.max_occurs
    if max_occurs is None or max_occurs > OCCURS_CEILING:
        stated = "unbounded" if max_occurs is None else str(max_occurs)
        context.log.warning(
            FindingCode.XSD_OCCURRENCE_CAPPED,
            f"{path} allows {stated} occurrences; the authoring model caps it at "
            f"{OCCURS_CEILING}.",
            "The cap is recorded in the pack's limitations.",
            location=path,
        )
        context.limitation(
            f"The source schema allows {stated} occurrences of {path}; this authoring "
            f"subset caps repetition at {OCCURS_CEILING}."
        )
        max_occurs = OCCURS_CEILING
    if max_occurs > 1:
        payload["maxOccurs"] = max_occurs
    return payload


def _map_element(
    element: ElementIR, context: MappingContext, path: str, depth: int
) -> dict[str, Any] | None:
    if depth > _RECURSION_LIMIT:
        context.log.error(
            FindingCode.XSD_RECURSION_LIMIT,
            f"The element tree at {path} exceeds depth {_RECURSION_LIMIT}.",
            "Check the schema for a recursive type.",
            location=path,
        )
        return None
    element = _resolve(element, context, path)
    occurs = _occurs_payload(element, context, path)
    if occurs is None:
        return None
    payload: dict[str, Any] = {
        "name": element.name,
        "displayName": display_name(element.name),
        **occurs,
    }

    if element.simple_type is not None:
        payload.update(_leaf_payload(element.simple_type, context, path))
        example = _example_value(element.simple_type.facets, context, path)
        if example is not None:
            payload["examples"] = [
                {"value": example, "explanation": "Synthetic value derived from the schema type."}
            ]
        return payload

    complex_ = element.complex_type
    if complex_ is None:
        context.log.error(
            FindingCode.XSD_TYPE_UNRESOLVED,
            f"{path} has no resolvable type.",
            "Declare the type in the bundle.",
            location=path,
        )
        return None

    if _amount_shape(complex_):
        payload["dataType"] = "ActiveCurrencyAndAmount"
        # The composer writes the currency as the Ccy attribute when this flag is set —
        # the same convention the hand-authored specs use.
        payload["currencyAttribute"] = True
        original = complex_.name
        if original and original != "ActiveCurrencyAndAmount":
            payload["technicalMeaning"] = (
                f"Currency-and-amount element; source schema type {original}."
            )
        payload["examples"] = [
            {"value": "USD 1000.00", "explanation": "Synthetic amount with its currency."}
        ]
        return payload

    if complex_.simple_content is not None:
        context.log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path} extends a simple type with attributes other than the amount shape.",
            "Only the decimal-plus-required-Ccy shape is generatable.",
            location=path,
        )
        return None

    required_attributes = [item for item in complex_.attributes if item.required]
    if required_attributes:
        context.log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path} requires attribute(s) "
            f"{', '.join(item.name for item in required_attributes)}, which the "
            "composer cannot write.",
            "Only the amount shape's Ccy attribute is supported.",
            location=path,
        )
        return None
    if complex_.attributes:
        names = ", ".join(item.name for item in complex_.attributes)
        context.log.warning(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path} allows optional attribute(s) {names}; the configured subset never "
            "writes them.",
            "Recorded in the pack's limitations.",
            location=path,
        )
        context.limitation(
            f"Optional attribute(s) {names} of {path} are outside the configured subset."
        )

    if complex_.model == "choice":
        payload["choice"] = True
    children: list[dict[str, Any]] = []
    for child in complex_.children:
        mapped = _map_element(child, context, f"{path}/{child.name}", depth + 1)
        if mapped is not None:
            if complex_.model == "choice":
                # A branch of a choice is never individually mandatory: the choice itself
                # carries "exactly one", which is how the hand-authored specs and the
                # structural validator model it.
                mapped.pop("presence", None)
            children.append(mapped)
    if not children:
        if complex_.open_content:
            context.limitation(
                f"Open XML content under {path} is outside the configured subset and is "
                "not written by the generic composer."
            )
            return None
        if element.min_occurs == 0:
            context.limitation(
                f"{path} was omitted because none of its optional or open-content "
                "children are representable in the configured subset."
            )
            return None
        context.log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path} has no representable children.",
            "Every container needs at least one supported child.",
            location=path,
        )
        return None
    payload["children"] = children
    return payload


_AREA_BY_FAMILY = {
    "pacs": "PAYMENTS_CLEARING_SETTLEMENT",
    "pain": "PAYMENT_INITIATION",
    "camt": "CASH_MANAGEMENT",
    "sese": "SECURITIES_SETTLEMENT",
    "semt": "SECURITIES_MANAGEMENT",
    "seev": "SECURITIES_EVENTS",
}


def map_message(
    ir: SchemaIR,
    *,
    source_type: str,
    source_reference: str,
    source_location: str,
    source_checksum: str,
    root_name: str | None = None,
) -> tuple[dict[str, Any], FindingLog]:
    """Map a read schema into an MxMessageSpec-shaped dict plus the findings."""
    log = FindingLog()
    context = MappingContext(ir=ir, log=log)

    namespace = ir.target_namespace
    if not namespace.startswith(NAMESPACE_PREFIX):
        log.error(
            FindingCode.XSD_NAMESPACE_UNSUPPORTED,
            f"targetNamespace {namespace or '(none)'} is not an ISO 20022 message "
            "namespace.",
            f"Expected a namespace starting {NAMESPACE_PREFIX}.",
        )
        return {}, log
    version = namespace.removeprefix(NAMESPACE_PREFIX)
    message_type = ".".join(version.split(".")[:2])

    document = None
    if root_name is not None:
        document = ir.global_elements.get(root_name)
        if document is None:
            log.error(
                FindingCode.XSD_ROOT_NOT_FOUND,
                f"No global element named {root_name}.",
                f"Available: {', '.join(sorted(ir.global_elements)) or 'none'}.",
            )
            return {}, log
    elif len(ir.global_elements) == 1:
        document = next(iter(ir.global_elements.values()))
    else:
        log.error(
            FindingCode.XSD_ROOT_AMBIGUOUS,
            f"The schema declares {len(ir.global_elements)} global elements: "
            f"{', '.join(sorted(ir.global_elements)) or 'none'}.",
            "Name the document element with --root.",
        )
        return {}, log

    document = _resolve(document, context, document.name)
    if document.complex_type is None or len(document.complex_type.children) != 1:
        log.error(
            FindingCode.XSD_ROOT_AMBIGUOUS,
            f"{document.name} does not contain exactly one message root element.",
            "ISO 20022 documents wrap one message root; check the schema.",
        )
        return {}, log
    root_ir = _resolve(
        document.complex_type.children[0], context, document.complex_type.children[0].name
    )
    if root_ir.complex_type is None:
        log.error(
            FindingCode.XSD_ROOT_AMBIGUOUS,
            f"The message root {root_ir.name} is not a structured element.",
            "Check the schema.",
        )
        return {}, log

    structure: list[dict[str, Any]] = []
    for child in root_ir.complex_type.children:
        mapped = _map_element(child, context, f"{root_ir.name}/{child.name}", 1)
        if mapped is not None:
            structure.append(mapped)

    if not structure:
        log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            "No representable elements were found under the message root.",
            "The schema may rely entirely on unsupported constructs.",
        )
        return {}, log

    family = message_type.split(".")[0]
    spec: dict[str, Any] = {
        "messageType": message_type,
        "version": version,
        "name": display_name(root_ir.name),
        "shortDescription": (
            f"Compiled from {source_location}; structure follows the source schema."
        ),
        "businessArea": _AREA_BY_FAMILY.get(family, "OTHER"),
        "namespace": namespace,
        "messageRoot": root_ir.name,
        "documentElement": document.name,
        "standardsRelease": f"SOURCE_SCHEMA_{version}",
        "authoritativeCompletenessKnown": False,
        "source": {
            "sourceType": source_type,
            "sourceReference": source_reference,
            "reviewedAt": "NOT_REVIEWED",
            "reviewedBy": "SPECIFICATION_COMPILER",
            "generated": True,
            "sourceLocation": source_location,
            "sourceVersion": version,
            "sourceChecksum": source_checksum,
            "compilerVersion": COMPILER_VERSION,
            "reviewStatus": "NOT_REVIEWED",
        },
        "limitations": [
            "This specification was machine-compiled from a source schema. Structure "
            "follows that schema; business rules, market practice and client rules are "
            "not configured.",
            *context.limitations,
        ],
        "structure": structure,
    }
    return spec, log

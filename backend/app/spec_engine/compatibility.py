# ruff: noqa: E501
"""Render the XSD compiler compatibility matrix.

The matrix is intentionally conservative: it states what the compiler model supports,
where support has limitations, which diagnostics are emitted, and what has not been seen
in committed tests. It is not an ISO 20022 coverage percentage.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "generated"
    / "xsd-compiler-compatibility.md"
)


class Support(StrEnum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_LIMITATION = "SUPPORTED_WITH_LIMITATION"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_SEEN = "NOT_SEEN"


@dataclass(frozen=True)
class Construct:
    name: str
    status: Support
    tests: str
    real_schemas: str
    limitation: str
    diagnostic: str


CONSTRUCTS = [
    Construct("xs:schema targetNamespace", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("global Document element", Support.SUPPORTED, "test_compiler, test_gates_and_diff", "not seen in committed real schemas", "", "XSD_ROOT_AMBIGUOUS"),
    Construct("named complexType", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", "XSD_TYPE_UNRESOLVED"),
    Construct("anonymous complexType", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("named simpleType restriction", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", "XSD_TYPE_UNRESOLVED"),
    Construct("xs:sequence", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("xs:choice", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "Branches are optional; the choice container carries exclusivity.", ""),
    Construct("xs:include", Support.SUPPORTED, "test_xsd_loader_security", "not seen in committed real schemas", "Must resolve inside the bundle.", "XSD_IMPORT_NOT_FOUND"),
    Construct("xs:import", Support.SUPPORTED, "test_compiler, test_xsd_loader_security", "not seen in committed real schemas", "Must resolve inside the bundle or be satisfied by a loaded namespace.", "XSD_IMPORT_NOT_FOUND"),
    Construct("xs:enumeration", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("xs:pattern", Support.SUPPORTED_WITH_LIMITATION, "test_compiler", "not seen in committed real schemas", "Generation needs a deterministic sample; underivable patterns warn.", "SAMPLE_VALUE_UNDERIVABLE"),
    Construct("length/minLength/maxLength", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("totalDigits/fractionDigits", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("minInclusive/maxInclusive", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("xs:boolean/date/dateTime/decimal/string", Support.SUPPORTED, "test_compiler", "not seen in committed real schemas", "", ""),
    Construct("simpleContent decimal + required Ccy", Support.SUPPORTED, "test_compiler, test_gates_and_diff", "not seen in committed real schemas", "Only this amount attribute shape is rendered.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("unbounded maxOccurs", Support.SUPPORTED_WITH_LIMITATION, "test_compiler", "not seen in committed real schemas", "Authoring model caps generated repetition at 1000 and records a limitation.", "XSD_OCCURRENCE_CAPPED"),
    Construct("optional attributes", Support.SUPPORTED_WITH_LIMITATION, "test_compiler", "not seen in committed real schemas", "Optional attributes are not written and are recorded as a limitation.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("xs:any / open content", Support.SUPPORTED_WITH_LIMITATION, "test_compiler", "not seen in committed real schemas", "Open content is omitted and recorded as a limitation when optional.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("required non-Ccy attributes", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "The generic composer cannot write arbitrary attributes.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("minOccurs greater than 1", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "Presence is mandatory/optional; exact minimum counts are not expressible.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("xs:all", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "The XML composer writes ordered content.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("xs:group", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "No group expansion model exists yet.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("complexContent extension/restriction", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "Inheritance is not mapped into the current structure tree.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("simpleType union/list", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "No honest runtime validation model exists for these yet.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("mixed content", Support.UNSUPPORTED, "test_compiler", "not seen in committed real schemas", "Financial message structures are element-oriented; mixed text is refused.", "XSD_UNSUPPORTED_CONSTRUCT"),
    Construct("remote schemaLocation", Support.UNSUPPORTED, "test_xsd_loader_security", "not applicable", "Compilation never fetches dependencies from schemas.", "XSD_REMOTE_FETCH_BLOCKED"),
    Construct("DOCTYPE/entity declarations", Support.UNSUPPORTED, "test_xsd_loader_security", "not applicable", "Rejected before XML parsing for XXE/entity-expansion safety.", "XSD_DOCTYPE_FORBIDDEN"),
]


def render_markdown() -> str:
    lines = [
        "# XSD Compiler Compatibility",
        "",
        "Generated by `make xsd-compatibility` from the compiler compatibility table. "
        "This matrix is construct coverage, not ISO 20022 message coverage.",
        "",
        "| Construct | Status | Tests | Real schemas exercising it | Limitation | Diagnostic |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in CONSTRUCTS:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.status.value,
                    item.tests,
                    item.real_schemas,
                    item.limitation or "",
                    item.diagnostic or "",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Observation Status Vocabulary",
            "",
            "- `SYNTHETICALLY_TESTED` means covered by committed synthetic fixtures.",
            "- `REAL_ISO_SCHEMA_OBSERVED` means the construct was seen while parsing a real "
            "ISO XSD but has not passed every gate.",
            "- `REAL_ISO_SCHEMA_PASSED` means at least one exact ISO XSD using the construct "
            "passed source load, compile, registry, sample, source-XSD and round-trip gates.",
            "- `REAL_ISO_SCHEMA_FAILED` means an exact ISO XSD using the construct exposed a "
            "compiler or runtime gap.",
            "",
            "Real ISO 20022 schemas are not committed to this repository. When an operator "
            "runs `make mx-scaleout` against legitimate source bundles, the batch report "
            "records which messages exercised which constructs and which diagnostics "
            "blocked any candidate.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or verify the XSD compatibility matrix")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = render_markdown()
    if args.check:
        if not DOCUMENT.exists() or DOCUMENT.read_text(encoding="utf-8") != expected:
            print("docs/generated/xsd-compiler-compatibility.md is stale")
            return 1
        print("docs/generated/xsd-compiler-compatibility.md is current")
        return 0
    if args.write:
        DOCUMENT.write_text(expected, encoding="utf-8")
        print(f"wrote {DOCUMENT}")
        return 0
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

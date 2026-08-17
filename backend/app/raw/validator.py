import re
from dataclasses import dataclass

from app.domain.enums import MessageType, Severity, ValidationStatus
from app.domain.models import (
    RawParsedField,
    RawValidationResponse,
    ValidationFinding,
    ValidationReport,
)
from app.profiles.loader import ClientProfile
from app.services.generation import DISCLAIMER

HEADER_PATTERN = re.compile(r"^\{2:(MT(?:530|537|54[0-8]|56[4-8]))\}$")
FIELD_PATTERN = re.compile(
    r"^:(?P<tag>\d{2}[A-Z]):(?::(?P<qualifier>[A-Z0-9]{4})//)?(?P<value>.+)$"
)
SEQUENCE_PATTERN = re.compile(r"^:16(?P<boundary>[RS]):(?P<name>[A-Z0-9]+)$")

SEQUENCE_ORDER: dict[MessageType, tuple[str, ...]] = {
    MessageType.MT530: ("GENL", "REQD"),
    MessageType.MT537: (
        "GENL",
        "PENA",
        "PENACUR",
        "PENACOUNT",
        "PENDET",
        "RELTRAN",
    ),
    MessageType.MT540: ("GENL", "TRADDET", "FIAC", "SETDET"),
    MessageType.MT541: ("GENL", "TRADDET", "FIAC", "SETDET"),
    MessageType.MT542: ("GENL", "TRADDET", "FIAC", "SETDET"),
    MessageType.MT543: ("GENL", "TRADDET", "FIAC", "SETDET"),
    MessageType.MT544: ("GENL", "CONFDET", "FIAC", "SETDET"),
    MessageType.MT545: ("GENL", "CONFDET", "FIAC", "SETDET"),
    MessageType.MT546: ("GENL", "CONFDET", "FIAC", "SETDET"),
    MessageType.MT547: ("GENL", "CONFDET", "FIAC", "SETDET"),
    MessageType.MT548: ("GENL", "LINK", "STAT"),
    MessageType.MT564: ("GENL", "USECU", "ACCTINFO", "CADETL", "CAOPTN"),
    MessageType.MT565: ("GENL", "LINK", "USECU", "ACCTINFO", "CAINST"),
    MessageType.MT566: ("GENL", "LINK", "USECU", "CACONF", "CASHMOVE"),
    MessageType.MT567: ("GENL", "LINK", "STAT"),
    MessageType.MT568: ("GENL", "LINK", "ADDINFO"),
}

ALLOWED_FIELDS: dict[str, set[tuple[str, str | None]]] = {
    "GENL": {
        ("28E", None),
        ("20C", "SEME"),
        ("20C", "RELA"),
        ("20C", "PREV"),
        ("20C", "COMM"),
        ("23G", None),
        ("98A", "STAT"),
        ("22H", "STST"),
        ("97A", "SAFE"),
        ("17B", "ACTI"),
        ("20C", "CORP"),
        ("22F", "CAEV"),
        ("22F", "CAMV"),
        ("25D", "PROC"),
    },
    "REQD": {("20C", "PREV"), ("22F", "PRIR")},
    "PENA": {("22F", "CODE")},
    "PENACUR": {
        ("11A", "PECU"),
        ("98A", "DACO"),
        ("95R", "ASDP"),
        ("22F", "TRCA"),
    },
    "PENACOUNT": {
        ("95R", "REPA"),
        ("22F", "TRCA"),
        ("19A", "AGNT"),
    },
    "PENDET": {
        ("20C", "PREF"),
        ("20C", "PCOM"),
        ("20C", "PPRF"),
        ("22H", "PNTP"),
        ("25D", "PNST"),
        ("19A", "AMCO"),
        ("99A", "DAAC"),
    },
    "RELTRAN": {("20C", "RELA")},
    "TRADDET": {
        ("98A", "TRAD"),
        ("98A", "SETT"),
        ("35B", None),
        ("36B", "SETT"),
    },
    "CONFDET": {
        ("98A", "ESET"),
        ("35B", None),
        ("36B", "ESTT"),
        ("19A", "ESTT"),
        ("22F", "STCO"),
    },
    "FIAC": {("97A", "SAFE")},
    "SETDET": {
        ("22F", "SETR"),
        ("95P", "PSET"),
        ("95R", "PSET"),
        ("95P", "DEAG"),
        ("95R", "DEAG"),
        ("95P", "REAG"),
        ("95R", "REAG"),
        ("19A", "SETT"),
    },
    "LINK": {("13A", "LINK"), ("20C", "RELA")},
    "STAT": {
        ("25D", "SETT"),
        ("24B", "PEND"),
        ("24B", "REJT"),
        ("24B", "MACH"),
        ("24B", "NMAT"),
        ("24B", "CAND"),
        ("24B", "CANR"),
        ("70D", "REAS"),
        ("25D", "IPRC"),
        ("25D", "CPRC"),
    },
    "USECU": {
        ("35B", None),
        ("97A", "SAFE"),
        ("93B", "ELIG"),
    },
    "ACCTINFO": {("97A", "SAFE")},
    "CADETL": {("98A", "PAYD")},
    "CAOPTN": {
        ("13A", "CAON"),
        ("22F", "CAOP"),
        ("17B", "DFLT"),
        ("98A", "RDDT"),
    },
    "CAINST": {("13A", "CAON"), ("22F", "CAOP"), ("36B", "QINS")},
    "CACONF": {("13A", "CAON"), ("22H", "CAOP")},
    "CASHMOVE": {("22H", "CRDB"), ("19B", "PSTA"), ("98A", "POST")},
    "REAS": {("24B", "IPRC"), ("24B", "CPRC")},
    "ADDINFO": {("70E", "ADTX")},
}

FIELD_RANK: dict[str, dict[tuple[str, str | None], int]] = {
    "GENL": {
        ("28E", None): 0,
        ("20C", "SEME"): 1,
        ("20C", "RELA"): 2,
        ("20C", "PREV"): 2,
        ("20C", "COMM"): 3,
        ("23G", None): 4,
        ("98A", "STAT"): 5,
        ("22H", "STST"): 6,
        ("97A", "SAFE"): 7,
        ("17B", "ACTI"): 8,
        ("20C", "CORP"): 1,
        ("22F", "CAEV"): 5,
        ("22F", "CAMV"): 6,
        ("25D", "PROC"): 7,
    },
    "REQD": {("20C", "PREV"): 0, ("22F", "PRIR"): 1},
    "PENA": {("22F", "CODE"): 0},
    "PENACUR": {
        ("11A", "PECU"): 0,
        ("98A", "DACO"): 1,
        ("95R", "ASDP"): 2,
        ("22F", "TRCA"): 3,
    },
    "PENACOUNT": {
        ("95R", "REPA"): 0,
        ("22F", "TRCA"): 1,
        ("19A", "AGNT"): 2,
    },
    "PENDET": {
        ("20C", "PREF"): 0,
        ("20C", "PCOM"): 1,
        ("20C", "PPRF"): 2,
        ("22H", "PNTP"): 3,
        ("25D", "PNST"): 4,
        ("19A", "AMCO"): 5,
        ("99A", "DAAC"): 6,
    },
    "RELTRAN": {("20C", "RELA"): 0},
    "TRADDET": {
        ("98A", "TRAD"): 0,
        ("98A", "SETT"): 1,
        ("35B", None): 2,
        ("36B", "SETT"): 3,
    },
    "CONFDET": {
        ("98A", "ESET"): 0,
        ("35B", None): 1,
        ("36B", "ESTT"): 2,
        ("19A", "ESTT"): 3,
        ("22F", "STCO"): 4,
    },
    "FIAC": {("97A", "SAFE"): 0},
    "SETDET": {
        ("22F", "SETR"): 0,
        ("95P", "PSET"): 1,
        ("95R", "PSET"): 2,
        ("95P", "DEAG"): 3,
        ("95R", "DEAG"): 4,
        ("95P", "REAG"): 5,
        ("95R", "REAG"): 6,
        ("19A", "SETT"): 7,
    },
    "LINK": {("13A", "LINK"): 0, ("20C", "RELA"): 1},
    "STAT": {
        ("25D", "SETT"): 0,
        ("24B", "PEND"): 1,
        ("24B", "REJT"): 1,
        ("24B", "MACH"): 1,
        ("24B", "NMAT"): 1,
        ("24B", "CAND"): 1,
        ("24B", "CANR"): 1,
        ("70D", "REAS"): 2,
        ("25D", "IPRC"): 0,
        ("25D", "CPRC"): 0,
    },
    "USECU": {("97A", "SAFE"): 0, ("35B", None): 1, ("93B", "ELIG"): 2},
    "ACCTINFO": {("97A", "SAFE"): 0},
    "CADETL": {("98A", "PAYD"): 0},
    "CAOPTN": {
        ("13A", "CAON"): 0,
        ("22F", "CAOP"): 1,
        ("17B", "DFLT"): 2,
        ("98A", "RDDT"): 3,
    },
    "CAINST": {("13A", "CAON"): 0, ("22F", "CAOP"): 1, ("36B", "QINS"): 2},
    "CACONF": {("13A", "CAON"): 0, ("22H", "CAOP"): 1},
    "CASHMOVE": {("22H", "CRDB"): 0, ("19B", "PSTA"): 1, ("98A", "POST"): 2},
    "REAS": {("24B", "IPRC"): 0, ("24B", "CPRC"): 0},
    "ADDINFO": {("70E", "ADTX"): 0},
}


@dataclass(frozen=True)
class _FindingFactory:
    findings: list[ValidationFinding]

    def add(
        self,
        rule_id: str,
        message: str,
        technical: str,
        *,
        field_path: str | None = None,
        current: object = None,
        expected: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.findings.append(
            ValidationFinding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                field_path=field_path,
                message=message,
                technical_explanation=technical,
                current_value=current,
                expected_condition=expected,
                suggestion=suggestion,
            )
        )


def validate_raw_message(raw_message: str, profile: ClientProfile) -> RawValidationResponse:
    """Validate only the deterministic demonstration syntax emitted by this application.

    Raw content is never executed or sent to an AI provider. The parser deliberately
    supports a narrow field and sequence allowlist rather than claiming universal parsing.
    """

    normalized = raw_message.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    findings: list[ValidationFinding] = []
    finding = _FindingFactory(findings)
    parsed_fields: list[RawParsedField] = []
    message_type: MessageType | None = None

    if "\x00" in raw_message:
        finding.add(
            "RAW-CONTROL-CHARACTER",
            "The raw message contains a null control character.",
            "Null bytes are rejected before supported-subset parsing.",
            suggestion="Remove the null character and revalidate.",
        )

    if len(lines) < 5 or lines[0] != "{1:DEMONSTRATION}":
        finding.add(
            "RAW-BLOCK-1",
            "The demonstration basic header is missing or misplaced.",
            "The supported subset requires {1:DEMONSTRATION} as the first line.",
            expected="{1:DEMONSTRATION}",
        )

    header_match = HEADER_PATTERN.fullmatch(lines[1]) if len(lines) > 1 else None
    if not header_match:
        finding.add(
            "RAW-BLOCK-2",
            "A supported Category 5 demonstration application header is required.",
            "The second line must identify exactly one supported Category 5 message type.",
            current=lines[1] if len(lines) > 1 else None,
            expected="An enabled MT530, MT537, MT540–MT548, or MT564–MT568 header",
        )
    else:
        message_type = MessageType(header_match.group(1))
        if message_type not in profile.supported_message_types:
            finding.add(
                "RAW-PROFILE-MESSAGE-NOT-SUPPORTED",
                f"{message_type.value} is not enabled by this profile.",
                "Raw validation applies the profile supported-message allowlist.",
                current=message_type.value,
                expected="A message type enabled by the selected profile",
            )

    if len(lines) < 3 or lines[2] != "{4:":
        finding.add(
            "RAW-BLOCK-4-OPEN",
            "The application text block opening is missing or misplaced.",
            "The supported subset requires {4: as the third line.",
            expected="{4:",
        )
    if not lines or lines[-1] != "-}":
        finding.add(
            "RAW-BLOCK-4-CLOSE",
            "The application text block is not closed correctly.",
            "The supported subset requires -} as the final line.",
            expected="-}",
        )

    sequence_stack: list[str] = []
    occurrence_stack: list[int] = []
    sequence_occurrences: dict[str, int] = {}
    observed_sequences: list[str] = []
    last_field_rank: dict[tuple[str, int], int] = {}
    seen_fields: set[tuple[str, int, str, str | None]] = set()
    body = lines[3:-1] if len(lines) >= 4 else []
    for line_number, line in enumerate(body, start=4):
        boundary = SEQUENCE_PATTERN.fullmatch(line)
        if boundary:
            name = boundary.group("name")
            if boundary.group("boundary") == "R":
                nested_types = {
                    MessageType.MT537,
                    MessageType.MT564,
                    MessageType.MT565,
                    MessageType.MT566,
                    MessageType.MT567,
                    MessageType.MT568,
                }
                if sequence_stack and message_type not in nested_types:
                    finding.add(
                        "RAW-SEQUENCE-NESTING",
                        "Nested sequences are outside the supported subset.",
                        "Generated messages use non-nested sequence boundaries.",
                        current=line,
                    )
                sequence_stack.append(name)
                sequence_occurrences[name] = sequence_occurrences.get(name, 0) + 1
                occurrence_stack.append(sequence_occurrences[name])
                observed_sequences.append(name)
            elif not sequence_stack or sequence_stack[-1] != name:
                finding.add(
                    "RAW-SEQUENCE-BOUNDARY",
                    f"Sequence {name} does not close the current sequence.",
                    "Each 16S boundary must match the immediately open 16R boundary.",
                    current=line,
                )
                sequence_stack.clear()
                occurrence_stack.clear()
            else:
                sequence_stack.pop()
                occurrence_stack.pop()
            continue

        field = FIELD_PATTERN.fullmatch(line)
        if not field:
            finding.add(
                "RAW-FIELD-FORMAT",
                f"Line {line_number} is not a supported field.",
                "Fields must use the generated tag and qualifier syntax.",
                current=line,
                suggestion="Use Business View or Tag View to correct the field.",
            )
            continue
        sequence = sequence_stack[-1] if sequence_stack else ""
        occurrence = occurrence_stack[-1] if occurrence_stack else 0
        tag = field.group("tag")
        qualifier = field.group("qualifier")
        value = field.group("value")
        parsed_fields.append(
            RawParsedField(
                sequence=sequence,
                tag=tag,
                qualifier=qualifier,
                value=value,
                line_number=line_number,
            )
        )
        if not sequence:
            finding.add(
                "RAW-FIELD-OUTSIDE-SEQUENCE",
                f"Field {tag} appears outside a supported sequence.",
                "Every data field emitted by the prototype belongs to an open sequence.",
                current=line,
            )
        elif (tag, qualifier) not in ALLOWED_FIELDS.get(sequence, set()):
            qualified_tag = f"{tag}::{qualifier}" if qualifier else tag
            finding.add(
                "RAW-FIELD-NOT-SUPPORTED",
                f"Field {qualified_tag} is not supported in {sequence}.",
                "The raw parser uses an explicit field and qualifier allowlist.",
                current=line,
            )
        else:
            field_key = (sequence, occurrence, tag, qualifier)
            if field_key in seen_fields:
                finding.add(
                    "RAW-FIELD-REPETITION",
                    f"Field {tag} is repeated in sequence {sequence}.",
                    (
                        "The deterministic subset emits each supported tag/qualifier "
                        "once per sequence."
                    ),
                    current=line,
                )
            seen_fields.add(field_key)
            rank = FIELD_RANK[sequence][(tag, qualifier)]
            occurrence_key = (sequence, occurrence)
            if rank < last_field_rank.get(occurrence_key, -1):
                finding.add(
                    "RAW-FIELD-ORDER",
                    f"Field {tag} is out of order in sequence {sequence}.",
                    "The deterministic subset defines a fixed order for generated fields.",
                    current=line,
                )
            last_field_rank[occurrence_key] = max(rank, last_field_rank.get(occurrence_key, -1))

    if sequence_stack:
        finding.add(
            "RAW-SEQUENCE-UNCLOSED",
            f"Sequence {sequence_stack[-1]} is not closed.",
            "Every 16R sequence must have a corresponding 16S boundary.",
            current=sequence_stack[-1],
        )

    if message_type:
        expected_sequences = SEQUENCE_ORDER[message_type]
        sequence_order_valid = tuple(observed_sequences) == expected_sequences
        if message_type == MessageType.MT537:
            sequence_order_valid = tuple(observed_sequences) in {
                expected_sequences,
                tuple(item for item in expected_sequences if item != "RELTRAN"),
            }
        if message_type == MessageType.MT564:
            sequence_order_valid = (
                observed_sequences[:4] == ["GENL", "USECU", "ACCTINFO", "CADETL"]
                and len(observed_sequences) >= 6
                and all(name == "CAOPTN" for name in observed_sequences[4:])
            )
        if message_type == MessageType.MT567:
            sequence_order_valid = tuple(observed_sequences) in {
                expected_sequences,
                (*expected_sequences, "REAS"),
            }
        if not sequence_order_valid:
            finding.add(
                "RAW-SEQUENCE-ORDER",
                "The message sequences are missing, repeated, or out of order.",
                "The deterministic engine emits a fixed supported sequence order per message type.",
                current=observed_sequences,
                expected=" -> ".join(expected_sequences),
            )

    report = ValidationReport(
        status=ValidationStatus.INVALID if findings else ValidationStatus.VALID,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        findings=findings,
        error_count=len(findings),
        warning_count=0,
    )
    return RawValidationResponse(
        message_type=message_type,
        supported_subset=not findings,
        parsed_fields=parsed_fields,
        validation=report,
        disclaimer=DISCLAIMER,
    )

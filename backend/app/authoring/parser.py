from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.authoring.composer import canonical_field_value
from app.domain.enums import MessageType
from app.specifications.models import FieldSpecification, MessageSpecification

DEMO_TYPE = re.compile(r"\{2:(MT(?:530|537|54[0-8]|56[4-8]))\}")
FIN_TYPE = re.compile(r"\{2:I(530|537|54[0-8]|56[4-8])[A-Z0-9]*[NU]\}")
FIELD = re.compile(
    r"^:(?P<tag>\d{2}[A-Z]):(?::(?P<qualifier>[A-Z0-9]{4})(?://|/))?(?P<value>.*)$"
)
BOUNDARY = re.compile(r"^:16(?P<boundary>[RS]):(?P<code>[A-Z0-9]+)$")


@dataclass(frozen=True)
class ParsedField:
    line_number: int
    sequence_path: str
    sequence_occurrence: int
    row: FieldSpecification
    value: str


@dataclass(frozen=True)
class UnsupportedField:
    line_number: int
    raw_line: str
    reason: str


@dataclass(frozen=True)
class ParsedMessage:
    message_type: MessageType
    block_4: str
    fields: list[ParsedField]
    unsupported: list[UnsupportedField]
    checksum: str


def parse_supported_message(
    raw_message: str,
    specification_lookup: Callable[[MessageType], MessageSpecification],
) -> ParsedMessage:
    normalized = raw_message.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in normalized:
        raise ValueError("Null control characters are not accepted")
    demo_match = DEMO_TYPE.search(normalized)
    fin_match = FIN_TYPE.search(normalized)
    if demo_match:
        message_type = MessageType(demo_match.group(1))
    elif fin_match:
        message_type = MessageType(f"MT{fin_match.group(1)}")
    else:
        raise ValueError("A supported MT530/537/540–548/564–568 Block 2 is required")
    start = normalized.find("{4:")
    end = normalized.rfind("-}")
    if start < 0 or end <= start:
        raise ValueError("A complete FIN text block is required")
    block_4 = normalized[start : end + 2]
    specification: MessageSpecification = specification_lookup(message_type)
    sequence_by_code = {item.code: item for item in specification.sequences}
    rows = specification.fields
    stack: list[tuple[str, int]] = []
    occurrence_counts: dict[str, int] = {}
    fields: list[ParsedField] = []
    unsupported: list[UnsupportedField] = []
    last_field: int | None = None
    for line_number, line in enumerate(block_4.splitlines()[1:-1], start=2):
        boundary = BOUNDARY.fullmatch(line)
        if boundary:
            code = boundary.group("code")
            sequence = sequence_by_code.get(code)
            if sequence is None:
                unsupported.append(UnsupportedField(line_number, line, "Unknown sequence"))
                continue
            if boundary.group("boundary") == "R":
                occurrence_counts[sequence.path] = occurrence_counts.get(sequence.path, 0) + 1
                stack.append((sequence.path, occurrence_counts[sequence.path]))
            else:
                if not stack or stack[-1][0] != sequence.path:
                    raise ValueError(f"Unbalanced sequence boundary at line {line_number}")
                stack.pop()
            last_field = None
            continue
        field_match = FIELD.fullmatch(line)
        if field_match:
            if not stack:
                unsupported.append(UnsupportedField(line_number, line, "Field outside a sequence"))
                continue
            sequence_path, sequence_occurrence = stack[-1]
            tag = field_match.group("tag")
            qualifier = field_match.group("qualifier")
            candidates = [
                item
                for item in rows
                if item.sequence_path == sequence_path
                and item.tag == tag
                and item.qualifier == qualifier
            ]
            if len(candidates) != 1:
                unsupported.append(
                    UnsupportedField(
                        line_number,
                        line,
                        "Field is not uniquely represented in the configured subset",
                    )
                )
                last_field = None
                continue
            fields.append(
                ParsedField(
                    line_number=line_number,
                    sequence_path=sequence_path,
                    sequence_occurrence=sequence_occurrence,
                    row=candidates[0],
                    # The composer writes a field's literal at render time, so reading one
                    # back takes it off again. Storing the rendered form would recompose as
                    # `ISIN ISIN XS0000000009`.
                    value=canonical_field_value(
                        candidates[0], field_match.group("value")
                    ),
                )
            )
            last_field = len(fields) - 1
            continue
        if last_field is not None and not line.startswith(":"):
            previous = fields[last_field]
            fields[last_field] = ParsedField(
                line_number=previous.line_number,
                sequence_path=previous.sequence_path,
                sequence_occurrence=previous.sequence_occurrence,
                row=previous.row,
                value=f"{previous.value}\n{line}",
            )
        elif line:
            unsupported.append(UnsupportedField(line_number, line, "Unsupported raw line"))
    if stack:
        raise ValueError("The text block contains unclosed sequences")
    return ParsedMessage(
        message_type=message_type,
        block_4=block_4,
        fields=fields,
        unsupported=unsupported,
        checksum=hashlib.sha256(block_4.encode()).hexdigest(),
    )

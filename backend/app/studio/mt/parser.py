"""Read an existing MT message back into canonical field values.

This is the exact inverse of :class:`app.authoring.composer.SpecificationComposer` and
:func:`app.studio.mt.fin.build_fin_message`, and — like the MX parser it is modelled on —
it is deliberately the *only* thing it does. Import produces ``FieldInput`` values, the
same type the JSON API and the Excel importer produce, and hands them to the ordinary
generation path. There is no import-only composer, validator or renderer, so an imported
message and a typed one cannot diverge.

The round-trip property the tests hold this to is::

    Compose(Parse(Compose(values))) == Compose(values)

Two things make MT harder than MX, and both are handled here rather than papered over:

*Sequences are not self-describing.* An MX document names its message in the namespace. A
FIN message names it in Block 2, but a pasted Block 4 does not name it at all, so the type
is resolved from Block 2 when it exists and otherwise narrowed deterministically from the
``:16R:`` skeleton and the tag addresses present. When more than one configured message
still fits, the import refuses and lists the candidates rather than picking one.

*Occurrence is a flat index.* The composer addresses a sequence instance as
``(sequence_path, occurrence)`` and gives child instance ``P#k`` the parent ``Q#k``, falling
back to ``Q#1``. A document whose nesting cannot be expressed that way is refused
(``MT_IMPORT_NESTED_REPEAT_UNSUPPORTED``) rather than silently reshaped — the same decision,
for the same reason, as the MX parser's nested-repeat case.

Nothing is silently discarded. A tag outside the configured subset, a sequence that never
closes, a value the canonical model will not carry, and a Block 5 trailer are each reported
as a named issue. An import that quietly loses half a message is worse than one that
refuses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.enums import MessageType
from app.specifications.models import FieldSpecification, MessageSpecification
from app.specifications.registry import specification_registry
from app.studio.models import (
    EnvelopeOverride,
    FieldInput,
    IssueSeverity,
    ValidationIssue,
    ValidationLayer,
)
from app.studio.mt.generator import plan_sequences

#: Maximum accepted input size. Parsing is linear, but an unbounded paste is still a way to
#: spend the server's memory, and no realistic securities message comes close to this.
MAX_IMPORT_BYTES = 1_000_000

_BLOCK_START = re.compile(r"\{(?P<id>[1-5]):")
_SEQUENCE_LINE = re.compile(r"^:16(?P<boundary>[RS]):(?P<code>[A-Z0-9]{1,16})$")
#: A field line is ``:<tag>:`` followed either by ``:<qualifier>//`` and a value, or by a
#: bare value. A value that itself begins with ``:XXXX//`` would be indistinguishable from a
#: qualifier — no configured field has one, and the composer could not have written it.
_FIELD_LINE = re.compile(
    r"^:(?P<tag>\d{2}[A-Z]?):(?::(?P<qualifier>[A-Z0-9]{4})//)?(?P<value>.*)$"
)
_BLOCK_1 = re.compile(
    r"^(?P<application>[A-Z])(?P<service>\d{2})(?P<sender>[A-Z0-9]{12})"
    r"(?P<session>\d{4})(?P<sequence>\d{6})$"
)
_BLOCK_2_INPUT = re.compile(
    r"^I(?P<type>\d{3})(?P<receiver>[A-Z0-9]{12})(?P<priority>[SNU])"
    r"(?P<delivery>\d)?(?P<obsolescence>\d{3})?$"
)
_BLOCK_2_OUTPUT = re.compile(r"^O(?P<type>\d{3})")
#: The envelope this repository's own sample exporter writes: `{1:DEMONSTRATION}{2:MT541}`.
#: It names the message but carries no interface values, and a tester pasting a golden file
#: or a downloaded sample will arrive with it, so it is read rather than called malformed.
_BLOCK_2_DEMONSTRATION = re.compile(r"^MT(?P<type>\d{3})$")
_BLOCK_1_DEMONSTRATION = "DEMONSTRATION"
_BLOCK_3_FIELD = re.compile(r"\{(?P<tag>\d{3}):(?P<value>[^}]*)\}")


class MtImportError(Exception):
    """The message could not be identified at all, so there is nothing to regenerate."""

    def __init__(self, issue: ValidationIssue) -> None:
        super().__init__(issue.message)
        self.issue = issue


@dataclass
class MtImportResult:
    specification: MessageSpecification
    fields: list[FieldInput]
    envelope: EnvelopeOverride
    #: The FIN blocks the text actually carried, in order — "4" alone for a pasted Block 4.
    blocks: list[str]
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


def _issue(
    rule_id: str,
    message: str,
    *,
    layer: ValidationLayer = ValidationLayer.CANONICAL,
    severity: IssueSeverity = IssueSeverity.ERROR,
    field_name: str | None = None,
    location: str | None = None,
    expected: str | None = None,
    current: str | None = None,
    suggestion: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=severity,
        layer=layer,
        field=field_name,
        location=location,
        message=message,
        expected=expected,
        current_value=current,
        suggestion=suggestion,
    )


# --------------------------------------------------------------------------------------
# Locating the blocks
# --------------------------------------------------------------------------------------


@dataclass
class _Blocks:
    #: Raw content of each block that was present, keyed by block number.
    content: dict[str, str]
    order: list[str]
    #: True when the text was a bare Block 4 body with no ``{4:`` wrapper at all.
    bare_text_block: bool


def _scan_blocks(text: str) -> _Blocks:
    """Split ``{1:}{2:}{3:}{4:...-}{5:}`` without assuming they are on separate lines.

    Blocks 3 and 5 nest braces, so they are read by balancing rather than by regex. Block 4
    is the exception in the standard: it is terminated by ``-}``, and its content is free
    text that may itself contain a closing brace.
    """
    content: dict[str, str] = {}
    order: list[str] = []
    position = 0
    while True:
        match = _BLOCK_START.search(text, position)
        if match is None:
            break
        block_id = match.group("id")
        body_start = match.end()
        if block_id == "4":
            end = text.find("-}", body_start)
            if end == -1:
                raise MtImportError(
                    _issue(
                        "MT_IMPORT_TEXT_BLOCK_NOT_CLOSED",
                        "The text block was opened with {4: but never closed with -}.",
                        layer=ValidationLayer.STRUCTURE,
                        expected="The text block ends with a line containing -}",
                        suggestion="Paste the whole message, including its final -} line.",
                    )
                )
            body = text[body_start:end]
            position = end + 2
        else:
            depth = 1
            cursor = body_start
            while cursor < len(text) and depth:
                if text[cursor] == "{":
                    depth += 1
                elif text[cursor] == "}":
                    depth -= 1
                cursor += 1
            if depth:
                raise MtImportError(
                    _issue(
                        "MT_IMPORT_BLOCK_NOT_CLOSED",
                        f"Block {block_id} was opened but never closed.",
                        layer=ValidationLayer.STRUCTURE,
                        location=f"block {block_id}",
                        suggestion="Paste the whole message.",
                    )
                )
            body = text[body_start : cursor - 1]
            position = cursor
        if block_id not in content:
            order.append(block_id)
        content[block_id] = body
    if not content:
        return _Blocks(content={"4": text}, order=["4"], bare_text_block=True)
    if "4" not in content:
        raise MtImportError(
            _issue(
                "MT_IMPORT_NO_TEXT_BLOCK",
                "That message has no text block, so it carries no field values.",
                layer=ValidationLayer.STRUCTURE,
                expected="A {4: … -} text block",
                current="Blocks " + ", ".join(order),
                suggestion="Paste the whole message, or paste the text block on its own.",
            )
        )
    return _Blocks(content=content, order=order, bare_text_block=False)


# --------------------------------------------------------------------------------------
# Identifying the message
# --------------------------------------------------------------------------------------


def _configured_types() -> list[MessageSpecification]:
    return specification_registry.list()


def _declared_type(blocks: _Blocks) -> tuple[str | None, list[ValidationIssue]]:
    """Read the message type out of Block 2, which is where a FIN message names itself."""
    warnings: list[ValidationIssue] = []
    block_2 = blocks.content.get("2")
    if block_2 is None:
        return None, warnings
    body = block_2.strip()
    match = (
        _BLOCK_2_INPUT.match(body)
        or _BLOCK_2_OUTPUT.match(body)
        or _BLOCK_2_DEMONSTRATION.match(body)
    )
    if match is None:
        warnings.append(
            _issue(
                "MT_IMPORT_BLOCK2_UNREADABLE",
                "The application header could not be read, so the message type was taken "
                "from the text block instead.",
                layer=ValidationLayer.FIN_ENVELOPE,
                severity=IssueSeverity.WARNING,
                location="block 2",
                current=body[:40],
                expected="I<type><receiver><priority>, for example I541DEMOUS33XXXXN",
                suggestion="Check the application header, or paste the text block on its own.",
            )
        )
        return None, warnings
    return f"MT{match.group('type')}", warnings


def _candidates_from_text(sequence_codes: set[str]) -> list[MessageSpecification]:
    """Narrow the configured messages to those whose sequences explain what is present.

    Deterministic set containment, never a similarity score: a message qualifies only if
    every sequence code in the text is one of its own.
    """
    if not sequence_codes:
        return []
    return [
        specification
        for specification in _configured_types()
        if sequence_codes <= {sequence.code for sequence in specification.sequences}
    ]


def _resolve_specification(
    blocks: _Blocks, requested: str | None, sequence_codes: set[str]
) -> tuple[MessageSpecification, list[ValidationIssue]]:
    declared, warnings = _declared_type(blocks)
    wanted = (requested or "").strip().upper() or None
    if wanted and not wanted.startswith("MT") and wanted.isdigit():
        wanted = f"MT{wanted}"

    if declared and wanted and declared != wanted:
        # Refusing beats reconciling. A file labelled one thing and containing another is
        # exactly the case where parsing against the caller's guess would produce a
        # confident, wrong answer.
        raise MtImportError(
            _issue(
                "MT_IMPORT_TYPE_MISMATCH",
                f"The message says it is {declared} but was imported as {wanted}.",
                layer=ValidationLayer.STRUCTURE,
                expected=declared,
                current=wanted,
                suggestion=f"Import it as {declared}, or leave the message type empty and "
                "let the application header decide.",
            )
        )

    chosen = declared or wanted
    if chosen is None:
        candidates = _candidates_from_text(sequence_codes)
        if len(candidates) == 1:
            return candidates[0], warnings
        if not candidates:
            raise MtImportError(
                _issue(
                    "MT_IMPORT_TYPE_UNKNOWN",
                    "The message type could not be worked out from that text.",
                    layer=ValidationLayer.STRUCTURE,
                    current=", ".join(sorted(sequence_codes)) or "no sequences",
                    expected=", ".join(item.message_type.value for item in _configured_types()),
                    suggestion="Paste the whole message including its application header, "
                    "or name the message type on the request.",
                )
            )
        raise MtImportError(
            _issue(
                "MT_IMPORT_TYPE_AMBIGUOUS",
                "That text block fits more than one message, so it cannot be imported "
                "without being told which one it is.",
                layer=ValidationLayer.STRUCTURE,
                current=", ".join(sorted(sequence_codes)),
                expected=", ".join(item.message_type.value for item in candidates),
                suggestion="Name the message type on the request, or paste the whole "
                "message including its application header.",
            )
        )

    try:
        message_type = MessageType(chosen)
    except ValueError as error:
        raise MtImportError(
            _issue(
                "MT_IMPORT_TYPE_NOT_CONFIGURED",
                f"{chosen} is not a message this repository is configured to generate.",
                layer=ValidationLayer.STRUCTURE,
                current=chosen,
                expected=", ".join(item.message_type.value for item in _configured_types()),
                suggestion="Import one of the configured messages, or add its specification "
                "to backend/config/specifications.",
            )
        ) from error
    return specification_registry.get(message_type), warnings


# --------------------------------------------------------------------------------------
# Reading the text block
# --------------------------------------------------------------------------------------


@dataclass
class _Instance:
    """One opened ``:16R:`` … ``:16S:`` sequence instance."""

    path: str
    code: str
    #: Index among all instances of this path, in document order — the composer's occurrence.
    index: int
    parent: _Instance | None


@dataclass
class _RawField:
    line_number: int
    tag: str
    qualifier: str | None
    value: str
    instance: _Instance


class _TextBlockReader:
    """Turn ``:16R:`` / tag lines into resolved specification rows and occurrences."""

    def __init__(self, specification: MessageSpecification) -> None:
        self._spec = specification
        self._by_code = {sequence.code: sequence for sequence in specification.sequences}
        self._by_address: dict[tuple[str, str, str | None], FieldSpecification] = {
            (row.sequence_path, row.tag, row.qualifier): row for row in specification.fields
        }
        self.fields: list[FieldInput] = []
        self.errors: list[ValidationIssue] = []
        self.warnings: list[ValidationIssue] = []
        self._counts: dict[str, int] = {}
        self._instances: list[_Instance] = []
        self._addressed: set[tuple[str, int]] = set()

    def read(self, body: str) -> None:
        raw = self._scan(body)
        if self.errors:
            return
        self._emit(raw)
        self._check_structure(raw)

    # -- pass one: structure ----------------------------------------------------------

    def _scan(self, body: str) -> list[_RawField]:
        stack: list[_Instance] = []
        raw: list[_RawField] = []
        pending: _RawField | None = None
        for number, line in enumerate(body.splitlines(), start=1):
            text = line.rstrip("\r")
            if not text.strip():
                continue
            if text == "-}":
                continue
            if not text.startswith(":"):
                if pending is None:
                    self.errors.append(
                        _issue(
                            "MT_IMPORT_UNPARSABLE_LINE",
                            f"Line {number} is not a field, a sequence marker or a "
                            "continuation of the line before it.",
                            layer=ValidationLayer.STRUCTURE,
                            location=f"line {number}",
                            current=text[:60],
                            expected="A line beginning with a colon, such as :20C::SEME//REF",
                            suggestion="Remove the line, or paste the message again "
                            "unedited.",
                        )
                    )
                    continue
                pending.value = f"{pending.value}\n{text}"
                continue

            boundary = _SEQUENCE_LINE.match(text)
            if boundary is not None:
                pending = None
                self._boundary(boundary, number, stack)
                continue

            field_match = _FIELD_LINE.match(text)
            if field_match is None:
                self.errors.append(
                    _issue(
                        "MT_IMPORT_UNPARSABLE_LINE",
                        f"Line {number} does not look like an MT field.",
                        layer=ValidationLayer.STRUCTURE,
                        location=f"line {number}",
                        current=text[:60],
                        expected="A tag and a value, such as :20C::SEME//REF",
                        suggestion="Correct the line, or paste the message again unedited.",
                    )
                )
                pending = None
                continue
            if not stack:
                self.errors.append(
                    _issue(
                        "MT_IMPORT_FIELD_OUTSIDE_SEQUENCE",
                        f"Line {number} carries a value that is not inside any sequence.",
                        layer=ValidationLayer.STRUCTURE,
                        location=f"line {number}",
                        current=text[:60],
                        expected="Every field sits between a :16R: and a :16S: marker",
                        suggestion="Paste the whole text block, starting at its first "
                        ":16R: line.",
                    )
                )
                pending = None
                continue
            pending = _RawField(
                line_number=number,
                tag=field_match.group("tag"),
                qualifier=field_match.group("qualifier"),
                value=field_match.group("value"),
                instance=stack[-1],
            )
            raw.append(pending)

        for unclosed in stack:
            self.errors.append(
                _issue(
                    "MT_IMPORT_SEQUENCE_NOT_CLOSED",
                    f"Sequence {unclosed.code} was opened but never closed.",
                    layer=ValidationLayer.STRUCTURE,
                    location=unclosed.path,
                    expected=f":16S:{unclosed.code}",
                    suggestion="Paste the whole text block.",
                )
            )
        return raw

    def _boundary(self, match: re.Match[str], number: int, stack: list[_Instance]) -> None:
        code = match.group("code")
        sequence = self._by_code.get(code)
        if sequence is None:
            self.errors.append(
                _issue(
                    "MT_IMPORT_UNKNOWN_SEQUENCE",
                    f"{code} is not a sequence of {self._spec.message_type.value}.",
                    layer=ValidationLayer.STRUCTURE,
                    location=f"line {number}",
                    current=code,
                    expected=", ".join(item.code for item in self._spec.sequences),
                    suggestion="Check the message type, or add the sequence to the message "
                    "specification in backend/config/specifications.",
                )
            )
            return
        if match.group("boundary") == "R":
            index = self._counts.get(sequence.path, 0) + 1
            self._counts[sequence.path] = index
            instance = _Instance(
                path=sequence.path,
                code=code,
                index=index,
                parent=stack[-1] if stack else None,
            )
            self._instances.append(instance)
            stack.append(instance)
            return
        if not stack:
            self.errors.append(
                _issue(
                    "MT_IMPORT_SEQUENCE_NOT_OPENED",
                    f"Sequence {code} is closed on line {number} but was never opened.",
                    layer=ValidationLayer.STRUCTURE,
                    location=f"line {number}",
                    expected=f":16R:{code} earlier in the message",
                    suggestion="Paste the whole text block.",
                )
            )
            return
        if stack[-1].code != code:
            self.errors.append(
                _issue(
                    "MT_IMPORT_SEQUENCE_MISMATCHED_END",
                    f"Sequence {stack[-1].code} is still open, but line {number} closes "
                    f"{code}.",
                    layer=ValidationLayer.STRUCTURE,
                    location=f"line {number}",
                    expected=f":16S:{stack[-1].code}",
                    current=f":16S:{code}",
                    suggestion="Sequences must close in the order they were opened.",
                )
            )
            return
        stack.pop()

    # -- pass two: can the address model hold what was read? --------------------------

    def _check_structure(self, raw: list[_RawField]) -> None:
        """Compare the nesting that was read with the nesting the composer would rebuild.

        The occurrence address is flat — ``(sequence_path, occurrence)`` — so not every
        nesting a real message can carry is expressible. Rather than restate that rule here
        and risk the two drifting apart, this runs the composer's own planner over the
        values that were read and checks the instance tree it produces is the tree the
        message actually had. A block that would come back somewhere else is refused, never
        quietly reshaped.
        """
        planned = plan_sequences(self._spec, self._addressed)
        bearing = {id(item.instance) for item in raw}
        failed: set[int] = set()
        for instance in self._instances:
            if instance.parent is not None and id(instance.parent) in failed:
                # Its container already failed; one explanation is enough.
                failed.add(id(instance))
                continue
            entry = planned.get((instance.path, instance.index))
            if entry is None:
                if self._holds_values(instance, bearing):
                    failed.add(id(instance))
                    self.errors.append(
                        _issue(
                            "MT_IMPORT_NESTED_REPEAT_UNSUPPORTED",
                            f"{instance.code} block {instance.index} carries no values of "
                            f"its own, so the studio cannot tell it apart from the "
                            f"{instance.code} block before it and their contents would be "
                            "merged.",
                            layer=ValidationLayer.STRUCTURE,
                            location=instance.path,
                            field_name=instance.code,
                            expected=f"A value directly inside each {instance.code} block",
                            suggestion=f"Import the {instance.code} blocks one at a time.",
                        )
                    )
                elif instance.index > 1 or not self._is_expected_empty(instance):
                    self.warnings.append(
                        _issue(
                            "MT_IMPORT_EMPTY_SEQUENCE_DROPPED",
                            f"The {instance.code} block held no values, so it is not "
                            "reproduced.",
                            layer=ValidationLayer.STRUCTURE,
                            severity=IssueSeverity.WARNING,
                            location=instance.path,
                            field_name=instance.code,
                            suggestion=f"Add a value inside the {instance.code} block if it "
                            "is meant to be there.",
                        )
                    )
                continue
            expected_parent = entry.parent_sequence_id
            actual_parent = (
                f"{instance.parent.path}#{instance.parent.index}"
                if instance.parent is not None
                else None
            )
            if expected_parent != actual_parent:
                failed.add(id(instance))
                rebuilt = (expected_parent or "the message").split("#")[0]
                container = instance.parent.code if instance.parent else "the message"
                self.errors.append(
                    _issue(
                        "MT_IMPORT_NESTED_REPEAT_UNSUPPORTED",
                        f"{instance.code} block {instance.index} is inside {container}, but "
                        "the studio addresses repeats by number alone and would rebuild it "
                        "somewhere else.",
                        layer=ValidationLayer.STRUCTURE,
                        location=instance.path,
                        field_name=instance.code,
                        current=f"Inside {container} block "
                        + (str(instance.parent.index) if instance.parent else "1"),
                        expected=f"Inside {rebuilt}",
                        suggestion=f"Import the {container} blocks one at a time.",
                    )
                )

    def _holds_values(self, instance: _Instance, bearing: set[int]) -> bool:
        if id(instance) in bearing:
            return True
        return any(
            id(other) in bearing and self._descends_from(other, instance)
            for other in self._instances
        )

    @staticmethod
    def _descends_from(instance: _Instance, ancestor: _Instance) -> bool:
        current = instance.parent
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent
        return False

    def _is_expected_empty(self, instance: _Instance) -> bool:
        """A first, mandatory sequence with no values is the ordinary "nothing filled in yet"
        case; the generator already reports its missing fields, so saying it was dropped as
        well would be two complaints about one thing."""
        sequence = self._by_code.get(instance.code)
        return bool(sequence and sequence.min_occurs >= 1 and instance.index == 1)

    # -- pass three: resolve every field ----------------------------------------------

    def _emit(self, raw: list[_RawField]) -> None:
        claimed: dict[tuple[str, int], int] = {}
        highest: dict[int, int] = {}
        order_reported = False
        for item in raw:
            row = self._by_address.get((item.instance.path, item.tag, item.qualifier))
            if row is None:
                label = item.tag + (f"/{item.qualifier}" if item.qualifier else "")
                self.errors.append(
                    _issue(
                        "MT_IMPORT_UNKNOWN_FIELD",
                        f"{label} is not part of the configured "
                        f"{self._spec.message_type.value} subset in sequence "
                        f"{item.instance.code}, so its value cannot be imported.",
                        layer=ValidationLayer.STRUCTURE,
                        location=f"line {item.line_number}",
                        field_name=label,
                        current=item.value[:40],
                        expected=", ".join(
                            sorted(
                                tag + (f"/{qualifier}" if qualifier else "")
                                for (path, tag, qualifier) in self._by_address
                                if path == item.instance.path
                            )
                        ),
                        suggestion="Remove the field, or add it to the message "
                        "specification in backend/config/knowledge.",
                    )
                )
                continue

            key = (row.row_id, item.instance.index)
            if key in claimed:
                self.errors.append(
                    _issue(
                        "MT_IMPORT_DUPLICATE_FIELD",
                        f"{row.business_name} appears twice in the same "
                        f"{item.instance.code} block, so only one of the two values could "
                        "be kept.",
                        layer=ValidationLayer.CANONICAL,
                        location=f"line {item.line_number}",
                        field_name=row.business_name,
                        current=item.value[:40],
                        expected=f"One {row.tag} per {item.instance.code} block",
                        suggestion=f"Remove the repeated field on line {item.line_number}, "
                        f"or split the message so each value has its own "
                        f"{item.instance.code} block.",
                    )
                )
                continue
            claimed[key] = item.line_number

            # The composer writes a sequence's fields in specification-row order. A message
            # that arrives in another order still regenerates correctly, but it regenerates
            # *reordered* — worth saying, because the tester will see the difference.
            seen = highest.get(id(item.instance), -1)
            if row.row_number < seen and not order_reported:
                order_reported = True
                self.warnings.append(
                    _issue(
                        "MT_IMPORT_FIELD_ORDER",
                        "The fields were written in a different order from the message "
                        "specification, so the regenerated message lists them in "
                        "specification order.",
                        layer=ValidationLayer.STRUCTURE,
                        severity=IssueSeverity.WARNING,
                        location=f"line {item.line_number}",
                        field_name=row.business_name,
                        suggestion="No action needed. The values are unchanged.",
                    )
                )
            highest[id(item.instance)] = max(seen, row.row_number)

            value = item.value.strip()
            if not value:
                self.errors.append(
                    _issue(
                        "MT_IMPORT_EMPTY_VALUE",
                        f"{row.business_name} is present but carries no value.",
                        layer=ValidationLayer.FORMAT,
                        location=f"line {item.line_number}",
                        field_name=row.business_name,
                        expected=row.format,
                        suggestion=f"Give {row.business_name} a value, or remove the line.",
                    )
                )
                continue
            try:
                self.fields.append(
                    FieldInput(
                        id=row.row_id,
                        occurrence=item.instance.index,
                        value=value,
                    )
                )
                self._addressed.add((item.instance.path, item.instance.index))
            except ValueError as error:
                # The canonical model refuses control characters, embedded FIN blocks and
                # over-long values. Reporting which field was refused is the whole point;
                # the alternative is a 500 on someone's malformed paste.
                self.errors.append(
                    _issue(
                        "MT_IMPORT_VALUE_REJECTED",
                        f"The value of {row.business_name} cannot be held as a field value.",
                        layer=ValidationLayer.FORMAT,
                        location=f"line {item.line_number}",
                        field_name=row.business_name,
                        current=value[:40],
                        expected=row.format,
                        suggestion=str(error).splitlines()[-1].strip()
                        or "Correct the value and import again.",
                    )
                )

    # -- what the caller needs to identify the message --------------------------------

    @property
    def sequence_codes(self) -> set[str]:
        return {instance.code for instance in self._instances}


def _sequence_codes(body: str) -> set[str]:
    """The ``:16R:`` skeleton, read before the message type is known."""
    return {
        match.group("code")
        for match in (
            _SEQUENCE_LINE.match(line.strip()) for line in body.splitlines() if line.strip()
        )
        if match is not None and match.group("boundary") == "R"
    }


def _root_order_warning(
    specification: MessageSpecification, body: str
) -> ValidationIssue | None:
    order = {sequence.code: sequence.order for sequence in specification.sequences}
    seen = [
        match.group("code")
        for match in (
            _SEQUENCE_LINE.match(line.strip()) for line in body.splitlines() if line.strip()
        )
        if match is not None and match.group("boundary") == "R"
    ]
    ranks = [order[code] for code in seen if code in order]
    if ranks == sorted(ranks):
        return None
    return _issue(
        "MT_IMPORT_SEQUENCE_ORDER",
        "The sequences were written in a different order from the message specification, "
        "so the regenerated message puts them back in specification order.",
        layer=ValidationLayer.STRUCTURE,
        severity=IssueSeverity.WARNING,
        current=", ".join(seen),
        expected=", ".join(
            item.code for item in sorted(specification.sequences, key=lambda x: x.order)
        ),
        suggestion="No action needed. The values are unchanged.",
    )


# --------------------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------------------


def _read_envelope(blocks: _Blocks) -> tuple[EnvelopeOverride, list[ValidationIssue]]:
    """Recover the interface values the message arrived with.

    Only values the message actually carries are returned. Nothing is completed from a
    default: an envelope value that is missing here is missing, and the ordinary generation
    path then falls back to the client profile or fails closed, exactly as it does for a
    message typed by hand.
    """
    warnings: list[ValidationIssue] = []
    envelope = EnvelopeOverride()

    block_1 = (blocks.content.get("1") or "").strip()
    demonstration = block_1 == _BLOCK_1_DEMONSTRATION or _BLOCK_2_DEMONSTRATION.match(
        (blocks.content.get("2") or "").strip()
    )
    if demonstration:
        # One explanation, not two "unreadable header" complaints. A demonstration envelope
        # is a valid thing to paste; it simply has no interface values in it.
        warnings.append(
            _issue(
                "MT_IMPORT_DEMONSTRATION_HEADER",
                "That message carries a demonstration envelope, which holds no interface "
                "addresses, so the sender, receiver, session and sequence come from the "
                "client profile.",
                layer=ValidationLayer.FIN_ENVELOPE,
                severity=IssueSeverity.WARNING,
                location="block 1",
                suggestion="No action needed. Set the envelope on the request to override "
                "the profile.",
            )
        )

    if block_1 and not demonstration:
        match = _BLOCK_1.match(block_1)
        if match is None:
            warnings.append(
                _issue(
                    "MT_IMPORT_BLOCK1_UNREADABLE",
                    "The basic header could not be read, so the sender, session and "
                    "sequence numbers were not carried over.",
                    layer=ValidationLayer.FIN_ENVELOPE,
                    severity=IssueSeverity.WARNING,
                    location="block 1",
                    current=block_1[:40],
                    expected="F01 followed by a 12-character terminal, 4-digit session and "
                    "6-digit sequence",
                    suggestion="The client profile supplies these values instead.",
                )
            )
        else:
            envelope.sender = match.group("sender")
            envelope.session_number = match.group("session")
            envelope.sequence_number = match.group("sequence")

    block_2 = (blocks.content.get("2") or "").strip()
    if block_2 and not demonstration:
        inbound = _BLOCK_2_INPUT.match(block_2)
        if inbound is not None:
            envelope.receiver = inbound.group("receiver")
            envelope.priority = inbound.group("priority")
        elif _BLOCK_2_OUTPUT.match(block_2) is not None:
            # An output header describes the delivery the network performed; it holds the
            # sender's input reference, not a receiver address. Reusing any of it as a
            # receiver would be inventing an address, so the profile's value is used.
            warnings.append(
                _issue(
                    "MT_IMPORT_OUTPUT_HEADER",
                    "That is a message as delivered, not as sent. Its header names the "
                    "delivering network rather than a receiver, so the receiver comes from "
                    "the client profile.",
                    layer=ValidationLayer.FIN_ENVELOPE,
                    severity=IssueSeverity.WARNING,
                    location="block 2",
                    suggestion="Set the receiver on the request if a specific one is needed.",
                )
            )

    block_3 = blocks.content.get("3")
    if block_3:
        found = {
            match.group("tag"): match.group("value") for match in _BLOCK_3_FIELD.finditer(block_3)
        }
        if "108" in found and found["108"]:
            envelope.message_user_reference = found["108"]
        unsupported = sorted(tag for tag in found if tag != "108")
        if unsupported:
            warnings.append(
                _issue(
                    "MT_IMPORT_USER_HEADER_FIELD_DROPPED",
                    "User header field"
                    + ("s " if len(unsupported) > 1 else " ")
                    + ", ".join(unsupported)
                    + " could not be carried over, because the studio only writes field 108.",
                    layer=ValidationLayer.FIN_ENVELOPE,
                    severity=IssueSeverity.WARNING,
                    location="block 3",
                    current=", ".join(unsupported),
                    expected="108",
                    suggestion="Add the field to the client profile if it is needed.",
                )
            )

    if blocks.content.get("5"):
        warnings.append(
            _issue(
                "MT_IMPORT_TRAILER_DROPPED",
                "The trailer was read but will not be reproduced. Authentication and "
                "checksum trailers are added by the messaging interface and the network, "
                "and the studio never generates them.",
                layer=ValidationLayer.FIN_ENVELOPE,
                severity=IssueSeverity.WARNING,
                location="block 5",
                suggestion="Let the receiving interface add the trailer.",
            )
        )
    return envelope, warnings


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def parse_message(text: str, *, message_type: str | None = None) -> MtImportResult:
    """Read an MT message — a full FIN message, a text block, or a pasted Block 4 body.

    :param message_type: only consulted when the text does not name itself. A Block 2 that
        disagrees with it is a refusal, not a reconciliation.
    :raises MtImportError: when the message cannot be identified at all, so there is
        nothing to hand to the generator.
    """
    body_text = text.strip()
    if not body_text:
        raise MtImportError(
            _issue(
                "MT_IMPORT_EMPTY",
                "There is no message to import.",
                layer=ValidationLayer.STRUCTURE,
                suggestion="Paste the message, or choose a file to upload.",
            )
        )
    if len(body_text.encode()) > MAX_IMPORT_BYTES:
        raise MtImportError(
            _issue(
                "MT_IMPORT_TOO_LARGE",
                "That message is larger than the studio accepts for import.",
                layer=ValidationLayer.STRUCTURE,
                expected=f"Up to {MAX_IMPORT_BYTES:,} bytes",
                suggestion="Import one message at a time.",
            )
        )

    blocks = _scan_blocks(body_text)
    text_block = blocks.content["4"]
    specification, warnings = _resolve_specification(
        blocks, message_type, _sequence_codes(text_block)
    )

    reader = _TextBlockReader(specification)
    reader.read(text_block)

    envelope, envelope_warnings = _read_envelope(blocks)
    warnings.extend(envelope_warnings)
    warnings.extend(reader.warnings)
    order_warning = _root_order_warning(specification, text_block)
    if order_warning is not None:
        warnings.append(order_warning)

    if not reader.fields and not reader.errors:
        warnings.append(
            _issue(
                "MT_IMPORT_NO_VALUES",
                "The message was read, but it contained no field values.",
                layer=ValidationLayer.STRUCTURE,
                severity=IssueSeverity.WARNING,
                suggestion="Check that the text block holds the fields you expect.",
            )
        )

    return MtImportResult(
        specification=specification,
        fields=reader.fields,
        envelope=envelope,
        blocks=blocks.order,
        errors=reader.errors,
        warnings=warnings,
    )

"""The guide's structure, offered to the rule compiler through the seam it already has.

``StructureIndex`` is the rule engine's only door onto structure, and it is read-only by
construction. Subclassing it here means a candidate rule derived from the SR2026 guide is
compiled by *the same compiler* that guards an installed pack — same reference resolution,
same type rules, same refusals — without the runtime registries being touched, and without
a second rule engine coming into existence to serve a second release.

The release boundary falls out of that rather than being policed on top of it. A candidate
compiled against this index binds to fields the SR2026 guide declares; the installed
runtime declares different fields under a different release, so the same pack simply does
not resolve there. Fail-closed is the default state, not an added check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.knowledge.models import PresenceRule
from app.rule_engine.mt_mrg.formatspec import (
    MrgFieldRow,
    MrgSequence,
    MrgStructure,
    RowStatus,
    SequencePresence,
)
from app.rule_engine.refs import FieldKind, FieldRef, ResolvedFieldRef, StructureIndex
from app.specifications.registry import MessageSpecificationRegistry
from app.studio.models import MessageFormat, Presence

#: A qualified single code — ``:4!c//4!c`` or an indicator's ``:4!c/[8c]/4!c``. Only these
#: hold one code as their whole value, so only these are compared against a code list. A
#: composite such as the message function's ``4!c[/4!c]`` is text: half of it is a
#: subfunction, and treating the pair as a code would make every real value unknown.
SINGLE_CODE_CONTENT = re.compile(r"^:4!c(?://|/\[8c\]/)4!c$")
AMOUNT_CONTENT = re.compile(r"15d|\d+d\b")
DATE_CONTENT = re.compile(r"8!n|YYYYMMDD")
#: Tags whose content the guide states as a format string rather than an option list, and
#: whose kind is therefore read from the tag itself.
KIND_BY_FIELD_NUMBER: dict[str, FieldKind] = {
    "19": FieldKind.DECIMAL,
    "32": FieldKind.DECIMAL,
    "33": FieldKind.DECIMAL,
    "34": FieldKind.DECIMAL,
    "36": FieldKind.DECIMAL,
    "90": FieldKind.DECIMAL,
    "92": FieldKind.DECIMAL,
    "98": FieldKind.DATE,
    "35": FieldKind.IDENTIFIER,
    "95": FieldKind.IDENTIFIER,
    "97": FieldKind.IDENTIFIER,
}
#: What a repeating row's cardinality is taken to be. The guide states repetition but not a
#: bound, and the number only has to be large enough that a ``COUNT`` rule is not refused
#: as unsatisfiable — it is never presented as a limit the standard sets.
UNBOUNDED_OCCURRENCES = 999


@dataclass(frozen=True)
class MrgField:
    """One addressable field the guide establishes, with where it said so."""

    key: str
    sequence_path: str
    tag: str
    qualifier: str | None
    display_name: str
    kind: FieldKind
    presence: Presence
    max_occurs: int
    codes: tuple[str, ...]
    always_present: bool
    page: int

    @property
    def field_number(self) -> str:
        return self.tag[:2]

    @property
    def option(self) -> str | None:
        suffix = self.tag[2:]
        return suffix if suffix.isupper() else None


def _kind(row: MrgFieldRow, codes: tuple[str, ...]) -> FieldKind:
    # Having a code list is not the same as *being* a code. The message function enumerates
    # its codes and still holds ``4!c[/4!c]`` — a function and an optional subfunction — so
    # treating the pair as one code would make every real value an unknown one.
    if SINGLE_CODE_CONTENT.fullmatch(row.content):
        return FieldKind.CODE
    known = KIND_BY_FIELD_NUMBER.get(row.field_number)
    if known is not None:
        return known
    if DATE_CONTENT.search(row.content):
        return FieldKind.DATE
    if AMOUNT_CONTENT.search(row.content):
        return FieldKind.DECIMAL
    return FieldKind.TEXT


def _mandatory_chain(structure: MrgStructure, sequence: MrgSequence) -> bool:
    """Whether every sequence from the message down to this one is mandatory."""
    current: MrgSequence | None = sequence
    while current is not None:
        if current.presence is not SequencePresence.MANDATORY:
            return False
        parent = current.parent_path
        current = structure.sequence(parent) if parent else None
    return True


def build_fields(structure: MrgStructure) -> tuple[MrgField, ...]:
    """Every field a rule may name, derived from the two tables the guide publishes.

    The Format Specifications place a tag in a sequence; the field's own qualifier table
    says which qualifiers it may carry there. Neither alone is enough — a tag with no
    qualifier context would let a rule name a combination the guide never allows — so a
    field exists here only where both tables agree it does.

    Each combination is offered twice: once under the generic tag the guide writes when the
    option does not matter (``:95a::PSET``), and once per declared option (``:95L::ALTE``).
    They are separate fields on purpose. A rule that names an option means that option, and
    collapsing the two would silently widen it.
    """
    fields: list[MrgField] = []
    seen: set[str] = set()
    for row in structure.rows:
        sequence = structure.sequence(row.sequence_path)
        if sequence is None:
            continue
        repeating = row.repetitive or sequence.repetitive
        mandatory = row.status is RowStatus.MANDATORY
        always = mandatory and not repeating and _mandatory_chain(structure, sequence)
        qualifier_rows = structure.qualifier_rows(row.sequence_path, row.tag)
        qualifiers: list[tuple[str | None, str, tuple[str, ...], tuple[str, ...]]] = []
        if row.generic_qualifier and qualifier_rows:
            for item in qualifier_rows:
                codes = _codes_for(structure, row, item.qualifier)
                qualifiers.append((item.qualifier, item.description, item.options, codes))
        elif row.qualifier:
            codes = _codes_for(structure, row, row.qualifier)
            qualifiers.append((row.qualifier, row.description, row.options, codes))
        else:
            codes = _codes_for(structure, row, None)
            qualifiers.append((None, row.description, row.options, codes))

        # A rule may name the field without naming a qualifier — ``:36B:`` means "36B
        # whatever it qualifies". That is a real, narrower-than-nothing reference, so the
        # field exists here in its own right as well as once per qualifier.
        if any(item[0] is not None for item in qualifiers):
            qualifiers.append((None, row.description, row.options, ()))

        for qualifier, name, options, codes in qualifiers:
            tags = {row.tag, row.field_number}
            tags.update(f"{row.field_number}{letter}" for letter in options)
            for tag in sorted(tags):
                key = _key(structure, row.sequence_path, tag, qualifier)
                if key in seen:
                    continue
                seen.add(key)
                fields.append(
                    MrgField(
                        key=key,
                        sequence_path=row.sequence_path,
                        tag=tag,
                        qualifier=qualifier,
                        display_name=_display_name(name, row, qualifier),
                        kind=_kind(row, codes),
                        presence=(
                            Presence(PresenceRule.MANDATORY.value)
                            if mandatory
                            else Presence(PresenceRule.OPTIONAL.value)
                        ),
                        max_occurs=UNBOUNDED_OCCURRENCES if repeating else 1,
                        codes=codes,
                        always_present=always,
                        page=row.page,
                    )
                )
    return tuple(fields)


def _key(structure: MrgStructure, sequence_path: str, tag: str, qualifier: str | None) -> str:
    parts = [structure.message_type, structure.standards_release, sequence_path, tag]
    if qualifier:
        parts.append(qualifier)
    return ":".join(parts)


def _display_name(name: str, row: MrgFieldRow, qualifier: str | None) -> str:
    cleaned = " ".join(name.replace("(see qualifier description)", "").split())
    if cleaned:
        return cleaned[:120]
    return f"{row.tag}{f'::{qualifier}' if qualifier else ''}"


def _codes_for(
    structure: MrgStructure, row: MrgFieldRow, qualifier: str | None
) -> tuple[str, ...]:
    """Codes the guide enumerates for exactly this qualifier of this field.

    Attribution matters more than coverage here: a CODES block may introduce several lists
    in turn, and handing one qualifier's codes to another is how a dropdown ends up
    offering a value the network rejects.
    """
    spec = next(
        (
            item
            for item in structure.field_specs
            if item.sequence_path == row.sequence_path and item.tag[:2] == row.field_number
        ),
        None,
    )
    if spec is None:
        return ()
    for named, codes in spec.codes:
        if named == (qualifier or ""):
            return codes
    return ()


class MrgStructureIndex(StructureIndex):
    """A read-only structure index over one guide, for one message, for one release."""

    def __init__(
        self,
        structure: MrgStructure,
        *,
        mt: MessageSpecificationRegistry | None = None,
    ) -> None:
        super().__init__(mt=mt)
        self._structure = structure
        self._fields = build_fields(structure)
        self._by_key = {item.key: item for item in self._fields}

    @property
    def structure(self) -> MrgStructure:
        return self._structure

    @property
    def mrg_fields(self) -> tuple[MrgField, ...]:
        return self._fields

    def known(self, format_: MessageFormat, message_type: str) -> bool:
        return (
            format_ is MessageFormat.MT
            and message_type.upper() == self._structure.message_type
        )

    def version(self, format_: MessageFormat, message_type: str) -> str | None:
        if not self.known(format_, message_type):
            return None
        return self._structure.standards_release

    def fields(self, format_: MessageFormat, message_type: str) -> list[ResolvedFieldRef]:
        if not self.known(format_, message_type):
            return []
        return [self._resolved(item, item.key) for item in self._fields]

    def resolve(self, ref: FieldRef, message_type: str) -> ResolvedFieldRef | None:
        if ref.format is not MessageFormat.MT or not self.known(MessageFormat.MT, message_type):
            return None
        if ref.field_id:
            found = self._by_key.get(ref.field_id)
            return self._resolved(found, ref.canonical()) if found else None
        matches = [
            item
            for item in self._fields
            if item.tag == ref.tag
            and item.qualifier == ref.qualifier
            and (
                ref.sequence_path is None
                or item.sequence_path.upper() == ref.sequence_path.upper()
            )
        ]
        if len(matches) != 1:
            # Ambiguous is as unusable as absent, exactly as the runtime index treats it.
            return None
        return self._resolved(matches[0], ref.canonical())

    def structure_checksum(self, format_: MessageFormat, message_type: str) -> str:
        if not self.known(format_, message_type):
            return "sha256:" + "0" * 64
        return self._structure.checksum()

    def _resolved(self, field: MrgField, canonical: str) -> ResolvedFieldRef:
        return ResolvedFieldRef(
            canonical=canonical,
            key=field.key,
            display_name=field.display_name,
            kind=field.kind,
            presence=field.presence,
            max_occurs=field.max_occurs,
            codes=field.codes,
            location=field.key,
            always_present=field.always_present,
        )

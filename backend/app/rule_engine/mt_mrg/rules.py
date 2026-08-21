"""Network Validated Rules: finding them, and translating the ones that translate.

Two separate jobs, kept separate on purpose.

**Discovery** is complete and unconditional. Every ``Cn`` the guide numbers is found, with
its page, its SWIFT error codes and a hash of its text, whether or not this repository can
express it. A rule that cannot be expressed is still a rule a reviewer must see, and an
inventory that quietly listed only the convenient ones would be worse than no inventory.

**Translation** is deliberately narrow. It recognises a closed set of sentence forms the
guide actually uses and refuses everything else, because the alternative — inferring a rule
from a sentence nobody anticipated — is how a validator ends up rejecting correct messages.
Each translation is classified by how faithful it is:

``EXACT``
    the expression means what the source rule means.
``PARTIAL``
    the expression is *weaker* than the source rule and can therefore only ever miss a
    violation, never invent one. The clause that was dropped is recorded.
``UNSUPPORTED``
    no sound expression exists in this DSL. Recorded with the reason, never approximated.

Nothing here calls a model. The guide states its rules in a small, stable, house style, and
a regular expression that matches that style is reproducible in a way a model is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.rule_engine.dsl import Expression, Operator, Predicate, Subject
from app.rule_engine.mt_mrg.document import (
    MrgPage,
    MrgSection,
    MrgSectionSpan,
    body_lines,
    flow,
)
from app.rule_engine.mt_mrg.formatspec import MrgStructure, error_codes_in
from app.rule_engine.refs import FieldRef
from app.rule_engine.sources import sha256_of
from app.studio.models import MessageFormat

RULE_START = re.compile(r"^C(?P<number>\d{1,2})\s+(?P<text>\S.*)$")
#: A field as the guide writes it: ``:19A::SETT``, ``:22F::DBNM//VEND``, ``:36B:``,
#: ``:97a::``. The option letter may be a literal (``95L``) or the generic ``a``.
FIELD_TOKEN = (
    r":(?P<{prefix}tag>\d{{2}}[A-Za-z]?):(?::(?P<{prefix}qualifier>[A-Z0-9]{{4}})"
    r"(?://(?P<{prefix}value>[A-Z0-9]{{1,4}}))?)?"
)


def _token(prefix: str) -> str:
    return FIELD_TOKEN.format(prefix=prefix)


class RuleFidelity(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_RECOGNISED = "NOT_RECOGNISED"


class UnsupportedReason(StrEnum):
    #: The rule constrains fields *within one occurrence* of a repeating (sub)sequence.
    #: The evaluator's value bag addresses a field, not a field-in-an-occurrence, so no
    #: sound expression exists — an occurrence-blind version would forbid a combination
    #: the source permits and reject correct messages.
    OCCURRENCE_SCOPE_NOT_EXPRESSIBLE = "OCCURRENCE_SCOPE_NOT_EXPRESSIBLE"
    #: The rule turns on a *component* of a field (a data source scheme, a format option)
    #: rather than on its value. References resolve to fields, not components.
    COMPONENT_SCOPE_NOT_EXPRESSIBLE = "COMPONENT_SCOPE_NOT_EXPRESSIBLE"
    #: The guide states the rule in a form this reader does not recognise.
    SENTENCE_FORM_NOT_RECOGNISED = "SENTENCE_FORM_NOT_RECOGNISED"
    #: The rule names a field the Format Specifications do not place in this message.
    REFERENCE_NOT_RESOLVED = "REFERENCE_NOT_RESOLVED"
    #: The rule names a field whose sequence the guide does not determine uniquely.
    REFERENCE_AMBIGUOUS = "REFERENCE_AMBIGUOUS"
    #: The rule reads Block 1, 2 or 3 of the FIN envelope (BICs, user header, validation
    #: flag), which a Block 4 rule engine does not see.
    ENVELOPE_DEPENDENT = "ENVELOPE_DEPENDENT"
    #: The rule adds or totals amounts; the DSL compares values and never computes them.
    ARITHMETIC_NOT_MODELLED = "ARITHMETIC_NOT_MODELLED"
    #: The sentence introduces a dependency table the reader could not read as rows.
    TABLE_NOT_READ = "TABLE_NOT_READ"


@dataclass(frozen=True)
class MrgSourceRule:
    """One numbered Network Validated Rule, exactly as the guide numbers it."""

    message_type: str
    standards_release: str
    source_rule_id: str
    ordinal: int
    error_codes: tuple[str, ...]
    first_page: int
    last_page: int
    first_line: int
    last_line: int
    #: A digest of the rule's own text. Identifies the rule's wording without reproducing
    #: it: if SWIFT rewords C6, the hash moves and every candidate derived from it is stale.
    text_hash: str
    character_count: int
    #: The flowed text, held in memory for translation. Never written anywhere committed.
    text: str

    @property
    def canonical_rule_id(self) -> str:
        """``SWIFT-SR2026-MT541-C6`` — message, release and the source's own number."""
        return f"SWIFT-{self.standards_release}-{self.message_type}-{self.source_rule_id}"


@dataclass(frozen=True)
class RuleReference:
    """One canonical target a rule names, resolved against the guide's own structure."""

    sequence_path: str
    tag: str
    qualifier: str | None
    value: str | None
    resolved: bool
    detail: str = ""

    @property
    def field_number(self) -> str:
        return self.tag[:2]

    @property
    def option(self) -> str | None:
        """The format option the guide named, or ``None`` where it wrote the generic ``a``.

        ``:95L::ALTE`` names option L; ``:95a::ALTE`` names the field whatever option it
        carries. The difference decides how wide the reference is, and a rule that
        widened ``:36B:`` to "any 36" would fire on messages the guide never meant.
        """
        suffix = self.tag[2:]
        return suffix if suffix.isupper() else None

    @property
    def canonical_id(self) -> str:
        parts = [self.sequence_path, self.tag]
        if self.qualifier:
            parts.append(self.qualifier)
        return ":".join(parts)

    def field_ref(self) -> FieldRef:
        return FieldRef(
            format=MessageFormat.MT,
            sequence_path=self.sequence_path,
            tag=self.tag if self.option else self.field_number,
            qualifier=self.qualifier,
        )

    def describe(self) -> str:
        """``:19A::SETT in E3`` — the guide's own spelling, plus where it sits."""
        qualifier = f":{self.qualifier}" if self.qualifier else ""
        return f":{self.tag}:{qualifier} in {self.sequence_path}"


@dataclass(frozen=True)
class RuleTranslation:
    rule: MrgSourceRule
    fidelity: RuleFidelity
    template: str
    when: Expression | None = None
    assertion: Expression | None = None
    references: tuple[RuleReference, ...] = ()
    #: What the expression does *not* say that the source rule does. Empty when EXACT.
    residual: tuple[str, ...] = ()
    reason: UnsupportedReason | None = None
    #: A plain-language restatement derived from the expression, never from the source
    #: prose — so a reviewer package can explain a candidate without reproducing the book.
    interpretation: str = ""


# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------


def discover(
    pages: tuple[MrgPage, ...],
    spans: tuple[MrgSectionSpan, ...],
    *,
    message_type: str,
    message_name: str,
    standards_release: str,
    release_text: str,
) -> tuple[MrgSourceRule, ...]:
    """Every Network Validated Rule the guide numbers, in source order.

    The section heading establishes where the rules are, and the guide's own ``Cn`` labels
    establish where each one starts and stops. Neither is inferred.
    """
    span = next(
        (item for item in spans if item.section is MrgSection.NETWORK_VALIDATED_RULE), None
    )
    if span is None:
        return ()
    lines = [
        line
        for line in body_lines(pages, message_type, message_name, release_text)
        if span.covers_line(line.number) and line.text.strip() != span.heading
    ]
    starts = [
        index for index, line in enumerate(lines) if RULE_START.match(line.text.strip())
    ]
    rules: list[MrgSourceRule] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = lines[index:end]
        match = RULE_START.match(block[0].text.strip())
        assert match is not None  # noqa: S101 - filtered above
        raw = "\n".join(item.text.strip() for item in block)
        text = flow([match.group("text"), *(item.text.strip() for item in block[1:])])
        rules.append(
            MrgSourceRule(
                message_type=message_type,
                standards_release=standards_release,
                source_rule_id=f"C{int(match.group('number'))}",
                ordinal=position + 1,
                error_codes=error_codes_in(text),
                first_page=block[0].page,
                last_page=block[-1].page,
                first_line=block[0].number,
                last_line=block[-1].number,
                text_hash=sha256_of(raw),
                character_count=len(raw),
                text=text,
            )
        )
    return tuple(rules)


def numbering_is_contiguous(rules: tuple[MrgSourceRule, ...]) -> bool:
    """Whether the guide's own numbering runs 1..n with nothing skipped or repeated."""
    return [item.source_rule_id for item in rules] == [
        f"C{index}" for index in range(1, len(rules) + 1)
    ]


# --------------------------------------------------------------------------------------
# Reference resolution
# --------------------------------------------------------------------------------------


def resolve_reference(
    structure: MrgStructure,
    *,
    tag: str,
    qualifier: str | None,
    value: str | None = None,
    sequence_path: str | None = None,
) -> RuleReference:
    """Place a field the guide names inside the structure the guide states.

    Where the rule names a sequence, that sequence must declare the tag. Where it does not,
    the qualifier tables decide — and only when they decide *uniquely*. A qualifier that
    two sequences both declare is reported ambiguous rather than assigned to the likelier
    of them, because the likelier one is a guess.
    """
    number = tag[:2]
    option = tag[2:] if tag[2:].isupper() else None
    if sequence_path:
        rows = [item for item in structure.rows_in(sequence_path) if item.field_number == number]
        if not rows:
            return RuleReference(
                sequence_path=sequence_path,
                tag=tag,
                qualifier=qualifier,
                value=value,
                resolved=False,
                detail=f"{structure.message_type} has no {tag} in {sequence_path}",
            )
        if option is not None and not any(
            item.tag == tag or option in item.options for item in rows
        ):
            offered = sorted({letter for item in rows for letter in item.options})
            return RuleReference(
                sequence_path=sequence_path,
                tag=tag,
                qualifier=qualifier,
                value=value,
                resolved=False,
                detail=(
                    f"{sequence_path}:{number}a offers option "
                    f"{', '.join(offered) if offered else 'none'}, not {option}"
                ),
            )
        if qualifier is not None and not any(
            item.qualifier == qualifier
            for item in structure.qualifier_rows(sequence_path, tag)
        ):
            declared = [item.qualifier for item in structure.qualifier_rows(sequence_path, tag)]
            return RuleReference(
                sequence_path=sequence_path,
                tag=tag,
                qualifier=qualifier,
                value=value,
                resolved=False,
                detail=(
                    f"{sequence_path}:{tag} declares "
                    f"{', '.join(declared) if declared else 'no qualifier'}, not {qualifier}"
                ),
            )
        return RuleReference(
            sequence_path=sequence_path,
            tag=tag,
            qualifier=qualifier,
            value=value,
            resolved=True,
        )

    if qualifier is None:
        rows = [
            item
            for item in structure.rows
            if item.field_number == number
            and (option is None or item.tag == tag or option in item.options)
        ]
        sequences = sorted({item.sequence_path for item in rows})
        if len(sequences) != 1:
            return RuleReference(
                sequence_path=sequences[0] if sequences else "?",
                tag=tag,
                qualifier=None,
                value=value,
                resolved=False,
                detail=(
                    f"{tag} appears in {', '.join(sequences) or 'no sequence'}; the rule "
                    "does not name one"
                ),
            )
        return RuleReference(
            sequence_path=sequences[0], tag=tag, qualifier=None, value=value, resolved=True
        )

    owners = sorted(
        {
            item.sequence_path
            for spec in structure.field_specs
            for item in spec.qualifiers
            if item.tag[:2] == number and item.qualifier == qualifier
        }
    )
    if len(owners) != 1:
        return RuleReference(
            sequence_path=owners[0] if owners else "?",
            tag=tag,
            qualifier=qualifier,
            value=value,
            resolved=False,
            detail=(
                f"{tag}::{qualifier} is declared in {', '.join(owners) or 'no sequence'}; "
                "the rule does not name one"
            ),
        )
    return RuleReference(
        sequence_path=owners[0], tag=tag, qualifier=qualifier, value=value, resolved=True
    )


def _exists(reference: RuleReference) -> Predicate:
    return Predicate(field=reference.field_ref(), operator=Operator.EXISTS)


def _absent(reference: RuleReference) -> Predicate:
    return Predicate(field=reference.field_ref(), operator=Operator.ABSENT)


def _at_most(reference: RuleReference, limit: int) -> Predicate:
    return Predicate(
        field=reference.field_ref(),
        operator=Operator.LESS_OR_EQUAL,
        subject=Subject.COUNT,
        value=str(limit),
    )


def _count_equals(reference: RuleReference, count: int) -> Predicate:
    return Predicate(
        field=reference.field_ref(),
        operator=Operator.EQUALS,
        subject=Subject.COUNT,
        value=str(count),
    )


def _describe(reference: RuleReference) -> str:
    qualifier = f"::{reference.qualifier}" if reference.qualifier else ""
    return f":{reference.tag}:{qualifier} in {reference.sequence_path}"

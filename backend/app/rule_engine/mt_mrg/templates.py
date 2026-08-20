"""The closed set of sentence forms this reader will translate, and nothing else.

A Message Reference Guide states its Network Validated Rules in a small house style that
barely varies between books or between releases. Matching that style exactly is what makes
translation reproducible: the same bytes give the same expression today and next year, with
no model in the loop and no judgement to drift.

The rule that governs every template here is **soundness in one direction**. An expression
may say *less* than the source rule — it will then miss a violation a reviewer can still
catch — but it may never say *more*, because a rule that says more rejects messages SWIFT
accepts. Where no weaker-or-equal expression exists, the template refuses and says why.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.rule_engine.dsl import (
    AllOf,
    Expression,
    Implication,
    Implies,
    Operator,
    Predicate,
    Subject,
)
from app.rule_engine.mt_mrg.formatspec import MrgStructure
from app.rule_engine.mt_mrg.rules import (
    MrgSourceRule,
    RuleFidelity,
    RuleReference,
    RuleTranslation,
    UnsupportedReason,
    resolve_reference,
)

#: The guide's own footnote for a rule that stops applying when a data source scheme is
#: present. A data source scheme is a *component* of the field, and references resolve to
#: fields, so a translation that ignores the footnote is wider than the source rule — it
#: would apply where the source says it does not. Recognising the footnote is what turns
#: that from a silent defect into a recorded residual.
DSS_CAVEAT = re.compile(
    r"If the Data Source Scheme is present.*?then the conditional rule does not apply",
    re.IGNORECASE,
)
#: Wording that scopes a constraint to one occurrence of a repeating (sub)sequence.
OCCURRENCE_SCOPED = re.compile(
    r"in the same (?:occurrence|subsequence|sequence)|within the same occurrence|"
    r"in each occurrence of|in another subsequence|and another one must contain",
    re.IGNORECASE,
)

_TAG = r"(?P<{name}tag>\d{{2}}[A-Za-z]?)"
_QUAL = r"(?P<{name}qualifier>[A-Z0-9]{{4}})"
_VALUE = r"(?://\s*(?P<{name}value>[A-Z0-9]{{1,4}}))?"


def _field(name: str) -> str:
    """A field written the way the guide writes it: ``:19A::SETT``, ``:22F::DBNM//VEND``."""
    return (
        ":"
        + _TAG.format(name=name)
        + ":(?::"
        + _QUAL.format(name=name)
        + _VALUE.format(name=name)
        + ")?"
    )


#: Every field the guide names anywhere in a rule, used by the list-shaped templates.
ANY_FIELD = re.compile(_field(""))


@dataclass(frozen=True)
class TemplateMatch:
    """What a template produced, before fidelity is finally decided."""

    template: str
    when: Expression | None
    assertion: Expression
    references: tuple[RuleReference, ...]
    interpretation: str
    fidelity: RuleFidelity = RuleFidelity.EXACT
    residual: tuple[str, ...] = ()
    reason: UnsupportedReason | None = None


Builder = Callable[[re.Match[str], MrgSourceRule, MrgStructure], TemplateMatch | None]


def _reference(
    structure: MrgStructure,
    match: re.Match[str],
    name: str,
    *,
    sequence_path: str | None = None,
) -> RuleReference | None:
    groups = match.groupdict()
    tag = groups.get(f"{name}tag")
    if tag is None:
        return None
    return resolve_reference(
        structure,
        tag=tag,
        qualifier=groups.get(f"{name}qualifier"),
        value=groups.get(f"{name}value"),
        sequence_path=sequence_path,
    )


def _exists(reference: RuleReference) -> Predicate:
    return Predicate(field=reference.field_ref(), operator=Operator.EXISTS)


def _absent(reference: RuleReference) -> Predicate:
    return Predicate(field=reference.field_ref(), operator=Operator.ABSENT)


def _equals(reference: RuleReference, value: str) -> Predicate:
    return Predicate(field=reference.field_ref(), operator=Operator.EQUALS, value=value)


def _count(reference: RuleReference, operator: Operator, value: int) -> Predicate:
    return Predicate(
        field=reference.field_ref(),
        operator=operator,
        subject=Subject.COUNT,
        value=str(value),
    )


def _implies(condition: Expression, consequence: Expression) -> Implies:
    return Implies(implies=Implication(if_=condition, then=consequence))


def _name(reference: RuleReference) -> str:
    return reference.describe()


# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------

UNIQUE_PER_SUBSEQUENCE = re.compile(
    r"^The following (?P<kind>amount|party) fields cannot appear in more than one "
    r"occurrence of the subsequence (?P<sequence>[A-Z]\d?)\b"
)
UNIQUE_IN_MESSAGE = re.compile(
    r"^The following (?P<kind>amount|party) fields cannot appear more than once in a "
    r"message\b"
)
CONDITIONAL_PRESENCE = re.compile(
    r"^In (?:\(sub\))?(?:sub)?sequence (?P<sequence>[A-Z]\d?), if (?:[^.()]*\()?field "
    + _field("a")
    + r"\)? is present, then (?:[^.()]*\()?field "
    + _field("b")
    + r"\)? must be present"
)
EXCHANGE_RATE_PAIR = re.compile(
    r"^In \(sub\)sequence (?P<sequence>[A-Z]\d?), if an exchange rate \(field "
    + _field("a")
    + r"\) is present, the corresponding resulting amount \(field "
    + _field("b")
    + r"\) must be present in the same subsequence\. If the exchange rate is not present "
    r"then the resulting amount is not allowed"
)
ABSENT_REQUIRES_TWO_PARTIES = re.compile(
    r"^If field "
    + _field("a")
    + r" is NOT present in sequence (?P<conditionsequence>[A-Z]\d?), then it is mandatory "
    r"to specify [^:]*: one occurrence of subsequence (?P<sequence>[A-Z]\d) [^:]*?must "
    r"contain party field "
    + _field("b")
    + r" and another one must contain party field "
    + _field("c")
)
PRESENT_REQUIRES_PARTY = re.compile(
    r"^If field "
    + _field("a")
    + r" is present in sequence (?P<conditionsequence>[A-Z]\d?), then an? [^,;]*? must be "
    r"specified[,;] that is,? one occurrence of (?:sub)?sequence (?P<sequence>[A-Z]\d?) "
    r"must contain field "
    + _field("b")
)
MANDATORY_QUALIFIED_FIELD = re.compile(
    r"^It is mandatory to specify [^:]*: one occurrence of the [^.]*?(?:sub)?sequence "
    r"(?P<sequence>[A-Z]\d?) must contain (?:\w+ )?field " + _field("a")
)
CHAIN_LINK = re.compile(
    r"If "
    + _field("a")
    + r" is present in subsequence (?P<sequence>[A-Z]\d), then "
    + _field("b")
    + r" must be present in another subsequence [A-Z]\d"
)
CHAIN_INTRODUCTION = re.compile(
    r"^If a qualifier from the list (?P<list>Deliverers|Receivers) is present in a "
    r"subsequence (?P<sequence>[A-Z]\d)"
)
CANCELLATION_PREVIOUS_REFERENCE = re.compile(
    r"^If the message is a cancellation, that is, Function of the Message \(field "
    r"(?P<functiontag>\d{2}[A-Z])\) is (?P<code>[A-Z]{4}), then subsequence "
    r"(?P<linkagesequence>[A-Z]\d) \([^)]*\) must be present at least once in the message, "
    r"and in one and only one occurrence of [A-Z]\d, field "
    + _field("a")
    + r" must be present"
)
SAME_OCCURRENCE_FORBIDDEN = re.compile(
    r"^In (?:each occurrence of )?(?:sub)?sequence (?P<sequence>[A-Z]\d?), if field "
    + _field("a")
    + r"[^,]*? is present[^,]*?, then field "
    + _field("b")
    + r"[^.]*? (?:is not allowed|must not be present|must not be used) in the same "
    r"(?:occurrence|subsequence|sequence)"
)
CROSS_SUBSEQUENCE_EXCLUSION = re.compile(
    r"^If field "
    + _field("a")
    + r" of subsequence (?P<sequence>[A-Z]\d) is present, then field "
    + _field("b")
    + r" in subsequence (?P<othersequence>[A-Z]\d) must NOT be present"
)
AT_MOST_TWICE_PAIRED = re.compile(
    r"^In sequence (?P<sequence>[A-Z]\d?), field "
    + _field("a")
    + r" cannot appear more than twice \(maximum two occurrences\)\. When repeated, one "
    r"occurrence must have (?P<firstkind>[\w /]+?) (?P<firstcode>[A-Z]{4}) and the other "
    r"occurrence must have"
)
AT_MOST_TWICE_OPTION = re.compile(
    r"In (?P<eachoccurrence>each occurrence of )?(?:sub)?sequence (?P<sequence>[A-Z]\d?), "
    r"field "
    + _field("a")
    + r" must not be present more than twice\. When repeated, one and only one occurrence "
    r"must be with format option (?P<option>[A-Z])"
)
LINKED_QUANTITY_TRANSACTION_TYPE = re.compile(
    r"^If field "
    + _field("a")
    + r" is present in minimum one occurrence of sequence (?P<conditionsequence>[A-Z]\d?), "
    r"then [^;]*?; that is,? sequence (?P<sequence>[A-Z]\d?) field :(?P<btag>\d{2}[A-Z])::"
    r"(?P<bqualifier>[A-Z0-9]{4})//\s*(?P<firstvalue>[A-Z]{4}) or :\d{2}[A-Z]::[A-Z0-9]{4}"
    r"//\s*(?P<secondvalue>[A-Z]{4}) must be present"
)
FOREX_CANCELLATION = re.compile(
    r"^If field :(?P<atag>\d{2}[A-Z])::(?P<aqualifier>[A-Z0-9]{4})//\s*(?P<firstvalue>"
    r"[A-Z]{4}) or (?P<secondvalue>[A-Z]{4}) is present in sequence (?P<sequence>[A-Z]\d?), "
    r"then the message must be a cancellation, that is, Function of the Message in sequence "
    r"(?P<functionsequence>[A-Z]\d?) \(field (?P<functiontag>\d{2}[A-Z])\) is "
    r"(?P<cancelcode>[A-Z]{4})\.\s*If field :\d{2}[A-Z]::[A-Z0-9]{4}//\s*"
    r"(?P<thirdvalue>[A-Z]{4}) is present in sequence [A-Z]\d?, then the message must be "
    r"new, that is, Function of the Message in sequence [A-Z]\d? \(field \d{2}[A-Z]\) is "
    r"(?P<newcode>[A-Z]{4})"
)
SPLIT_SETTLEMENT_VALUE_DATE = re.compile(
    r"in any occurrence of subsequence (?P<sequence>[A-Z]\d), if value date field "
    + _field("a")
    + r" is present, then in sequence (?P<othersequence>[A-Z]\d?) field :(?P<btag>\d{2}"
    r"[A-Z])::(?P<bqualifier>[A-Z0-9]{4})//\s*(?P<bvalue>[A-Z]{4}) must be present, and "
    r"[\w ]*?field "
    + _field("c")
    + r" must be present in the same subsequence"
)


def _all_fields(text: str, structure: MrgStructure, sequence: str | None) -> list[RuleReference]:
    seen: list[RuleReference] = []
    for match in ANY_FIELD.finditer(text):
        reference = resolve_reference(
            structure,
            tag=match.group("tag"),
            qualifier=match.group("qualifier"),
            value=match.group("value"),
            sequence_path=sequence,
        )
        if reference.qualifier is None:
            continue
        if any(item.canonical_id == reference.canonical_id for item in seen):
            continue
        seen.append(reference)
    return seen


def _repeats_within_occurrence(structure: MrgStructure, reference: RuleReference) -> bool:
    """Whether the guide's own R/N column says this qualifier repeats inside its sequence."""
    rows = [
        item
        for item in structure.qualifier_rows(reference.sequence_path, reference.tag)
        if item.qualifier == reference.qualifier
    ]
    return any(item.repetition == "R" for item in rows)


def _unique_fields(
    rule: MrgSourceRule,
    structure: MrgStructure,
    sequence: str | None,
    template: str,
    scope: str,
) -> TemplateMatch | None:
    references = _all_fields(rule.text, structure, sequence)
    if not references:
        return None
    residual: list[str] = []
    for reference in references:
        if _repeats_within_occurrence(structure, reference):
            # The guide allows this qualifier to repeat inside one occurrence, so counting
            # occurrences across the message would forbid a combination the guide permits.
            residual.append(
                f"{_name(reference)} may repeat within its own occurrence, so a "
                "message-wide count is not a sound reading"
            )
    if residual:
        return TemplateMatch(
            template=template,
            when=None,
            assertion=_exists(references[0]),
            references=tuple(references),
            interpretation="",
            fidelity=RuleFidelity.UNSUPPORTED,
            residual=tuple(residual),
            reason=UnsupportedReason.OCCURRENCE_SCOPE_NOT_EXPRESSIBLE,
        )
    return TemplateMatch(
        template=template,
        when=None,
        assertion=AllOf(
            all_of=tuple(_count(item, Operator.LESS_OR_EQUAL, 1) for item in references)
        ),
        references=tuple(references),
        interpretation=(
            f"Each of {len(references)} listed fields may appear at most once {scope}."
        ),
    )


def _build_unique_per_subsequence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequence = match.group("sequence")
    return _unique_fields(
        rule,
        structure,
        sequence,
        "AMOUNT_FIELDS_UNIQUE_PER_SUBSEQUENCE",
        f"across the occurrences of {sequence}",
    )


def _build_unique_in_message(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    return _unique_fields(
        rule, structure, None, "PARTY_FIELDS_UNIQUE_IN_MESSAGE", "in the message"
    )


def _build_conditional_presence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequence = match.group("sequence")
    first = _reference(structure, match, "a", sequence_path=None)
    second = _reference(structure, match, "b", sequence_path=None)
    if first is None or second is None:
        return None
    # The rule opens by naming the sequence; use it wherever the qualifier tables do not
    # decide on their own, so "In sequence C" is honoured rather than re-derived.
    if not first.resolved:
        first = _reference(structure, match, "a", sequence_path=sequence) or first
    if not second.resolved:
        second = _reference(structure, match, "b", sequence_path=sequence) or second
    return TemplateMatch(
        template="CONDITIONAL_PRESENCE",
        when=_exists(first),
        assertion=_exists(second),
        references=(first, second),
        interpretation=f"When {_name(first)} is present, {_name(second)} must be present.",
    )


def _build_exchange_rate_pair(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequence = match.group("sequence")
    first = _reference(structure, match, "a", sequence_path=sequence)
    second = _reference(structure, match, "b", sequence_path=sequence)
    if first is None or second is None:
        return None
    return TemplateMatch(
        template="EXCHANGE_RATE_REQUIRES_RESULTING_AMOUNT",
        when=None,
        assertion=AllOf(
            all_of=(
                _implies(_exists(first), _exists(second)),
                _implies(_absent(first), _absent(second)),
            )
        ),
        references=(first, second),
        interpretation=(
            f"{_name(second)} must be present when {_name(first)} is, and must be absent "
            "when it is not."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source requires the resulting amount in the *same* occurrence of the "
            "subsequence; this expression only requires it somewhere in the message.",
        ),
    )


def _build_absent_requires_two_parties(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    condition = _reference(
        structure, match, "a", sequence_path=match.group("conditionsequence")
    )
    sequence = match.group("sequence")
    first = _reference(structure, match, "b", sequence_path=sequence)
    second = _reference(structure, match, "c", sequence_path=sequence)
    if condition is None or first is None or second is None:
        return None
    return TemplateMatch(
        template="ABSENT_INDICATOR_REQUIRES_TWO_PARTIES",
        when=_absent(condition),
        assertion=AllOf(all_of=(_exists(first), _exists(second))),
        references=(condition, first, second),
        interpretation=(
            f"When {_name(condition)} is absent, both {_name(first)} and {_name(second)} "
            "must be present."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            f"The source requires {_name(first)} and {_name(second)} in *different* "
            f"occurrences of {sequence}; this expression only requires both to be present.",
        ),
    )


def _build_present_requires_party(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    condition = _reference(
        structure, match, "a", sequence_path=match.group("conditionsequence")
    )
    party = _reference(structure, match, "b", sequence_path=match.group("sequence"))
    if condition is None or party is None:
        return None
    value = match.groupdict().get("avalue")
    when: Expression = _equals(condition, value) if value else _exists(condition)
    said = (
        f"{_name(condition)} carries {value}" if value else f"{_name(condition)} is present"
    )
    return TemplateMatch(
        template="PRESENT_INDICATOR_REQUIRES_PARTY",
        when=when,
        assertion=_exists(party),
        references=(condition, party),
        interpretation=f"When {said}, {_name(party)} must be present.",
    )


def _build_mandatory_qualified_field(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    reference = _reference(structure, match, "a", sequence_path=match.group("sequence"))
    if reference is None:
        return None
    return TemplateMatch(
        template="MANDATORY_QUALIFIED_FIELD",
        when=None,
        assertion=_exists(reference),
        references=(reference,),
        interpretation=f"{_name(reference)} must be present in every message.",
    )


def _build_chain(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    links: list[tuple[RuleReference, RuleReference]] = []
    for link in CHAIN_LINK.finditer(rule.text):
        sequence = link.group("sequence")
        first = _reference(structure, link, "a", sequence_path=sequence)
        second = _reference(structure, link, "b", sequence_path=sequence)
        if first is None or second is None:
            continue
        links.append((first, second))
    if not links:
        return None
    references = [item for pair in links for item in pair]
    return TemplateMatch(
        template="PARTY_CHAIN_COMPLETENESS",
        when=None,
        assertion=AllOf(
            all_of=tuple(_implies(_exists(a), _exists(b)) for a, b in links)
        ),
        references=tuple(references),
        interpretation=(
            f"{len(links)} party-chain links: naming a party requires the next party in "
            "its chain to be named as well."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source requires the next party in *another* occurrence of the "
            "subsequence; this expression only requires it to be present.",
        ),
    )


def _build_cancellation_previous_reference(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    function = resolve_reference(
        structure, tag=match.group("functiontag"), qualifier=None, sequence_path="A"
    )
    previous = _reference(
        structure, match, "a", sequence_path=match.group("linkagesequence")
    )
    if previous is None:
        return None
    code = match.group("code")
    if _repeats_within_occurrence(structure, previous):
        return TemplateMatch(
            template="CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE",
            when=None,
            assertion=_exists(previous),
            references=(function, previous),
            interpretation="",
            fidelity=RuleFidelity.UNSUPPORTED,
            residual=(
                f"{_name(previous)} may repeat inside one occurrence, so counting it "
                "across the message does not express 'exactly one occurrence'.",
            ),
            reason=UnsupportedReason.OCCURRENCE_SCOPE_NOT_EXPRESSIBLE,
        )
    return TemplateMatch(
        template="CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE",
        # The function field carries an optional sub-function after a slash, so the code is
        # matched as the first component rather than compared to the whole value.
        when=Predicate(
            field=function.field_ref(),
            operator=Operator.MATCHES,
            value=f"{code}(/[A-Z0-9]{{1,4}})?",
        ),
        assertion=_count(previous, Operator.EQUALS, 1),
        references=(function, previous),
        interpretation=(
            f"When the message function is {code}, exactly one {_name(previous)} must be "
            "present."
        ),
    )


def _build_same_occurrence_forbidden(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequence = match.group("sequence")
    first = _reference(structure, match, "a", sequence_path=sequence)
    second = _reference(structure, match, "b", sequence_path=sequence)
    if first is None or second is None:
        return None
    # These rules routinely name more fields than the sentence's two anchor positions —
    # "if :95a::EXCH or :95a::TRRE is present". Recording every field the rule names keeps
    # the reviewer package honest about the rule's real reach, and lets the guide's own
    # cross-references confirm or contradict it.
    named = [first, second]
    for extra in _all_fields(rule.text, structure, sequence):
        if all(item.canonical_id != extra.canonical_id for item in named):
            named.append(extra)
    return TemplateMatch(
        template="SAME_OCCURRENCE_EXCLUSION",
        when=_exists(first),
        assertion=_absent(second),
        references=tuple(named),
        interpretation="",
        fidelity=RuleFidelity.UNSUPPORTED,
        residual=(
            f"The source forbids {_name(second)} only in the occurrence of {sequence} that "
            f"carries {_name(first)}. Forbidding it anywhere in {sequence} would reject "
            "messages the source allows.",
        ),
        reason=UnsupportedReason.OCCURRENCE_SCOPE_NOT_EXPRESSIBLE,
    )


def _build_cross_subsequence_exclusion(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    first = _reference(structure, match, "a", sequence_path=match.group("sequence"))
    second = _reference(structure, match, "b", sequence_path=match.group("othersequence"))
    if first is None or second is None:
        return None
    return TemplateMatch(
        template="CROSS_SUBSEQUENCE_EXCLUSION",
        when=_exists(first),
        assertion=_absent(second),
        references=(first, second),
        interpretation=f"When {_name(first)} is present, {_name(second)} must be absent.",
    )


def _build_at_most_twice_paired(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    reference = _reference(structure, match, "a", sequence_path=match.group("sequence"))
    if reference is None:
        return None
    return TemplateMatch(
        template="AT_MOST_TWICE_WITH_PAIRED_CODES",
        when=None,
        assertion=_count(reference, Operator.LESS_OR_EQUAL, 2),
        references=(reference,),
        interpretation=f"{_name(reference)} may appear at most twice.",
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source also requires the two occurrences to carry different quantity "
            "type codes; this expression only limits the count.",
        ),
    )


def _build_at_most_twice_option(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    clauses = list(AT_MOST_TWICE_OPTION.finditer(rule.text))
    if not clauses:
        return None
    references: list[RuleReference] = []
    per_occurrence = False
    for clause in clauses:
        if clause.group("eachoccurrence"):
            per_occurrence = True
        reference = _reference(structure, clause, "a", sequence_path=clause.group("sequence"))
        if reference is not None:
            references.append(reference)
    if not references:
        return None
    if per_occurrence:
        return TemplateMatch(
            template="AT_MOST_TWICE_WITH_ONE_OPTION",
            when=None,
            assertion=_count(references[0], Operator.LESS_OR_EQUAL, 2),
            references=tuple(references),
            interpretation="",
            fidelity=RuleFidelity.UNSUPPORTED,
            residual=(
                "Part of the source rule limits the count *within each occurrence* of a "
                "repeating subsequence. A message-wide count would reject messages the "
                "source allows.",
            ),
            reason=UnsupportedReason.OCCURRENCE_SCOPE_NOT_EXPRESSIBLE,
        )
    return TemplateMatch(
        template="AT_MOST_TWICE_WITH_ONE_OPTION",
        when=None,
        assertion=AllOf(
            all_of=tuple(_count(item, Operator.LESS_OR_EQUAL, 2) for item in references)
        ),
        references=tuple(references),
        interpretation="Each listed field may appear at most twice.",
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source also requires exactly one of the two occurrences to use a named "
            "format option; a reference resolves to a field, not to a format option.",
        ),
    )


def _build_linked_quantity_transaction_type(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    condition = _reference(
        structure, match, "a", sequence_path=match.group("conditionsequence")
    )
    indicator = resolve_reference(
        structure,
        tag=match.group("btag"),
        qualifier=match.group("bqualifier"),
        sequence_path=match.group("sequence"),
    )
    if condition is None:
        return None
    return TemplateMatch(
        template="LINKED_QUANTITY_REQUIRES_TRANSACTION_TYPE",
        when=_exists(condition),
        assertion=Predicate(
            field=indicator.field_ref(),
            operator=Operator.IN,
            values=(match.group("firstvalue"), match.group("secondvalue")),
        ),
        references=(condition, indicator),
        interpretation=(
            f"When {_name(condition)} is present, {_name(indicator)} must be "
            f"{match.group('firstvalue')} or {match.group('secondvalue')}."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source also requires no data source scheme on the indicator; a reference "
            "resolves to a field, not to one of its components.",
        ),
    )


def _build_forex_cancellation(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    indicator = resolve_reference(
        structure,
        tag=match.group("atag"),
        qualifier=match.group("aqualifier"),
        sequence_path=match.group("sequence"),
    )
    function = resolve_reference(
        structure,
        tag=match.group("functiontag"),
        qualifier=None,
        sequence_path=match.group("functionsequence"),
    )
    cancel = match.group("cancelcode")
    new = match.group("newcode")
    return TemplateMatch(
        template="FOREX_INDICATOR_REQUIRES_MESSAGE_FUNCTION",
        when=None,
        assertion=AllOf(
            all_of=(
                _implies(
                    Predicate(
                        field=indicator.field_ref(),
                        operator=Operator.IN,
                        values=(match.group("firstvalue"), match.group("secondvalue")),
                    ),
                    Predicate(
                        field=function.field_ref(),
                        operator=Operator.MATCHES,
                        value=f"{cancel}(/[A-Z0-9]{{1,4}})?",
                    ),
                ),
                _implies(
                    _equals(indicator, match.group("thirdvalue")),
                    Predicate(
                        field=function.field_ref(),
                        operator=Operator.MATCHES,
                        value=f"{new}(/[A-Z0-9]{{1,4}})?",
                    ),
                ),
            )
        ),
        references=(indicator, function),
        interpretation=(
            f"{_name(indicator)} carrying {match.group('firstvalue')} or "
            f"{match.group('secondvalue')} requires message function {cancel}; "
            f"{match.group('thirdvalue')} requires {new}."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source suspends the rule when a data source scheme is present on the "
            "indicator; a reference resolves to a field, not to one of its components.",
        ),
    )


def _build_split_settlement_value_date(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    value_date = _reference(structure, match, "a", sequence_path=match.group("sequence"))
    condition_indicator = resolve_reference(
        structure,
        tag=match.group("btag"),
        qualifier=match.group("bqualifier"),
        sequence_path=match.group("othersequence"),
    )
    amount = _reference(structure, match, "c", sequence_path=match.group("sequence"))
    if value_date is None or amount is None:
        return None
    return TemplateMatch(
        template="VALUE_DATE_REQUIRES_SPLIT_SETTLEMENT",
        when=_exists(value_date),
        assertion=AllOf(
            all_of=(
                _equals(condition_indicator, match.group("bvalue")),
                _exists(amount),
            )
        ),
        references=(value_date, condition_indicator, amount),
        interpretation=(
            f"When {_name(value_date)} is present, {_name(condition_indicator)} must carry "
            f"{match.group('bvalue')} and {_name(amount)} must be present."
        ),
        fidelity=RuleFidelity.PARTIAL,
        residual=(
            "The source ties the settlement amount to the *same* occurrence of the "
            "subsequence as the value date, and requires no data source scheme on the "
            "condition indicator.",
        ),
    )


#: Order matters: the first template whose sentence form matches wins, so the more specific
#: forms are listed before the general ones they would otherwise be swallowed by.
TEMPLATES: tuple[tuple[str, re.Pattern[str], Builder], ...] = (
    ("AMOUNT_FIELDS_UNIQUE_PER_SUBSEQUENCE", UNIQUE_PER_SUBSEQUENCE, _build_unique_per_subsequence),
    ("PARTY_FIELDS_UNIQUE_IN_MESSAGE", UNIQUE_IN_MESSAGE, _build_unique_in_message),
    ("MANDATORY_QUALIFIED_FIELD", MANDATORY_QUALIFIED_FIELD, _build_mandatory_qualified_field),
    ("EXCHANGE_RATE_REQUIRES_RESULTING_AMOUNT", EXCHANGE_RATE_PAIR, _build_exchange_rate_pair),
    (
        "ABSENT_INDICATOR_REQUIRES_TWO_PARTIES",
        ABSENT_REQUIRES_TWO_PARTIES,
        _build_absent_requires_two_parties,
    ),
    ("PARTY_CHAIN_COMPLETENESS", CHAIN_INTRODUCTION, _build_chain),
    (
        "CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE",
        CANCELLATION_PREVIOUS_REFERENCE,
        _build_cancellation_previous_reference,
    ),
    (
        "CROSS_SUBSEQUENCE_EXCLUSION",
        CROSS_SUBSEQUENCE_EXCLUSION,
        _build_cross_subsequence_exclusion,
    ),
    ("SAME_OCCURRENCE_EXCLUSION", SAME_OCCURRENCE_FORBIDDEN, _build_same_occurrence_forbidden),
    (
        "FOREX_INDICATOR_REQUIRES_MESSAGE_FUNCTION",
        FOREX_CANCELLATION,
        _build_forex_cancellation,
    ),
    ("PRESENT_INDICATOR_REQUIRES_PARTY", PRESENT_REQUIRES_PARTY, _build_present_requires_party),
    (
        "LINKED_QUANTITY_REQUIRES_TRANSACTION_TYPE",
        LINKED_QUANTITY_TRANSACTION_TYPE,
        _build_linked_quantity_transaction_type,
    ),
    ("AT_MOST_TWICE_WITH_PAIRED_CODES", AT_MOST_TWICE_PAIRED, _build_at_most_twice_paired),
    (
        "VALUE_DATE_REQUIRES_SPLIT_SETTLEMENT",
        SPLIT_SETTLEMENT_VALUE_DATE,
        _build_split_settlement_value_date,
    ),
    ("CONDITIONAL_PRESENCE", CONDITIONAL_PRESENCE, _build_conditional_presence),
    ("AT_MOST_TWICE_WITH_ONE_OPTION", AT_MOST_TWICE_OPTION, _build_at_most_twice_option),
)


def translate(rule: MrgSourceRule, structure: MrgStructure) -> RuleTranslation:
    """Turn one source rule into an expression, or say precisely why it cannot be."""
    for name, pattern, builder in TEMPLATES:
        match = pattern.search(rule.text)
        if match is None:
            continue
        produced = builder(match, rule, structure)
        if produced is None:
            continue
        return _finalise(rule, produced, name)
    return RuleTranslation(
        rule=rule,
        fidelity=RuleFidelity.NOT_RECOGNISED,
        template="",
        reason=UnsupportedReason.SENTENCE_FORM_NOT_RECOGNISED,
    )


def _finalise(
    rule: MrgSourceRule, produced: TemplateMatch, name: str
) -> RuleTranslation:
    """Apply the checks every template is subject to, whatever it matched."""
    unresolved = [item for item in produced.references if not item.resolved]
    if unresolved:
        ambiguous = any("does not name one" in item.detail for item in unresolved)
        return RuleTranslation(
            rule=rule,
            fidelity=RuleFidelity.UNSUPPORTED,
            template=name,
            references=produced.references,
            residual=tuple(item.detail for item in unresolved),
            reason=(
                UnsupportedReason.REFERENCE_AMBIGUOUS
                if ambiguous
                else UnsupportedReason.REFERENCE_NOT_RESOLVED
            ),
        )
    if produced.fidelity is RuleFidelity.UNSUPPORTED:
        return RuleTranslation(
            rule=rule,
            fidelity=RuleFidelity.UNSUPPORTED,
            template=name,
            references=produced.references,
            residual=produced.residual,
            reason=produced.reason,
        )

    fidelity = produced.fidelity
    residual = list(produced.residual)
    # Two checks every template is subject to, whatever it matched, so a new template
    # cannot silently claim to be exact when the guide qualified the rule.
    noted = any("data source scheme" in item.lower() for item in residual)
    if DSS_CAVEAT.search(rule.text) and not noted:
        fidelity = RuleFidelity.PARTIAL
        residual.append(
            "The guide suspends this rule where a data source scheme is present; a "
            "reference resolves to a field, not to one of its components."
        )
    if fidelity is RuleFidelity.EXACT and OCCURRENCE_SCOPED.search(rule.text):
        fidelity = RuleFidelity.PARTIAL
        residual.append(
            "The guide scopes part of this rule to one occurrence of a repeating "
            "(sub)sequence, which a field reference cannot express."
        )
    return RuleTranslation(
        rule=rule,
        fidelity=fidelity,
        template=name,
        when=produced.when,
        assertion=produced.assertion,
        references=produced.references,
        residual=tuple(residual),
        interpretation=produced.interpretation,
    )

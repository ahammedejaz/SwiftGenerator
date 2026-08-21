"""Generic sentence forms found across every category's Message Reference Guide.

Phase 5B/5C read the Category 5 house style. Reading all 156 SR2026 guides showed the
remaining rules fall into a small number of *compositional* shapes — a condition on one
field's presence or value, a consequence on another field's presence, codes or option; a
dependency table; a count limit; a currency-consistency statement; an either/or — and a
handful of shapes that depend on the FIN envelope or on arithmetic, which are recorded as
unsupported with their reason rather than approximated.

The soundness rule of :mod:`templates` applies unchanged: an expression may say less than
the source, never more. Every builder here either produces an expression that is exactly
the sentence, a weaker one with the dropped clause recorded as residual, or a refusal.
"""

# ruff: noqa: E501 - the sentence patterns read better on one line each than wrapped
from __future__ import annotations

import re
from collections.abc import Callable

from app.knowledge_base.structures.swift_format import component_pattern
from app.rule_engine.dsl import (
    AllEqual,
    AtLeastOne,
    AtMostOne,
    ComponentRef,
    ExactlyOne,
    Expression,
    Extraction,
    Not,
    Operator,
    Predicate,
    Subject,
)
from app.rule_engine.mt_mrg.formatspec import ROOT_SEQUENCE, MrgFieldRow, MrgStructure
from app.rule_engine.mt_mrg.rules import (
    MrgSourceRule,
    RuleFidelity,
    RuleReference,
    UnsupportedReason,
    resolve_reference,
)
from app.rule_engine.mt_mrg.templates import (
    TemplateMatch,
    _absent,
    _all,
    _count,
    _equals,
    _exists,
    _for_each,
    _implies,
    _name,
)
from app.rule_engine.refs import FieldRef
from app.studio.models import MessageFormat

# --------------------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------------------

SEQ = r"[A-Z](?:\d+|[a-z]|[A-Z])*"
#: ``field 36``, ``field :19A::SETT``, ``field 32B``, ``(field 36)`` — with or without the
#: leading colon the guides use for ISO 15022 fields.
FIELD = r":?(?P<{n}tag>\d{{2}}[A-Za-z]?):?(?::(?P<{n}qualifier>[A-Z0-9]{{4}}))?(?://\s?(?P<{n}value>[A-Z0-9]{{1,4}}))?"


def _f(name: str) -> str:
    return FIELD.format(n=name)


_LIST_FIELD = re.compile(r":?(\d{2}[A-Za-z]?):?(?::([A-Z0-9]{4}))?")
CODE = r"[A-Z0-9]{1,5}"  # four letters, or OTHER
CODES = rf"{CODE}(?:,\s*{CODE})*(?:,?\s*(?:or|and)\s+{CODE})?"

SCOPE = (
    r"^(?:(?:In|Within) (?P<each>each occurrence of |any occurrence of |all occurrences of )?"
    r"(?:(?P<therep>the repetitive (?:sub)?sequence)|"
    rf"(?:\(sub\))?(?:sub-?)?sequences? (?P<scope>{SEQ})(?P<scopelist>(?:,\s*{SEQ})*"
    rf"(?:,?\s*(?:and|or)\s+{SEQ})?)?)[^,:]*?,\s*)?"
)
CONDITION = (
    r"(?:[Ii]f|[Ww]hen|[Ww]here)\s+(?:the\s+)?(?:[^()]*?\()?(?:field\s+)?"
    + _f("a")
    + rf"\)?(?:\s+in\s+(?:sub)?sequence\s+(?P<aseq>{SEQ}))?\s+"
    r"(?P<cond>is present|is not present|is NOT present|is absent|is NOT used|is not used|is used|"
    rf'is\s+"?(?P<val>{CODE})"?|is equal to\s+"?(?P<val2>{CODE})"?|'
    rf"contains (?:the )?(?:code )?(?P<code>{CODE})|contains one of the codes\s+(?P<codes>{CODES})|"
    rf"contains (?:the )?codes?\s+(?P<codes2>{CODES})|"
    rf"does not contain (?:the )?(?:code )?(?P<notcode>{CODE}))"
)
CONSEQUENCE = (
    rf"\s*(?:,\s*)?(?:then\s+)?(?:in\s+(?:sub)?sequence\s+(?P<bseq0>{SEQ}),?\s+)?"
    r"(?:[^()]*?\()?(?:the\s+)?(?:field\s+)?"
    + _f("b")
    + rf"\)?(?:\s+in\s+(?:sub)?sequence\s+(?P<bseq>{SEQ}))?(?:\s*\([^)]*\))?\s+"
    r"(?P<cons>is mandatory|must be present|must also be present|is required|"
    r"is not allowed|must not be present|must not be used|may not be present|is optional|"
    r"must not be used with option (?P<optno>[A-Z])|may be used with option (?P<optonly>[A-Z]) only|"
    r"must be used with option (?P<optmust>[A-Z])|"
    rf"may (?:only )?contain (?:only )?(?:the )?(?:codes? )?(?P<allowed>{CODES})|"
    rf"must contain (?:the )?(?:code )?(?P<mustcode>{CODE})|"
    rf"must not contain (?:the )?(?:code )?(?P<notallowed>{CODE}))"
)
OTHERWISE = (
    r"(?:[,;]?\s*otherwise,?\s+(?:field\s+)?(?P<otherfield>:?\d{2}[A-Za-z]?:?)?\s*"
    r"(?P<other>is optional|is not allowed|must not be present|is mandatory|must be present|"
    r"may not be present))?"
)
CONDITIONAL_GENERAL = re.compile(SCOPE + CONDITION + CONSEQUENCE + OTHERWISE)

EITHER_OR = re.compile(
    SCOPE
    + rf"(?:[Ee]ither\s+)?fields?\s+{_f('a')}\s+or\s+(?:field\s+)?{_f('b')}(?P<both>,\s*but not both,?)?\s+"
    r"(?P<mode>may|must) be present",
)
BOTH_OR_NEITHER = re.compile(
    SCOPE
    + rf"(?:[Ww]hen used, )?fields?\s+{_f('a')}\s+and\s+(?:field\s+)?{_f('b')}\s+must\s+"
    r"(?:both|either both)\s+be present",
)
COUNT_LIMIT = re.compile(
    SCOPE
    + rf"[Ff]ields?\s+(?P<list>{_LIST_FIELD.pattern}(?:\s*(?:,|and|or)\s*{_LIST_FIELD.pattern})*)\s+"
    r"(?:cannot|may not|must not)\s+(?:appear|be present|be used)\s+more than\s+"
    r"(?P<limit>once|twice|\w+)(?:\s+times)?",
)
SEQUENCE_COUNT = re.compile(
    r"^The repetitive (?:sub)?sequence(?:\s+(?P<scope>" + SEQ + r"))? must "
    r"(?:(?:appear|be present) at least (?P<atleast>\w+)(?: times?)?,? (?:but|and) )?"
    r"(?:not (?:(?:appear|be present) )?more than|(?:(?:appear|be present) )?at most) "
    r"(?P<atmost>\w+)(?: times?)?",
)
NOT_ONLY_FIELD = re.compile(
    SCOPE
    + r"(?:"
    + rf"fields?\s+{_f('a')}(?:\s+(?:and|or)\s+(?:field\s+)?{_f('x')})?\s+may not be the only fields?(?: present)?"
    + rf"(?:[,.]\s*that is,\s*if\s+field\s+{_f('c')}\s+is present,?\s+then\s+at least one of the other fields"
    + rf"(?:\s+of\s+(?:sub)?sequence\s+(?P<oseq>{SEQ}))?\s+must be present)?"
    + r"|"
    + rf"[Ii]f\s+field\s+{_f('d')}\s+is present,?\s+then\s+at least one of the other fields"
    + rf"(?:\s+of\s+(?:sub)?sequence\s+(?P<oseq2>{SEQ}))?\s+must be present"
    + r")",
)
CURRENCY_SAME = re.compile(
    r"^The (?P<first>first two characters of the three character )?currency code in (?:the )?"
    rf"(?:amount )?fields?\s+(?P<list>{_LIST_FIELD.pattern}(?:\s*(?:,|and|or)\s*{_LIST_FIELD.pattern})*)"
    rf"(?:\s+in\s+(?:sub)?sequences?\s+(?P<seqs>{SEQ}(?:\s*(?:,|and)\s*{SEQ})*))?"
    r"\s+must be the same(?P<all>\s+for all occurrences of (?:this|these) fields? in the message)?",
)
CURRENCY_DIFFERENT_CONDITION = re.compile(
    rf"^If field\s+{_f('a')}\s+is present and the currency code is different from the "
    rf"currency code in field\s+{_f('b')},\s*field\s+{_f('c')}\s+must be present,?\s+"
    rf"otherwise field\s+:?(?P=ctag):?\s+is not allowed",
)
EXCHANGE_RATE_GENERAL = re.compile(
    SCOPE
    + rf"[Ii]f an exchange rate \(field\s+{_f('a')}\) is present, the corresponding resulting "
    rf"amount \(field\s+{_f('b')}\) must be present in the same (?:sub)?sequence"
    r"(?P<reverse>\.\s*If the exchange rate is not present,? then the resulting amount is not allowed)?",
)
CANCELLATION_GENERAL = re.compile(
    r"^If the message is a cancellation(?P<reversal> or a reversal)?, that is, Function of the "
    rf"Message \(field\s+{_f('fn')}\) is (?P<code>[A-Z]{{4}})(?: or (?P<code2>[A-Z]{{4}}))?, then "
    rf"(?:(?:sub)?sequence\s+{SEQ}\s*(?:\([^)]*\))?\s*must be present at least once in the message, "
    rf"and in one and only one occurrence of\s+{SEQ},\s*)?field\s+{_f('a')}\s+must be present"
    rf"(?: in one and only one occurrence of\s+(?:sub)?sequence\s+(?P<scope>{SEQ}))?",
)
RESPECTIVE_SEQUENCE = re.compile(
    rf"^In (?:sub)?sequences?\s+(?P<seqs>{SEQ}(?:\s*(?:,|and)\s*{SEQ})*),\s*if field\s+{_f('a')}\s+"
    rf"contains (?:the )?code\s+(?P<code>{CODE}),\s*field\s+{_f('b')}\s+must be present in the "
    r"respective (?:sub)?sequence",
)
ABSENT_FORBIDS_CODES = re.compile(
    rf"^If field\s+{_f('a')}\s+is not present, no field\s+{_f('b')}\s+may contain\s+(?P<codes>{CODES})",
)
PRESENT_IN_ONE_NOT_OTHER = re.compile(
    rf"^If the [^()]*\({_f('a')}\) is present in (?:sub)?sequence\s+(?P<seqa>{SEQ}), it must not be "
    rf"present in any occurrence of (?:sub)?sequence\s+(?P<seqb>{SEQ})",
)
FLAG_FORBIDS_SEQUENCE = re.compile(
    rf"^If the [^()]*\(field\s+{_f('a')}\) in (?:sub)?sequence\s+(?P<seqa>{SEQ})[^,]*? is "
    rf"(?P<code>{CODE}), then (?:sub)?sequence\s+(?P<seqb>{SEQ}) must not be present",
)
DEPENDENCY_TABLE = re.compile(
    SCOPE
    + r"[Tt]he presence of (?P<what>(?:the )?(?:sub)?sequence\s+(?P<tseq>"
    + SEQ
    + rf")|fields?\s+(?P<tlist>{_LIST_FIELD.pattern}(?:\s*(?:,|and|or)\s*{_LIST_FIELD.pattern})*))"
    rf"(?:\s+in\s+(?:sub)?sequence\s+(?P<tin>{SEQ}))?\s+depends on the "
    rf"(?P<on>value|presence) of fields?\s+{_f('a')}"
    rf"(?:\s+in\s+(?:sub)?sequence\s+(?P<aseq>{SEQ}))?\s+as follows\s*(?:\([^)]*\))?\s*:",
)
#: One row of a dependency table, after the header lines: ``NEWT Mandatory``,
#: ``Not present Not allowed``, ``Present Optional``, ``Any other value Optional``.
TABLE_ROW = re.compile(
    rf"(?P<left>Not equal to {CODES}|Any other value|Otherwise|Not present|Present|{CODES})\s+"
    r"(?P<right>Mandatory|Optional|Not allowed|Not present|Present)\b"
)
ENVELOPE_DEPENDENT = re.compile(
    r"Sender's and the Receiver's BICs|user header of the message|block 3\b|field 119|"
    r"Validation Flag|Receiver's BIC|Sender's BIC|service identifier|Block 2|block 2\b",
)
ARITHMETIC = re.compile(
    r"must (?:be )?equal the sum|sum of the amounts|the total of|must be (?:greater|less) than the amount",
)
UNIQUE_WITHIN_OCCURRENCE = re.compile(
    r"^The following (?:amount|party|[a-z]+) fields(?: for (?:sub)?sequences? [^:]*?)? cannot appear "
    rf"more than once in (?:the same occurrence of |each occurrence of )?(?:\(sub\))?(?:sub)?sequence\s+(?P<scope>{SEQ})"
)
PREVIOUS_REFERENCE_ONCE = re.compile(
    rf"^A reference to the previously received message must be specified, that is,? field\s+{_f('a')}\s+"
    rf"must be present in one and only one occurrence of (?:sub)?sequence\s+(?P<scope>{SEQ})"
)
MANDATORY_IN_OPTIONAL_SEQUENCE = re.compile(
    r"^In all optional sequences(?: and sub-?sequences)?, the fields with status M must be "
    r"present if the sequence(?: or sub-?sequence)? is present,? and are otherwise not allowed",
)

NUMBER_WORDS = {
    "once": 1,
    "twice": 2,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "fifty": 50,
    "hundred": 100,
}


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _tag(raw: str) -> str:
    """``60a`` stays generic (the guide's ``a`` means any option); ``32b`` is option B."""
    return raw[:2] + (raw[2:] if raw[2:] == "a" else raw[2:].upper())


def _number(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return NUMBER_WORDS.get(word.lower())


def _codes(text: str) -> tuple[str, ...]:
    return tuple(
        item.upper()
        for item in re.split(r"\s*(?:,|\bor\b|\band\b)\s*", text.strip(), flags=re.IGNORECASE)
        if item
    )


def _fields_in(text: str) -> list[tuple[str, str | None]]:
    return [(tag, qualifier) for tag, qualifier in _LIST_FIELD.findall(text)]


def _ref(
    structure: MrgStructure,
    match: re.Match[str],
    name: str,
    sequence_path: str | None,
) -> RuleReference | None:
    groups = match.groupdict()
    tag = groups.get(f"{name}tag")
    if tag is None:
        return None
    return resolve_reference(
        structure,
        tag=_tag(tag),
        qualifier=groups.get(f"{name}qualifier"),
        value=groups.get(f"{name}value"),
        sequence_path=sequence_path,
    )


def _scope_of(match: re.Match[str], structure: MrgStructure) -> tuple[str | None, bool]:
    """``(sequence path the sentence names, whether it speaks per occurrence)``."""
    groups = match.groupdict()
    scope = groups.get("scope")
    if scope is None and groups.get("therep"):
        # "the repetitive sequence": the guide names none, so the table must declare one.
        repetitive = [item.path for item in structure.sequences if item.repetitive]
        scope = repetitive[0] if len(repetitive) == 1 else None
    if scope is None:
        return None, False
    if groups.get("scopelist"):
        return scope, bool(groups.get("each"))  # several sequences: the first one anchors
    sequence = structure.sequence(scope)
    per_occurrence = bool(groups.get("each")) or bool(sequence is not None and sequence.repetitive)
    return scope, per_occurrence


def _scoped(
    structure: MrgStructure,
    scope: str | None,
    per_occurrence: bool,
    assertion: Expression,
    references: tuple[RuleReference, ...],
) -> tuple[Expression, tuple[str, ...]]:
    """Wrap in ``forEachOccurrence`` when the sentence is per occurrence of a repeating
    sequence and every reference sits inside it; record why when it cannot."""
    if scope is None:
        return assertion, ()
    sequence = structure.sequence(scope)
    if sequence is None or not sequence.repetitive:
        return assertion, ()
    if all(_inside(ref.sequence_path, scope) for ref in references):
        return _for_each(scope, assertion), ()
    return assertion, (
        f"The guide scopes this rule to each occurrence of {scope}; a field it names sits "
        "outside that sequence, so the rule is read message-wide.",
    )


def _inside(path: str, scope: str) -> bool:
    return path == scope or path.startswith(scope)


def _all_resolved(*references: RuleReference | None) -> tuple[RuleReference, ...]:
    return tuple(item for item in references if item is not None)


def _unsupported(
    template_name: str, reason: UnsupportedReason, detail: str, references: tuple[RuleReference, ...] = ()
) -> TemplateMatch:
    return TemplateMatch(
        template=template_name,
        when=None,
        assertion=Predicate(field=_placeholder(), operator=Operator.EXISTS),
        references=references,
        interpretation="",
        fidelity=RuleFidelity.UNSUPPORTED,
        residual=(detail,),
        reason=reason,
    )


def _placeholder() -> FieldRef:
    """A reference for a TemplateMatch that carries no expression (a refusal, or a rule
    the structure enforces): never compiled, never evaluated."""
    return FieldRef(format=MessageFormat.MT, sequence_path=ROOT_SEQUENCE, tag="20")


def _rows_for(structure: MrgStructure, reference: RuleReference) -> list[MrgFieldRow]:
    return [
        row
        for row in structure.rows_in(reference.sequence_path)
        if row.field_number == reference.field_number
    ]


def _notations_for(structure: MrgStructure, reference: RuleReference) -> set[str]:
    """Every format notation the guide states for the field the reference names: the
    Field Specification's FORMAT block per option first, the table's content column as
    the fallback for a guide whose specification the reader could not place."""
    found: set[str] = set()
    rows = _rows_for(structure, reference)
    for row in rows:
        options = [letter for letter in row.options] if row.options else [row.option or ""]
        wanted = [
            option
            for option in options
            if reference.option is None or option.upper() == reference.option
        ]
        for spec in structure.field_specs:
            if spec.sequence_path != reference.sequence_path or spec.tag[:2] != row.field_number:
                continue
            for option, notation in spec.formats:
                if option.upper() in {item.upper() for item in wanted}:
                    found.add(notation)
    if not found:
        for row in rows:
            if not row.options and row.content:
                found.add(row.content)
    return found


def _extraction(structure: MrgStructure, reference: RuleReference, component: str) -> Extraction | None:
    """The component's extraction for one field, when every option states one pattern."""
    patterns = {component_pattern(notation, component) for notation in _notations_for(structure, reference)}
    patterns.discard(None)
    if len(patterns) != 1:
        return None
    (pattern,) = patterns
    assert pattern is not None  # noqa: S101 - None discarded above
    return Extraction(pattern=pattern, group="value")


def _mandatory_row(structure: MrgStructure, sequence_path: str) -> RuleReference | None:
    """The first value-carrying mandatory row of a sequence: its presence *is* the
    sequence's presence, which is how a rule about a sequence becomes one about a field."""
    for row in structure.rows_in(sequence_path):
        if row.tag in {"16R", "16S"} or row.status.value != "M":
            continue
        return resolve_reference(
            structure, tag=row.tag, qualifier=row.qualifier, sequence_path=sequence_path
        )
    return None


def _other_fields(structure: MrgStructure, sequence_path: str, *exclude: RuleReference) -> list[RuleReference]:
    skip = {(item.sequence_path, item.field_number) for item in exclude}
    found: list[RuleReference] = []
    seen: set[str] = set()
    for row in structure.rows_in(sequence_path):
        if row.tag in {"16R", "16S"} or (sequence_path, row.field_number) in skip:
            continue
        if row.field_number in seen:
            continue
        seen.add(row.field_number)
        found.append(
            resolve_reference(structure, tag=row.tag, qualifier=row.qualifier, sequence_path=sequence_path)
        )
    return found


def _option_row_refs(structure: MrgStructure, reference: RuleReference, option: str) -> RuleReference:
    return resolve_reference(
        structure,
        tag=f"{reference.field_number}{option}",
        qualifier=reference.qualifier,
        sequence_path=reference.sequence_path,
    )


def _other_option_refs(structure: MrgStructure, reference: RuleReference, keep: str) -> list[RuleReference]:
    letters: set[str] = set()
    for row in _rows_for(structure, reference):
        letters.update(letter for letter in row.options if letter)
        if not row.options and row.option:
            letters.add(row.option)
    return [_option_row_refs(structure, reference, letter) for letter in sorted(letters - {keep})]


def _condition(match: re.Match[str], a: RuleReference) -> tuple[Expression | None, str, str]:
    """The condition predicate, its plain reading, and a residual where the value form
    forces a weaker reading."""
    groups = match.groupdict()
    cond = (groups.get("cond") or "").lower()
    if cond in {"is present", "is used"}:
        if a.value:
            return _equals(a, a.value), f"{_name(a)} is {a.value}", ""
        return _exists(a), f"{_name(a)} is present", ""
    if cond in {"is not present", "is absent", "is not used"}:
        if a.value:
            return (
                Predicate(field=a.field_ref(), operator=Operator.NOT_EQUALS, value=a.value),
                f"{_name(a)} is not {a.value}",
                "",
            )
        return _absent(a), f"{_name(a)} is absent", ""
    value = groups.get("val") or groups.get("val2") or groups.get("code")
    if value:
        return _equals(a, value.upper()), f"{_name(a)} is {value.upper()}", ""
    codes = groups.get("codes") or groups.get("codes2")
    if codes:
        listed = _codes(codes.upper())
        return (
            Predicate(field=a.field_ref(), operator=Operator.IN, values=listed),
            f"{_name(a)} is one of {', '.join(listed)}",
            "",
        )
    notcode = groups.get("notcode")
    if notcode:
        return (
            Predicate(field=a.field_ref(), operator=Operator.NOT_EQUALS, value=notcode.upper()),
            f"{_name(a)} is not {notcode.upper()}",
            "",
        )
    return None, "", ""


def _consequence(
    match: re.Match[str], structure: MrgStructure, b: RuleReference
) -> tuple[Expression | None, str, tuple[RuleReference, ...]]:
    groups = match.groupdict()
    cons = (groups.get("cons") or "").lower()
    if cons in {"is mandatory", "must be present", "must also be present", "is required"}:
        if b.value:
            return _equals(b, b.value), f"{_name(b)} must be {b.value}", ()
        return _exists(b), f"{_name(b)} must be present", ()
    if cons in {"is not allowed", "must not be present", "must not be used", "may not be present"}:
        return _absent(b), f"{_name(b)} must not be present", ()
    if cons == "is optional":
        return None, "", ()
    if groups.get("optno"):
        ref = _option_row_refs(structure, b, groups["optno"].upper())
        return _absent(ref), f"{_name(ref)} must not be used", (ref,)
    if groups.get("optonly") or groups.get("optmust"):
        keep = (groups.get("optonly") or groups.get("optmust") or "").upper()
        others = _other_option_refs(structure, b, keep)
        if not others:
            return None, "", ()
        return (
            _all(tuple(_absent(item) for item in others)),
            f"{_name(b)} may be used with option {keep} only",
            tuple(others),
        )
    if groups.get("allowed"):
        listed = _codes(groups["allowed"].upper())
        return (
            Predicate(field=b.field_ref(), operator=Operator.IN, values=listed),
            f"{_name(b)} may contain only {', '.join(listed)}",
            (),
        )
    if groups.get("mustcode"):
        return _equals(b, groups["mustcode"].upper()), f"{_name(b)} must be {groups['mustcode'].upper()}", ()
    if groups.get("notallowed"):
        code = groups["notallowed"].upper()
        return (
            Predicate(field=b.field_ref(), operator=Operator.NOT_EQUALS, value=code),
            f"{_name(b)} must not be {code}",
            (),
        )
    return None, "", ()


def _otherwise(match: re.Match[str], b: RuleReference) -> Expression | None:
    other = (match.groupdict().get("other") or "").lower()
    if other in {"is not allowed", "must not be present", "may not be present"}:
        return _absent(b)
    if other in {"is mandatory", "must be present"}:
        return _exists(b)
    return None


# --------------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------------


def _build_unique_within_occurrence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    """Each listed field at most once *within one occurrence* of the named sequence."""
    from app.rule_engine.mt_mrg.templates import _all_fields

    scope = match.group("scope")
    # The listed party fields sit in the scope's own subsequences ("Subsequence B2b2
    # :95a::…"), so each resolves through its qualifier table and must land inside the scope.
    references = _all_fields(rule.text[match.end() :], structure, None)
    if not references:
        return None
    outside = [item for item in references if item.resolved and not _inside(item.sequence_path, scope)]
    if outside:
        return _unsupported(
            "FIELDS_UNIQUE_WITHIN_OCCURRENCE",
            UnsupportedReason.REFERENCE_NOT_RESOLVED,
            f"{', '.join(_name(item) for item in outside)} resolve(s) outside {scope}.",
            tuple(references),
        )
    node = _all(tuple(_count(item, Operator.LESS_OR_EQUAL, 1) for item in references))
    sequence = structure.sequence(scope)
    assertion = _for_each(scope, node) if sequence is not None and sequence.repetitive else node
    return TemplateMatch(
        template="FIELDS_UNIQUE_WITHIN_OCCURRENCE",
        when=None,
        assertion=assertion,
        references=tuple(references),
        interpretation=(
            f"Each of {len(references)} listed fields appears at most once in an occurrence of {scope}."
        ),
    )


def _build_previous_reference_once(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope = match.group("scope")
    a = _ref(structure, match, "a", scope)
    if a is None:
        return None
    return TemplateMatch(
        template="PREVIOUS_REFERENCE_EXACTLY_ONCE",
        when=None,
        assertion=_count(a, Operator.EQUALS, 1),
        references=(a,),
        interpretation=f"{_name(a)} is present in exactly one occurrence of {scope}.",
    )


def _build_envelope_dependent(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    del structure
    return _unsupported(
        "ENVELOPE_DEPENDENT",
        UnsupportedReason.ENVELOPE_DEPENDENT,
        "The rule turns on Block 1, 2 or 3 of the FIN envelope (the BICs, the user header, "
        "the validation flag); a Block 4 rule engine cannot read it.",
    )


def _build_arithmetic(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    del structure
    return _unsupported(
        "ARITHMETIC_RELATION",
        UnsupportedReason.ARITHMETIC_NOT_MODELLED,
        "The rule relates amounts arithmetically (a sum or a total); the DSL compares "
        "values, it does not add them.",
    )


def _build_mandatory_in_optional_sequence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    """Already what the structure validator enforces: a present sequence carries its
    mandatory rows. Exact, with no expression of its own."""
    del structure
    return TemplateMatch(
        template="MANDATORY_FIELDS_IN_OPTIONAL_SEQUENCE",
        when=None,
        assertion=Predicate(field=_placeholder(), operator=Operator.EXISTS),
        references=(),
        interpretation=(
            "A present optional sequence carries every field the table marks M — the "
            "structure validator enforces this on every message."
        ),
        fidelity=RuleFidelity.EXACT,
        residual=("ENFORCED_BY_STRUCTURE",),
    )


def _build_conditional_general(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    groups = match.groupdict()
    a = _ref(structure, match, "a", groups.get("aseq") or scope)
    b = _ref(structure, match, "b", groups.get("bseq") or groups.get("bseq0") or scope)
    if a is None or b is None:
        return None
    condition, reading, _ = _condition(match, a)
    consequence, reading_b, extra_refs = _consequence(match, structure, b)
    if condition is None:
        return None
    references = _all_resolved(a, b, *extra_refs)
    parts: list[Expression] = []
    if consequence is not None:
        parts.append(_implies(condition, consequence))
    reverse = _otherwise(match, b)
    if reverse is not None:
        parts.append(_implies(Not(not_=condition), reverse))
    if not parts:
        return None
    assertion, residual = _scoped(structure, scope, per_occurrence, _all(tuple(parts)), references)
    interpretation = f"If {reading}, then {reading_b or 'nothing further'}."
    if reverse is not None:
        interpretation += " Otherwise the reverse applies."
    listed = groups.get("scopelist")
    if listed:
        residual = (
            *residual,
            f"The guide states this for sequences {scope}{listed}; the reading binds the "
            f"first, {scope}, only.",
        )
    return TemplateMatch(
        template="CONDITIONAL_PRESENCE_GENERAL",
        when=None,
        assertion=assertion,
        references=references,
        interpretation=interpretation,
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _build_either_or(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    a = _ref(structure, match, "a", scope)
    b = _ref(structure, match, "b", scope)
    if a is None or b is None:
        return None
    references = (a, b)
    both = bool(match.group("both"))
    must = match.group("mode").lower() == "must"
    if both and must:
        node: Expression = ExactlyOne(exactly_one=(a.field_ref(), b.field_ref()))
        reading = "exactly one of"
    elif both:
        node = AtMostOne(at_most_one=(a.field_ref(), b.field_ref()))
        reading = "at most one of"
    elif must:
        node = AtLeastOne(at_least_one=(a.field_ref(), b.field_ref()))
        reading = "at least one of"
    else:
        return None  # "either may be present" constrains nothing
    assertion, residual = _scoped(structure, scope, per_occurrence, node, references)
    return TemplateMatch(
        template="EITHER_OR",
        when=None,
        assertion=assertion,
        references=references,
        interpretation=f"{reading.capitalize()} {_name(a)} and {_name(b)} is present.",
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _build_both_or_neither(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    a = _ref(structure, match, "a", scope)
    b = _ref(structure, match, "b", scope)
    if a is None or b is None:
        return None
    node = _all((_implies(_exists(a), _exists(b)), _implies(_exists(b), _exists(a))))
    assertion, residual = _scoped(structure, scope, per_occurrence, node, (a, b))
    return TemplateMatch(
        template="BOTH_OR_NEITHER",
        when=None,
        assertion=assertion,
        references=(a, b),
        interpretation=f"{_name(a)} and {_name(b)} are present together or not at all.",
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _build_count_limit(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    limit = _number(match.group("limit"))
    if limit is None:
        return None
    references: list[RuleReference] = []
    for tag, qualifier in _fields_in(match.group("list")):
        references.append(
            resolve_reference(structure, tag=_tag(tag), qualifier=qualifier or None, sequence_path=scope)
        )
    if not references:
        return None
    node = _all(tuple(_count(ref, Operator.LESS_OR_EQUAL, limit) for ref in references))
    assertion, residual = _scoped(structure, scope, per_occurrence, node, tuple(references))
    return TemplateMatch(
        template="COUNT_LIMIT",
        when=None,
        assertion=assertion,
        references=tuple(references),
        interpretation=(
            f"{', '.join(_name(ref) for ref in references)} appear(s) at most {limit} time(s)"
            + (f" in each occurrence of {scope}" if per_occurrence and scope else "")
            + "."
        ),
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _build_sequence_count(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope = match.group("scope")
    if scope is None:
        repetitive = [item for item in structure.sequences if item.repetitive]
        if len(repetitive) != 1:
            return _unsupported(
                "SEQUENCE_COUNT",
                UnsupportedReason.REFERENCE_AMBIGUOUS,
                "The rule speaks of 'the repetitive sequence' and the table declares "
                f"{len(repetitive)} repetitive sequences.",
            )
        scope = repetitive[0].path
    anchor = _mandatory_row(structure, scope)
    if anchor is None or not anchor.resolved:
        return _unsupported(
            "SEQUENCE_COUNT",
            UnsupportedReason.REFERENCE_NOT_RESOLVED,
            f"Sequence {scope} has no mandatory field whose count could stand for the "
            "sequence's.",
        )
    parts: list[Expression] = []
    at_most = _number(match.group("atmost") or "")
    at_least = _number(match.group("atleast") or "") if match.group("atleast") else None
    if at_most is not None:
        parts.append(_count(anchor, Operator.LESS_OR_EQUAL, at_most))
    if at_least is not None:
        parts.append(_count(anchor, Operator.GREATER_OR_EQUAL, at_least))
    if not parts:
        return None
    return TemplateMatch(
        template="SEQUENCE_COUNT",
        when=None,
        assertion=_all(tuple(parts)),
        references=(anchor,),
        interpretation=(
            f"Sequence {scope} occurs "
            + (f"at least {at_least} and " if at_least else "")
            + f"at most {at_most} times, counted through its mandatory {_name(anchor)}."
        ),
    )


def _build_not_only_field(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    groups = match.groupdict()
    sequence = groups.get("oseq") or groups.get("oseq2") or scope
    if sequence is None:
        return None
    subjects: list[RuleReference] = []
    for name in ("a", "x", "c", "d"):
        ref = _ref(structure, match, name, sequence)
        if ref is not None and not any(
            item.field_number == ref.field_number and item.qualifier == ref.qualifier for item in subjects
        ):
            subjects.append(ref)
    if not subjects:
        return None
    others = _other_fields(structure, sequence, *subjects)
    if not others:
        return None
    node = _all(
        tuple(
            _implies(_exists(ref), AtLeastOne(at_least_one=tuple(item.field_ref() for item in others)))
            for ref in subjects
        )
    )
    references = (*subjects, *others)
    assertion, residual = _scoped(structure, sequence, per_occurrence, node, references)
    return TemplateMatch(
        template="NOT_THE_ONLY_FIELD",
        when=None,
        assertion=assertion,
        references=references,
        interpretation=(
            f"{', '.join(_name(ref) for ref in subjects)} may not be the only field(s) present in {sequence}."
        ),
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _build_currency_same(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequences = [item.strip() for item in re.split(r"\s*(?:,|and)\s*", match.group("seqs") or "") if item.strip()]
    members: list[ComponentRef] = []
    references: list[RuleReference] = []
    for tag, qualifier in _fields_in(match.group("list")):
        targets = sequences or [None]
        for sequence in targets:
            ref = resolve_reference(structure, tag=_tag(tag), qualifier=qualifier or None, sequence_path=sequence)
            references.append(ref)
            if not ref.resolved:
                continue
            extraction = _extraction(structure, ref, "CURRENCY")
            if extraction is None:
                return _unsupported(
                    "CURRENCY_CONSISTENT",
                    UnsupportedReason.COMPONENT_SCOPE_NOT_EXPRESSIBLE,
                    f"The format of {_name(ref)} does not state one currency component the "
                    "reader can extract.",
                    tuple(references),
                )
            if match.group("first"):
                extraction = Extraction(
                    pattern=extraction.pattern.replace("(?P<value>[A-Z]{3})", "(?P<value>[A-Z]{2})"),
                    group="value",
                )
            members.append(ComponentRef(field=ref.field_ref(), extract=extraction))
    if not members:
        return None
    what = "first two characters of the currency" if match.group("first") else "currency"
    return TemplateMatch(
        template="CURRENCY_CONSISTENT",
        when=None,
        assertion=AllEqual(all_equal=tuple(members)),
        references=tuple(references),
        interpretation=(
            f"The {what} is the same in every present value of "
            f"{', '.join(_name(ref) for ref in references)}."
        ),
    )


def _build_currency_different_condition(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    a = _ref(structure, match, "a", None)
    b = _ref(structure, match, "b", None)
    c = _ref(structure, match, "c", None)
    if a is None or b is None or c is None:
        return None
    references = (a, b, c)
    if not all(item.resolved for item in references):
        return TemplateMatch(
            template="CURRENCY_DIFFERENCE_CONDITION",
            when=None,
            assertion=_exists(c),
            references=references,
            interpretation="",
        )
    extract_a = _extraction(structure, a, "CURRENCY")
    extract_b = _extraction(structure, b, "CURRENCY")
    if extract_a is None or extract_b is None:
        return _unsupported(
            "CURRENCY_DIFFERENCE_CONDITION",
            UnsupportedReason.COMPONENT_SCOPE_NOT_EXPRESSIBLE,
            "The formats do not state one currency component the reader can extract.",
            references,
        )
    differ = Predicate(
        field=a.field_ref(),
        operator=Operator.NOT_EQUALS,
        other_field=b.field_ref(),
        extract=extract_a,
        other_extract=extract_b,
    )
    condition = _all((_exists(a), differ))
    assertion = _all((_implies(condition, _exists(c)), _implies(Not(not_=condition), _absent(c))))
    return TemplateMatch(
        template="CURRENCY_DIFFERENCE_CONDITION",
        when=None,
        assertion=assertion,
        references=references,
        interpretation=(
            f"{_name(c)} is present exactly when {_name(a)} is present with a currency other "
            f"than the one in {_name(b)}."
        ),
    )


def _build_exchange_rate_general(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, _per = _scope_of(match, structure)
    a = _ref(structure, match, "a", scope)
    b = _ref(structure, match, "b", scope)
    if a is None or b is None:
        return None
    parts: list[Expression] = [_implies(_exists(a), _exists(b))]
    if match.group("reverse"):
        parts.append(_implies(_absent(a), _absent(b)))
    node = _all(tuple(parts))
    sequence = structure.sequence(a.sequence_path) if a.resolved else None
    assertion = _for_each(a.sequence_path, node) if sequence is not None and sequence.repetitive else node
    return TemplateMatch(
        template="EXCHANGE_RATE_REQUIRES_RESULTING_AMOUNT",
        when=None,
        assertion=assertion,
        references=(a, b),
        interpretation=f"Where {_name(a)} is present, {_name(b)} is present in the same occurrence.",
    )


def _build_cancellation_general(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    fn = _ref(structure, match, "fn", None)
    scope = match.group("scope")
    a = _ref(structure, match, "a", scope)
    if fn is None or a is None:
        return None
    codes = tuple(code for code in (match.group("code"), match.group("code2")) if code)
    pattern = "|".join(codes) + r"(/[A-Z0-9]{1,4})?"
    condition = Predicate(field=fn.field_ref(), operator=Operator.MATCHES, value=pattern)
    sequence = structure.sequence(a.sequence_path) if a.resolved else None
    if sequence is not None and sequence.repetitive:
        consequence: Expression = Predicate(
            field=a.field_ref(), operator=Operator.EQUALS, subject=Subject.COUNT, value="1"
        )
        reading = f"{_name(a)} is present in exactly one occurrence of {a.sequence_path}"
    else:
        consequence = _exists(a)
        reading = f"{_name(a)} is present"
    return TemplateMatch(
        template="CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE",
        when=None,
        assertion=_implies(condition, consequence),
        references=(fn, a),
        interpretation=f"When {_name(fn)} is {' or '.join(codes)}, {reading}.",
    )


def _build_respective_sequence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    sequences = [item.strip() for item in re.split(r"\s*(?:,|and)\s*", match.group("seqs")) if item.strip()]
    parts: list[Expression] = []
    references: list[RuleReference] = []
    skipped: list[str] = []
    for sequence in sequences:
        a = _ref(structure, match, "a", sequence)
        b = _ref(structure, match, "b", sequence)
        if a is None or b is None:
            return None
        if not a.resolved or not b.resolved:
            # "In the respective sequence": where a listed sequence does not carry the
            # field, the condition cannot arise there and the sequence is left out.
            skipped.append(sequence)
            continue
        references.extend((a, b))
        node = _implies(_equals(a, match.group("code").upper()), _exists(b))
        spec = structure.sequence(sequence)
        parts.append(_for_each(sequence, node) if spec is not None and spec.repetitive else node)
    if not parts:
        return _unsupported(
            "CODE_REQUIRES_FIELD_IN_RESPECTIVE_SEQUENCE",
            UnsupportedReason.REFERENCE_NOT_RESOLVED,
            f"None of {', '.join(sequences)} carries both fields the rule names.",
        )
    return TemplateMatch(
        template="CODE_REQUIRES_FIELD_IN_RESPECTIVE_SEQUENCE",
        when=None,
        assertion=_all(tuple(parts)),
        references=tuple(references),
        interpretation=(
            f"In each of {', '.join(item for item in sequences if item not in skipped)}, a value "
            f"{match.group('code').upper()} requires the companion field in the same sequence."
        ),
    )


def _build_absent_forbids_codes(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    a = _ref(structure, match, "a", None)
    b = _ref(structure, match, "b", None)
    if a is None or b is None:
        return None
    codes = _codes(match.group("codes").upper())
    return TemplateMatch(
        template="ABSENT_FIELD_FORBIDS_CODES",
        when=None,
        assertion=_implies(
            _absent(a), Predicate(field=b.field_ref(), operator=Operator.NOT_IN, values=codes)
        ),
        references=(a, b),
        interpretation=f"Without {_name(a)}, {_name(b)} is not {', '.join(codes)}.",
    )


def _build_present_in_one_not_other(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    a = _ref(structure, match, "a", match.group("seqa"))
    groups = match.groupdict()
    b = resolve_reference(
        structure,
        tag=_tag(groups["atag"]),
        qualifier=groups.get("aqualifier"),
        sequence_path=match.group("seqb"),
    )
    if a is None:
        return None
    return TemplateMatch(
        template="PRESENT_IN_ONE_SEQUENCE_NOT_ANOTHER",
        when=None,
        assertion=_implies(_exists(a), _absent(b)),
        references=(a, b),
        interpretation=f"{_name(a)} and {_name(b)} are not both present.",
    )


def _build_flag_forbids_sequence(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    a = _ref(structure, match, "a", match.group("seqa"))
    anchor = _mandatory_row(structure, match.group("seqb"))
    if a is None:
        return None
    if anchor is None:
        return _unsupported(
            "FLAG_FORBIDS_SEQUENCE",
            UnsupportedReason.REFERENCE_NOT_RESOLVED,
            f"Sequence {match.group('seqb')} has no mandatory field whose absence could stand "
            "for the sequence's.",
            (a,),
        )
    return TemplateMatch(
        template="FLAG_FORBIDS_SEQUENCE",
        when=None,
        assertion=_implies(_equals(a, match.group("code").upper()), _absent(anchor)),
        references=(a, anchor),
        interpretation=(
            f"When {_name(a)} is {match.group('code').upper()}, sequence {match.group('seqb')} "
            f"is absent (read through its mandatory {_name(anchor)})."
        ),
    )


def _table_rows(rule: MrgSourceRule) -> tuple[list[tuple[str, str]], int]:
    """``(parsed rows, table words left unread)``.

    The PDF text runs the table's cells together on one line ("AMND Mandatory CANC
    Mandatory NEWT Optional"), so rows are read as a token stream after the header cells
    ("if field 22A is ... then field 21 is ...") rather than line by line.
    """
    text = " ".join(rule.text.split())
    anchor = text.find("as follows")
    if anchor < 0:
        return [], 0
    tail = text[anchor:]
    colon = tail.find(":")
    tail = tail[colon + 1 :] if colon >= 0 else ""
    # Header cells end with "is ..." — everything up to the last one is the header.
    header_end = max((m.end() for m in re.finditer(r"\bis\s*\.\.\.", tail)), default=0)
    body = tail[header_end:]
    rows = [(m.group("left"), m.group("right")) for m in TABLE_ROW.finditer(body)]
    covered = sum(m.end() - m.start() for m in TABLE_ROW.finditer(body))
    unread = len(body.split()) - sum(len(left.split()) + len(right.split()) for left, right in rows)
    del covered
    return rows, max(unread, 0)


def _build_dependency_table(
    match: re.Match[str], rule: MrgSourceRule, structure: MrgStructure
) -> TemplateMatch | None:
    scope, per_occurrence = _scope_of(match, structure)
    groups = match.groupdict()
    a = _ref(structure, match, "a", groups.get("aseq") or scope)
    if a is None:
        return None
    targets: list[RuleReference] = []
    if groups.get("tseq"):
        anchor = _mandatory_row(structure, groups["tseq"])
        if anchor is None:
            return _unsupported(
                "DEPENDENCY_TABLE",
                UnsupportedReason.REFERENCE_NOT_RESOLVED,
                f"Sequence {groups['tseq']} has no mandatory field whose presence could stand "
                "for the sequence's.",
                (a,),
            )
        targets.append(anchor)
    else:
        for tag, qualifier in _fields_in(groups.get("tlist") or ""):
            targets.append(
                resolve_reference(
                    structure,
                    tag=_tag(tag),
                    qualifier=qualifier or None,
                    sequence_path=groups.get("tin") or scope,
                )
            )
    if not targets:
        return None
    rows, unread = _table_rows(rule)
    if not rows:
        return _unsupported(
            "DEPENDENCY_TABLE",
            UnsupportedReason.TABLE_NOT_READ,
            "The dependency table that follows the sentence could not be read as rows.",
            (a, *targets),
        )
    on_value = (groups.get("on") or "").lower() == "value"
    parts: list[Expression] = []
    listed_codes: list[str] = []
    deferred: list[str] = []
    for left, right in rows:
        consequence = _table_consequence(right, targets)
        left_key = left.strip()
        if on_value:
            if re.match(r"^(Any other value|Other(?:wise)?|Not equal to)", left_key, re.IGNORECASE):
                deferred.append(right)
                continue
            codes = _codes(left_key.upper())
            listed_codes.extend(codes)
            condition: Expression = (
                _equals(a, codes[0])
                if len(codes) == 1
                else Predicate(field=a.field_ref(), operator=Operator.IN, values=codes)
            )
        else:
            if left_key.lower() == "present":
                condition = _exists(a)
            elif left_key.lower() == "not present":
                condition = _absent(a)
            else:
                deferred.append(right)
                continue
        if consequence is not None:
            parts.append(_implies(condition, consequence))
    for right in deferred:
        consequence = _table_consequence(right, targets)
        if consequence is None or not listed_codes:
            continue
        parts.append(
            _implies(
                Predicate(field=a.field_ref(), operator=Operator.NOT_IN, values=tuple(dict.fromkeys(listed_codes))),
                consequence,
            )
        )
    if not parts:
        return TemplateMatch(
            template="DEPENDENCY_TABLE",
            when=None,
            assertion=_exists(a),
            references=(a, *targets),
            interpretation="Every row of the table reads 'optional': the table constrains nothing.",
            fidelity=RuleFidelity.EXACT,
            residual=("TABLE_CONSTRAINS_NOTHING",),
        )
    references = (a, *targets)
    assertion, residual = _scoped(structure, scope, per_occurrence, _all(tuple(parts)), references)
    if unread:
        residual = (
            *residual,
            f"{unread} word(s) of the dependency table could not be read as rows and are "
            "not represented.",
        )
    return TemplateMatch(
        template="DEPENDENCY_TABLE",
        when=None,
        assertion=assertion,
        references=references,
        interpretation=(
            f"The presence of {', '.join(_name(t) for t in targets)} follows the table keyed on "
            f"{_name(a)} ({len(rows)} row(s))."
        ),
        fidelity=RuleFidelity.PARTIAL if residual else RuleFidelity.EXACT,
        residual=residual,
    )


def _table_consequence(right: str, targets: list[RuleReference]) -> Expression | None:
    word = right.lower()
    if word in {"mandatory", "present"}:
        return _all(tuple(_exists(item) for item in targets))
    if word in {"not allowed", "not present"}:
        return _all(tuple(_absent(item) for item in targets))
    return None


Builder = Callable[[re.Match[str], MrgSourceRule, MrgStructure], TemplateMatch | None]

#: Order: refusals first (an envelope rule may also contain "if field … is present"), then
#: the specific shapes, then the general conditional, which would otherwise swallow them.
GENERIC_TEMPLATES: tuple[tuple[str, re.Pattern[str], Builder], ...] = (
    ("ENVELOPE_DEPENDENT", ENVELOPE_DEPENDENT, _build_envelope_dependent),
    ("ARITHMETIC_RELATION", ARITHMETIC, _build_arithmetic),
    ("FIELDS_UNIQUE_WITHIN_OCCURRENCE", UNIQUE_WITHIN_OCCURRENCE, _build_unique_within_occurrence),
    ("PREVIOUS_REFERENCE_EXACTLY_ONCE", PREVIOUS_REFERENCE_ONCE, _build_previous_reference_once),
    (
        "MANDATORY_FIELDS_IN_OPTIONAL_SEQUENCE",
        MANDATORY_IN_OPTIONAL_SEQUENCE,
        _build_mandatory_in_optional_sequence,
    ),
    ("CURRENCY_DIFFERENCE_CONDITION", CURRENCY_DIFFERENT_CONDITION, _build_currency_different_condition),
    ("CURRENCY_CONSISTENT", CURRENCY_SAME, _build_currency_same),
    ("EXCHANGE_RATE_REQUIRES_RESULTING_AMOUNT", EXCHANGE_RATE_GENERAL, _build_exchange_rate_general),
    ("CANCELLATION_REQUIRES_ONE_PREVIOUS_REFERENCE", CANCELLATION_GENERAL, _build_cancellation_general),
    ("CODE_REQUIRES_FIELD_IN_RESPECTIVE_SEQUENCE", RESPECTIVE_SEQUENCE, _build_respective_sequence),
    ("ABSENT_FIELD_FORBIDS_CODES", ABSENT_FORBIDS_CODES, _build_absent_forbids_codes),
    ("PRESENT_IN_ONE_SEQUENCE_NOT_ANOTHER", PRESENT_IN_ONE_NOT_OTHER, _build_present_in_one_not_other),
    ("FLAG_FORBIDS_SEQUENCE", FLAG_FORBIDS_SEQUENCE, _build_flag_forbids_sequence),
    ("DEPENDENCY_TABLE", DEPENDENCY_TABLE, _build_dependency_table),
    ("SEQUENCE_COUNT", SEQUENCE_COUNT, _build_sequence_count),
    ("COUNT_LIMIT", COUNT_LIMIT, _build_count_limit),
    ("NOT_THE_ONLY_FIELD", NOT_ONLY_FIELD, _build_not_only_field),
    ("EITHER_OR", EITHER_OR, _build_either_or),
    ("BOTH_OR_NEITHER", BOTH_OR_NEITHER, _build_both_or_neither),
    ("CONDITIONAL_PRESENCE_GENERAL", CONDITIONAL_GENERAL, _build_conditional_general),
)

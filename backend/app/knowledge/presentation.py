"""Which control a field deserves, decided once.

The browser used to work this out for itself, from a heuristic over whether one of the
field's examples happened to appear in its code list. That put a UI rule in React, and it
got it wrong in both directions: a quantity such as ``UNIT/1000`` became a free-text box
because ``UNIT`` is only the prefix of the value, and any value outside the list silently
downgraded a dropdown back to a text input.

The answer is already in the specification. ISO 15022 encodes it in the tag and the field
option — a ``98a`` is a date, a ``95P`` is a BIC, a ``95R`` is a scheme plus an identifier —
so it is derived from those rather than restated per record. Configuration still owns the
*codes*; this owns only the *control*, and a knowledge record may override it.

Deriving it here rather than in each YAML file also removes a whole class of defect: a
per-record ``inputKind`` is copied by a YAML merge key onto every field that inherits from
it, which is how a payment date once came to declare the code list of a voluntary-event
indicator.
"""

from __future__ import annotations

from app.knowledge.models import InputKind

#: Tags whose value is a controlled code taken directly from the row's code list, with
#: nothing else in the field. Shared with the composer and the MT validator so "is this a
#: code field?" has one answer.
DIRECT_CODE_TAG_PREFIXES = frozenset({"11", "17", "22", "23", "24", "25"})

#: Tags whose value is ``<code>/<number>`` — the code is a prefix, not the whole value.
QUANTITY_TAGS = frozenset({"36B", "93B"})

#: Tags whose value is a currency and an amount.
AMOUNT_TAGS = frozenset({"19A", "19B"})

NARRATIVE_TAGS = frozenset({"70D", "70E"})

#: ``28E`` is a page number and a continuation code joined by a slash, so its code list
#: describes part of the value rather than all of it.
COMPOSITE_TAGS = frozenset({"28E"})


def derive_input_kind(
    tag: str,
    *,
    allowed_codes: list[str],
    literal_prefix: str | None = None,
    identifier_types: list[str] | None = None,
) -> InputKind:
    """The control for one field, from its tag, its option and whether it carries codes."""
    option = tag[-1] if tag else ""
    family = tag[:2]

    if literal_prefix or identifier_types:
        return InputKind.IDENTIFIER
    if family == "95":
        return InputKind.PARTY_BIC if option == "P" else InputKind.PARTY_PROPRIETARY
    if tag in QUANTITY_TAGS:
        return InputKind.QUANTITY
    if tag in AMOUNT_TAGS:
        return InputKind.AMOUNT
    if tag in NARRATIVE_TAGS:
        return InputKind.NARRATIVE
    if tag in COMPOSITE_TAGS:
        return InputKind.TEXT
    if family == "98":
        return InputKind.DATE
    if family == "20":
        return InputKind.REFERENCE
    if family == "17":
        return InputKind.INDICATOR
    if allowed_codes:
        return InputKind.SELECT
    return InputKind.TEXT


def choice_key(choice_group: str | None) -> str | None:
    """The business value a field option belongs to, or None if the field stands alone.

    ``SETTLEMENT-E-DEAG/95P`` and ``SETTLEMENT-E-DEAG/95R`` are the BIC and the proprietary
    forms of one delivering agent, so both resolve to ``SETTLEMENT-E-DEAG``. Requiring the
    group rather than each member is what stops a form demanding a party twice.
    """
    if not choice_group:
        return None
    return choice_group.rsplit("/", 1)[0]


#: Field options whose SWIFT format carries a *mandatory* data source scheme —
#: ``:4!c/8c/34x`` — and therefore a single slash after the qualifier. Every other qualified
#: field writes ``:QUAL//``. A format fact (the same class of fact as the per-tag format
#: table in the composer), recorded once so the composer and the parser agree.
MANDATORY_DATA_SOURCE_SCHEME_TAGS = frozenset({"95R", "95S"})


def qualifier_separator_for(tag: str) -> str:
    return "/" if tag in MANDATORY_DATA_SOURCE_SCHEME_TAGS else "//"


def is_direct_code_field(tag: str, allowed_codes: list[str]) -> bool:
    """Whether the whole value must be one of the configured codes."""
    return bool(allowed_codes) and tag[:2] in DIRECT_CODE_TAG_PREFIXES


__all__ = [
    "AMOUNT_TAGS",
    "COMPOSITE_TAGS",
    "DIRECT_CODE_TAG_PREFIXES",
    "NARRATIVE_TAGS",
    "QUANTITY_TAGS",
    "choice_key",
    "derive_input_kind",
    "is_direct_code_field",
]

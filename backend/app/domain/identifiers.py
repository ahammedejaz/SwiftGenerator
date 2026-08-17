"""Deterministic identifier normalisation and verification.

One module, no model call, no network lookup. Every entry point — the browser, the JSON
API, Excel and MT import — reaches an identifier through here, so "what counts as a valid
ISIN" cannot be answered differently on two screens.

Two claims are kept apart on purpose, because they are different claims:

``FORMAT_VALID``
    The value has the shape ISO 15022 field 35B requires of a ``4!c//12!c`` identifier —
    twelve characters, two leading letters, a numeric final character. This is a **SWIFT
    field-format** statement.

``CHECK_DIGIT_VALID``
    The final character is the modulus-10 check digit ISO 6166 derives from the other
    eleven. This is an **identifier-quality** statement about the ISIN itself. The FIN
    network does not compute it, so collapsing it into the format verdict would claim a
    field-format rule that does not exist.

Neither says the identifier has been *assigned*. A value that satisfies both is
``STRUCTURALLY_VALID_SYNTHETIC``; ``REGISTERED_REAL_IDENTIFIER`` needs a national numbering
agency directory, which this repository does not have and does not pretend to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

#: The literal that field 35B carries in front of the identifier. The composer writes it;
#: the caller never types it. Kept here rather than in the composer so normalisation and
#: rendering cannot drift apart.
ISIN_LITERAL = "ISIN"

ISIN_LENGTH = 12

#: Two country/prefix letters, nine alphanumerics, one numeric check digit.
ISIN_SHAPE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

#: 4 alpha institution, 2 alpha country, 2 alphanumeric location, optional 3 alphanumeric
#: branch. The registered-BIC question is separate and is not answered here.
BIC_SHAPE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")

#: Option R is ``<data source scheme>/<proprietary identifier>``. Requiring the scheme is
#: what stops a BIC being written into the proprietary field, which is the mistake the
#: field exists to make impossible.
PROPRIETARY_PARTY_SHAPE = re.compile(r"^[A-Z0-9]{1,8}/[A-Z0-9./\-]{1,34}$")

_LEADING_ISIN = re.compile(r"^ISIN[\s:]+", re.IGNORECASE)


class IdentifierAssurance(StrEnum):
    """How much is actually known about an identifier. Never inflated."""

    #: Satisfies the format and the check digit. Nothing more is claimed.
    STRUCTURALLY_VALID_SYNTHETIC = "STRUCTURALLY_VALID_SYNTHETIC"
    #: Confirmed against a national numbering agency directory. No code path produces this.
    REGISTERED_REAL_IDENTIFIER = "REGISTERED_REAL_IDENTIFIER"


class IsinProblem(StrEnum):
    """Exactly what is wrong, so the message can say it rather than describe a regex."""

    EMPTY = "EMPTY"
    LENGTH = "LENGTH"
    PREFIX_NOT_ALPHABETIC = "PREFIX_NOT_ALPHABETIC"
    INVALID_CHARACTER = "INVALID_CHARACTER"
    CHECK_DIGIT_NOT_NUMERIC = "CHECK_DIGIT_NOT_NUMERIC"
    CHECK_DIGIT_MISMATCH = "CHECK_DIGIT_MISMATCH"


@dataclass(frozen=True)
class IsinVerdict:
    value: str
    format_valid: bool
    check_digit_valid: bool
    problem: IsinProblem | None = None
    #: The digit ISO 6166 derives, when the value is well-shaped enough to derive one.
    expected_check_digit: str | None = None

    @property
    def assurance(self) -> IdentifierAssurance | None:
        if self.format_valid and self.check_digit_valid:
            return IdentifierAssurance.STRUCTURALLY_VALID_SYNTHETIC
        return None


def normalise_isin(raw: str) -> str:
    """Turn whatever was typed or pasted into the canonical bare identifier.

    Accepts ``xs0000000009``, ``  XS0000000009  ``, ``ISIN XS0000000009`` and
    ``ISIN: XS0000000009``. Only presentation is changed — spacing, case and the field's own
    literal. The identifier characters are never rewritten, so a wrong ISIN stays wrong and
    is reported rather than quietly repaired.
    """
    candidate = raw.strip().upper()
    candidate = _LEADING_ISIN.sub("", candidate, count=1).strip()
    return "".join(candidate.split())


def isin_check_digit(body: str) -> str:
    """The ISO 6166 modulus-10 check digit for the first eleven characters.

    Letters become their two-digit ordinal (``A``=10 … ``Z``=35), the digit string is read
    from the right doubling every second digit, and digits above nine have nine subtracted.
    """
    expanded = "".join(str(ord(item) - 55) if item.isalpha() else item for item in body.upper())
    if not expanded.isdigit():
        raise ValueError("An ISIN body may hold only letters and digits")
    total = 0
    for index, character in enumerate(reversed(expanded)):
        digit = int(character)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def validate_isin(value: str) -> IsinVerdict:
    """Verify a **canonical** identifier. Call :func:`normalise_isin` first."""
    candidate = value.strip()
    if not candidate:
        return IsinVerdict(candidate, False, False, IsinProblem.EMPTY)
    if len(candidate) != ISIN_LENGTH:
        return IsinVerdict(candidate, False, False, IsinProblem.LENGTH)
    if not candidate[:2].isalpha() or not candidate[:2].isupper():
        return IsinVerdict(candidate, False, False, IsinProblem.PREFIX_NOT_ALPHABETIC)
    if not candidate[11].isdigit():
        # Reported ahead of the general character check because it is the specific mistake
        # a tester makes — pasting an identifier that is not an ISIN at all.
        return IsinVerdict(candidate, False, False, IsinProblem.CHECK_DIGIT_NOT_NUMERIC)
    if not ISIN_SHAPE.fullmatch(candidate):
        return IsinVerdict(candidate, False, False, IsinProblem.INVALID_CHARACTER)
    expected = isin_check_digit(candidate[:11])
    if expected != candidate[11]:
        return IsinVerdict(
            candidate, True, False, IsinProblem.CHECK_DIGIT_MISMATCH, expected_check_digit=expected
        )
    return IsinVerdict(candidate, True, True, None, expected_check_digit=expected)


def synthetic_isin(body: str) -> str:
    """Complete an eleven-character body into a checksum-valid synthetic identifier.

    For tests and samples. The result satisfies ISO 6166 arithmetic and nothing else — it is
    not registered, and no caller may present it as though it were.
    """
    candidate = body.strip().upper()
    if len(candidate) != ISIN_LENGTH - 1 or not candidate[:2].isalpha():
        raise ValueError("An ISIN body is two letters followed by nine alphanumerics")
    if not all(character.isalnum() for character in candidate):
        raise ValueError("An ISIN body may hold only letters and digits")
    return candidate + isin_check_digit(candidate)


def normalise_bic(raw: str) -> str:
    return "".join(raw.strip().upper().split())


def bic_format_valid(value: str) -> bool:
    """Whether the value has a BIC's shape. Says nothing about registration."""
    return BIC_SHAPE.fullmatch(value.strip()) is not None


def proprietary_party_valid(value: str) -> bool:
    """Whether an option-R value names its data source scheme."""
    return PROPRIETARY_PARTY_SHAPE.fullmatch(value.strip()) is not None


__all__ = [
    "BIC_SHAPE",
    "ISIN_LENGTH",
    "ISIN_LITERAL",
    "ISIN_SHAPE",
    "IdentifierAssurance",
    "IsinProblem",
    "IsinVerdict",
    "bic_format_valid",
    "isin_check_digit",
    "normalise_bic",
    "normalise_isin",
    "proprietary_party_valid",
    "synthetic_isin",
    "validate_isin",
]

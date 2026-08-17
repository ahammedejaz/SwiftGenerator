"""The deterministic identifier utility.

Two verdicts are kept apart on purpose — shape is an ISO 15022 field-format question, the
check digit is an ISO 6166 identifier-quality one — so both are asserted separately.
"""

from __future__ import annotations

import pytest

from app.domain.identifiers import (
    IdentifierAssurance,
    IsinProblem,
    bic_format_valid,
    isin_check_digit,
    normalise_bic,
    normalise_isin,
    proprietary_party_valid,
    synthetic_isin,
    validate_isin,
)

# -- normalisation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entered", "canonical"),
    [
        ("XS0000000009", "XS0000000009"),
        ("  XS0000000009  ", "XS0000000009"),
        ("xs0000000009", "XS0000000009"),
        ("xS0000000009", "XS0000000009"),
        # The field's own literal is the composer's to write. A tester who pastes a whole
        # rendered field must not end up with it twice.
        ("ISIN XS0000000009", "XS0000000009"),
        ("isin xs0000000009", "XS0000000009"),
        ("ISIN  XS0000000009", "XS0000000009"),
        ("ISIN: XS0000000009", "XS0000000009"),
        ("XS 0000 0000 09", "XS0000000009"),
    ],
)
def test_presentation_is_normalised_but_the_identifier_is_not_rewritten(
    entered: str, canonical: str
) -> None:
    assert normalise_isin(entered) == canonical


def test_normalising_a_wrong_identifier_leaves_it_wrong() -> None:
    """Only spacing, case and the literal are touched — never the identifier itself.

    Silently repairing a check digit would hide the mistake the tester needs to see.
    """
    assert normalise_isin("ISIN us9897778abc") == "US9897778ABC"
    assert validate_isin(normalise_isin("ISIN us9897778abc")).format_valid is False


def test_the_prefix_is_stripped_once_so_a_double_prefix_survives_as_an_error() -> None:
    assert normalise_isin("ISIN ISIN XS0000000009") == "ISINXS0000000009"


# -- format ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ("", IsinProblem.EMPTY),
        ("XS000000000", IsinProblem.LENGTH),
        ("XS00000000099", IsinProblem.LENGTH),
        ("1S0000000009", IsinProblem.PREFIX_NOT_ALPHABETIC),
        ("XS00000-00009"[:12], IsinProblem.INVALID_CHARACTER),
        # The tester's original value: the final character is a letter, so it cannot be a
        # check digit at all.
        ("US9897778ABC", IsinProblem.CHECK_DIGIT_NOT_NUMERIC),
    ],
)
def test_each_way_an_identifier_can_be_malformed_is_named(
    value: str, problem: IsinProblem
) -> None:
    verdict = validate_isin(value)

    assert verdict.format_valid is False
    assert verdict.problem is problem


def test_the_reported_message_reproduces_the_users_message() -> None:
    """The exact value from the reported defect, rejected for the exact right reason."""
    verdict = validate_isin("US9897778ABC")

    assert verdict.problem is IsinProblem.CHECK_DIGIT_NOT_NUMERIC
    assert verdict.check_digit_valid is False


# -- check digit -----------------------------------------------------------------------


def test_check_digit_follows_iso_6166() -> None:
    assert isin_check_digit("XS000000000") == "9"
    assert isin_check_digit("US912828U81"[:11]) == isin_check_digit("US912828U81")


def test_a_well_shaped_identifier_can_still_fail_the_check_digit() -> None:
    """The distinction the two layers exist for.

    ``XS0000000001`` satisfies the ISO 15022 field format for 35B — twelve characters, two
    leading letters, a numeric final character — and fails ISO 6166. It was this
    repository's own sample value until this change.
    """
    verdict = validate_isin("XS0000000001")

    assert verdict.format_valid is True
    assert verdict.check_digit_valid is False
    assert verdict.expected_check_digit == "9"


def test_a_valid_identifier_passes_both_and_claims_only_what_is_known() -> None:
    verdict = validate_isin("XS0000000009")

    assert verdict.format_valid is True
    assert verdict.check_digit_valid is True
    # Structurally valid. Never "registered": no numbering-agency directory is integrated.
    assert verdict.assurance is IdentifierAssurance.STRUCTURALLY_VALID_SYNTHETIC


def test_no_code_path_can_claim_an_identifier_is_registered() -> None:
    assert validate_isin("XS0000000009").assurance is not (
        IdentifierAssurance.REGISTERED_REAL_IDENTIFIER
    )


# -- synthetic helper ------------------------------------------------------------------


def test_the_test_helper_produces_checksum_valid_values() -> None:
    for body in ["XS000000000", "GB000000000", "US000000000", "DE000000000"]:
        candidate = synthetic_isin(body)

        assert len(candidate) == 12
        assert validate_isin(candidate).check_digit_valid is True


def test_the_helper_refuses_a_body_it_cannot_complete() -> None:
    with pytest.raises(ValueError):
        synthetic_isin("XS00000000")
    with pytest.raises(ValueError):
        synthetic_isin("00000000000")


# -- parties ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["DEMOGB2LXXX", "DEMOGB2L", "ZZZZUS00XXX"])
def test_a_well_shaped_bic_is_accepted(value: str) -> None:
    assert bic_format_valid(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "DEMOGB2",  # too short
        "DEMOGB2LXX",  # ten characters is neither 8 nor 11
        "DEMOGB2LXXXX",  # too long
        "DEM0GB2LXXX",  # a digit in the institution code
        "CSD/DEMOPSET01",  # a proprietary value, not a BIC
    ],
)
def test_a_malformed_bic_is_rejected(value: str) -> None:
    assert bic_format_valid(value) is False


def test_bic_normalisation_is_presentation_only() -> None:
    assert normalise_bic(" demogb2lxxx ") == "DEMOGB2LXXX"


@pytest.mark.parametrize("value", ["CSD/DEMOPSET01", "AGT/DEMODEAG01", "BFSDEMO1/SYNTHPARTY"])
def test_a_proprietary_party_names_its_data_source_scheme(value: str) -> None:
    assert proprietary_party_valid(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # The value from the reported defect: a BIC written into the proprietary field.
        "MGTHMEXXX",
        "BEBE76XXX",
        "/DEMOPSET01",
        "CSD/",
    ],
)
def test_a_proprietary_party_without_a_scheme_is_rejected(value: str) -> None:
    assert proprietary_party_valid(value) is False

"""The FIN envelope must be real, and must refuse to invent what it does not know."""

from __future__ import annotations

import pytest

from app.profiles.loader import ClientProfile, profiles
from app.studio.models import EnvelopeOverride, FieldOrigin
from app.studio.mt.fin import (
    FORBIDDEN_TRAILER_TAGS,
    FinEnvelopeUnavailable,
    build_fin_message,
    envelope_availability,
)

BLOCK_4 = "{4:\n:16R:GENL\n:20C::SEME//TESTREF001\n:16S:GENL\n-}"


@pytest.fixture
def profile() -> ClientProfile:
    return profiles.get("BASE_DEMO_V1")


def _without_fin(profile: ClientProfile) -> ClientProfile:
    return profile.model_copy(update={"fin_envelope": None})


def _without(profile: ClientProfile, **updates: object) -> ClientProfile:
    assert profile.fin_envelope is not None
    return profile.model_copy(
        update={"fin_envelope": profile.fin_envelope.model_copy(update=updates)}
    )


def test_builds_the_expected_block_structure(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    assert message.text.startswith("{1:F01DEMOGB2LAXXX0001000001}\n")
    assert "{2:I541DEMOUS33XXXXN}" in message.text
    assert message.text.endswith("-}")


def test_block_1_is_exactly_25_characters(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    block_1 = message.text.splitlines()[0]
    # {1: + F + 01 + 12-char LT + 4-digit session + 6-digit sequence + }
    assert len(block_1) == len("{1:") + 1 + 2 + 12 + 4 + 6 + len("}")


def test_no_demonstration_placeholder_survives(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    assert "DEMONSTRATION" not in message.text
    assert "{2:MT541}" not in message.text


def test_message_type_digits_come_from_the_message_type(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT548", block_4=BLOCK_4, profile=profile)

    assert "{2:I548" in message.text


def test_block_3_appears_only_with_a_message_user_reference(profile: ClientProfile) -> None:
    without = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)
    with_mur = build_fin_message(
        message_type="MT541",
        block_4=BLOCK_4,
        profile=profile,
        override=EnvelopeOverride(message_user_reference="MUR000001"),
    )

    assert "{3:" not in without.text
    assert "{3:{108:MUR000001}}" in with_mur.text


def test_block_5_is_not_emitted_without_configured_trailers(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    assert "{5:" not in message.text
    trailer = next(item for item in message.fields if item.block == "5")
    assert trailer.value is None
    assert trailer.origin is FieldOrigin.NETWORK_GENERATED


@pytest.mark.parametrize("tag", sorted(FORBIDDEN_TRAILER_TAGS))
def test_network_generated_trailers_are_refused(profile: ClientProfile, tag: str) -> None:
    configured = _without(profile, trailer_fields={tag: "0123456789ABCDEF"})

    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=configured)

    assert "{5:" not in message.text
    assert any(item.rule_id == "FIN_TRAILER_NOT_GENERATED" for item in message.warnings)


def test_permitted_trailer_is_emitted(profile: ClientProfile) -> None:
    configured = _without(profile, trailer_fields={"MRF": "2609011200260901120001"})

    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=configured)

    assert message.text.endswith("{5:{MRF:2609011200260901120001}}")


def test_missing_session_number_fails_closed(profile: ClientProfile) -> None:
    configured = _without(profile, session_number=None)

    with pytest.raises(FinEnvelopeUnavailable) as raised:
        build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=configured)

    codes = {issue.rule_id for issue in raised.value.issues}
    assert "FIN_SESSION_NUMBER_NOT_SUPPLIED" in codes


def test_missing_sequence_number_fails_closed(profile: ClientProfile) -> None:
    configured = _without(profile, sequence_number=None)

    with pytest.raises(FinEnvelopeUnavailable) as raised:
        build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=configured)

    assert {issue.rule_id for issue in raised.value.issues} == {
        "FIN_SEQUENCE_NUMBER_NOT_SUPPLIED"
    }


def test_a_request_may_supply_the_interface_values(profile: ClientProfile) -> None:
    configured = _without(profile, session_number=None, sequence_number=None)

    message = build_fin_message(
        message_type="MT541",
        block_4=BLOCK_4,
        profile=configured,
        override=EnvelopeOverride(session_number="4321", sequence_number="000099"),
    )

    assert message.text.startswith("{1:F01DEMOGB2LAXXX4321000099}")
    session = next(item for item in message.fields if item.name == "Session number")
    assert session.origin is FieldOrigin.USER_ENTERED


def test_profile_without_an_envelope_cannot_produce_fin(profile: ClientProfile) -> None:
    bare = _without_fin(profile)

    with pytest.raises(FinEnvelopeUnavailable):
        build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=bare)
    assert envelope_availability(bare)[0].rule_id == "FIN_ENVELOPE_NOT_CONFIGURED"


def test_a_configured_profile_reports_no_blockers(profile: ClientProfile) -> None:
    assert envelope_availability(profile) == []


def test_invalid_addresses_are_rejected(profile: ClientProfile) -> None:
    with pytest.raises(FinEnvelopeUnavailable) as raised:
        build_fin_message(
            message_type="MT541",
            block_4=BLOCK_4,
            profile=profile,
            override=EnvelopeOverride(sender="TOOSHORT"),
        )

    assert {issue.rule_id for issue in raised.value.issues} == {"FIN_SENDER_INVALID"}


def test_every_emitted_value_is_classified(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    assert all(isinstance(item.origin, FieldOrigin) for item in message.fields)
    # Nothing the platform emits may claim to be a network-generated value.
    emitted_network = [
        item
        for item in message.fields
        if item.origin is FieldOrigin.NETWORK_GENERATED and item.value is not None
    ]
    assert emitted_network == []


def test_line_breaks_are_preserved_for_downstream_use(profile: ClientProfile) -> None:
    message = build_fin_message(message_type="MT541", block_4=BLOCK_4, profile=profile)

    assert "\r" not in message.text
    assert message.text.count("\n") == BLOCK_4.count("\n") + 2

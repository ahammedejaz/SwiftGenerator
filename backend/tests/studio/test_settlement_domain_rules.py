"""The settlement domain corrections, asserted per message rather than per example.

Three rules are under test, and each was previously wrong in a way a tester could see:

* ``22F::SETR`` carries the *type* of settlement transaction, once, in Settlement Details.
  It never carries a direction, because the message type carries that.
* A receive instruction names the chain that **delivers**; a delivery names the chain that
  **receives**. The other chain stays available, but is not required.
* The ``ISIN`` literal belongs to the composer. A caller supplies the identifier alone.

Every one of these is reconciled against this repository's own ISO 20022 definition of the
same business message, ``config/mx/sese.023.001.11.yaml``.
"""

from __future__ import annotations

import pytest

from app.domain.enums import MessageType
from app.knowledge.models import PresenceRule
from app.specifications.registry import specification_registry
from app.studio.models import (
    FieldInput,
    GenerateRequest,
    InputKind,
    MessageFormat,
    Presence,
    SampleVariant,
)
from app.studio.samples import build_sample
from app.studio.service import studio_service

#: A receive instruction or its confirmation. The delivering agent is the counterparty.
RECEIVE_MESSAGES = ["MT540", "MT541", "MT544", "MT545"]
#: A delivery or its confirmation. The receiving agent is the counterparty.
DELIVER_MESSAGES = ["MT542", "MT543", "MT546", "MT547"]
#: Against payment, so a cash leg is carried.
AGAINST_PAYMENT = ["MT541", "MT543", "MT545", "MT547"]
#: Free of payment, so no cash leg exists in the configured subset at all.
FREE_OF_PAYMENT = ["MT540", "MT542", "MT544", "MT546"]
INSTRUCTIONS = ["MT540", "MT541", "MT542", "MT543"]


def typical(message_type: str) -> str:
    sample = build_sample(MessageFormat.MT, message_type, SampleVariant.TYPICAL)
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT,
            message_type=message_type,
            fields=list(sample.inputs),
            persist=False,
        )
    )
    assert result.valid, [item.message for item in result.validation.errors]
    return result.outputs.block4 or ""


def rows(message_type: str):  # type: ignore[no-untyped-def]
    return specification_registry.get(MessageType(message_type)).fields


def presence_of(message_type: str, tag: str, qualifier: str) -> PresenceRule:
    return next(
        item.presence
        for item in rows(message_type)
        if item.tag == tag and item.qualifier == qualifier
    )


# -- 22F::SETR --------------------------------------------------------------------------


@pytest.mark.parametrize("message_type", INSTRUCTIONS)
def test_settlement_transaction_type_is_configured_once_and_only_in_settlement_details(
    message_type: str,
) -> None:
    setr = [item for item in rows(message_type) if item.qualifier == "SETR"]

    assert len(setr) == 1
    assert setr[0].sequence_code == "SETDET"


@pytest.mark.parametrize("message_type", INSTRUCTIONS)
def test_a_generated_instruction_carries_exactly_one_setr(message_type: str) -> None:
    block4 = typical(message_type)

    assert block4.count(":22F::SETR//") == 1


@pytest.mark.parametrize("message_type", INSTRUCTIONS)
def test_an_ordinary_trade_settles_as_trad(message_type: str) -> None:
    assert ":22F::SETR//TRAD" in typical(message_type)


@pytest.mark.parametrize("message_type", INSTRUCTIONS)
@pytest.mark.parametrize("code", ["BUY", "SELL", "RECE", "DELI"])
def test_direction_and_buy_sell_are_not_settlement_transaction_types(
    message_type: str, code: str
) -> None:
    """The four codes the studio used to emit are now refused, by name.

    ``RECE``/``DELI`` state a securities movement — sese.023 carries them in
    ``SctiesMvmntTp`` — and ``BUY``/``SELL`` are not a settlement transaction type at all.
    """
    sample = build_sample(MessageFormat.MT, message_type, SampleVariant.TYPICAL)
    fields = [
        item.model_copy(update={"value": code}) if item.qualifier == "SETR" else item
        for item in sample.inputs
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type=message_type, fields=fields, persist=False
        )
    )

    assert not result.valid
    issue = next(
        item for item in result.validation.errors if item.rule_id == "MT_CODE_NOT_ALLOWED"
    )
    # The error carries the words, not just the codes, so a beginner can choose.
    assert "TRAD (Trade)" in (issue.expected or "")


@pytest.mark.parametrize("message_type", INSTRUCTIONS)
def test_trade_details_no_longer_accepts_a_transaction_type(message_type: str) -> None:
    sample = build_sample(MessageFormat.MT, message_type, SampleVariant.TYPICAL)
    fields = [
        *sample.inputs,
        FieldInput(sequence="TRADDET", tag="22F", qualifier="SETR", value="TRAD"),
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type=message_type, fields=fields, persist=False
        )
    )

    assert any(item.rule_id == "MT_UNKNOWN_FIELD" for item in result.validation.errors)


def test_the_mt_and_mx_transaction_type_vocabularies_are_the_same_list() -> None:
    """One code list, two formats. Reading the same configuration is what guarantees it."""
    from app.studio.catalogue import message_spec

    mt = next(
        item
        for item in message_spec(MessageFormat.MT, "MT541").fields
        if item.qualifier == "SETR"
    )
    mx = next(
        item
        for item in message_spec(MessageFormat.MX, "sese.023").fields
        if item.business_path == "trade.transactionType"
    )

    assert mt.allowed_codes == mx.allowed_codes
    assert [item.label for item in mt.allowed_values] == [
        item.label for item in mx.allowed_values
    ]


# -- settlement parties -----------------------------------------------------------------


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES)
def test_a_receive_message_requires_the_delivering_agent(message_type: str) -> None:
    assert presence_of(message_type, "95P", "DEAG") is PresenceRule.MANDATORY
    assert presence_of(message_type, "95R", "DEAG") is PresenceRule.MANDATORY


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES)
def test_a_receive_message_does_not_require_the_receiving_agent(message_type: str) -> None:
    """Not forbidden — sese.023 marks both chains conditional — but not another core field."""
    assert presence_of(message_type, "95P", "REAG") is PresenceRule.OPTIONAL
    assert presence_of(message_type, "95R", "REAG") is PresenceRule.OPTIONAL


@pytest.mark.parametrize("message_type", DELIVER_MESSAGES)
def test_a_deliver_message_requires_the_receiving_agent(message_type: str) -> None:
    assert presence_of(message_type, "95P", "REAG") is PresenceRule.MANDATORY
    assert presence_of(message_type, "95R", "REAG") is PresenceRule.MANDATORY


@pytest.mark.parametrize("message_type", DELIVER_MESSAGES)
def test_a_deliver_message_does_not_require_the_delivering_agent(message_type: str) -> None:
    assert presence_of(message_type, "95P", "DEAG") is PresenceRule.OPTIONAL
    assert presence_of(message_type, "95R", "DEAG") is PresenceRule.OPTIONAL


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES)
def test_a_receive_sample_names_the_delivering_side_and_the_place_of_settlement(
    message_type: str,
) -> None:
    block4 = typical(message_type)

    assert "::DEAG//" in block4
    assert "::PSET//" in block4
    assert "::REAG//" not in block4


@pytest.mark.parametrize("message_type", DELIVER_MESSAGES)
def test_a_deliver_sample_names_the_receiving_side_and_the_place_of_settlement(
    message_type: str,
) -> None:
    block4 = typical(message_type)

    assert "::REAG//" in block4
    assert "::PSET//" in block4
    assert "::DEAG//" not in block4


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES + DELIVER_MESSAGES)
def test_the_additional_chain_stays_available_rather_than_being_removed(
    message_type: str,
) -> None:
    """A settlement chain the message does not require is still a field it may carry."""
    from app.studio.catalogue import message_spec

    spec = message_spec(MessageFormat.MT, message_type)
    optional_agents = [
        item
        for item in spec.fields
        if item.qualifier in {"DEAG", "REAG"} and item.presence is Presence.OPTIONAL
    ]

    assert optional_agents


# -- party identification option --------------------------------------------------------


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES + DELIVER_MESSAGES)
@pytest.mark.parametrize("qualifier", ["PSET", "DEAG", "REAG"])
def test_every_party_offers_a_bic_form_and_a_proprietary_form(
    message_type: str, qualifier: str
) -> None:
    from app.studio.catalogue import message_spec

    options = {
        item.tag: item
        for item in message_spec(MessageFormat.MT, message_type).fields
        if item.qualifier == qualifier
    }

    assert set(options) == {"95P", "95R"}
    assert options["95P"].input_kind is InputKind.PARTY_BIC
    assert options["95R"].input_kind is InputKind.PARTY_PROPRIETARY
    # Two field options for one business party, so exactly one of them is needed.
    assert options["95P"].choice_group != options["95R"].choice_group
    assert options["95P"].choice_group.rsplit("/", 1)[0] == (
        options["95R"].choice_group.rsplit("/", 1)[0]
    )


@pytest.mark.parametrize("message_type", RECEIVE_MESSAGES + DELIVER_MESSAGES)
def test_a_sample_identifies_its_parties_by_bic(message_type: str) -> None:
    assert ":95P::" in typical(message_type)


def test_the_proprietary_option_refuses_a_bic() -> None:
    """The exact mistake the reported message made, now named.

    ``:95R::DEAG/MGTHMEXXX`` writes a BIC into the proprietary field, which has no data
    source scheme to say what the code means.
    """
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        item
        for item in sample.inputs
        if item.qualifier != "DEAG"
    ] + [FieldInput(sequence="SETDET", tag="95R", qualifier="DEAG", value="MGTHMEXXX")]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )

    issue = next(
        item
        for item in result.validation.errors
        if item.rule_id == "MT_FORMAT_INVALID" and item.location == "MT541-E-95R-DEAG"
    )
    assert "data source scheme" in (issue.expected or "").lower()


def test_the_bic_option_refuses_a_proprietary_value() -> None:
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        item.model_copy(update={"value": "CSD/DEMODEAG01"})
        if item.qualifier == "DEAG"
        else item
        for item in sample.inputs
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )

    assert any(
        item.location == "MT541-E-95P-DEAG" for item in result.validation.errors
    )


def test_identifying_one_party_in_two_ways_is_refused() -> None:
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        *sample.inputs,
        FieldInput(sequence="SETDET", tag="95R", qualifier="DEAG", value="AGT/DEMODEAG01"),
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )

    issue = next(
        item
        for item in result.validation.errors
        if item.rule_id == "MT_FIELD_OPTION_CONFLICT"
    )
    # The error is in business words, not option letters.
    assert "BIC" in (issue.expected or "")
    assert "proprietary identifier" in (issue.expected or "")


def test_either_party_option_satisfies_the_requirement_on_its_own() -> None:
    """Neither option is individually mandatory; the business party is."""
    sample = build_sample(MessageFormat.MT, "MT541", SampleVariant.TYPICAL)
    fields = [
        item.model_copy(
            update={
                "id": "MT541-E-95R-DEAG",
                "tag": "95R",
                "option": "R",
                "value": "AGT/DEMODEAG01",
            }
        )
        if item.qualifier == "DEAG"
        else item
        for item in sample.inputs
    ]

    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MT, message_type="MT541", fields=fields, persist=False
        )
    )

    assert result.valid, [item.message for item in result.validation.errors]
    assert ":95R::DEAG/AGT/DEMODEAG01" in (result.outputs.block4 or "")


# -- free of payment --------------------------------------------------------------------


@pytest.mark.parametrize("message_type", FREE_OF_PAYMENT)
def test_a_free_of_payment_message_has_no_cash_field_to_ask_for(message_type: str) -> None:
    """The form cannot ask for a settlement amount, because the message has no such field.

    Better than validating it away afterwards: the question is never put.
    """
    amount_rows = [
        item for item in rows(message_type) if item.tag in {"19A", "19B"}
    ]

    assert amount_rows == []
    assert ":19A::" not in typical(message_type)


@pytest.mark.parametrize("message_type", AGAINST_PAYMENT)
def test_an_against_payment_message_carries_a_cash_leg(message_type: str) -> None:
    assert ":19A::" in typical(message_type)

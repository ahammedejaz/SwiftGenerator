"""MX composition, namespaces, ordering, choices, XSD and AppHdr consistency."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from app.profiles.loader import ClientProfile, profiles
from app.studio.models import (
    ElementInput,
    EnvelopeOverride,
    GenerateRequest,
    MessageFormat,
    OutputMode,
    SampleVariant,
    ValidationLayer,
)
from app.studio.mx.generator import MxEnvelopeUnavailable, check_well_formed, mx_generator
from app.studio.mx.registry import mx_registry
from app.studio.mx.xsd import SchemaSource, derive_schema, validate_document
from app.studio.samples import build_sample
from app.studio.service import studio_service

ROOT = "/Document/SctiesSttlmTxInstr"
APPHDR_NS = "urn:iso:std:iso:20022:tech:xsd:head.001.001.03"


@pytest.fixture
def profile() -> ClientProfile:
    return profiles.get("BASE_DEMO_V1")


@pytest.fixture
def sese023_elements() -> list[ElementInput]:
    return list(build_sample(MessageFormat.MX, "sese.023", SampleVariant.TYPICAL).elements)


def generate(message_type: str, elements: list[ElementInput]):  # type: ignore[no-untyped-def]
    return studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MX,
            message_type=message_type,
            elements=elements,
            persist=False,
        )
    )


def replace(elements: list[ElementInput], suffix: str, value: str) -> list[ElementInput]:
    return [
        ElementInput(path=item.path, occurrence=item.occurrence, value=value)
        if item.path.endswith(suffix)
        else item
        for item in elements
    ]


def drop(elements: list[ElementInput], fragment: str) -> list[ElementInput]:
    return [item for item in elements if fragment not in item.path]


# -- structure -------------------------------------------------------------------------


def test_document_uses_the_versioned_namespace(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    assert result.outputs.document is not None
    root = ElementTree.fromstring(result.outputs.document)
    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:sese.023.001.11}Document"


def test_mx_never_emits_fin_blocks(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    combined = (result.outputs.xml or "") + (result.outputs.document or "")
    assert "{1:" not in combined
    assert "{4:" not in combined
    assert result.outputs.fin is None
    assert result.outputs.block4 is None


def test_elements_are_written_in_specification_order(
    sese023_elements: list[ElementInput],
) -> None:
    # Shuffle the inputs; document order must still follow the specification.
    result = generate("sese.023", list(reversed(sese023_elements)))

    assert result.outputs.document is not None
    text = result.outputs.document
    assert text.index("<TxId>") < text.index("<SttlmTpAndAddtlParams>")
    assert text.index("<SttlmTpAndAddtlParams>") < text.index("<TradDtls>")
    assert text.index("<TradDtls>") < text.index("<FinInstrmId>")
    assert text.index("<FinInstrmId>") < text.index("<QtyAndAcctDtls>")
    assert text.index("<QtyAndAcctDtls>") < text.index("<SttlmAmt>")


def test_nested_and_repeated_paths_resolve_to_distinct_elements() -> None:
    paths = {item.path for item in mx_registry.leaves("sese.023")}

    assert f"{ROOT}/TradDtls/TradDt/Dt/Dt" in paths
    assert f"{ROOT}/TradDtls/SttlmDt/Dt/Dt" in paths


def test_amount_currency_becomes_an_attribute(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    assert result.outputs.document is not None
    assert '<Amt Ccy="USD">25000.00</Amt>' in result.outputs.document


def test_xml_escaping_is_applied() -> None:
    elements = build_sample(MessageFormat.MX, "sese.023", SampleVariant.FULL).elements
    with_markup = replace(list(elements), "/FinInstrmId/Desc", "A & B <TEST> BOND")

    result = generate("sese.023", with_markup)

    assert result.outputs.document is not None
    assert "A &amp; B &lt;TEST&gt; BOND" in result.outputs.document
    assert check_well_formed(result.outputs.document) is None


def test_repeatable_element_accepts_multiple_occurrences(
    sese023_elements: list[ElementInput],
) -> None:
    path = f"{ROOT}/SttlmParams/SttlmTxCond/Cd"
    elements = [
        *sese023_elements,
        ElementInput(path=path, occurrence=1, value="NOMC"),
        ElementInput(path=path, occurrence=2, value="PART"),
    ]

    result = generate("sese.023", elements)

    assert result.valid, [item.message for item in result.validation.errors]
    assert result.outputs.document is not None
    assert result.outputs.document.count("<SttlmTxCond>") == 2


# -- validation ------------------------------------------------------------------------


def test_missing_mandatory_element_is_reported(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", drop(sese023_elements, "/FinInstrmId/ISIN"))

    assert not result.valid
    codes = {item.rule_id for item in result.validation.errors}
    assert "MX_MANDATORY_ELEMENT_MISSING" in codes


def test_invalid_code_is_reported_with_the_allowed_values(
    sese023_elements: list[ElementInput],
) -> None:
    result = generate("sese.023", replace(sese023_elements, "/SctiesTxTp/Cd", "NOPE"))

    issue = next(
        item for item in result.validation.errors if item.rule_id == "MX_CODE_NOT_ALLOWED"
    )
    assert "TRAD" in (issue.expected or "")
    assert issue.suggestion


def test_mt_style_date_is_rejected_with_a_helpful_suggestion(
    sese023_elements: list[ElementInput],
) -> None:
    result = generate("sese.023", replace(sese023_elements, "SttlmDt/Dt/Dt", "20260818"))

    issue = next(
        item for item in result.validation.errors if item.rule_id == "MX_FORMAT_INVALID"
    )
    assert "2026-08-18" in (issue.suggestion or "")


def test_mt_style_isin_prefix_is_rejected(sese023_elements: list[ElementInput]) -> None:
    result = generate(
        "sese.023", replace(sese023_elements, "/FinInstrmId/ISIN", "ISIN XS0000000001")
    )

    assert not result.valid
    assert any(item.rule_id == "MX_FORMAT_INVALID" for item in result.validation.errors)


def test_unknown_element_path_names_the_input(sese023_elements: list[ElementInput]) -> None:
    elements = [*sese023_elements, ElementInput(path=f"{ROOT}/NotAnElement", value="X")]

    result = generate("sese.023", elements)

    issue = next(
        item for item in result.validation.errors if item.rule_id == "MX_UNKNOWN_ELEMENT"
    )
    assert "NotAnElement" in (issue.current_value or "")


def test_addressing_a_container_is_rejected(sese023_elements: list[ElementInput]) -> None:
    elements = [*sese023_elements, ElementInput(path=f"{ROOT}/TradDtls", value="X")]

    result = generate("sese.023", elements)

    assert any(
        item.rule_id == "MX_CONTAINER_NOT_A_VALUE" for item in result.validation.errors
    )


def test_choice_allows_only_one_branch() -> None:
    root = "/Document/SctiesSttlmTxStsAdvc"
    elements = [
        ElementInput(path=f"{root}/TxIdDtls/SctiesMvmntTp", value="RECE"),
        ElementInput(path=f"{root}/TxIdDtls/Pmt", value="APMT"),
        ElementInput(path=f"{root}/TxIdDtls/AcctOwnrTxId", value="TESTREF001"),
        ElementInput(path=f"{root}/PrcgSts/AckdAccptd/NoSpcfdRsn", value="NORE"),
        ElementInput(path=f"{root}/PrcgSts/Rjctd/Rsn/Cd/Cd", value="DSEC"),
    ]

    result = generate("sese.024", elements)

    assert any(item.rule_id == "MX_CHOICE_VIOLATION" for item in result.validation.errors)


def test_status_advice_requires_at_least_one_status() -> None:
    root = "/Document/SctiesSttlmTxStsAdvc"
    elements = [
        ElementInput(path=f"{root}/TxIdDtls/SctiesMvmntTp", value="RECE"),
        ElementInput(path=f"{root}/TxIdDtls/Pmt", value="APMT"),
        ElementInput(path=f"{root}/TxIdDtls/AcctOwnrTxId", value="TESTREF001"),
    ]

    result = generate("sese.024", elements)

    assert any(
        item.rule_id == "MX_REQUIRED_GROUP_MISSING" for item in result.validation.errors
    )


def test_against_payment_requires_an_amount(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", drop(sese023_elements, "/SttlmAmt/"))

    assert any(
        item.rule_id == "MX_AMOUNT_REQUIRED_FOR_APMT" for item in result.validation.errors
    )


def test_free_of_payment_forbids_an_amount(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", replace(sese023_elements, "SttlmTpAndAddtlParams/Pmt", "FREE"))

    assert any(
        item.rule_id == "MX_AMOUNT_NOT_ALLOWED_FOR_FREE" for item in result.validation.errors
    )


def test_settlement_before_trade_is_rejected(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", replace(sese023_elements, "SttlmDt/Dt/Dt", "2026-01-01"))

    assert any(
        item.rule_id == "SETTLEMENT_DATE_BEFORE_TRADE_DATE"
        for item in result.validation.errors
    )


def test_currency_outside_the_profile_is_rejected(
    sese023_elements: list[ElementInput],
) -> None:
    result = generate("sese.023", replace(sese023_elements, "/SttlmAmt/Amt", "JPY 25000.00"))

    assert any(
        item.rule_id == "PROFILE_CURRENCY_NOT_ALLOWED" for item in result.validation.errors
    )


# -- XSD -------------------------------------------------------------------------------


def test_derived_schema_compiles_for_every_configured_message() -> None:
    from lxml import etree

    for spec in mx_registry.all_specs():
        etree.XMLSchema(etree.fromstring(derive_schema(spec).encode()))


def test_valid_document_passes_xsd(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)
    outcome = validate_document(mx_registry.get("sese.023"), result.outputs.document or "")

    assert outcome.performed
    assert outcome.passed
    assert outcome.schema_source is SchemaSource.SUBSET_DERIVED


def test_xsd_catches_out_of_order_elements(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)
    lines = (result.outputs.document or "").splitlines()
    tx_id = next(line for line in lines if "<TxId>" in line)
    lines.remove(tx_id)
    index = next(i for i, line in enumerate(lines) if "</SttlmTpAndAddtlParams>" in line)
    lines.insert(index + 1, tx_id)

    outcome = validate_document(mx_registry.get("sese.023"), "\n".join(lines))

    assert outcome.performed
    assert not outcome.passed
    assert outcome.issues


def test_xsd_catches_a_missing_required_attribute(
    sese023_elements: list[ElementInput],
) -> None:
    result = generate("sese.023", sese023_elements)
    broken = (result.outputs.document or "").replace('<Amt Ccy="USD">', "<Amt>")

    outcome = validate_document(mx_registry.get("sese.023"), broken)

    assert not outcome.passed
    assert any("Ccy" in issue.message for issue in outcome.issues)


def test_xsd_layer_is_reported_in_the_result(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    layer = next(
        item for item in result.validation.layers if item.layer is ValidationLayer.XSD
    )
    assert layer.state.value == "PASSED"
    assert "configured subset" in (layer.detail or "")


def test_official_schema_is_preferred_when_present(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The licensed-schema drop point is configuration, not a code change.

    Pointing the setting at a directory is the whole procedure, so the test performs the
    procedure rather than reaching into the module to fake its result.
    """
    import app.studio.mx.xsd as xsd_module
    from app.config import get_settings

    spec = mx_registry.get("sese.023")
    official = tmp_path / f"{spec.version}.xsd"
    official.write_text(derive_schema(spec), encoding="utf-8")
    monkeypatch.setenv("MX_OFFICIAL_XSD_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert xsd_module.official_schema_path(spec) == official
    finally:
        monkeypatch.delenv("MX_OFFICIAL_XSD_DIRECTORY", raising=False)
        get_settings.cache_clear()


def test_the_official_schema_directory_defaults_to_the_committed_one() -> None:
    """A clean clone with no environment must keep working."""
    from app.studio.mx.xsd import official_schema_directory

    directory = official_schema_directory()

    assert directory.is_dir()
    assert directory.parts[-4:] == ("config", "mx", "xsd", "official")


# -- AppHdr ----------------------------------------------------------------------------


def test_app_hdr_uses_the_head_namespace(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    assert result.outputs.app_hdr is not None
    root = ElementTree.fromstring(result.outputs.app_hdr)
    assert root.tag == f"{{{APPHDR_NS}}}AppHdr"


def test_app_hdr_message_definition_matches_the_document(
    sese023_elements: list[ElementInput],
) -> None:
    result = generate("sese.023", sese023_elements)

    assert "<MsgDefIdr>sese.023.001.11</MsgDefIdr>" in (result.outputs.app_hdr or "")
    assert "sese.023.001.11" in (result.outputs.document or "")


def test_app_hdr_bics_come_from_the_profile(
    profile: ClientProfile, sese023_elements: list[ElementInput]
) -> None:
    assert profile.mx_envelope is not None
    result = generate("sese.023", sese023_elements)

    assert f"<BICFI>{profile.mx_envelope.from_bic}</BICFI>" in (result.outputs.app_hdr or "")


def test_app_hdr_never_fabricates_a_signature(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)

    assert "<Sgntr>" not in (result.outputs.app_hdr or "")
    signature = next(
        item for item in result.envelope_fields if item.name.startswith("Signature")
    )
    assert signature.value is None


def test_app_hdr_fails_closed_without_a_configured_bic(
    profile: ClientProfile, sese023_elements: list[ElementInput]
) -> None:
    bare = profile.model_copy(update={"mx_envelope": None})
    spec = mx_registry.get("sese.023")

    with pytest.raises(MxEnvelopeUnavailable):
        mx_generator.compose_app_hdr(spec, bare, None)


def test_wrapper_is_profile_driven(
    profile: ClientProfile, sese023_elements: list[ElementInput]
) -> None:
    assert profile.mx_envelope is not None
    wrapper = profile.mx_envelope.wrapper_element
    result = generate("sese.023", sese023_elements)

    assert f"<{wrapper}>" in (result.outputs.xml or "")


def test_no_wrapper_is_invented_when_none_is_configured(
    profile: ClientProfile, sese023_elements: list[ElementInput]
) -> None:
    unwrapped = profile.model_copy(
        update={"mx_envelope": profile.mx_envelope.model_copy(update={"wrapper_element": None})}
    )
    spec = mx_registry.get("sese.023")
    resolved, _ = mx_generator.resolve(spec, sese023_elements)
    build = mx_generator.build("sese.023", unwrapped, sese023_elements)

    assert "<BusinessMessage>" not in build.xml
    assert any(item.rule_id == "MX_WRAPPER_NOT_CONFIGURED" for item in build.warnings)
    assert resolved


def test_request_may_override_the_header_identifier(
    sese023_elements: list[ElementInput],
) -> None:
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MX,
            message_type="sese.023",
            elements=sese023_elements,
            envelope=EnvelopeOverride(business_message_identifier="MYBIZMSGID001"),
            persist=False,
        )
    )

    assert "<BizMsgIdr>MYBIZMSGID001</BizMsgIdr>" in (result.outputs.app_hdr or "")


# -- round trip ------------------------------------------------------------------------


def test_generated_xml_parses_and_round_trips(sese023_elements: list[ElementInput]) -> None:
    result = generate("sese.023", sese023_elements)
    namespace = "{urn:iso:std:iso:20022:tech:xsd:sese.023.001.11}"

    root = ElementTree.fromstring(result.outputs.document or "")
    instruction = root.find(f"{namespace}SctiesSttlmTxInstr")
    assert instruction is not None
    assert instruction.findtext(f"{namespace}TxId") == "TESTREF001"

    supplied = {item.path: item.value for item in sese023_elements}
    settlement_date = supplied[f"{ROOT}/TradDtls/SttlmDt/Dt/Dt"]
    assert f"<Dt>{settlement_date}</Dt>" in (result.outputs.document or "")


def test_all_configured_mx_messages_generate_from_their_samples() -> None:
    for spec in mx_registry.all_specs():
        for variant in SampleVariant:
            sample = build_sample(MessageFormat.MX, spec.message_type, variant)
            if sample.field_count == 0:
                continue
            result = generate(spec.message_type, list(sample.elements))
            assert result.valid, (
                spec.message_type,
                variant,
                [item.message for item in result.validation.errors],
            )


def test_output_modes_are_honoured(sese023_elements: list[ElementInput]) -> None:
    result = studio_service.generate(
        GenerateRequest(
            format=MessageFormat.MX,
            message_type="sese.023",
            elements=sese023_elements,
            output_modes=[OutputMode.DOCUMENT],
            persist=False,
        )
    )

    assert result.outputs.document is not None
    assert result.outputs.xml is None
    assert result.outputs.canonical_json is None

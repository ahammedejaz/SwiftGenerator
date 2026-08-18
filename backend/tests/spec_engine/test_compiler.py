"""The XSD compiler: every supported construct compiles exactly; nothing flattens silently."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.spec_engine.diagnostics import CompilationError, FindingCode
from app.spec_engine.mapper import display_name
from app.spec_engine.patterns import sample_from_pattern
from app.spec_engine.pipeline import compile_schema
from app.studio.mx.models import MxMessageSpec

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "xsd" / "test.001.001.01.xsd"
NS = "urn:iso:std:iso:20022:tech:xsd:test.001.001.01"


def _write_schema(tmp_path: Path, body: str, namespace: str = NS) -> Path:
    path = tmp_path / "schema.xsd"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{namespace}" xmlns="{namespace}" elementFormDefault="qualified">'
        f"{body}</xs:schema>",
        encoding="utf-8",
    )
    return path


_MINIMAL = """
  <xs:element name="Document" type="Document"/>
  <xs:complexType name="Document">
    <xs:sequence><xs:element name="Msg" type="Msg"/></xs:sequence>
  </xs:complexType>
  <xs:complexType name="Msg">
    <xs:sequence>{body}</xs:sequence>
  </xs:complexType>
"""


def _compile_body(tmp_path: Path, body: str, **kwargs):  # type: ignore[no-untyped-def]
    return compile_schema(_write_schema(tmp_path, _MINIMAL.format(body=body)), **kwargs)


def _element(pack, *names):  # type: ignore[no-untyped-def]
    node_list = pack.spec.structure
    node = None
    for name in names:
        node = next(item for item in node_list if item.name == name)
        node_list = node.children
    return node


# ------------------------------------------------------------------ the full fixture


def test_the_fixture_compiles_and_loads_as_an_ordinary_spec() -> None:
    pack = compile_schema(FIXTURE)
    spec = MxMessageSpec.model_validate(yaml.safe_load(pack.yaml_text))
    assert spec.message_type == "test.001"
    assert spec.version == "test.001.001.01"
    assert spec.namespace == NS
    assert spec.message_root == "SynthTstInstr"
    assert spec.source.generated is True
    assert spec.source.source_checksum == pack.source_checksum
    assert spec.authoritative_completeness_known is False


def test_compilation_is_deterministic_byte_for_byte() -> None:
    first = compile_schema(FIXTURE).yaml_text
    second = compile_schema(FIXTURE).yaml_text
    assert first == second


def test_known_representation_classes_map_by_name() -> None:
    pack = compile_schema(FIXTURE)
    assert _element(pack, "TxId").data_type is not None
    assert _element(pack, "TxId").data_type.value == "Max35Text"
    assert _element(pack, "CreDt").data_type.value == "ISODate"
    assert _element(pack, "AckSts").data_type.value == "YesNoIndicator"


def test_the_amount_shape_becomes_a_currency_bearing_amount() -> None:
    amount = _element(compile_schema(FIXTURE), "SttlmAmt")
    assert amount.data_type is not None
    assert amount.data_type.value == "ActiveCurrencyAndAmount"
    assert amount.currency_attribute is True


def test_enumerations_become_code_lists_in_document_order() -> None:
    priority = _element(compile_schema(FIXTURE), "Prty")
    assert priority.data_type.value == "Code"
    assert priority.codes == ["HIGH", "NORM"]


def test_choices_compile_with_branches_never_individually_mandatory() -> None:
    party = _element(compile_schema(FIXTURE), "Pty")
    assert party.choice is True
    assert all(child.presence.value != "MANDATORY" for child in party.children)


def test_unknown_simple_types_become_verbatim_restrictions() -> None:
    quantity = _element(compile_schema(FIXTURE), "Qty")
    assert quantity.data_type is None
    assert quantity.restriction is not None
    assert quantity.restriction.type_name == "RestrictedQuantity"
    assert quantity.restriction.total_digits == 14
    assert quantity.restriction.fraction_digits == 3
    assert quantity.restriction.min_inclusive == "0"


def test_an_inline_anonymous_simple_type_compiles() -> None:
    instrument = _element(compile_schema(FIXTURE), "Mvmnt", "FinInstrmId")
    assert instrument.restriction is not None
    assert instrument.restriction.pattern == "[A-Z]{2,2}[A-Z0-9]{9,9}[0-9]{1,1}"


def test_unbounded_repetition_caps_visibly() -> None:
    pack = compile_schema(FIXTURE)
    movement = _element(pack, "Mvmnt")
    assert movement.max_occurs == 1_000
    assert any(f.code is FindingCode.XSD_OCCURRENCE_CAPPED for f in pack.findings)
    assert any("caps repetition" in item for item in pack.spec.limitations)


def test_every_mandatory_leaf_gets_a_deterministic_example() -> None:
    pack = compile_schema(FIXTURE)

    def check(elements) -> None:  # type: ignore[no-untyped-def]
        for element in elements:
            if element.is_leaf and element.presence.value == "MANDATORY":
                assert element.examples, element.name
            check(element.children)

    check(pack.spec.structure)


# ------------------------------------------------------------------ construct-level


def test_optional_and_required_presence(tmp_path: Path) -> None:
    pack = _compile_body(
        tmp_path,
        '<xs:element name="A" type="xs:string" minOccurs="0"/>'
        '<xs:element name="B" type="xs:string"/>',
    )
    a, b = pack.spec.structure
    assert a.presence.value == "OPTIONAL"
    assert b.presence.value == "MANDATORY"


def test_cross_schema_include_and_import(tmp_path: Path) -> None:
    common_ns = "urn:iso:std:iso:20022:tech:xsd:test.002.001.01"
    (tmp_path / "common.xsd").write_text(
        '<?xml version="1.0"?>'
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{common_ns}">'
        '<xs:simpleType name="CommonText"><xs:restriction base="xs:string">'
        '<xs:maxLength value="10"/></xs:restriction></xs:simpleType>'
        "</xs:schema>",
        encoding="utf-8",
    )
    (tmp_path / "included.xsd").write_text(
        '<?xml version="1.0"?>'
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        f'targetNamespace="{NS}" xmlns="{NS}">'
        '<xs:simpleType name="LocalText"><xs:restriction base="xs:string">'
        '<xs:minLength value="1"/><xs:maxLength value="5"/></xs:restriction></xs:simpleType>'
        "</xs:schema>",
        encoding="utf-8",
    )
    body = (
        '<xs:include schemaLocation="included.xsd"/>'
        '<xs:import namespace="%s" schemaLocation="common.xsd"/>'
        '<xs:element name="Document" type="Document"/>'
        '<xs:complexType name="Document"><xs:sequence>'
        '<xs:element name="Msg" type="Msg"/></xs:sequence></xs:complexType>'
        '<xs:complexType name="Msg"><xs:sequence>'
        '<xs:element name="Txt" type="LocalText"/>'
        "</xs:sequence></xs:complexType>"
    ).replace("%s", common_ns)
    pack = compile_schema(_write_schema(tmp_path, body))
    leaf = pack.spec.structure[0]
    assert leaf.restriction is not None
    assert leaf.restriction.max_length == 5


def test_min_occurs_above_one_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as caught:
        _compile_body(tmp_path, '<xs:element name="A" type="xs:string" minOccurs="2"/>')
    assert any(
        f.code is FindingCode.XSD_UNSUPPORTED_CONSTRUCT for f in caught.value.findings
    )


def test_a_required_non_currency_attribute_is_refused(tmp_path: Path) -> None:
    body = (
        '<xs:element name="A"><xs:complexType><xs:sequence>'
        '<xs:element name="B" type="xs:string"/></xs:sequence>'
        '<xs:attribute name="Cd" type="xs:string" use="required"/>'
        "</xs:complexType></xs:element>"
    )
    with pytest.raises(CompilationError) as caught:
        _compile_body(tmp_path, body)
    assert any("Cd" in f.message for f in caught.value.findings)


def test_xs_any_is_a_warning_and_a_recorded_limitation(tmp_path: Path) -> None:
    body = (
        '<xs:element name="Splmtry"><xs:complexType><xs:sequence>'
        '<xs:element name="Real" type="xs:string"/>'
        '<xs:any processContents="lax" minOccurs="0"/>'
        "</xs:sequence></xs:complexType></xs:element>"
    )
    pack = _compile_body(tmp_path, body)
    assert any(f.code is FindingCode.XSD_UNSUPPORTED_CONSTRUCT for f in pack.findings)


def test_an_unresolved_type_is_a_named_error(tmp_path: Path) -> None:
    with pytest.raises(CompilationError) as caught:
        _compile_body(tmp_path, '<xs:element name="A" type="NoSuchType"/>')
    assert any(f.code is FindingCode.XSD_TYPE_UNRESOLVED for f in caught.value.findings)


def test_recursion_is_depth_limited(tmp_path: Path) -> None:
    body = (
        '<xs:element name="Document" type="Document"/>'
        '<xs:complexType name="Document"><xs:sequence>'
        '<xs:element name="Msg" type="Loop"/></xs:sequence></xs:complexType>'
        '<xs:complexType name="Loop"><xs:sequence>'
        '<xs:element name="Again" type="Loop"/>'
        "</xs:sequence></xs:complexType>"
    )
    with pytest.raises(CompilationError) as caught:
        compile_schema(_write_schema(tmp_path, body))
    assert any(f.code is FindingCode.XSD_RECURSION_LIMIT for f in caught.value.findings)


def test_a_non_iso_namespace_is_refused(tmp_path: Path) -> None:
    path = _write_schema(
        tmp_path,
        _MINIMAL.format(body='<xs:element name="A" type="xs:string"/>'),
        namespace="urn:something:else",
    )
    with pytest.raises(CompilationError) as caught:
        compile_schema(path)
    assert any(
        f.code is FindingCode.XSD_NAMESPACE_UNSUPPORTED for f in caught.value.findings
    )


def test_multiple_globals_need_an_explicit_root(tmp_path: Path) -> None:
    body = (
        '<xs:element name="Document" type="Document"/>'
        '<xs:element name="Other" type="xs:string"/>'
        '<xs:complexType name="Document"><xs:sequence>'
        '<xs:element name="Msg" type="Msg"/></xs:sequence></xs:complexType>'
        '<xs:complexType name="Msg"><xs:sequence>'
        '<xs:element name="A" type="xs:string"/></xs:sequence></xs:complexType>'
    )
    with pytest.raises(CompilationError) as caught:
        compile_schema(_write_schema(tmp_path, body))
    assert any(f.code is FindingCode.XSD_ROOT_AMBIGUOUS for f in caught.value.findings)
    pack = compile_schema(_write_schema(tmp_path, body), root_name="Document")
    assert pack.spec.message_root == "Msg"


# ------------------------------------------------------------------ presentation


def test_display_names_are_mechanical_and_deterministic() -> None:
    assert display_name("SttlmDt") == "Settlement Date"
    assert display_name("TxId") == "Transaction Identification"
    assert display_name("FinInstrmId") == "Financial Instrument Identification"
    # An unknown token renders as itself — honest, never invented.
    assert display_name("Zzzq") == "Zzzq"


def test_pattern_samples_cover_the_iso_shapes() -> None:
    assert sample_from_pattern("[A-Z]{2,2}[A-Z0-9]{9,9}[0-9]{1,1}") == "AAAAAAAAAAA0"
    assert sample_from_pattern("[A-Z]{3,3}") == "AAA"
    bic = sample_from_pattern("[A-Z0-9]{4,4}[A-Z]{2,2}[A-Z0-9]{2,2}([A-Z0-9]{3,3}){0,1}")
    assert bic == "AAAAAAAA"
    assert sample_from_pattern("(?!bad)lookahead") is None

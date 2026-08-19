"""Field references resolve through the registries the composer already uses.

A rule that names something the structure does not have must not resolve, and a reference
that could mean two fields must not resolve either — a rule addressing "whichever of these
two the resolver happened to pick first" is worse than one that fails to compile.
"""

from __future__ import annotations

import pytest

from app.rule_engine.refs import FieldKind, FieldRef, StructureIndex
from app.studio.models import MessageFormat, Presence
from tests.rule_engine.conftest import AMT, MESSAGE, PMT, TRADDT, TXID, mx


def test_an_mx_path_resolves_to_what_the_structure_says(index: StructureIndex) -> None:
    resolved = index.resolve(mx(PMT), MESSAGE)
    assert resolved is not None
    assert resolved.kind is FieldKind.CODE
    assert resolved.codes == (
        "APMT",
        "FREE",
    )
    assert resolved.presence is Presence.MANDATORY
    assert resolved.key == PMT
    assert resolved.location == PMT


def test_kinds_come_from_the_structure_not_from_the_name(index: StructureIndex) -> None:
    assert index.resolve(mx(AMT), MESSAGE).kind is FieldKind.DECIMAL  # type: ignore[union-attr]
    assert index.resolve(mx(TRADDT), MESSAGE).kind is FieldKind.DATE  # type: ignore[union-attr]


def test_an_unknown_path_does_not_resolve(index: StructureIndex) -> None:
    assert index.resolve(mx("/Document/SctiesSttlmTxInstr/NotAnElement"), MESSAGE) is None


def test_an_unknown_message_does_not_resolve(index: StructureIndex) -> None:
    assert index.resolve(mx(PMT), "sese.999") is None
    assert not index.known(MessageFormat.MX, "sese.999")


def test_mt_resolves_by_row_id_and_by_the_spreadsheet_triple(index: StructureIndex) -> None:
    by_id = index.resolve(FieldRef(format=MessageFormat.MT, field_id="MT541-A-20C-SEME"), "MT541")
    assert by_id is not None
    by_tag = index.resolve(
        FieldRef(format=MessageFormat.MT, sequence_path="A", tag="20C", qualifier="SEME"),
        "MT541",
    )
    assert by_tag is not None
    # Two spellings of one address must land on the same field.
    assert by_id.key == by_tag.key == "MT541-A-20C-SEME"
    # And each keeps its own canonical identity, so the binding table finds it again.
    assert by_id.canonical != by_tag.canonical


def test_an_ambiguous_mt_reference_is_treated_as_unresolvable(index: StructureIndex) -> None:
    # 20C appears more than once in MT541 under different qualifiers. Without the
    # qualifier the reference names two fields, which is as unusable as naming none.
    rows = [
        row for row in index.fields(MessageFormat.MT, "MT541") if "-20C-" in row.key
    ]
    assert len(rows) > 1
    assert index.resolve(FieldRef(format=MessageFormat.MT, tag="20C"), "MT541") is None


def test_the_structure_checksum_is_stable_and_specific(index: StructureIndex) -> None:
    first = index.structure_checksum(MessageFormat.MX, MESSAGE)
    assert first == index.structure_checksum(MessageFormat.MX, MESSAGE)
    assert first.startswith("sha256:")
    assert first != index.structure_checksum(MessageFormat.MX, "sese.024")
    assert first != index.structure_checksum(MessageFormat.MT, "MT541")


def test_the_checksum_ignores_presentation_and_notices_structure(
    index: StructureIndex, tmp_path
) -> None:
    """Rewording a business explanation must not invalidate a rule pack; changing a code
    set must. Prose has no authority over a rule, so it cannot be allowed to expire one."""
    import shutil

    import yaml

    from app.studio.mx.registry import MxRegistry

    source = index.structure_checksum(MessageFormat.MX, MESSAGE)
    directory = tmp_path / "mx"
    directory.mkdir()
    original = (
        __import__("pathlib").Path("config/mx/sese.023.001.11.yaml").read_text(encoding="utf-8")
    )
    shutil.copy("config/mx/sese.023.001.11.yaml", directory / "sese.023.001.11.yaml")

    payload = yaml.safe_load(original)

    def first_leaf(elements):
        for element in elements:
            if element.get("children"):
                found = first_leaf(element["children"])
                if found is not None:
                    return found
            elif element.get("dataType"):
                return element
        return None

    leaf = first_leaf(payload["structure"])
    assert leaf is not None
    leaf["businessMeaning"] = "Reworded for this test and carrying no authority at all."
    (directory / "sese.023.001.11.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    reworded = StructureIndex(mx=MxRegistry(directory))
    assert reworded.structure_checksum(MessageFormat.MX, MESSAGE) == source

    leaf["maxOccurs"] = 3
    (directory / "sese.023.001.11.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    widened = StructureIndex(mx=MxRegistry(directory))
    assert widened.structure_checksum(MessageFormat.MX, MESSAGE) != source


def test_always_present_marks_only_fields_no_message_can_omit(index: StructureIndex) -> None:
    fields = {item.key: item for item in index.fields(MessageFormat.MX, MESSAGE)}
    assert fields[TXID].always_present
    assert not fields[
        "/Document/SctiesSttlmTxInstr/SttlmTpAndAddtlParams/CmonId"
    ].always_present


@pytest.mark.parametrize(
    "payload",
    [
        {"format": "MX"},
        {"format": "MX", "path": "not-a-path"},
        {"format": "MT"},
        {"format": "MT", "tag": "999X"},
        {"format": "MT", "field_id": "not-a-row"},
        {"format": "MX", "path": AMT, "tag": "20C"},
    ],
)
def test_malformed_references_never_construct(payload: dict) -> None:
    with pytest.raises(ValueError):
        FieldRef(**payload)


def test_a_canonical_identity_round_trips_through_describe() -> None:
    assert mx(AMT).canonical() == f"MX|{AMT}"
    assert mx(AMT).describe() == AMT
    triple = FieldRef(format=MessageFormat.MT, sequence_path="E", tag="22F", qualifier="SETR")
    assert triple.canonical() == "MT|E/22F/SETR"

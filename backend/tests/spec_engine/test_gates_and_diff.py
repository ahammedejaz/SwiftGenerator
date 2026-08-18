"""The pack gates and the structural diff."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.spec_engine.gates import validate_pack
from app.spec_engine.pipeline import compile_schema
from app.spec_engine.structdiff import diff_packs
from app.studio.mx.models import MxMessageSpec

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "xsd" / "test.001.001.01.xsd"


def test_every_gate_passes_for_the_fixture_pack() -> None:
    pack = compile_schema(FIXTURE)
    result = validate_pack(pack.yaml_text, pack.version, FIXTURE)
    assert result.registry_load.passed
    assert result.sample.passed
    assert result.compose.passed
    # The critical property: the generated document is valid against the ORIGINAL
    # source schema, not merely against the schema derived from the pack itself.
    assert result.source_xsd.passed, result.source_xsd.detail
    assert result.invalid_variants.passed, result.invalid_variants.detail
    assert result.round_trip.passed, result.round_trip.detail
    assert result.passed


def test_the_source_schema_rejects_the_broken_variants() -> None:
    pack = compile_schema(FIXTURE)
    result = validate_pack(pack.yaml_text, pack.version, FIXTURE)
    rejected = result.invalid_variants.detail
    assert "missing mandatory element" in rejected
    assert "invalid datatype" in rejected
    assert "wrong element order" in rejected


def test_a_corrupt_pack_fails_the_registry_gate_loudly() -> None:
    pack = compile_schema(FIXTURE)
    broken = pack.yaml_text.replace("messageRoot: SynthTstInstr", "messageRoot: X")
    result = validate_pack(broken, pack.version, FIXTURE)
    assert not result.registry_load.passed
    assert not result.passed


def test_the_diff_reports_exactly_what_moved(tmp_path: Path) -> None:
    pack = compile_schema(FIXTURE)
    before = MxMessageSpec.model_validate(yaml.safe_load(pack.yaml_text))

    mutated = yaml.safe_load(pack.yaml_text)
    structure = mutated["structure"]
    # Remove one element, change a cardinality, change an enumeration.
    removed = structure.pop(7)  # AckSts
    next(item for item in structure if item["name"] == "Mvmnt")["maxOccurs"] = 5
    next(item for item in structure if item["name"] == "Prty")["codes"] = ["HIGH", "LOWW"]
    structure.append(
        {"name": "NewFld", "displayName": "New Field", "dataType": "Max35Text"}
    )
    after = MxMessageSpec.model_validate(mutated)

    diff = diff_packs(before, after)
    assert not diff.identical
    assert diff.removed == [f"SynthTstInstr/{removed['name']}"]
    assert diff.added == ["SynthTstInstr/NewFld"]
    assert any("Mvmnt" in item for item in diff.cardinality_changed)
    assert diff.enumerations_changed == ["SynthTstInstr/Prty"]

    assert diff_packs(before, before).identical

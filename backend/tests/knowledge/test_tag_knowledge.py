from pathlib import Path

import pytest
import yaml

from app.composers.dvp_confirmation import DvpConfirmationComposer
from app.composers.dvp_instruction import DvpInstructionComposer
from app.composers.fop_confirmation import FopConfirmationComposer
from app.composers.fop_instruction import FopInstructionComposer
from app.composers.settlement_status import SettlementStatusComposer
from app.domain.enums import MessageType
from app.knowledge.loader import TagKnowledgeRepository, knowledge_repository
from app.knowledge.models import PresenceRule
from app.profiles.loader import profiles
from tests.fixtures.golden_scenarios import golden_scenario

SETTLEMENT_TYPES = [
    MessageType.MT540,
    MessageType.MT541,
    MessageType.MT542,
    MessageType.MT543,
    MessageType.MT544,
    MessageType.MT545,
    MessageType.MT546,
    MessageType.MT547,
    MessageType.MT548,
]


def _compose(message_type: MessageType):  # type: ignore[no-untyped-def]
    scenario = golden_scenario(message_type)
    profile = profiles.get("BASE_DEMO_V1")
    if message_type in {MessageType.MT540, MessageType.MT542}:
        return FopInstructionComposer().compose(scenario, profile)
    if message_type in {MessageType.MT541, MessageType.MT543}:
        return DvpInstructionComposer().compose(scenario, profile)
    if message_type in {MessageType.MT544, MessageType.MT546}:
        return FopConfirmationComposer().compose(scenario, profile)
    if message_type in {MessageType.MT545, MessageType.MT547}:
        return DvpConfirmationComposer().compose(scenario, profile)
    return SettlementStatusComposer().compose(scenario, profile)


@pytest.mark.parametrize("message_type", SETTLEMENT_TYPES)
def test_every_emitted_settlement_field_has_verified_knowledge(
    message_type: MessageType,
) -> None:
    result = _compose(message_type)
    for field in result.field_map:
        knowledge = knowledge_repository.find_for_rendered_field(
            message_type,
            field.sequence,
            field.tag,
            field.qualifier,
            "BASE_DEMO_V1",
        )
        assert knowledge.record.business_meaning
        assert knowledge.record.technical_meaning
        assert knowledge.record.why_used
        assert knowledge.record.business_question
        assert knowledge.record.format_explanation
        assert knowledge.record.source.review_status.value == "VERIFIED"


def test_pset_has_message_specific_verified_explanation_and_profile_overlay() -> None:
    base = knowledge_repository.effective("MT541-E-95R-PSET", "BASE_DEMO_V1")
    bfs = knowledge_repository.effective("MT541-E-95R-PSET", "BFS_CLIENT_DEMO_V1")

    assert base.record.display_name == "Place of Settlement"
    assert "where the securities actually settle" in base.record.business_meaning.lower()
    assert "data source scheme" in " ".join(base.record.common_mistakes)
    assert base.record.presence == PresenceRule.CONDITIONAL
    assert base.effective_presence == PresenceRule.MANDATORY
    assert base.record.related_fields == ["DEAG", "REAG"]
    assert base.record.source.review_status.value == "VERIFIED"
    assert bfs.profile_override_applied is True
    assert bfs.client_explanation is not None
    assert bfs.effective_options == ["R"]


def test_search_and_dependencies_are_deterministic() -> None:
    results = knowledge_repository.search("place of settlement")
    assert results
    assert all(result.record.qualifier == "PSET" for result in results)
    dependencies = knowledge_repository.dependencies("MT541-E-95R-PSET", "BASE_DEMO_V1")
    assert {item.record.qualifier for item in dependencies.related_fields} == {
        "DEAG",
        "REAG",
    }


def _write_modified_pack(tmp_path: Path, mutate):  # type: ignore[no-untyped-def]
    source = Path(__file__).resolve().parents[2] / "config" / "knowledge" / "settlement_v1.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutate(payload)
    (tmp_path / "settlement_v1.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["records"].append(payload["records"][0].copy()),
            "Duplicate knowledge ID",
        ),
        (
            lambda payload: payload["records"][0].update({"fieldTag": "99Z"}),
            "Unknown supported field signature",
        ),
        (
            lambda payload: payload["records"][0].pop("businessMeaning"),
            "businessMeaning",
        ),
        (
            lambda payload: payload["records"][0].pop("source"),
            "source",
        ),
        (
            lambda payload: payload["records"][0].update({"relatedFields": ["ZZZZ"]}),
            "Broken dependency",
        ),
    ],
)
def test_loader_rejects_invalid_knowledge_packs(
    tmp_path: Path,
    mutate,
    message: str,  # type: ignore[no-untyped-def]
) -> None:
    _write_modified_pack(tmp_path, mutate)
    with pytest.raises((ValueError, RuntimeError), match=message):
        TagKnowledgeRepository(tmp_path)

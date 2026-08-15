from pathlib import Path

import pytest

from app.composers.dvp_confirmation import DvpConfirmationComposer
from app.composers.dvp_instruction import DvpInstructionComposer
from app.composers.fop_confirmation import FopConfirmationComposer
from app.composers.fop_instruction import FopInstructionComposer
from app.composers.settlement_status import SettlementStatusComposer
from app.domain.enums import MessageType
from app.profiles.loader import profiles
from tests.fixtures.golden_scenarios import golden_scenario

EXPECTED_DIR = Path(__file__).parent / "expected"
SETTLEMENT_MESSAGE_TYPES = [
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


def compose(message_type: MessageType) -> str:
    scenario = golden_scenario(message_type)
    profile = profiles.get("BASE_DEMO_V1")
    if message_type in {MessageType.MT540, MessageType.MT542}:
        return FopInstructionComposer().compose(scenario, profile).raw_message
    if message_type in {MessageType.MT541, MessageType.MT543}:
        return DvpInstructionComposer().compose(scenario, profile).raw_message
    if message_type in {MessageType.MT544, MessageType.MT546}:
        return FopConfirmationComposer().compose(scenario, profile).raw_message
    if message_type in {MessageType.MT545, MessageType.MT547}:
        return DvpConfirmationComposer().compose(scenario, profile).raw_message
    return SettlementStatusComposer().compose(scenario, profile).raw_message


@pytest.mark.parametrize("message_type", SETTLEMENT_MESSAGE_TYPES)
def test_message_matches_approved_golden_file(message_type: MessageType) -> None:
    expected = (EXPECTED_DIR / f"{message_type.value.lower()}.txt").read_text(encoding="utf-8")
    assert compose(message_type) == expected.rstrip("\n")

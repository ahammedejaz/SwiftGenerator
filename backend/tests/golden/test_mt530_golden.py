from pathlib import Path

from app.composers.settlement_command import SettlementCommandComposer
from app.domain.enums import (
    Lifecycle,
    MessageFunction,
    MessageType,
    SettlementCommandType,
)
from app.domain.models import (
    Account,
    SettlementCommandDetails,
    SettlementScenario,
)
from app.profiles.loader import profiles


def test_mt530_priority_subset_matches_golden_file() -> None:
    scenario = SettlementScenario(
        scenario_id="GOLDEN-MT530",
        lifecycle=Lifecycle.INSTRUCTION,
        message_type=MessageType.MT530,
        function=MessageFunction.NEWM,
        sender_reference="COMMAND000001",
        account=Account(safekeeping_account="SYNTHSAFE01"),
        command=SettlementCommandDetails(
            command_type=SettlementCommandType.MODIFY_PRIORITY,
            original_instruction_reference="ORIGCMD000001",
            priority=42,
        ),
    )
    actual = SettlementCommandComposer().compose(scenario, profiles.get("BASE_DEMO_V1"))
    expected = (Path(__file__).parent / "expected" / "mt530.txt").read_text(encoding="utf-8")
    assert actual.raw_message == expected.rstrip("\n")

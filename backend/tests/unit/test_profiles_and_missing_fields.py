from app.domain.enums import MessageType
from app.domain.missing_fields import find_missing_fields
from app.domain.models import SettlementScenario
from app.profiles.loader import profiles


def test_bfs_profile_applies_synthetic_pset_default_and_requires_client_reference() -> None:
    scenario = SettlementScenario(
        scenario_id="TC-PROFILE",
        profile_id="BFS_CLIENT_DEMO_V1",
    )
    profile = profiles.get("BFS_CLIENT_DEMO_V1")
    result = find_missing_fields(scenario, MessageType.MT541, profile)
    paths = [field.field_path for field in result.missing_fields]
    assert result.scenario_with_defaults.settlement.place_of_settlement == "SYNTHPSET01"
    assert "settlement.place_of_settlement" not in paths
    assert "client_reference" in paths


def test_mt541_missing_engine_asks_for_cash_fields() -> None:
    scenario = SettlementScenario(scenario_id="TC-MISSING")
    profile = profiles.get("BASE_DEMO_V1")
    result = find_missing_fields(scenario, MessageType.MT541, profile)
    paths = [field.field_path for field in result.missing_fields]
    assert "settlement.currency" in paths
    assert "settlement.amount" in paths
    assert result.next_question is not None
    assert "received or delivered" in result.next_question.question

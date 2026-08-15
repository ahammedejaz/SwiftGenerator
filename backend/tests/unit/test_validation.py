from app.domain.models import SettlementScenario
from app.domain.validation.engine import validate_scenario
from app.profiles.loader import profiles


def test_mt541_missing_amount_has_stable_rule_id(valid_mt541_payload) -> None:
    valid_mt541_payload["messageType"] = "MT541"
    valid_mt541_payload["settlement"]["amount"] = None
    scenario = SettlementScenario.model_validate(valid_mt541_payload)
    report = validate_scenario(scenario, profiles.get("BASE_DEMO_V1"))
    assert report.status.value == "INVALID"
    assert "MT541-SETTLEMENT-AMOUNT-REQUIRED" in {finding.rule_id for finding in report.findings}


def test_settlement_before_trade_date_is_rejected(valid_mt541_payload) -> None:
    valid_mt541_payload["messageType"] = "MT541"
    valid_mt541_payload["trade"]["settlementDate"] = "2026-08-01"
    scenario = SettlementScenario.model_validate(valid_mt541_payload)
    report = validate_scenario(scenario, profiles.get("BASE_DEMO_V1"))
    assert "SETTLEMENT-DATE-NOT-BEFORE-TRADE" in {finding.rule_id for finding in report.findings}

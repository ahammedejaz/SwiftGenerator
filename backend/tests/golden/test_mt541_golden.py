from pathlib import Path

from app.domain.models import SettlementScenario
from app.profiles.loader import profiles
from app.services.generation import GenerationService

EXPECTED = Path(__file__).parent / "expected" / "mt541_receive_against_payment.txt"


def test_mt541_matches_approved_golden_file(valid_mt541_payload) -> None:
    service = GenerationService(profiles)
    generated = service.generate(SettlementScenario.model_validate(valid_mt541_payload))
    assert generated.raw_message == EXPECTED.read_text(encoding="utf-8").rstrip("\n")
    assert generated.validation.status.value == "VALID"
    assert generated.resolved_message_type.value == "MT541"

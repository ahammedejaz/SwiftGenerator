from pathlib import Path

from app.composers.penalty_statement import PenaltyStatementComposer
from app.workflows.penalties import PenaltyStatement


def test_mt537_penalty_subset_matches_golden_file() -> None:
    statement = PenaltyStatement.model_validate(
        {
            "workflowId": "WF-GOLD-MT537",
            "statementReference": "PENASTMTGOLD001",
            "statementDate": "2026-08-05",
            "safekeepingAccount": "SYNTHSAFE01",
            "accountServicer": "SYNTHSERVICER",
            "relatedParty": "SYNTHPARTY",
            "listType": "NEW_ONLY",
            "penalties": [
                {
                    "penaltyReference": "PENALTYGOLD0001",
                    "commonReference": "COMMONGOLD0001",
                    "relatedInstructionReference": "ORIGGOLD000001",
                    "penaltyType": "SETTLEMENT_FAIL",
                    "action": "NEW",
                    "status": "ACTIVE",
                    "currency": "EUR",
                    "amount": "25.00",
                    "amountDirection": "PAYABLE",
                    "detectionDate": "2026-08-04",
                    "numberOfDays": 1,
                }
            ],
        }
    )
    actual = PenaltyStatementComposer().compose(statement).raw_message
    expected = (Path(__file__).parent / "expected" / "mt537.txt").read_text(encoding="utf-8")
    assert actual == expected.rstrip("\n")

from pathlib import Path

import pytest

from app.composers.corporate_actions import CorporateActionComposer
from app.domain.models import ValidationReport
from app.workflows.corporate_actions import (
    CorporateActionConfirmationRequest,
    CorporateActionInstructionRequest,
    CorporateActionNarrativeRequest,
    CorporateActionNotification,
    CorporateActionStatusRequest,
)
from app.workflows.models import WorkflowGeneratedMessage


def _fixtures() -> dict[str, str]:
    notification = CorporateActionNotification.model_validate(
        {
            "workflowId": "CA-WF-GOLD",
            "eventReference": "CAEVENTGOLD001",
            "messageReference": "CA564GOLD0001",
            "securityIdentifier": "XS0000000001",
            "safekeepingAccount": "SYNTHSAFE01",
            "eligibleQuantity": "1000",
            "electionDeadline": "2099-08-10",
            "paymentDate": "2099-08-15",
            "options": [
                {"optionNumber": 1, "optionCode": "CASH", "defaultOption": True},
                {
                    "optionNumber": 2,
                    "optionCode": "SECURITIES",
                    "defaultOption": False,
                },
            ],
        }
    )
    instruction = CorporateActionInstructionRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA565GOLD0001",
            "notificationMessageId": "NOTIFICATION-ID",
            "optionNumber": 1,
            "instructedQuantity": "800",
        }
    )
    report = ValidationReport.model_validate(
        {
            "status": "VALID",
            "profileId": "BASE_DEMO_V1",
            "profileVersion": "1.0.0",
            "findings": [],
            "errorCount": 0,
            "warningCount": 0,
        }
    )
    instruction_message = WorkflowGeneratedMessage.model_validate(
        {
            "messageId": "INSTRUCTION-ID",
            "workflowId": notification.workflow_id,
            "workflowModule": "CORPORATE_ACTIONS",
            "resolvedMessageType": "MT565",
            "canonicalData": {"messageReference": instruction.message_reference},
            "rawMessage": "synthetic",
            "fieldMap": [],
            "profileId": "BASE_DEMO_V1",
            "profileVersion": "1.0.0",
            "validation": report,
        }
    )
    status = CorporateActionStatusRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA567GOLD0001",
            "instructionMessageId": "INSTRUCTION-ID",
            "status": "PENDING",
        }
    )
    confirmation = CorporateActionConfirmationRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA566GOLD0001",
            "instructionMessageId": "INSTRUCTION-ID",
            "optionNumber": 1,
            "confirmedQuantity": "800",
            "cashCurrency": "USD",
            "cashAmount": "125.50",
            "paymentDate": "2099-08-15",
        }
    )
    narrative = CorporateActionNarrativeRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA568GOLD0001",
            "notificationMessageId": "NOTIFICATION-ID",
            "narrative": "SYNTHETIC SUPPORTING INFORMATION ONLY.",
        }
    )
    composer = CorporateActionComposer()
    return {
        "mt564": composer.notification(notification).raw_message,
        "mt565": composer.instruction(
            instruction, notification, notification.options[0]
        ).raw_message,
        "mt567": composer.status(status, notification, instruction_message).raw_message,
        "mt566": composer.confirmation(
            confirmation, notification, notification.options[0], instruction_message
        ).raw_message,
        "mt568": composer.narrative(narrative, notification).raw_message,
    }


@pytest.mark.parametrize("message_type", ["mt564", "mt565", "mt566", "mt567", "mt568"])
def test_corporate_action_message_matches_golden(message_type: str) -> None:
    expected = (Path(__file__).parent / "expected" / f"{message_type}.txt").read_text(
        encoding="utf-8"
    )
    assert _fixtures()[message_type] == expected.rstrip("\n")

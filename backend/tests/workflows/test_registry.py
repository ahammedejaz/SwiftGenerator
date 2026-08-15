from dataclasses import replace

import pytest

from app.domain.enums import MessageType
from app.knowledge.models import WorkflowModuleId
from app.workflows.registry import WorkflowRegistry, workflow_registry


def test_registry_has_one_owner_for_every_implemented_message() -> None:
    expected = {
        MessageType.MT530,
        MessageType.MT537,
        *[MessageType(f"MT{number}") for number in range(540, 549)],
        *[MessageType(f"MT{number}") for number in range(564, 569)],
    }
    assert {
        message_type
        for module in workflow_registry.catalogue().modules
        for message_type in module.supported_message_types
    } == expected
    assert workflow_registry.module_for(MessageType.MT541).module_id == WorkflowModuleId.SETTLEMENT
    assert workflow_registry.module_for(MessageType.MT537).module_id == WorkflowModuleId.PENALTIES


def test_registry_rejects_duplicate_ownership() -> None:
    module = workflow_registry.module_for(MessageType.MT530)
    duplicate_owner = replace(module, module_id=WorkflowModuleId.PENALTIES)
    with pytest.raises(ValueError, match="multiple modules"):
        WorkflowRegistry([module, duplicate_owner])


def test_capability_api_distinguishes_implemented_partial_and_planned(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/capabilities?profileId=BASE_DEMO_V1")
    assert response.status_code == 200
    payload = response.json()
    statuses = {item["moduleId"]: item["status"] for item in payload["modules"]}
    assert statuses["SETTLEMENT"] == "IMPLEMENTED"
    assert statuses["PENALTIES"] == "PARTIALLY_IMPLEMENTED"
    assert statuses["CORPORATE_ACTIONS"] == "PARTIALLY_IMPLEMENTED"
    assert "ISO 20022 equivalents" in payload["plannedWorkflows"]
    assert "All SWIFT messages" in payload["unsupportedClaims"]
    assert all(item["knowledgeRecordCount"] > 0 for item in payload["modules"])


def test_unknown_message_has_no_implicit_owner() -> None:
    empty = WorkflowRegistry([])
    with pytest.raises(KeyError, match="No workflow module owns"):
        empty.module_for(MessageType.MT541)

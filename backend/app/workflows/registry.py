from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from app.domain.enums import MessageType
from app.domain.models import ApiModel
from app.knowledge.loader import TagKnowledgeRepository, knowledge_repository
from app.knowledge.models import TagKnowledge, WorkflowModuleId
from app.profiles.loader import ClientProfile


class CapabilityStatus(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    DISABLED = "DISABLED"
    PLANNED = "PLANNED"
    UNSUPPORTED = "UNSUPPORTED"


class WorkflowCapability(ApiModel):
    module_id: WorkflowModuleId
    display_name: str
    status: CapabilityStatus
    enabled: bool
    supported_message_types: list[MessageType]
    implemented_features: list[str]
    limitations: list[str]
    knowledge_record_count: int


class CapabilityCatalogue(ApiModel):
    modules: list[WorkflowCapability]
    planned_workflows: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    registry_version: str


class WorkflowModule(Protocol):
    @property
    def module_id(self) -> WorkflowModuleId: ...

    @property
    def supported_message_types(self) -> frozenset[MessageType]: ...

    def capability(
        self,
        profile: ClientProfile | None,
        knowledge: TagKnowledgeRepository,
    ) -> WorkflowCapability: ...

    def knowledge_records(self, knowledge: TagKnowledgeRepository) -> list[TagKnowledge]: ...


@dataclass(frozen=True)
class RegisteredWorkflowModule:
    module_id: WorkflowModuleId
    display_name: str
    supported_message_types: frozenset[MessageType]
    status: CapabilityStatus
    implemented_features: tuple[str, ...]
    limitations: tuple[str, ...]

    def knowledge_records(self, knowledge: TagKnowledgeRepository) -> list[TagKnowledge]:
        return [
            effective.record for effective in knowledge.list_records(workflow_module=self.module_id)
        ]

    def capability(
        self,
        profile: ClientProfile | None,
        knowledge: TagKnowledgeRepository,
    ) -> WorkflowCapability:
        enabled_types = self.supported_message_types
        if profile is not None:
            enabled_types = enabled_types.intersection(profile.supported_message_types)
        return WorkflowCapability(
            module_id=self.module_id,
            display_name=self.display_name,
            status=self.status if enabled_types else CapabilityStatus.DISABLED,
            enabled=bool(enabled_types),
            supported_message_types=sorted(enabled_types, key=lambda item: item.value),
            implemented_features=list(self.implemented_features),
            limitations=list(self.limitations),
            knowledge_record_count=len(self.knowledge_records(knowledge)),
        )


class WorkflowRegistry:
    registry_version = "workflow-registry-v1"

    def __init__(self, modules: list[WorkflowModule]) -> None:
        self._modules = {module.module_id: module for module in modules}
        if len(self._modules) != len(modules):
            raise ValueError("Workflow module IDs must be unique")
        owners: dict[MessageType, WorkflowModuleId] = {}
        for module in modules:
            for message_type in module.supported_message_types:
                if message_type in owners:
                    raise ValueError(
                        f"Message type {message_type.value} is owned by multiple modules"
                    )
                owners[message_type] = module.module_id
        self._owners = owners

    def module_for(self, message_type: MessageType) -> WorkflowModule:
        try:
            return self._modules[self._owners[message_type]]
        except KeyError as exc:
            raise KeyError(f"No workflow module owns {message_type.value}") from exc

    def catalogue(self, profile: ClientProfile | None = None) -> CapabilityCatalogue:
        return CapabilityCatalogue(
            modules=[
                module.capability(profile, knowledge_repository)
                for module in self._modules.values()
            ],
            planned_workflows=[
                "Additional Category 5 messages",
                "Statements and reconciliation",
                "Collateral workflows",
                "Trade confirmation workflows",
                "Treasury messages",
                "Payment messages",
                "ISO 20022 equivalents",
            ],
            unsupported_claims=[
                "All SWIFT messages",
                "Universal amendment handling",
                "SWIFT network certification",
                "Institution-independent production validity",
            ],
            registry_version=self.registry_version,
        )


workflow_registry = WorkflowRegistry(
    [
        RegisteredWorkflowModule(
            module_id=WorkflowModuleId.SETTLEMENT,
            display_name="Settlement Instructions, Confirmations, and Status",
            supported_message_types=frozenset(
                MessageType(value)
                for value in [
                    "MT540",
                    "MT541",
                    "MT542",
                    "MT543",
                    "MT544",
                    "MT545",
                    "MT546",
                    "MT547",
                    "MT548",
                ]
            ),
            status=CapabilityStatus.IMPLEMENTED,
            implemented_features=(
                "MT540–MT548 deterministic generation",
                "Instruction/status/confirmation correlation",
                "Controlled negative testing",
            ),
            limitations=("Configured demonstration field subset only",),
        ),
        RegisteredWorkflowModule(
            module_id=WorkflowModuleId.SETTLEMENT_COMMAND,
            display_name="Settlement Processing and Amendment",
            supported_message_types=frozenset({MessageType.MT530}),
            status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
            implemented_features=(
                "Priority modification command",
                "Instruction cancellation",
                "Cancel and rebook decisioning",
            ),
            limitations=("MT530 is limited to the verified priority command",),
        ),
        RegisteredWorkflowModule(
            module_id=WorkflowModuleId.PENALTIES,
            display_name="Penalty Statements",
            supported_message_types=frozenset({MessageType.MT537}),
            status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
            implemented_features=(
                "New, updated, and removed penalties",
                "Settlement-fail and late-matching-fail reporting",
            ),
            limitations=("Penalty amounts are supplied, never calculated",),
        ),
        RegisteredWorkflowModule(
            module_id=WorkflowModuleId.CORPORATE_ACTIONS,
            display_name="Corporate Actions",
            supported_message_types=frozenset(
                {
                    MessageType.MT564,
                    MessageType.MT565,
                    MessageType.MT566,
                    MessageType.MT567,
                    MessageType.MT568,
                }
            ),
            status=CapabilityStatus.PARTIALLY_IMPLEMENTED,
            implemented_features=(
                "Dividend-with-options notification and cash election",
                "Instruction status, cash confirmation, and narrative",
            ),
            limitations=(
                "Only DVOP is enabled",
                "Securities-movement confirmation is not enabled",
            ),
        ),
    ]
)

from app.composers.base import CompositionResult, MessageComposer
from app.domain.enums import GenerationMode, MessageType, NegativeMutation
from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile


class SettlementStatusComposer(MessageComposer):
    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        del profile
        if scenario.message_type != MessageType.MT548:
            raise ValueError("The settlement status composer requires MT548")
        required = (
            scenario.sender_reference,
            scenario.function,
            scenario.status.category,
            scenario.status.code,
            scenario.status.reason_code,
            scenario.status.related_instruction_message_type,
        )
        if any(value is None for value in required):
            raise ValueError("Composer received an incomplete MT548 scenario")
        assert scenario.function is not None
        assert scenario.status.category is not None
        assert scenario.status.related_instruction_message_type is not None
        missing_related_mutation = (
            scenario.test_configuration.mode == GenerationMode.NEGATIVE_TEST
            and scenario.test_configuration.mutation
            == NegativeMutation.MT548_MISSING_RELATED_REFERENCE
        )
        if scenario.related_reference is None and not missing_related_mutation:
            raise ValueError("Composer received an MT548 without a related reference")

        fields: list[RenderedField] = []
        lines = ["{1:DEMONSTRATION}", "{2:MT548}", "{4:"]

        def add(
            sequence: str,
            tag: str,
            qualifier: str | None,
            value: str,
            path: str,
            meaning: str,
        ) -> None:
            lines.append(f":{tag}::{qualifier}//{value}" if qualifier else f":{tag}:{value}")
            fields.append(
                RenderedField(
                    sequence=sequence,
                    tag=tag,
                    qualifier=qualifier,
                    value=value,
                    business_path=path,
                    business_meaning=meaning,
                )
            )

        lines.append(":16R:GENL")
        add(
            "A",
            "20C",
            "SEME",
            scenario.sender_reference or "",
            "senderReference",
            "Status reference",
        )
        if scenario.related_reference is not None:
            add(
                "A",
                "20C",
                "RELA",
                scenario.related_reference,
                "relatedReference",
                "Instruction reference",
            )
        add("A", "23G", None, scenario.function.value, "function", "Message function")
        lines.append(":16S:GENL")

        lines.append(":16R:LINK")
        add(
            "A1",
            "13A",
            "LINK",
            scenario.status.related_instruction_message_type.value.removeprefix("MT"),
            "status.relatedInstructionMessageType",
            "Related instruction message type",
        )
        lines.append(":16S:LINK")

        lines.append(":16R:STAT")
        add("D", "25D", "SETT", scenario.status.code or "", "status.code", "Processing status")
        add(
            "D",
            "24B",
            scenario.status.code,
            scenario.status.reason_code or "",
            "status.reasonCode",
            "Controlled status reason",
        )
        if scenario.status.narrative:
            add(
                "D",
                "70D",
                "REAS",
                scenario.status.narrative,
                "status.narrative",
                "Reason narrative",
            )
        lines.append(":16S:STAT")
        lines.append("-}")
        return CompositionResult(raw_message="\n".join(lines), field_map=fields)

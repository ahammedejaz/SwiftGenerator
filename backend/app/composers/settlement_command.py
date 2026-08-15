from app.composers.base import CompositionResult, MessageComposer
from app.domain.enums import MessageFunction, MessageType, SettlementCommandType
from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile


class SettlementCommandComposer(MessageComposer):
    """Compose the source-bounded MT530 priority-modification subset."""

    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        del profile
        if scenario.message_type != MessageType.MT530:
            raise ValueError("The settlement command composer supports MT530 only")
        if scenario.function != MessageFunction.NEWM:
            raise ValueError("The supported MT530 subset uses NEWM only")
        if scenario.command.command_type != SettlementCommandType.MODIFY_PRIORITY:
            raise ValueError("Only the verified MT530 priority command is enabled")
        required = (
            scenario.sender_reference,
            scenario.account.safekeeping_account,
            scenario.command.original_instruction_reference,
            scenario.command.priority,
        )
        if any(value is None for value in required):
            raise ValueError("Composer received an incomplete MT530 priority command")
        assert scenario.command.priority is not None

        fields: list[RenderedField] = []
        lines = ["{1:DEMONSTRATION}", "{2:MT530}", "{4:"]

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
            "Command reference",
        )
        add("A", "23G", None, MessageFunction.NEWM.value, "function", "Message function")
        add(
            "A",
            "97A",
            "SAFE",
            scenario.account.safekeeping_account or "",
            "account.safekeepingAccount",
            "Safekeeping account",
        )
        lines.append(":16S:GENL")
        lines.append(":16R:REQD")
        add(
            "B",
            "20C",
            "PREV",
            scenario.command.original_instruction_reference or "",
            "command.originalInstructionReference",
            "Previous instruction reference",
        )
        add(
            "B",
            "22F",
            "PRIR",
            f"{scenario.command.priority:04d}",
            "command.priority",
            "Execution priority",
        )
        lines.append(":16S:REQD")
        lines.append("-}")
        return CompositionResult(raw_message="\n".join(lines), field_map=fields)

from app.composers.base import CompositionResult, MessageComposer, swift_decimal
from app.domain.enums import Direction, MessageType
from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile


class FopConfirmationComposer(MessageComposer):
    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        del profile
        if scenario.message_type not in {MessageType.MT544, MessageType.MT546}:
            raise ValueError("The FOP confirmation composer supports MT544 and MT546")
        required = (
            scenario.sender_reference,
            scenario.related_reference,
            scenario.function,
            scenario.security.identifier,
            scenario.account.safekeeping_account,
            scenario.settlement.place_of_settlement,
            scenario.settlement.delivering_agent,
            scenario.settlement.receiving_agent,
            scenario.confirmation.actual_settlement_date,
            scenario.confirmation.settled_quantity,
            scenario.confirmation.settlement_result,
        )
        if any(value is None for value in required):
            raise ValueError("Composer received an incomplete FOP confirmation")
        assert scenario.function is not None
        assert scenario.confirmation.actual_settlement_date is not None
        assert scenario.confirmation.settlement_result is not None

        fields: list[RenderedField] = []
        lines = ["{1:DEMONSTRATION}", f"{{2:{scenario.message_type.value}}}", "{4:"]

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
            "Confirmation reference",
        )
        add(
            "A",
            "20C",
            "RELA",
            scenario.related_reference or "",
            "relatedReference",
            "Instruction reference",
        )
        if scenario.client_reference:
            add(
                "A", "20C", "COMM", scenario.client_reference, "clientReference", "Client reference"
            )
        add("A", "23G", None, scenario.function.value, "function", "Message function")
        lines.append(":16S:GENL")

        lines.append(":16R:CONFDET")
        add(
            "B",
            "98A",
            "ESET",
            scenario.confirmation.actual_settlement_date.strftime("%Y%m%d"),
            "confirmation.actualSettlementDate",
            "Actual settlement date",
        )
        add(
            "B",
            "35B",
            None,
            f"ISIN {scenario.security.identifier}",
            "security.identifier",
            "Security identifier",
        )
        add(
            "B",
            "36B",
            "ESTT",
            f"UNIT/{swift_decimal(scenario.confirmation.settled_quantity)}",
            "confirmation.settledQuantity",
            "Settled quantity",
        )
        add(
            "B",
            "22F",
            "STCO",
            scenario.confirmation.settlement_result.value,
            "confirmation.settlementResult",
            "Full or partial settlement result",
        )
        lines.append(":16S:CONFDET")

        lines.append(":16R:FIAC")
        add(
            "C",
            "97A",
            "SAFE",
            scenario.account.safekeeping_account or "",
            "account.safekeepingAccount",
            "Safekeeping account",
        )
        lines.append(":16S:FIAC")

        lines.append(":16R:SETDET")
        add(
            "E",
            "95R",
            "PSET",
            f"SYNTH/{scenario.settlement.place_of_settlement}",
            "settlement.placeOfSettlement",
            "Synthetic place of settlement",
        )
        # A receipt names the chain that delivers; a delivery names the chain that
        # receives. Emitting both made every instruction require its own counterparty twice.
        if scenario.direction == Direction.RECEIVE:
            add(
                "E",
                "95R",
                "DEAG",
                f"SYNTH/{scenario.settlement.delivering_agent}",
                "settlement.deliveringAgent",
                "Synthetic delivering agent",
            )
        else:
            add(
                "E",
                "95R",
                "REAG",
                f"SYNTH/{scenario.settlement.receiving_agent}",
                "settlement.receivingAgent",
                "Synthetic receiving agent",
            )
        lines.append(":16S:SETDET")
        lines.append("-}")
        return CompositionResult(raw_message="\n".join(lines), field_map=fields)

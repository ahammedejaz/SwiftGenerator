from app.composers.base import CompositionResult, MessageComposer, swift_decimal
from app.domain.enums import Direction, GenerationMode, MessageType, NegativeMutation
from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile


class FopInstructionComposer(MessageComposer):
    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        del profile
        if scenario.message_type not in {MessageType.MT540, MessageType.MT542}:
            raise ValueError("The FOP instruction composer supports MT540 and MT542")
        required = (
            scenario.sender_reference,
            scenario.function,
            scenario.trade.trade_date,
            scenario.trade.settlement_date,
            scenario.trade.transaction_type,
            scenario.security.identifier,
            scenario.security.quantity,
            scenario.account.safekeeping_account,
            scenario.settlement.delivering_agent,
            scenario.settlement.receiving_agent,
            scenario.direction,
        )
        if any(value is None for value in required):
            raise ValueError("Composer received an incomplete FOP instruction")
        assert scenario.function is not None
        assert scenario.trade.trade_date is not None
        assert scenario.trade.settlement_date is not None
        assert scenario.trade.transaction_type is not None
        assert scenario.direction is not None
        missing_pset_mutation = (
            scenario.test_configuration.mode == GenerationMode.NEGATIVE_TEST
            and scenario.test_configuration.mutation == NegativeMutation.MISSING_PLACE_OF_SETTLEMENT
        )
        if scenario.settlement.place_of_settlement is None and not missing_pset_mutation:
            raise ValueError("Composer received an instruction without a place of settlement")

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
            "Sender reference",
        )
        if scenario.related_reference:
            add(
                "A",
                "20C",
                "PREV",
                scenario.related_reference,
                "relatedReference",
                "Previous instruction reference",
            )
        if scenario.client_reference:
            add(
                "A", "20C", "COMM", scenario.client_reference, "clientReference", "Client reference"
            )
        add("A", "23G", None, scenario.function.value, "function", "Message function")
        lines.append(":16S:GENL")

        lines.append(":16R:TRADDET")
        add(
            "B",
            "98A",
            "TRAD",
            scenario.trade.trade_date.strftime("%Y%m%d"),
            "trade.tradeDate",
            "Trade date",
        )
        add(
            "B",
            "98A",
            "SETT",
            scenario.trade.settlement_date.strftime("%Y%m%d"),
            "trade.settlementDate",
            "Intended settlement date",
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
            "SETT",
            f"UNIT/{swift_decimal(scenario.security.quantity)}",
            "security.quantity",
            "Settlement quantity",
        )
        add(
            "B",
            "22F",
            "SETR",
            scenario.trade.transaction_type.value,
            "trade.transactionType",
            "Transaction type",
        )
        lines.append(":16S:TRADDET")

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
        direction_code = "RECE" if scenario.direction == Direction.RECEIVE else "DELI"
        add(
            "E",
            "22F",
            "SETR",
            direction_code,
            "direction",
            f"{scenario.direction.value.title()} direction",
        )
        if scenario.settlement.place_of_settlement is not None:
            add(
                "E",
                "95R",
                "PSET",
                f"SYNTH/{scenario.settlement.place_of_settlement}",
                "settlement.placeOfSettlement",
                "Synthetic place of settlement",
            )
        add(
            "E",
            "95R",
            "DEAG",
            f"SYNTH/{scenario.settlement.delivering_agent}",
            "settlement.deliveringAgent",
            "Synthetic delivering agent",
        )
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

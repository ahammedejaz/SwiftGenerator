from app.composers.base import CompositionResult, MessageComposer, swift_decimal
from app.domain.enums import Direction, GenerationMode, MessageType, NegativeMutation
from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile

#: The transaction type an ordinary settlement of a trade carries in 22F::SETR.
#:
#: Reconciled against this repository's own ISO 20022 definition of the same business
#: message — sese.023.001.11 SttlmParams/SctiesTxTp/Cd — whose configured code list is the
#: authority for this field. Receive versus deliver is carried by the message type, and a
#: buy/sell classification is not a settlement transaction type at all.
SETTLEMENT_TRANSACTION_TYPE_CODE = "TRAD"



class DvpInstructionComposer(MessageComposer):
    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        if scenario.message_type not in {MessageType.MT541, MessageType.MT543}:
            raise ValueError("The DVP instruction composer supports MT541 and MT543")
        required_objects = (
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
            scenario.settlement.currency,
        )
        if any(value is None for value in required_objects):
            raise ValueError("Composer received an incomplete MT541 scenario")
        missing_amount_mutation = (
            scenario.test_configuration.mode == GenerationMode.NEGATIVE_TEST
            and scenario.test_configuration.mutation == NegativeMutation.MISSING_SETTLEMENT_AMOUNT
        )
        if scenario.settlement.amount is None and not missing_amount_mutation:
            raise ValueError("Composer received an MT541 without a settlement amount")
        missing_pset_mutation = (
            scenario.test_configuration.mode == GenerationMode.NEGATIVE_TEST
            and scenario.test_configuration.mutation == NegativeMutation.MISSING_PLACE_OF_SETTLEMENT
        )
        if scenario.settlement.place_of_settlement is None and not missing_pset_mutation:
            raise ValueError("Composer received an instruction without a place of settlement")
        assert scenario.function is not None
        assert scenario.trade.transaction_type is not None

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
            if qualifier:
                lines.append(f":{tag}::{qualifier}//{value}")
            else:
                lines.append(f":{tag}:{value}")
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
                "A",
                "20C",
                "COMM",
                scenario.client_reference,
                "clientReference",
                "Client reference",
            )
        add("A", "23G", None, scenario.function.value, "function", "Message function")
        lines.append(":16S:GENL")

        lines.append(":16R:TRADDET")
        add(
            "B",
            "98A",
            "TRAD",
            scenario.trade.trade_date.strftime("%Y%m%d"),  # type: ignore[union-attr]
            "trade.tradeDate",
            "Trade date",
        )
        add(
            "B",
            "98A",
            "SETT",
            scenario.trade.settlement_date.strftime("%Y%m%d"),  # type: ignore[union-attr]
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
        # 22F::SETR states the *type* of settlement transaction, not the direction. The
        # message type already carries receive versus deliver — that is what selected
        # MT540..MT543 in the first place — and BUY/SELL is not a transaction-type code.
        # Reconciled against this repository's own sese.023 definition of the same message.
        add(
            "E",
            "22F",
            "SETR",
            SETTLEMENT_TRANSACTION_TYPE_CODE,
            "trade.transactionType",
            "Settlement transaction type",
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
        if scenario.settlement.amount is not None:
            add(
                "E",
                "19A",
                "SETT",
                f"{scenario.settlement.currency}{swift_decimal(scenario.settlement.amount, 2)}",
                "settlement.amount",
                "Settlement currency and amount",
            )
        lines.append(":16S:SETDET")
        lines.append("-}")
        return CompositionResult(raw_message="\n".join(lines), field_map=fields)

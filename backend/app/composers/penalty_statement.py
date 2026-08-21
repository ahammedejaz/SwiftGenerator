from decimal import Decimal

from app.composers.base import CompositionResult, swift_decimal
from app.domain.enums import (
    AmountDirection,
    PenaltyListType,
    PenaltyStatus,
    PenaltyType,
)
from app.domain.models import RenderedField
from app.knowledge.presentation import qualifier_separator_for
from app.workflows.penalties import PenaltyStatement

LIST_CODES = {
    PenaltyListType.CURRENT: "CURR",
    PenaltyListType.NEW_ONLY: "FWIS",
    PenaltyListType.UPDATED_OR_REMOVED: "FWAM",
}
TYPE_CODES = {
    PenaltyType.SETTLEMENT_FAIL: "SEFP",
    PenaltyType.LATE_MATCHING_FAIL: "LMFP",
}
STATUS_CODES = {
    PenaltyStatus.ACTIVE: "ACTV",
    PenaltyStatus.NOT_COMPUTED: "NCOM",
    PenaltyStatus.REMOVED: "REMO",
}


class PenaltyStatementComposer:
    def compose(self, statement: PenaltyStatement) -> CompositionResult:
        fields: list[RenderedField] = []
        lines = ["{1:DEMONSTRATION}", "{2:MT537}", "{4:"]

        def add(
            sequence: str,
            tag: str,
            qualifier: str | None,
            value: str,
            path: str,
            meaning: str,
        ) -> None:
            lines.append(
                f":{tag}::{qualifier}{qualifier_separator_for(tag)}{value}"
                if qualifier
                else f":{tag}:{value}"
            )
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

        first = statement.penalties[0]
        lines.append(":16R:GENL")
        add("A", "28E", None, "1/ONLY", "pagination", "Single demonstration page")
        add(
            "A",
            "20C",
            "SEME",
            statement.statement_reference,
            "statementReference",
            "Statement reference",
        )
        add("A", "23G", None, "PENA", "function", "Penalty statement function")
        add(
            "A",
            "98A",
            "STAT",
            statement.statement_date.strftime("%Y%m%d"),
            "statementDate",
            "Statement date",
        )
        add("A", "22H", "STST", "PENA", "statementStructure", "Penalty statement structure")
        add(
            "A",
            "97A",
            "SAFE",
            statement.safekeeping_account,
            "safekeepingAccount",
            "Safekeeping account",
        )
        add("A", "17B", "ACTI", "Y", "activity", "Penalty activity present")
        lines.append(":16S:GENL")

        lines.append(":16R:PENA")
        add("D", "22F", "CODE", LIST_CODES[statement.list_type], "listType", "Penalty list type")
        lines.append(":16R:PENACUR")
        add("D1", "11A", "PECU", first.currency, "penalties.currency", "Penalty currency")
        add(
            "D1",
            "98A",
            "DACO",
            first.detection_date.strftime("%Y%m%d"),
            "penalties.detectionDate",
            "Penalty detection date",
        )
        add(
            "D1",
            "95R",
            "ASDP",
            f"BFSDEMO1/{statement.account_servicer}",
            "accountServicer",
            "Synthetic account servicer",
        )
        add("D1", "22F", "TRCA", "CSDP", "accountServicerCapacity", "Configured party capacity")

        lines.append(":16R:PENACOUNT")
        add(
            "D1a",
            "95R",
            "REPA",
            f"BFSDEMO1/{statement.related_party}",
            "relatedParty",
            "Synthetic related party",
        )
        add("D1a", "22F", "TRCA", "CSDP", "relatedPartyCapacity", "Configured party capacity")
        net = sum(
            (
                item.amount if item.amount_direction == AmountDirection.RECEIVABLE else -item.amount
                for item in statement.penalties
            ),
            start=Decimal("0"),
        )
        add(
            "D1a",
            "19A",
            "AGNT",
            _amount(first.currency, net),
            "netAmount",
            "Bilateral net of supplied amounts",
        )

        for index, penalty in enumerate(statement.penalties):
            prefix = f"penalties.{index}"
            lines.append(":16R:PENDET")
            add(
                "D1a1",
                "20C",
                "PREF",
                penalty.penalty_reference,
                f"{prefix}.penaltyReference",
                "Penalty reference",
            )
            if penalty.common_reference:
                add(
                    "D1a1",
                    "20C",
                    "PCOM",
                    penalty.common_reference,
                    f"{prefix}.commonReference",
                    "Penalty common reference",
                )
            if penalty.previous_penalty_reference:
                add(
                    "D1a1",
                    "20C",
                    "PPRF",
                    penalty.previous_penalty_reference,
                    f"{prefix}.previousPenaltyReference",
                    "Previous penalty reference",
                )
            add(
                "D1a1",
                "22H",
                "PNTP",
                TYPE_CODES[penalty.penalty_type],
                f"{prefix}.penaltyType",
                "Penalty type",
            )
            add(
                "D1a1",
                "25D",
                "PNST",
                STATUS_CODES[penalty.status],
                f"{prefix}.status",
                "Penalty status",
            )
            signed = (
                penalty.amount
                if penalty.amount_direction == AmountDirection.RECEIVABLE
                else -penalty.amount
            )
            add(
                "D1a1",
                "19A",
                "AMCO",
                _amount(penalty.currency, signed),
                f"{prefix}.amount",
                "Supplied computed penalty amount",
            )
            add(
                "D1a1",
                "99A",
                "DAAC",
                str(penalty.number_of_days),
                f"{prefix}.numberOfDays",
                "Supplied number of days",
            )
            if penalty.related_instruction_reference:
                lines.append(":16R:RELTRAN")
                add(
                    "D1a1B",
                    "20C",
                    "RELA",
                    penalty.related_instruction_reference,
                    f"{prefix}.relatedInstructionReference",
                    "Related settlement reference",
                )
                lines.append(":16S:RELTRAN")
            lines.append(":16S:PENDET")
        lines.extend([":16S:PENACOUNT", ":16S:PENACUR", ":16S:PENA", "-}"])
        return CompositionResult(raw_message="\n".join(lines), field_map=fields)


def _amount(currency: str, value: Decimal) -> str:
    sign = "N" if value < 0 else ""
    return f"{sign}{currency}{swift_decimal(abs(value), 2)}"

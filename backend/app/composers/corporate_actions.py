from __future__ import annotations

from decimal import Decimal

from app.composers.base import CompositionResult, swift_decimal
from app.domain.enums import (
    CorporateActionInstructionStatus,
    CorporateActionOptionCode,
)
from app.domain.models import RenderedField
from app.knowledge.presentation import qualifier_separator_for
from app.workflows.corporate_actions import (
    CorporateActionConfirmationRequest,
    CorporateActionInstructionRequest,
    CorporateActionNarrativeRequest,
    CorporateActionNotification,
    CorporateActionOption,
    CorporateActionStatusRequest,
)
from app.workflows.models import WorkflowGeneratedMessage

OPTION_CODES = {
    CorporateActionOptionCode.CASH: "CASH",
    CorporateActionOptionCode.SECURITIES: "SECU",
}
STATUS_CODES = {
    CorporateActionInstructionStatus.ACKNOWLEDGED: ("INST", "IPRC", "PACK"),
    CorporateActionInstructionStatus.PENDING: ("INST", "IPRC", "PEND"),
    CorporateActionInstructionStatus.REJECTED: ("INST", "IPRC", "REJT"),
    CorporateActionInstructionStatus.CANCELLATION_ACKNOWLEDGED: ("CAST", "CPRC", "PACK"),
    CorporateActionInstructionStatus.CANCELLATION_REJECTED: ("CAST", "CPRC", "REJT"),
}


class _Builder:
    def __init__(self, message_type: str) -> None:
        self.lines = ["{1:DEMONSTRATION}", f"{{2:{message_type}}}", "{4:"]
        self.fields: list[RenderedField] = []

    def start(self, name: str) -> None:
        self.lines.append(f":16R:{name}")

    def end(self, name: str) -> None:
        self.lines.append(f":16S:{name}")

    def add(
        self,
        sequence: str,
        tag: str,
        qualifier: str | None,
        value: str,
        path: str,
        meaning: str,
    ) -> None:
        self.lines.append(
            f":{tag}::{qualifier}{qualifier_separator_for(tag)}{value}"
            if qualifier
            else f":{tag}:{value}"
        )
        self.fields.append(
            RenderedField(
                sequence=sequence,
                tag=tag,
                qualifier=qualifier,
                value=value,
                business_path=path,
                business_meaning=meaning,
            )
        )

    def result(self) -> CompositionResult:
        self.lines.append("-}")
        return CompositionResult(raw_message="\n".join(self.lines), field_map=self.fields)


class CorporateActionComposer:
    """Source-bounded deterministic composers for the DVOP demonstration lifecycle."""

    def notification(self, item: CorporateActionNotification) -> CompositionResult:
        out = _Builder("MT564")
        out.start("GENL")
        _references(out, item.event_reference, item.message_reference)
        out.add("A", "23G", None, "NEWM", "function", "New notification")
        out.add("A", "22F", "CAEV", "DVOP", "eventType", "Dividend with options")
        out.add("A", "22F", "CAMV", "VOLU", "classification", "Voluntary event")
        out.add("A", "25D", "PROC", "COMP", "processingStatus", "Complete notification")
        out.end("GENL")

        out.start("USECU")
        out.add(
            "B",
            "35B",
            None,
            f"ISIN {item.security_identifier}",
            "securityIdentifier",
            "Underlying security",
        )
        out.start("ACCTINFO")
        out.add("B1", "97A", "SAFE", item.safekeeping_account, "safekeepingAccount", "Account")
        out.end("ACCTINFO")
        out.add(
            "B",
            "93B",
            "ELIG",
            f"UNIT/{_quantity(item.eligible_quantity)}",
            "eligibleQuantity",
            "Eligible balance",
        )
        out.end("USECU")

        out.start("CADETL")
        out.add(
            "C",
            "98A",
            "PAYD",
            item.payment_date.strftime("%Y%m%d"),
            "paymentDate",
            "Payment date",
        )
        out.end("CADETL")
        for index, option in enumerate(item.options):
            out.start("CAOPTN")
            prefix = f"options.{index}"
            out.add(
                "E",
                "13A",
                "CAON",
                f"{option.option_number:03d}",
                f"{prefix}.optionNumber",
                "Corporate-action option number",
            )
            out.add(
                "E",
                "22F",
                "CAOP",
                OPTION_CODES[option.option_code],
                f"{prefix}.optionCode",
                "Corporate-action option code",
            )
            out.add(
                "E",
                "17B",
                "DFLT",
                "Y" if option.default_option else "N",
                f"{prefix}.defaultOption",
                "Default-option flag",
            )
            out.add(
                "E",
                "98A",
                "RDDT",
                item.election_deadline.strftime("%Y%m%d"),
                "electionDeadline",
                "Response deadline",
            )
            out.end("CAOPTN")
        return out.result()

    def instruction(
        self,
        request: CorporateActionInstructionRequest,
        event: CorporateActionNotification,
        option: CorporateActionOption,
    ) -> CompositionResult:
        out = _Builder("MT565")
        out.start("GENL")
        _references(out, event.event_reference, request.message_reference)
        out.add("A", "23G", None, "NEWM", "function", "New corporate-action instruction")
        out.add("A", "22F", "CAEV", "DVOP", "eventType", "Dividend with options")
        out.end("GENL")
        _link(out, event.message_reference)
        out.start("USECU")
        out.add(
            "B", "35B", None, f"ISIN {event.security_identifier}", "securityIdentifier", "Security"
        )
        out.start("ACCTINFO")
        out.add("B1", "97A", "SAFE", event.safekeeping_account, "safekeepingAccount", "Account")
        out.end("ACCTINFO")
        out.end("USECU")
        out.start("CAINST")
        out.add(
            "D", "13A", "CAON", f"{option.option_number:03d}", "optionNumber", "Selected option"
        )
        out.add(
            "D",
            "22F",
            "CAOP",
            OPTION_CODES[option.option_code],
            "optionCode",
            "Selected option code",
        )
        out.add(
            "D",
            "36B",
            "QINS",
            f"UNIT/{_quantity(request.instructed_quantity)}",
            "instructedQuantity",
            "Instructed quantity",
        )
        out.end("CAINST")
        return out.result()

    def status(
        self,
        request: CorporateActionStatusRequest,
        event: CorporateActionNotification,
        instruction: WorkflowGeneratedMessage,
    ) -> CompositionResult:
        function, qualifier, code = STATUS_CODES[request.status]
        out = _Builder("MT567")
        out.start("GENL")
        _references(out, event.event_reference, request.message_reference)
        out.add("A", "23G", None, function, "function", "Status function")
        out.add("A", "22F", "CAEV", "DVOP", "eventType", "Dividend with options")
        out.end("GENL")
        _link(out, str(instruction.canonical_data["messageReference"]))
        out.start("STAT")
        out.add("C", "25D", qualifier, code, "status", "Processing status")
        if request.reason_code:
            out.start("REAS")
            out.add(
                "C1",
                "24B",
                qualifier,
                request.reason_code,
                "reasonCode",
                "Controlled status reason",
            )
            out.end("REAS")
        out.end("STAT")
        return out.result()

    def confirmation(
        self,
        request: CorporateActionConfirmationRequest,
        event: CorporateActionNotification,
        option: CorporateActionOption,
        instruction: WorkflowGeneratedMessage,
    ) -> CompositionResult:
        out = _Builder("MT566")
        out.start("GENL")
        _references(out, event.event_reference, request.message_reference)
        out.add("A", "23G", None, "NEWM", "function", "New corporate-action confirmation")
        out.add("A", "22F", "CAEV", "DVOP", "eventType", "Dividend with options")
        out.end("GENL")
        _link(out, str(instruction.canonical_data["messageReference"]))
        out.start("USECU")
        out.add("B", "97A", "SAFE", event.safekeeping_account, "safekeepingAccount", "Account")
        out.add(
            "B", "35B", None, f"ISIN {event.security_identifier}", "securityIdentifier", "Security"
        )
        out.add(
            "B",
            "93B",
            "ELIG",
            f"UNIT/{_quantity(event.eligible_quantity)}",
            "eligibleQuantity",
            "Balance before posting",
        )
        out.end("USECU")
        out.start("CACONF")
        out.add(
            "D", "13A", "CAON", f"{option.option_number:03d}", "optionNumber", "Confirmed option"
        )
        out.add(
            "D",
            "22H",
            "CAOP",
            OPTION_CODES[option.option_code],
            "optionCode",
            "Confirmed option code",
        )
        if option.option_code == CorporateActionOptionCode.CASH:
            assert request.cash_currency and request.cash_amount and request.payment_date
            out.start("CASHMOVE")
            out.add("D2", "22H", "CRDB", "CRED", "cashDirection", "Cash credit")
            out.add(
                "D2",
                "19B",
                "PSTA",
                f"{request.cash_currency}{swift_decimal(request.cash_amount, 2)}",
                "cashAmount",
                "Posted cash amount",
            )
            out.add(
                "D2",
                "98A",
                "POST",
                request.payment_date.strftime("%Y%m%d"),
                "paymentDate",
                "Posting date",
            )
            out.end("CASHMOVE")
        out.end("CACONF")
        return out.result()

    def narrative(
        self,
        request: CorporateActionNarrativeRequest,
        event: CorporateActionNotification,
    ) -> CompositionResult:
        out = _Builder("MT568")
        out.start("GENL")
        _references(out, event.event_reference, request.message_reference)
        out.add("A", "23G", None, "NEWM", "function", "New corporate-action narrative")
        out.add("A", "22F", "CAEV", "DVOP", "eventType", "Dividend with options")
        out.end("GENL")
        _link(out, event.message_reference)
        out.start("ADDINFO")
        out.add("C", "70E", "ADTX", request.narrative, "narrative", "Additional event text")
        out.end("ADDINFO")
        return out.result()


def _references(out: _Builder, event_reference: str, message_reference: str) -> None:
    out.add("A", "20C", "CORP", event_reference, "eventReference", "Corporate-action reference")
    out.add("A", "20C", "SEME", message_reference, "messageReference", "Message reference")


def _link(out: _Builder, related_reference: str) -> None:
    out.start("LINK")
    out.add("A1", "20C", "RELA", related_reference, "relatedReference", "Related message reference")
    out.end("LINK")


def _quantity(value: Decimal) -> str:
    return swift_decimal(value)

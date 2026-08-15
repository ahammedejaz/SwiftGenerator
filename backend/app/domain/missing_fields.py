from typing import Any

from app.domain.enums import MessageType
from app.domain.models import MissingField, MissingFieldsResponse, SettlementScenario
from app.profiles.loader import ClientProfile

QUESTIONS: dict[str, tuple[str, str, str | None]] = {
    "direction": (
        "Will the securities be received or delivered?",
        "Receive means securities enter the account; Deliver means they leave it.",
        "Message family decision",
    ),
    "payment_type": (
        "Will cash be exchanged as part of this settlement?",
        "Against Payment includes a cash leg. Free of Payment does not.",
        "Message family decision",
    ),
    "sender_reference": (
        "What synthetic reference should identify this instruction?",
        "Use a unique demonstration reference so related responses can link to it.",
        "20C/SEME",
    ),
    "client_reference": (
        "What synthetic client reference should be included?",
        "The selected client profile requires its own demonstration reference.",
        "20C/COMM",
    ),
    "trade.transaction_type": (
        "Is the underlying transaction a buy or a sell?",
        "This describes the business transaction independently of settlement direction.",
        "22F/SETR",
    ),
    "trade.trade_date": (
        "What is the trade date?",
        "This is the date on which the trade was agreed.",
        "98A/TRAD",
    ),
    "trade.settlement_date": (
        "What is the intended settlement date?",
        "This is when the securities and cash are expected to settle.",
        "98A/SETT",
    ),
    "security.identifier": (
        "What is the synthetic ISIN for the security?",
        "Use a demonstration identifier, never production security data.",
        "35B/ISIN",
    ),
    "security.quantity": (
        "How many units of the security should settle?",
        "Enter a positive number of securities units.",
        "36B/SETT",
    ),
    "account.safekeeping_account": (
        "What synthetic safekeeping account should be used?",
        "This identifies the demonstration custody account.",
        "97A/SAFE",
    ),
    "settlement.currency": (
        "What is the settlement currency?",
        "Against Payment instructions require the currency of the cash leg.",
        "19A/SETT currency",
    ),
    "settlement.amount": (
        "What is the settlement amount?",
        "Against Payment instructions require a positive cash amount.",
        "19A/SETT amount",
    ),
    "settlement.place_of_settlement": (
        "What synthetic place-of-settlement identifier should be used?",
        "This identifies the demonstration settlement location.",
        "95R/PSET",
    ),
    "settlement.delivering_agent": (
        "What synthetic identifier represents the delivering agent?",
        "This is the party delivering the securities in the demonstration.",
        "95R/DEAG",
    ),
    "settlement.receiving_agent": (
        "What synthetic identifier represents the receiving agent?",
        "This is the party receiving the securities in the demonstration.",
        "95R/REAG",
    ),
}


def get_value(scenario: SettlementScenario, field_path: str) -> Any:
    current: Any = scenario
    for part in field_path.split("."):
        current = getattr(current, part, None)
        if current is None:
            return None
    return current


def find_missing_fields(
    scenario: SettlementScenario,
    message_type: MessageType,
    profile: ClientProfile,
) -> MissingFieldsResponse:
    scenario_with_defaults = profile.apply_defaults(scenario)
    requirements = profile.requirements_for(message_type)
    missing_paths = [
        path for path in requirements if get_value(scenario_with_defaults, path) in (None, "")
    ]
    missing_fields = []
    for path in missing_paths:
        question, explanation, mapping = QUESTIONS.get(
            path,
            (f"Please provide {path}.", "This value is required by the profile.", None),
        )
        missing_fields.append(
            MissingField(
                field_path=path,
                question=question,
                explanation=explanation,
                technical_mapping=mapping,
            )
        )
    total = len(requirements)
    completion = 100 if total == 0 else round(((total - len(missing_paths)) / total) * 100)
    return MissingFieldsResponse(
        message_type=message_type,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        missing_fields=missing_fields,
        next_question=missing_fields[0] if missing_fields else None,
        completion_percentage=completion,
        scenario_with_defaults=scenario_with_defaults,
    )

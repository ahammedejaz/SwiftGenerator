from enum import StrEnum


class Lifecycle(StrEnum):
    INSTRUCTION = "INSTRUCTION"
    CONFIRMATION = "CONFIRMATION"
    STATUS = "STATUS"


class Direction(StrEnum):
    RECEIVE = "RECEIVE"
    DELIVER = "DELIVER"


class PaymentType(StrEnum):
    FREE_OF_PAYMENT = "FREE_OF_PAYMENT"
    AGAINST_PAYMENT = "AGAINST_PAYMENT"


class MessageType(StrEnum):
    MT530 = "MT530"
    MT537 = "MT537"
    MT540 = "MT540"
    MT541 = "MT541"
    MT542 = "MT542"
    MT543 = "MT543"
    MT544 = "MT544"
    MT545 = "MT545"
    MT546 = "MT546"
    MT547 = "MT547"
    MT548 = "MT548"
    MT564 = "MT564"
    MT565 = "MT565"
    MT566 = "MT566"
    MT567 = "MT567"
    MT568 = "MT568"


class MessageFunction(StrEnum):
    NEWM = "NEWM"
    CANC = "CANC"
    REVR = "REVR"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class IdentifierType(StrEnum):
    ISIN = "ISIN"


class QuantityType(StrEnum):
    UNIT = "UNIT"


class GenerationMode(StrEnum):
    VALID = "VALID"
    NEGATIVE_TEST = "NEGATIVE_TEST"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    INTENTIONALLY_INVALID = "INTENTIONALLY_INVALID"


class ResponseAction(StrEnum):
    PENDING_STATUS = "PENDING_STATUS"
    REJECTED_STATUS = "REJECTED_STATUS"
    MATCHED_STATUS = "MATCHED_STATUS"
    UNMATCHED_STATUS = "UNMATCHED_STATUS"
    CANCELLATION_ACCEPTED_STATUS = "CANCELLATION_ACCEPTED_STATUS"
    CANCELLATION_REJECTED_STATUS = "CANCELLATION_REJECTED_STATUS"
    FULL_CONFIRMATION = "FULL_CONFIRMATION"
    PARTIAL_CONFIRMATION = "PARTIAL_CONFIRMATION"


class SettlementResult(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"


class StatusCategory(StrEnum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    CANCELLATION_ACCEPTED = "CANCELLATION_ACCEPTED"
    CANCELLATION_REJECTED = "CANCELLATION_REJECTED"


class NegativeMutation(StrEnum):
    MISSING_SETTLEMENT_AMOUNT = "MISSING_SETTLEMENT_AMOUNT"
    SETTLEMENT_DATE_BEFORE_TRADE_DATE = "SETTLEMENT_DATE_BEFORE_TRADE_DATE"
    SENDER_REFERENCE_TOO_LONG = "SENDER_REFERENCE_TOO_LONG"
    MISSING_PLACE_OF_SETTLEMENT = "MISSING_PLACE_OF_SETTLEMENT"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    MISSING_PREVIOUS_REFERENCE_FOR_CANCELLATION = "MISSING_PREVIOUS_REFERENCE_FOR_CANCELLATION"
    CONFIRMATION_QUANTITY_EXCEEDS_INSTRUCTION = "CONFIRMATION_QUANTITY_EXCEEDS_INSTRUCTION"
    CONFIRMATION_MESSAGE_TYPE_MISMATCH = "CONFIRMATION_MESSAGE_TYPE_MISMATCH"
    MT548_MISSING_RELATED_REFERENCE = "MT548_MISSING_RELATED_REFERENCE"
    INVALID_STATUS_REASON_COMBINATION = "INVALID_STATUS_REASON_COMBINATION"


class AmendmentClassification(StrEnum):
    PROCESSING_DATA_MODIFICATION = "PROCESSING_DATA_MODIFICATION"
    CORE_BUSINESS_DATA_CHANGE = "CORE_BUSINESS_DATA_CHANGE"
    CANCELLATION_ONLY = "CANCELLATION_ONLY"
    UNSUPPORTED_MODIFICATION = "UNSUPPORTED_MODIFICATION"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class AmendmentField(StrEnum):
    PROCESSING_PRIORITY = "processing.priority"
    HOLD_RELEASE = "processing.holdRelease"
    NON_MATCHING_INFORMATION = "processing.nonMatchingInformation"
    QUANTITY = "security.quantity"
    SECURITY_IDENTIFIER = "security.identifier"
    SETTLEMENT_AMOUNT = "settlement.amount"
    SETTLEMENT_DATE = "trade.settlementDate"
    SETTLEMENT_PARTIES = "settlement.parties"
    SAFEKEEPING_ACCOUNT = "account.safekeepingAccount"
    CANCEL_TRANSACTION = "transaction.cancel"


class SettlementCommandType(StrEnum):
    MODIFY_PRIORITY = "MODIFY_PRIORITY"


class PenaltyListType(StrEnum):
    CURRENT = "CURRENT"
    NEW_ONLY = "NEW_ONLY"
    UPDATED_OR_REMOVED = "UPDATED_OR_REMOVED"


class PenaltyAction(StrEnum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    REMOVED = "REMOVED"


class PenaltyType(StrEnum):
    SETTLEMENT_FAIL = "SETTLEMENT_FAIL"
    LATE_MATCHING_FAIL = "LATE_MATCHING_FAIL"


class PenaltyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    NOT_COMPUTED = "NOT_COMPUTED"
    REMOVED = "REMOVED"


class AmountDirection(StrEnum):
    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class CorporateActionEventType(StrEnum):
    DIVIDEND_WITH_OPTIONS = "DIVIDEND_WITH_OPTIONS"


class CorporateActionClassification(StrEnum):
    VOLUNTARY = "VOLUNTARY"


class CorporateActionOptionCode(StrEnum):
    CASH = "CASH"
    SECURITIES = "SECURITIES"


class CorporateActionInstructionStatus(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    CANCELLATION_ACKNOWLEDGED = "CANCELLATION_ACKNOWLEDGED"
    CANCELLATION_REJECTED = "CANCELLATION_REJECTED"


class CorporateActionNarrativeCategory(StrEnum):
    ADDITIONAL_TEXT = "ADDITIONAL_TEXT"


class CanonicalFieldPath(StrEnum):
    LIFECYCLE = "lifecycle"
    DIRECTION = "direction"
    PAYMENT_TYPE = "paymentType"
    FUNCTION = "function"
    TRANSACTION_TYPE = "trade.transactionType"
    SENDER_REFERENCE = "senderReference"
    RELATED_REFERENCE = "relatedReference"
    CLIENT_REFERENCE = "clientReference"
    TRADE_DATE = "trade.tradeDate"
    SETTLEMENT_DATE = "trade.settlementDate"
    SECURITY_IDENTIFIER = "security.identifier"
    SECURITY_QUANTITY = "security.quantity"
    SAFEKEEPING_ACCOUNT = "account.safekeepingAccount"
    SETTLEMENT_CURRENCY = "settlement.currency"
    SETTLEMENT_AMOUNT = "settlement.amount"
    PLACE_OF_SETTLEMENT = "settlement.placeOfSettlement"
    DELIVERING_AGENT = "settlement.deliveringAgent"
    RECEIVING_AGENT = "settlement.receivingAgent"
    ACTUAL_SETTLEMENT_DATE = "confirmation.actualSettlementDate"
    SETTLED_QUANTITY = "confirmation.settledQuantity"
    SETTLED_AMOUNT = "confirmation.settledAmount"
    REASON_NARRATIVE = "status.narrative"


class AiSource(StrEnum):
    OPENROUTER = "openrouter"
    DETERMINISTIC_NON_AI = "deterministic_non_ai"
    TEST_MOCK = "test_mock"


class AiProcessingSource(StrEnum):
    LIVE_API = "LIVE_API"
    CACHE = "CACHE"
    DETERMINISTIC = "DETERMINISTIC"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


class AiCircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.models import RenderedField, SettlementScenario
from app.profiles.loader import ClientProfile


@dataclass(frozen=True)
class CompositionResult:
    raw_message: str
    field_map: list[RenderedField]


class MessageComposer(ABC):
    @abstractmethod
    def compose(self, scenario: SettlementScenario, profile: ClientProfile) -> CompositionResult:
        """Compose a validated canonical scenario in deterministic field order."""


def swift_decimal(value: object, minimum_decimals: int = 0) -> str:
    text = format(value, "f")
    if "." not in text and minimum_decimals:
        text = f"{text}.{'0' * minimum_decimals}"
    return text.replace(".", ",")

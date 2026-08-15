from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from app.domain.enums import StatusCategory
from app.domain.models import StatusOption


class StatusDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    reasons: list[str]


class StatusRegistry:
    def __init__(self, path: Path | None = None) -> None:
        config_path = path or Path(__file__).resolve().parents[2] / "config" / "statuses.yaml"
        with config_path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        self._definitions = {
            StatusCategory(key): StatusDefinition.model_validate(value)
            for key, value in payload["statuses"].items()
        }

    def get(self, category: StatusCategory) -> StatusDefinition:
        try:
            return self._definitions[category]
        except KeyError as exc:
            raise ValueError(f"Unsupported status category: {category.value}") from exc

    def validate_reason(self, category: StatusCategory, reason_code: str) -> bool:
        return reason_code in self.get(category).reasons

    def list(self) -> list[StatusOption]:
        return [
            StatusOption(category=category, code=definition.code, reasons=definition.reasons)
            for category, definition in self._definitions.items()
        ]


statuses = StatusRegistry()

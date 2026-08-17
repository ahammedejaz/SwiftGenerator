"""Controlled code lists, loaded once and shared by everything that shows a code.

A code list is configuration, not code. This module only reads it and answers two
questions: *what codes are allowed here* and *what does each one mean in English*.

The point of a single registry is that the browser dropdown, the JSON API's
``allowedValues``, the Excel ``Codes`` sheet and the MX element definitions cannot end up
offering different vocabularies for the same field — which is exactly what happens when a
list is restated in a React component.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ApiModel
from app.knowledge.models import KnowledgeSource

#: The one file in ``config/knowledge`` that is not a record file.
CODE_LIST_FILENAME = "code_lists.yaml"


class CodeValue(ApiModel):
    code: str
    label: str
    description: str


class CodeListDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=600)
    source: KnowledgeSource
    codes: list[CodeValue] = Field(min_length=1)


class CodeList(ApiModel):
    id: str
    name: str
    description: str
    values: list[CodeValue]

    @property
    def codes(self) -> list[str]:
        return [item.code for item in self.values]


class CodeListRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (
            Path(__file__).resolve().parents[2] / "config" / "knowledge" / CODE_LIST_FILENAME
        )
        self._lists = self._load()

    def _load(self) -> dict[str, CodeList]:
        if not self._path.exists():
            return {}
        with self._path.open(encoding="utf-8") as source:
            payload = yaml.safe_load(source) or {}
        definitions = payload.get("lists")
        if not isinstance(definitions, list):
            raise ValueError(f"{self._path.name} must contain a lists entry")
        result: dict[str, CodeList] = {}
        for raw in definitions:
            definition = CodeListDefinition.model_validate(raw)
            if definition.id in result:
                raise ValueError(f"Duplicate code list: {definition.id}")
            codes = [item.code for item in definition.codes]
            if len(codes) != len(set(codes)):
                raise ValueError(f"Code list {definition.id} repeats a code")
            result[definition.id] = CodeList(
                id=definition.id,
                name=definition.name,
                description=definition.description,
                values=definition.codes,
            )
        return result

    def get(self, list_id: str) -> CodeList:
        try:
            return self._lists[list_id]
        except KeyError as missing:
            raise KeyError(f"Unknown code list: {list_id}") from missing

    def known(self, list_id: str) -> bool:
        return list_id in self._lists

    def all(self) -> list[CodeList]:
        return [self._lists[key] for key in sorted(self._lists)]

    def describe(self, list_id: str | None, codes: list[str]) -> list[CodeValue]:
        """Codes with their words, whether or not a named list backs them.

        A field that has codes but no list still gets a select — it simply shows the code as
        its own label rather than nothing at all.
        """
        if list_id and self.known(list_id):
            by_code = {item.code: item for item in self.get(list_id).values}
            return [
                by_code.get(code, CodeValue(code=code, label=code, description=""))
                for code in codes
            ]
        return [CodeValue(code=code, label=code, description="") for code in codes]


code_lists = CodeListRegistry()

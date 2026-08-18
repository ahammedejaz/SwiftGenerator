"""The manifest index — the single authority for which MT messages exist.

The specification manifest (``config/specifications/supported_subset_v1.yaml``) already
owned each message's sequences; it now also owns the message list itself, each message's
workflow module and its catalogue description. Before this module existed those three
facts were duplicated in Python (`MessageType`, `KNOWN_MESSAGE_OWNERS`,
`MT_DESCRIPTIONS`), so onboarding a message meant editing code — which contradicts the
repository's own rule that a message is configuration.

Both the knowledge loader and the specification registry read this index, and it imports
neither, so it cannot participate in an import cycle. It deliberately parses only the
message-level facts; the full registry still owns field rows and validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings, source_path
from app.knowledge.models import WorkflowModuleId

#: The shape of an ISO 15022 message identifier as this platform writes it.
MT_TYPE_PATTERN = re.compile(r"^MT\d{3}$")


def manifest_path() -> Path:
    return source_path(
        get_settings().mt_specification_manifest,
        "specifications",
        "supported_subset_v1.yaml",
    )


@dataclass(frozen=True)
class ManifestMessage:
    """The message-level facts every layer may rely on before field rows are built."""

    message_type: str
    name: str
    scope: str
    short_description: str
    workflow_module: WorkflowModuleId
    sequence_paths: tuple[str, ...]
    sequence_codes: tuple[str, ...]


class ManifestIndex:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or manifest_path()
        self._messages = self._parse()

    def _parse(self) -> dict[str, ManifestMessage]:
        with self._path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        entries = raw.get("messages")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{self._path.name} must declare a messages list")
        messages: dict[str, ManifestMessage] = {}
        for entry in entries:
            message_type = str(entry.get("messageType", "")).strip().upper()
            if not MT_TYPE_PATTERN.fullmatch(message_type):
                raise ValueError(f"Manifest message type is not an MT identifier: {entry!r}")
            if message_type in messages:
                raise ValueError(f"Duplicate manifest message: {message_type}")
            module_raw = entry.get("workflowModule")
            if module_raw is None:
                raise ValueError(f"{message_type} must declare its workflowModule")
            sequences = entry.get("sequences")
            if not isinstance(sequences, list) or not sequences:
                raise ValueError(f"{message_type} must define sequences")
            messages[message_type] = ManifestMessage(
                message_type=message_type,
                name=str(entry.get("name", "")),
                scope=str(entry.get("scope", "")),
                short_description=str(entry.get("shortDescription", "") or entry.get("scope", "")),
                workflow_module=WorkflowModuleId(str(module_raw)),
                sequence_paths=tuple(str(item["path"]) for item in sequences),
                sequence_codes=tuple(str(item["code"]) for item in sequences),
            )
        return messages

    def known(self, message_type: str) -> bool:
        return message_type.strip().upper() in self._messages

    def get(self, message_type: str) -> ManifestMessage:
        candidate = message_type.strip().upper()
        try:
            return self._messages[candidate]
        except KeyError as error:
            raise KeyError(f"Unknown MT message type: {message_type}") from error

    def message_types(self) -> list[str]:
        return sorted(self._messages)

    def all_messages(self) -> list[ManifestMessage]:
        return [self._messages[key] for key in sorted(self._messages)]


@lru_cache(maxsize=1)
def manifest_index() -> ManifestIndex:
    return ManifestIndex()

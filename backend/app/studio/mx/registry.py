"""Loads the configured MX message specifications and flattens them for addressing."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.studio.models import Presence
from app.studio.mx.models import FlatElement, MxElement, MxMessageSpec

CONFIG_DIRECTORY = Path(__file__).resolve().parents[3] / "config" / "mx"


class MxRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or CONFIG_DIRECTORY
        self._specs: dict[str, MxMessageSpec] = {}
        self._flat: dict[str, list[FlatElement]] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self._directory.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                spec = MxMessageSpec.model_validate(yaml.safe_load(handle))
            key = spec.message_type.lower()
            if key in self._specs:
                raise ValueError(f"Duplicate MX specification: {spec.message_type}")
            self._specs[key] = spec
            self._flat[key] = _flatten(spec)
        if not self._specs:
            raise RuntimeError(f"No MX specifications found in {self._directory}")

    def known(self, message_type: str) -> bool:
        return _key(message_type) in self._specs

    def all_specs(self) -> list[MxMessageSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def by_namespace(self, namespace: str) -> MxMessageSpec | None:
        """Identify a message from its XML namespace.

        The namespace is the only self-describing part of an ISO 20022 document, so this is
        how an imported document is recognised — never by guessing from the root tag.
        """
        for spec in self._specs.values():
            if spec.namespace == namespace:
                return spec
        return None

    def namespaces(self) -> list[str]:
        return sorted(spec.namespace for spec in self._specs.values())

    def get(self, message_type: str) -> MxMessageSpec:
        try:
            return self._specs[_key(message_type)]
        except KeyError as error:
            raise KeyError(f"Unknown MX message type: {message_type}") from error

    def flat(self, message_type: str) -> list[FlatElement]:
        self.get(message_type)
        return self._flat[_key(message_type)]

    def by_path(self, message_type: str) -> dict[str, FlatElement]:
        return {item.path: item for item in self.flat(message_type)}

    def leaves(self, message_type: str) -> list[FlatElement]:
        return [item for item in self.flat(message_type) if item.element.is_leaf]


def _key(message_type: str) -> str:
    """Accept ``sese.023``, ``SESE.023`` or a full ``sese.023.001.11`` version string."""
    candidate = message_type.strip().lower()
    parts = candidate.split(".")
    if len(parts) >= 2:
        candidate = f"{parts[0]}.{parts[1]}"
    return candidate


def _flatten(spec: MxMessageSpec) -> list[FlatElement]:
    root = f"/{spec.document_element}/{spec.message_root}"
    flat: list[FlatElement] = []
    counter = [0]

    def walk(
        elements: list[MxElement],
        parent_path: str,
        ancestors: tuple[str, ...],
        depth: int,
        parent_choice: str | None,
        parent_branch: str | None,
        mandatory_chain: bool,
    ) -> None:
        for element in elements:
            path = f"{parent_path}/{element.name}"
            counter[0] += 1
            chain = mandatory_chain and element.presence is Presence.MANDATORY
            # A node directly under a choice opens a new branch; deeper nodes inherit it, so
            # every descendant knows which mutually exclusive option it belongs to.
            branch = path if (parent_choice and parent_branch is None) else parent_branch
            flat.append(
                FlatElement(
                    path=path,
                    depth=depth,
                    order=counter[0],
                    element=element,
                    parent_path=parent_path if parent_path != root else root,
                    ancestors=ancestors,
                    choice_group=parent_choice,
                    choice_branch=branch,
                    mandatory_chain=chain,
                )
            )
            if element.children:
                child_choice = path if element.choice else parent_choice
                child_branch = None if element.choice else branch
                walk(
                    element.children,
                    path,
                    (*ancestors, element.name),
                    depth + 1,
                    child_choice,
                    child_branch,
                    chain,
                )

    walk(spec.structure, root, (), 1, None, None, True)
    return flat


mx_registry = MxRegistry()

"""Loads the configured MX message specifications and flattens them for addressing."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import get_settings, source_path
from app.studio.models import Presence
from app.studio.mx.models import FlatElement, MxElement, MxMessageSpec

#: libyaml when available: a compiled pacs pack is thousands of lines, and the pure-Python
#: loader makes a preview registry of eight of them a multi-second start.
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _config_directory() -> Path:
    return source_path(get_settings().mx_specification_directory, "mx")


class MxRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or _config_directory()
        self._specs: dict[str, MxMessageSpec] = {}
        self._flat: dict[str, list[FlatElement]] = {}
        self._by_path: dict[str, dict[str, FlatElement]] = {}
        self._load()

    def _load(self) -> None:
        # Keyed by the full version (``pacs.008.001.14``) so two releases of one message
        # can coexist; the short form (``pacs.008``) resolves through ``_resolve`` when it
        # names exactly one of them.
        for path in sorted(self._directory.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                spec = MxMessageSpec.model_validate(yaml.load(handle, Loader=_LOADER))  # noqa: S506
            key = spec.version.lower()
            if key in self._specs:
                raise ValueError(f"Duplicate MX specification: {spec.version}")
            self._specs[key] = spec
            self._flat[key] = _flatten(spec)
            self._by_path[key] = {item.path: item for item in self._flat[key]}
        if not self._specs:
            raise RuntimeError(f"No MX specifications found in {self._directory}")

    def _resolve(self, message_type: str) -> str | None:
        candidate = message_type.strip().lower()
        if candidate in self._specs:
            return candidate
        short = _key(candidate)
        matches = [key for key in self._specs if _key(key) == short]
        return matches[0] if len(matches) == 1 else None

    def versions(self, message_type: str) -> list[str]:
        short = _key(message_type)
        return sorted(self._specs[key].version for key in self._specs if _key(key) == short)

    def known(self, message_type: str) -> bool:
        return self._resolve(message_type) is not None

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
        key = self._resolve(message_type)
        if key is None:
            versions = self.versions(message_type)
            if len(versions) > 1:
                raise KeyError(
                    f"{message_type} names more than one version ({', '.join(versions)}); "
                    "use the full message definition identifier"
                )
            raise KeyError(f"Unknown MX message type: {message_type}")
        return self._specs[key]

    def flat(self, message_type: str) -> list[FlatElement]:
        key = self._resolve(message_type)
        if key is None:
            self.get(message_type)
        assert key is not None
        return self._flat[key]

    def by_path(self, message_type: str) -> dict[str, FlatElement]:
        key = self._resolve(message_type)
        if key is None:
            self.get(message_type)
        assert key is not None
        return self._by_path[key]

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

"""Deterministic structural diff between two specification packs.

For standards-release upgrades: compile the new schema, diff against the committed pack,
and read exactly what moved. Pure structure comparison — no model, no heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.studio.mx.models import MxElement, MxMessageSpec


@dataclass
class StructuralDiff:
    namespace_changed: tuple[str, str] | None = None
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    cardinality_changed: list[str] = field(default_factory=list)
    type_changed: list[str] = field(default_factory=list)
    enumerations_changed: list[str] = field(default_factory=list)
    choice_changed: list[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not any(
            (
                self.namespace_changed,
                self.added,
                self.removed,
                self.cardinality_changed,
                self.type_changed,
                self.enumerations_changed,
                self.choice_changed,
            )
        )

    def render(self) -> str:
        if self.identical:
            return "The two packs are structurally identical."
        lines: list[str] = []
        if self.namespace_changed:
            lines.append(
                f"namespace: {self.namespace_changed[0]} -> {self.namespace_changed[1]}"
            )
        for label, paths in (
            ("added", self.added),
            ("removed", self.removed),
            ("cardinality changed", self.cardinality_changed),
            ("type changed", self.type_changed),
            ("enumerations changed", self.enumerations_changed),
            ("choice changed", self.choice_changed),
        ):
            for path in paths:
                lines.append(f"{label}: {path}")
        return "\n".join(lines)


def _index(spec: MxMessageSpec) -> dict[str, MxElement]:
    flat: dict[str, MxElement] = {}

    def walk(elements: list[MxElement], prefix: str) -> None:
        for element in elements:
            path = f"{prefix}/{element.name}"
            flat[path] = element
            walk(element.children, path)

    walk(spec.structure, spec.message_root)
    return flat


def _type_label(element: MxElement) -> str:
    if element.data_type is not None:
        return element.data_type.value
    if element.restriction is not None:
        facets = element.restriction
        return (
            f"{facets.base.value}:{facets.type_name or ''}:{facets.pattern or ''}:"
            f"{facets.min_length}:{facets.max_length}:{facets.length}:"
            f"{facets.total_digits}:{facets.fraction_digits}:"
            f"{facets.min_inclusive}:{facets.max_inclusive}"
        )
    return "container"


def diff_packs(before: MxMessageSpec, after: MxMessageSpec) -> StructuralDiff:
    result = StructuralDiff()
    if before.namespace != after.namespace:
        result.namespace_changed = (before.namespace, after.namespace)
    old, new = _index(before), _index(after)
    result.added = sorted(set(new) - set(old))
    result.removed = sorted(set(old) - set(new))
    for path in sorted(set(old) & set(new)):
        a, b = old[path], new[path]
        if (a.presence, a.max_occurs) != (b.presence, b.max_occurs):
            result.cardinality_changed.append(
                f"{path} ({a.presence.value} x{a.max_occurs} -> "
                f"{b.presence.value} x{b.max_occurs})"
            )
        if _type_label(a) != _type_label(b):
            result.type_changed.append(path)
        if a.codes != b.codes:
            result.enumerations_changed.append(path)
        if a.choice != b.choice:
            result.choice_changed.append(path)
    return result

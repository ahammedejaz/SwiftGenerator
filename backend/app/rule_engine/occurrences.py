"""Occurrence-aware evaluation state for declarative rules.

The public studio inputs still carry the same flat field/element occurrence numbers. This
module is the internal view the rule evaluator needs when a rule is scoped to one
structural repeat occurrence. A local index is never an identity on its own; the sequence
path and parent lineage travel with it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class OccurrenceLevel:
    sequence_path: str
    occurrence: int

    def label(self) -> str:
        return f"{self.sequence_path}[{self.occurrence}]"


@dataclass(frozen=True, order=True)
class OccurrenceIdentity:
    levels: tuple[OccurrenceLevel, ...]

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("An occurrence identity needs at least one level")
        for level in self.levels:
            if level.occurrence < 1:
                raise ValueError("Occurrence numbers are one-based")

    @property
    def sequence_path(self) -> str:
        return self.levels[-1].sequence_path

    @property
    def occurrence(self) -> int:
        return self.levels[-1].occurrence

    @property
    def lineage(self) -> tuple[str, ...]:
        return tuple(level.label() for level in self.levels)

    @property
    def display_path(self) -> str:
        return "/".join(self.lineage)

    def has_prefix(self, other: OccurrenceIdentity) -> bool:
        return self.levels[: len(other.levels)] == other.levels

    @classmethod
    def one(
        cls,
        sequence_path: str,
        occurrence: int = 1,
        *,
        parent: OccurrenceIdentity | None = None,
    ) -> OccurrenceIdentity:
        levels = (
            (*parent.levels, OccurrenceLevel(sequence_path, occurrence))
            if parent is not None
            else (OccurrenceLevel(sequence_path, occurrence),)
        )
        return cls(levels)


@dataclass(frozen=True)
class OccurrenceValue:
    key: str
    value: str
    occurrence: OccurrenceIdentity


@dataclass(frozen=True)
class EvaluationContext:
    """A global value bag plus optional occurrence-indexed values."""

    bag: Mapping[str, Sequence[str]]
    occurrence_values: tuple[OccurrenceValue, ...] = ()
    active_occurrence: OccurrenceIdentity | None = None

    @classmethod
    def from_bag(cls, bag: Mapping[str, Sequence[str]]) -> EvaluationContext:
        return cls(bag=bag)

    def occurrences(self, sequence_path: str) -> tuple[OccurrenceIdentity, ...]:
        wanted = sequence_path.upper()
        found = {
            item.occurrence
            for item in self.occurrence_values
            if item.occurrence.sequence_path.upper() == wanted
            and (
                self.active_occurrence is None
                or item.occurrence.has_prefix(self.active_occurrence)
            )
        }
        return tuple(sorted(found))

    def for_occurrence(self, occurrence: OccurrenceIdentity) -> EvaluationContext:
        scoped: dict[str, list[str]] = {}
        for item in self.occurrence_values:
            if item.occurrence == occurrence:
                scoped.setdefault(item.key, []).append(item.value)
        return EvaluationContext(
            bag=scoped,
            occurrence_values=self.occurrence_values,
            active_occurrence=occurrence,
        )


def as_context(value: Mapping[str, Sequence[str]] | EvaluationContext) -> EvaluationContext:
    if isinstance(value, EvaluationContext):
        return value
    return EvaluationContext.from_bag(value)

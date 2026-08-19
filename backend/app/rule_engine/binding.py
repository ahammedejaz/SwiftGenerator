"""Turning a resolved message into the value bag the evaluator reads.

Deliberately duck-typed: the caller supplies (key, value) pairs, so this module knows
nothing about either format adapter and neither adapter knows anything about the rule
engine. The key is whatever the format already uses to address a field — an MX element
path, an MT specification row id — which is the same key ``StructureIndex`` resolves a
reference to.
"""

from __future__ import annotations

from collections.abc import Iterable


def value_bag(entries: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """Group supplied values by field, keeping occurrence order."""
    bag: dict[str, list[str]] = {}
    for key, value in entries:
        bag.setdefault(key, []).append(value)
    return bag

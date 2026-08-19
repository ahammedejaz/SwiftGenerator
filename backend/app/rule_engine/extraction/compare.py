"""Deterministic comparison of two isolated extraction passes.

Two passes agreeing does not make a rule true — they may share a provider, a model family
and training data, so they are *isolated passes*, never independent authorities. Agreement
only reduces how much of a reviewer's attention a candidate needs. Disagreement is never
resolved by picking a side: it is recorded facet by facet and sent to the refuter and then
to a human.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rule_engine.extraction.canonical import CanonicalCandidate
from app.rule_engine.models import ExtractionAgreement


@dataclass(frozen=True)
class FacetDifference:
    facet: str
    in_a: str
    in_b: str


@dataclass(frozen=True)
class CandidatePair:
    key: tuple[str, tuple[str, ...]]
    in_a: CanonicalCandidate | None
    in_b: CanonicalCandidate | None
    differences: tuple[FacetDifference, ...] = ()

    @property
    def matched(self) -> bool:
        return self.in_a is not None and self.in_b is not None

    @property
    def candidate(self) -> CanonicalCandidate:
        """Whichever pass produced it; for a matched pair, A. Never a merge of the two."""
        found = self.in_a or self.in_b
        assert found is not None
        return found


@dataclass(frozen=True)
class ComparisonResult:
    agreement: ExtractionAgreement
    pairs: tuple[CandidatePair, ...]

    def render(self) -> str:
        if self.agreement is ExtractionAgreement.NO_RULE:
            return "Both passes found no rule."
        lines = [f"Agreement: {self.agreement.value}"]
        for pair in self.pairs:
            where = "A and B" if pair.matched else ("A only" if pair.in_a else "B only")
            lines.append(f"  {pair.key[0]} {' + '.join(pair.key[1]) or '-'} [{where}]")
            for difference in pair.differences:
                lines.append(
                    f"    {difference.facet}: A={difference.in_a!r} B={difference.in_b!r}"
                )
        return "\n".join(lines)


def compare(
    first: list[CanonicalCandidate], second: list[CanonicalCandidate]
) -> ComparisonResult:
    by_key_a = {item.key: item for item in first}
    by_key_b = {item.key: item for item in second}
    if not by_key_a and not by_key_b:
        return ComparisonResult(agreement=ExtractionAgreement.NO_RULE, pairs=())
    if not by_key_b:
        return ComparisonResult(
            agreement=ExtractionAgreement.ONLY_A,
            pairs=tuple(
                CandidatePair(key=key, in_a=item, in_b=None)
                for key, item in sorted(by_key_a.items())
            ),
        )
    if not by_key_a:
        return ComparisonResult(
            agreement=ExtractionAgreement.ONLY_B,
            pairs=tuple(
                CandidatePair(key=key, in_a=None, in_b=item)
                for key, item in sorted(by_key_b.items())
            ),
        )

    pairs: list[CandidatePair] = []
    unmatched = False
    differing = False
    for key in sorted(set(by_key_a) | set(by_key_b)):
        left, right = by_key_a.get(key), by_key_b.get(key)
        if left is None or right is None:
            unmatched = True
            pairs.append(CandidatePair(key=key, in_a=left, in_b=right))
            continue
        left_facets, right_facets = left.facets(), right.facets()
        differences = tuple(
            FacetDifference(facet=facet, in_a=left_facets[facet], in_b=right_facets[facet])
            for facet in left_facets
            if left_facets[facet] != right_facets[facet]
        )
        if differences:
            differing = True
        pairs.append(CandidatePair(key=key, in_a=left, in_b=right, differences=differences))

    if unmatched:
        agreement = ExtractionAgreement.CONFLICT
    elif differing:
        agreement = ExtractionAgreement.PARTIAL_AGREEMENT
    else:
        agreement = ExtractionAgreement.AGREE
    return ComparisonResult(agreement=agreement, pairs=tuple(pairs))

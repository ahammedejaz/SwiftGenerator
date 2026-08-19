"""Deterministic Rule Pack diff.

Two reviewed packs, one list of what changed. No model, no heuristics — this is what a
standards-release upgrade will be read through, so it has to be exact rather than
plausible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.rule_engine.models import CodeRestriction, Rule, RulePack


class PackChangeKind(StrEnum):
    RULE_ADDED = "RULE_ADDED"
    RULE_REMOVED = "RULE_REMOVED"
    CONDITION_CHANGED = "CONDITION_CHANGED"
    ASSERTION_CHANGED = "ASSERTION_CHANGED"
    SEVERITY_CHANGED = "SEVERITY_CHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    REVIEW_STATE_CHANGED = "REVIEW_STATE_CHANGED"
    FINDING_TEXT_CHANGED = "FINDING_TEXT_CHANGED"
    RESTRICTION_ADDED = "RESTRICTION_ADDED"
    RESTRICTION_REMOVED = "RESTRICTION_REMOVED"
    ALLOWED_CODES_CHANGED = "ALLOWED_CODES_CHANGED"
    PACK_IDENTITY_CHANGED = "PACK_IDENTITY_CHANGED"
    STRUCTURE_TARGET_CHANGED = "STRUCTURE_TARGET_CHANGED"


@dataclass(frozen=True)
class PackChange:
    kind: PackChangeKind
    identifier: str
    before: str | None = None
    after: str | None = None

    def render(self) -> str:
        if self.before is None and self.after is not None:
            return f"{self.kind} {self.identifier}: {self.after}"
        if self.after is None and self.before is not None:
            return f"{self.kind} {self.identifier}: {self.before}"
        if self.before is None and self.after is None:
            return f"{self.kind} {self.identifier}"
        return f"{self.kind} {self.identifier}: {self.before} -> {self.after}"


@dataclass
class PackDiff:
    changes: list[PackChange] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not self.changes

    def render(self) -> str:
        if self.identical:
            return "The two packs are identical."
        lines = [f"{len(self.changes)} change(s):"]
        lines.extend(f"  {change.render()}" for change in self.changes)
        return "\n".join(lines)


def _expression_text(rule: Rule, which: str) -> str:
    node = rule.when if which == "when" else rule.assert_
    if node is None:
        return "(unconditional)"
    return node.model_dump_json(by_alias=True, exclude_defaults=True)


def _evidence_text(item: Rule | CodeRestriction) -> str:
    return ";".join(
        f"{entry.source_id}/{entry.segment_id}/{entry.segment_hash[7:19]}"
        for entry in item.evidence
    )


def diff_packs(before: RulePack, after: RulePack) -> PackDiff:
    diff = PackDiff()

    if before.pack_id != after.pack_id:
        diff.changes.append(
            PackChange(
                PackChangeKind.PACK_IDENTITY_CHANGED, "pack", before.pack_id, after.pack_id
            )
        )
    if (
        before.structure_compatibility.structure_checksum
        != after.structure_compatibility.structure_checksum
    ):
        diff.changes.append(
            PackChange(
                PackChangeKind.STRUCTURE_TARGET_CHANGED,
                "structure",
                before.structure_compatibility.structure_checksum[:19] + "…",
                after.structure_compatibility.structure_checksum[:19] + "…",
            )
        )

    before_rules = {item.rule_id: item for item in before.rules}
    after_rules = {item.rule_id: item for item in after.rules}
    for rule_id in sorted(set(before_rules) - set(after_rules)):
        diff.changes.append(
            PackChange(PackChangeKind.RULE_REMOVED, rule_id, before=before_rules[rule_id].title)
        )
    for rule_id in sorted(set(after_rules) - set(before_rules)):
        diff.changes.append(
            PackChange(PackChangeKind.RULE_ADDED, rule_id, after=after_rules[rule_id].title)
        )
    for rule_id in sorted(set(before_rules) & set(after_rules)):
        old, new = before_rules[rule_id], after_rules[rule_id]
        if _expression_text(old, "when") != _expression_text(new, "when"):
            diff.changes.append(
                PackChange(
                    PackChangeKind.CONDITION_CHANGED,
                    rule_id,
                    _expression_text(old, "when"),
                    _expression_text(new, "when"),
                )
            )
        if _expression_text(old, "assert") != _expression_text(new, "assert"):
            diff.changes.append(
                PackChange(
                    PackChangeKind.ASSERTION_CHANGED,
                    rule_id,
                    _expression_text(old, "assert"),
                    _expression_text(new, "assert"),
                )
            )
        if old.severity is not new.severity:
            diff.changes.append(
                PackChange(
                    PackChangeKind.SEVERITY_CHANGED,
                    rule_id,
                    old.severity.value,
                    new.severity.value,
                )
            )
        if _evidence_text(old) != _evidence_text(new):
            diff.changes.append(
                PackChange(
                    PackChangeKind.EVIDENCE_CHANGED,
                    rule_id,
                    _evidence_text(old),
                    _evidence_text(new),
                )
            )
        if old.review.status is not new.review.status:
            diff.changes.append(
                PackChange(
                    PackChangeKind.REVIEW_STATE_CHANGED,
                    rule_id,
                    old.review.status.value,
                    new.review.status.value,
                )
            )
        if old.finding != new.finding:
            diff.changes.append(
                PackChange(
                    PackChangeKind.FINDING_TEXT_CHANGED,
                    rule_id,
                    old.finding.message,
                    new.finding.message,
                )
            )

    before_codes = {item.restriction_id: item for item in before.code_restrictions}
    after_codes = {item.restriction_id: item for item in after.code_restrictions}
    for identifier in sorted(set(before_codes) - set(after_codes)):
        diff.changes.append(
            PackChange(
                PackChangeKind.RESTRICTION_REMOVED,
                identifier,
                before=", ".join(before_codes[identifier].codes),
            )
        )
    for identifier in sorted(set(after_codes) - set(before_codes)):
        diff.changes.append(
            PackChange(
                PackChangeKind.RESTRICTION_ADDED,
                identifier,
                after=", ".join(after_codes[identifier].codes),
            )
        )
    for identifier in sorted(set(before_codes) & set(after_codes)):
        old_codes, new_codes = before_codes[identifier], after_codes[identifier]
        if old_codes.codes != new_codes.codes:
            diff.changes.append(
                PackChange(
                    PackChangeKind.ALLOWED_CODES_CHANGED,
                    identifier,
                    ", ".join(old_codes.codes),
                    ", ".join(new_codes.codes),
                )
            )
        if _evidence_text(old_codes) != _evidence_text(new_codes):
            diff.changes.append(
                PackChange(
                    PackChangeKind.EVIDENCE_CHANGED,
                    identifier,
                    _evidence_text(old_codes),
                    _evidence_text(new_codes),
                )
            )
        if old_codes.review.status is not new_codes.review.status:
            diff.changes.append(
                PackChange(
                    PackChangeKind.REVIEW_STATE_CHANGED,
                    identifier,
                    old_codes.review.status.value,
                    new_codes.review.status.value,
                )
            )
    return diff

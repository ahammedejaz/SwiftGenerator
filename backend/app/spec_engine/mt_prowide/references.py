from __future__ import annotations

from dataclasses import dataclass

from app.spec_engine.mt_prowide.models import MtProwideExtraction


@dataclass(frozen=True)
class MtStructuralReference:
    source_release: str
    message_type: str
    source_model: str
    sequence_path: str
    sequence_occurrence: int | None
    tag: str
    option: str | None
    qualifier: str | None
    component: int | None

    @property
    def canonical_id(self) -> str:
        parts = [
            "MT",
            self.source_release,
            self.source_model,
            self.sequence_path,
            self.tag,
        ]
        if self.qualifier:
            parts.append(self.qualifier)
        if self.component is not None:
            parts.append(f"C{self.component}")
        if self.sequence_occurrence is not None:
            parts.append(f"O{self.sequence_occurrence}")
        return ":".join(parts)


def resolve_field_reference(
    extraction: MtProwideExtraction,
    *,
    message_type: str,
    sequence_path: str,
    tag: str,
    qualifier: str | None = None,
    component: int | None = None,
    sequence_occurrence: int | None = None,
) -> MtStructuralReference:
    message = next(
        (item for item in extraction.messages if item.message_type == message_type),
        None,
    )
    if message is None:
        raise KeyError(f"Unknown Prowide source model: {message_type}")
    sequence_codes = {item.path: item.code for item in message.sequences}
    group = next(
        (
            item
            for item in message.field_groups
            if tag in item.tags
            and (
                item.sequence_path == sequence_path
                or sequence_codes.get(item.sequence_path) == sequence_path
            )
        ),
        None,
    )
    if group is None:
        raise KeyError(f"{message_type} has no {tag} field group in {sequence_path}")
    option = tag.removeprefix(group.field_number) or None
    return MtStructuralReference(
        source_release=extraction.source.swift_standards_release,
        message_type=message.base_message_type,
        source_model=message.source_model,
        sequence_path=sequence_codes.get(group.sequence_path, group.sequence_path),
        sequence_occurrence=sequence_occurrence,
        tag=tag,
        option=option,
        qualifier=qualifier,
        component=component,
    )

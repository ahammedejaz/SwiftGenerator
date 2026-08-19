"""Format-neutral field references, and their resolution against the structure registries.

A rule names a field the way the rest of the platform already names it: an MX element path
(what ``ElementInput.path`` carries) or an MT specification row (what ``FieldInput.id``
carries, with the sequence/tag/qualifier triple accepted as the spreadsheet-friendly
alternative). No third addressing scheme is invented, so a reference either resolves
through the same registry the composer uses or it does not resolve at all.

``StructureIndex`` is the only door onto structure the rule engine has, and it is
read-only. That is what makes "a Rule Pack cannot mutate a Structure Pack" a property of
the architecture rather than a promise.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.specifications.registry import MessageSpecificationRegistry, specification_registry
from app.studio.models import MessageFormat, Presence
from app.studio.mx.models import MxDataType, MxMessageSpec, MxRestrictionBase
from app.studio.mx.registry import MxRegistry, mx_registry

MX_PATH_PATTERN = re.compile(r"^(/[A-Za-z][A-Za-z0-9_.-]{0,63})+$")
MT_TAG_PATTERN = re.compile(r"^[0-9]{2}[A-Z]?$")
MT_ROW_ID_PATTERN = re.compile(r"^MT\d{3}-[A-Z0-9]+-[0-9]{2}[A-Z]?(-[A-Z0-9]+)?$")


class FieldKind(StrEnum):
    """What a field holds, reduced to the distinctions a business rule can act on."""

    TEXT = "TEXT"
    CODE = "CODE"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    DATE_TIME = "DATE_TIME"
    BOOLEAN = "BOOLEAN"
    IDENTIFIER = "IDENTIFIER"


#: Kinds a numeric comparison may be applied to.
NUMERIC_KINDS = frozenset({FieldKind.DECIMAL})
#: Kinds a date comparison may be applied to.
DATE_KINDS = frozenset({FieldKind.DATE, FieldKind.DATE_TIME})


class RuleModel(BaseModel):
    """Closed by construction: an unknown key is a validation error, not a silent extra."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class FieldRef(RuleModel):
    """One addressable field, in either format."""

    format: MessageFormat
    #: MX: the absolute element path.
    path: str | None = Field(default=None, max_length=500)
    #: MT: the specification row id, e.g. ``MT541-E-22F-SETR``.
    field_id: str | None = Field(default=None, alias="fieldId", max_length=64)
    #: MT: the spreadsheet triple, used when a row id is not to hand.
    sequence_path: str | None = Field(default=None, alias="sequencePath", max_length=16)
    tag: str | None = Field(default=None, max_length=4)
    qualifier: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def check_addressing(self) -> FieldRef:
        if self.format is MessageFormat.MX:
            if not self.path:
                raise ValueError("An MX field reference must carry a path")
            if self.field_id or self.sequence_path or self.tag or self.qualifier:
                raise ValueError("An MX field reference carries a path and nothing else")
            if not MX_PATH_PATTERN.fullmatch(self.path):
                raise ValueError(f"Not an element path: {self.path}")
            return self
        if self.path:
            raise ValueError("An MT field reference uses a row id or a tag, not a path")
        if self.field_id:
            if self.sequence_path or self.tag or self.qualifier:
                raise ValueError("An MT field reference carries a fieldId or a tag, not both")
            if not MT_ROW_ID_PATTERN.fullmatch(self.field_id):
                raise ValueError(f"Not a specification row id: {self.field_id}")
            return self
        if not self.tag:
            raise ValueError("An MT field reference must carry a fieldId or a tag")
        if not MT_TAG_PATTERN.fullmatch(self.tag):
            raise ValueError(f"Not an MT tag: {self.tag}")
        return self

    def canonical(self) -> str:
        """A stable string identity, used to key resolution and to compare candidates."""
        if self.format is MessageFormat.MX:
            return f"MX|{self.path}"
        if self.field_id:
            return f"MT|{self.field_id}"
        parts = [self.sequence_path or "*", self.tag or "", self.qualifier or "*"]
        return "MT|" + "/".join(parts)

    def describe(self) -> str:
        return self.path or self.field_id or self.canonical().removeprefix("MT|")


@dataclass(frozen=True)
class ResolvedFieldRef:
    """What the structure says about a referenced field. Read-only, always."""

    canonical: str
    #: The key this field's values appear under in a resolved message.
    key: str
    display_name: str
    kind: FieldKind
    presence: Presence
    max_occurs: int
    codes: tuple[str, ...]
    #: The address a validation finding points at, so "go to this field" keeps working.
    location: str

    @property
    def repeatable(self) -> bool:
        return self.max_occurs > 1


def _mx_kind(spec_element_data_type: MxDataType | None, restriction_base: str | None) -> FieldKind:
    if spec_element_data_type is not None:
        match spec_element_data_type:
            case MxDataType.CODE:
                return FieldKind.CODE
            case MxDataType.ISO_DATE:
                return FieldKind.DATE
            case MxDataType.ISO_DATE_TIME:
                return FieldKind.DATE_TIME
            case MxDataType.DECIMAL | MxDataType.AMOUNT:
                return FieldKind.DECIMAL
            case MxDataType.YES_NO:
                return FieldKind.BOOLEAN
            case MxDataType.ISIN | MxDataType.ANY_BIC | MxDataType.LEI:
                return FieldKind.IDENTIFIER
            case _:
                return FieldKind.TEXT
    match restriction_base:
        case MxRestrictionBase.DATE:
            return FieldKind.DATE
        case MxRestrictionBase.DATE_TIME:
            return FieldKind.DATE_TIME
        case MxRestrictionBase.DECIMAL:
            return FieldKind.DECIMAL
        case MxRestrictionBase.BOOLEAN:
            return FieldKind.BOOLEAN
        case _:
            return FieldKind.TEXT


def _mt_kind(input_kind: str, allowed_codes: list[str]) -> FieldKind:
    if allowed_codes or input_kind == "SELECT":
        return FieldKind.CODE
    match input_kind:
        case "DATE":
            return FieldKind.DATE
        case "AMOUNT" | "QUANTITY":
            return FieldKind.DECIMAL
        case "INDICATOR":
            return FieldKind.BOOLEAN
        case "IDENTIFIER" | "PARTY_BIC" | "PARTY_PROPRIETARY":
            return FieldKind.IDENTIFIER
        case _:
            return FieldKind.TEXT


class StructureIndex:
    """Read-only access to both structure registries, injectable for tests."""

    def __init__(
        self,
        *,
        mx: MxRegistry | None = None,
        mt: MessageSpecificationRegistry | None = None,
    ) -> None:
        self._mx = mx or mx_registry
        self._mt = mt or specification_registry

    # -- identity ----------------------------------------------------------------------

    def known(self, format_: MessageFormat, message_type: str) -> bool:
        if format_ is MessageFormat.MX:
            return self._mx.known(message_type)
        return self._mt.known(message_type)

    def version(self, format_: MessageFormat, message_type: str) -> str | None:
        if format_ is MessageFormat.MX:
            return self._mx.get(message_type).version
        return None

    # -- fields ------------------------------------------------------------------------

    def fields(self, format_: MessageFormat, message_type: str) -> list[ResolvedFieldRef]:
        if format_ is MessageFormat.MX:
            return [
                ResolvedFieldRef(
                    canonical=f"MX|{item.path}",
                    key=item.path,
                    display_name=item.element.display_name,
                    kind=_mx_kind(
                        item.element.data_type,
                        item.element.restriction.base if item.element.restriction else None,
                    ),
                    presence=item.element.presence,
                    max_occurs=item.element.max_occurs,
                    codes=tuple(item.element.codes),
                    location=item.path,
                )
                for item in self._mx.leaves(message_type)
            ]
        return [
            ResolvedFieldRef(
                canonical=f"MT|{row.row_id}",
                key=row.row_id,
                display_name=row.business_name,
                kind=_mt_kind(row.input_kind.value, row.allowed_codes),
                presence=Presence(row.presence.value),
                max_occurs=row.max_occurs,
                codes=tuple(row.allowed_codes),
                location=row.row_id,
            )
            for row in self._mt.get(message_type).fields
        ]

    def resolve(
        self, ref: FieldRef, message_type: str
    ) -> ResolvedFieldRef | None:
        """The referenced field, or ``None`` when the structure has no such field."""
        if not self.known(ref.format, message_type):
            return None
        candidates = self.fields(ref.format, message_type)
        if ref.format is MessageFormat.MX:
            return next((item for item in candidates if item.key == ref.path), None)
        if ref.field_id:
            return next((item for item in candidates if item.key == ref.field_id), None)
        rows = self._mt.get(message_type).fields
        matches = [
            row
            for row in rows
            if row.tag == ref.tag
            and (ref.qualifier is None or row.qualifier == ref.qualifier)
            and (
                ref.sequence_path is None
                or ref.sequence_path.upper() in {row.sequence_path.upper(), row.sequence_code}
            )
        ]
        if len(matches) != 1:
            # Ambiguous is as unusable as absent: a rule must name exactly one field.
            return None
        by_key = {item.key: item for item in candidates}
        resolved = by_key.get(matches[0].row_id)
        if resolved is None:
            return None
        # Keep the reference's own canonical identity so the binding table looks it up.
        return ResolvedFieldRef(
            canonical=ref.canonical(),
            key=resolved.key,
            display_name=resolved.display_name,
            kind=resolved.kind,
            presence=resolved.presence,
            max_occurs=resolved.max_occurs,
            codes=resolved.codes,
            location=resolved.location,
        )

    # -- compatibility -----------------------------------------------------------------

    def structure_checksum(self, format_: MessageFormat, message_type: str) -> str:
        """A digest of everything a rule can depend on, and nothing it cannot.

        Presentation prose is deliberately excluded: a reworded business explanation has no
        authority over a rule, so it must not invalidate a rule pack. Element identity,
        order, presence, cardinality, kind and code set are exactly what rules bind to.
        """
        parts: list[str] = []
        if format_ is MessageFormat.MX:
            spec: MxMessageSpec = self._mx.get(message_type)
            parts.append(f"{spec.message_type}|{spec.version}|{spec.namespace}")
            for item in self._mx.flat(message_type):
                element = item.element
                kind = _mx_kind(
                    element.data_type,
                    element.restriction.base if element.restriction else None,
                )
                parts.append(
                    "|".join(
                        [
                            item.path,
                            element.presence.value,
                            str(element.max_occurs),
                            "choice" if element.choice else "node",
                            kind.value,
                            ",".join(element.codes),
                        ]
                    )
                )
        else:
            specification = self._mt.get(message_type)
            parts.append(f"{specification.message_type}|{specification.standards_release}")
            for row in specification.fields:
                parts.append(
                    "|".join(
                        [
                            row.row_id,
                            row.sequence_path,
                            row.tag,
                            row.qualifier or "",
                            row.presence.value,
                            str(row.max_occurs),
                            _mt_kind(row.input_kind.value, row.allowed_codes).value,
                            ",".join(row.allowed_codes),
                        ]
                    )
                )
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

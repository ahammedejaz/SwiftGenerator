from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from app.spec_engine.mt_prowide.models import (
    MtFieldGroupEvidence,
    MtFieldSetEvidence,
    MtMessageEvidence,
    MtSequenceEvidence,
    Presence,
)

_SOURCE_PATH = re.compile(
    r"^com/prowidesoftware/swift/model/mt/mt(?P<category>\d)xx/(?P<class>MT\d{3}(?:_[A-Z]+)?)\.java$"
)
_PACKAGE = re.compile(r"^package\s+(?P<package>[\w.]+);", re.MULTILINE)
_MESSAGE_NAME = re.compile(r"MT\s+\d{3}\s+-\s+(?P<name>[^.\n]+)\.", re.MULTILINE)
_SRU = re.compile(r"public static final int SRU = (?P<sru>\d{4});")
_SEQUENCE_CONSTANT = re.compile(
    r"public static class Sequence(?P<path>[A-Za-z0-9_]+).*?"
    r'public static final String START_END_16RS = "(?P<code>[^"]+)";',
    re.DOTALL,
)
_SEQUENCE = re.compile(
    r"^Sequence\s+(?P<path>[A-Za-z0-9_]+)(?:\s+-\s*(?P<name>.*?))?\s*"
    r"\((?P<presence>[MO])\)(?P<tail>.*)$"
)
_FIELDSET = re.compile(
    r"^Fieldset\s+(?P<number>\d{2,3}[A-Z]?)\s+\((?P<presence>[MO])"
    r"\)(?P<tail>.*)$"
)
_FIELD = re.compile(
    r"^Field(?:setItem)?\s+(?P<number>\d{2,3}[A-Z]?)"
    r"(?:\s+(?P<options>[A-Z]+(?:,[A-Z]+)*))?"
    r"\s+\((?P<presence>[MO])\)(?P<tail>.*)$"
)


@dataclass
class _Node:
    kind: str
    text: list[str] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)

    @property
    def label(self) -> str:
        return " ".join(part.strip() for part in self.text if part.strip()).strip()


class _SchemeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self._stack: list[_Node] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "li":
            return
        attributes = dict(attrs)
        kind = attributes.get("class") or "fieldset-item"
        node = _Node(kind)
        parent = self._stack[-1] if self._stack else self.root
        parent.children.append(node)
        self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].text.append(data)


@dataclass
class _SequenceContext:
    path: str
    parent_path: str | None


@dataclass(frozen=True)
class _ParsedSequence:
    path: str
    name: str
    presence: Presence
    repeatable: bool


@dataclass(frozen=True)
class _ParsedFieldSet:
    number: str
    presence: Presence
    repeatable: bool


@dataclass(frozen=True)
class _ParsedField:
    number: str
    options: list[str]
    presence: Presence
    repeatable: bool


def discovered_categories(source_jar: Path) -> list[int]:
    categories = {
        int(match.group("category"))
        for match in _matched_source_paths(source_jar)
    }
    return sorted(categories)


def message_source_paths(
    source_jar: Path,
    *,
    category: int | None = None,
    categories: Iterable[int] | None = None,
) -> list[str]:
    selected = _selected_categories(category=category, categories=categories)
    return sorted(
        name
        for match in _matched_source_paths(source_jar)
        for name in [match.string]
        if selected is None or int(match.group("category")) in selected
    )


def _matched_source_paths(source_jar: Path) -> list[re.Match[str]]:
    with zipfile.ZipFile(source_jar) as archive:
        return [
            match
            for name in archive.namelist()
            for match in [_SOURCE_PATH.match(name)]
            if match is not None
        ]


def _selected_categories(
    *,
    category: int | None,
    categories: Iterable[int] | None,
) -> set[int] | None:
    if category is not None and categories is not None:
        raise ValueError("Pass either category or categories, not both")
    if category is not None:
        return {category}
    if categories is not None:
        return set(categories)
    return None


def extract_message_schemes(
    source_jar: Path,
    *,
    category: int | None = None,
    categories: Iterable[int] | None = None,
) -> list[MtMessageEvidence]:
    with zipfile.ZipFile(source_jar) as archive:
        return [
            _extract_message(archive, source_path)
            for source_path in message_source_paths(
                source_jar,
                category=category,
                categories=categories,
            )
        ]


def _extract_message(archive: zipfile.ZipFile, source_path: str) -> MtMessageEvidence:
    source = archive.read(source_path).decode("utf-8")
    path_match = _SOURCE_PATH.match(source_path)
    if path_match is None:
        raise ValueError(f"Not a Prowide MT source path: {source_path}")
    class_name = path_match.group("class")
    base_message_type = class_name.split("_", maxsplit=1)[0]
    variant = class_name.split("_", maxsplit=1)[1] if "_" in class_name else None
    package_match = _PACKAGE.search(source)
    if package_match is None:
        raise ValueError(f"{source_path} has no package declaration")
    sru_match = _SRU.search(source)
    if sru_match is None:
        raise ValueError(f"{source_path} has no SRU constant")
    scheme = _scheme_tree(source)
    sequence_codes = {
        match.group("path"): match.group("code")
        for match in _SEQUENCE_CONSTANT.finditer(source)
    }
    sequences: list[MtSequenceEvidence] = []
    fieldsets: list[MtFieldSetEvidence] = []
    field_groups: list[MtFieldGroupEvidence] = []
    counters = {"sequence": 0, "fieldset": 0, "field_group": 0}
    _walk_scheme(
        class_name,
        scheme.children,
        sequence_codes,
        None,
        sequences,
        fieldsets,
        field_groups,
        counters,
    )
    distinct_tags = sorted({tag for group in field_groups for tag in group.tags})
    name_match = _MESSAGE_NAME.search(source)
    name = name_match.group("name").strip() if name_match else class_name
    return MtMessageEvidence(
        message_type=class_name,
        base_message_type=base_message_type,
        category=int(path_match.group("category")),
        source_model=class_name,
        variant=variant,
        name=name,
        package_name=package_match.group("package"),
        class_name=class_name,
        source_path=source_path,
        sru=int(sru_match.group("sru")),
        sequence_count=len(sequences),
        fieldset_count=len(fieldsets),
        field_group_count=len(field_groups),
        distinct_tags=distinct_tags,
        sequences=sequences,
        fieldsets=fieldsets,
        field_groups=field_groups,
    )


def _scheme_tree(source: str) -> _Node:
    match = re.search(r'<div class="scheme"><ul>(?P<body>.*?)</ul></div>', source, re.DOTALL)
    if match is None:
        raise ValueError("Prowide source did not contain a generated message scheme")
    parser = _SchemeParser()
    parser.feed("<ul>" + match.group("body") + "</ul>")
    return parser.root


def _walk_scheme(
    message_type: str,
    nodes: list[_Node],
    sequence_codes: dict[str, str],
    sequence: _SequenceContext | None,
    sequences: list[MtSequenceEvidence],
    fieldsets: list[MtFieldSetEvidence],
    field_groups: list[MtFieldGroupEvidence],
    counters: dict[str, int],
    fieldset_id: str | None = None,
) -> None:
    for node in nodes:
        label = node.label
        if node.kind == "sequence":
            parsed = _parse_sequence(label)
            counters["sequence"] += 1
            current = _SequenceContext(parsed.path, sequence.path if sequence else None)
            code = sequence_codes.get(current.path, "UNKNOWN")
            sequences.append(
                MtSequenceEvidence(
                    path=current.path,
                    code=code,
                    name=parsed.name,
                    parent_path=current.parent_path,
                    order=counters["sequence"],
                    presence=parsed.presence,
                    min_occurs=_min_occurs(parsed.presence),
                    max_occurs=_max_occurs(parsed.repeatable),
                    repeatable=parsed.repeatable,
                    source_text=label,
                )
            )
            _walk_scheme(
                message_type,
                node.children,
                sequence_codes,
                current,
                sequences,
                fieldsets,
                field_groups,
                counters,
            )
            continue
        if node.kind == "fieldset":
            active_sequence = sequence or _ensure_root_sequence(
                message_type, sequences, counters
            )
            parsed_set = _parse_fieldset(label)
            counters["fieldset"] += 1
            current_fieldset_id = (
                f"{message_type}-{active_sequence.path}-FIELDSET-{parsed_set.number}-"
                f"{counters['fieldset']}"
            )
            fieldsets.append(
                MtFieldSetEvidence(
                    id=current_fieldset_id,
                    sequence_path=active_sequence.path,
                    parent_sequence_path=active_sequence.parent_path,
                    field_number=parsed_set.number,
                    order=counters["fieldset"],
                    presence=parsed_set.presence,
                    min_occurs=_min_occurs(parsed_set.presence),
                    max_occurs=_max_occurs(parsed_set.repeatable),
                    repeatable=parsed_set.repeatable,
                    source_text=label,
                )
            )
            _walk_scheme(
                message_type,
                node.children,
                sequence_codes,
                active_sequence,
                sequences,
                fieldsets,
                field_groups,
                counters,
                current_fieldset_id,
            )
            continue
        if node.kind in {"field", "fieldset-item"}:
            active_sequence = sequence or _ensure_root_sequence(
                message_type, sequences, counters
            )
            parsed_field = _parse_field(label)
            counters["field_group"] += 1
            field_groups.append(
                MtFieldGroupEvidence(
                    id=(
                        f"{message_type}-{active_sequence.path}-GROUP-"
                        f"{counters['field_group']}"
                    ),
                    sequence_path=active_sequence.path,
                    fieldset_id=fieldset_id,
                    order=counters["field_group"],
                    field_number=parsed_field.number,
                    options=parsed_field.options,
                    tags=_tags(parsed_field.number, parsed_field.options),
                    presence=parsed_field.presence,
                    min_occurs=_min_occurs(parsed_field.presence),
                    max_occurs=_max_occurs(parsed_field.repeatable),
                    repeatable=parsed_field.repeatable,
                    source_text=label,
                )
            )


def _parse_sequence(label: str) -> _ParsedSequence:
    match = _SEQUENCE.match(label)
    if match is None:
        raise ValueError(f"Unsupported Prowide sequence label: {label}")
    return _ParsedSequence(
        path=match.group("path"),
        name=(match.group("name") or "").strip(),
        presence=_presence(match.group("presence")),
        repeatable=_repeatable(match.group("tail")),
    )


def _ensure_root_sequence(
    message_type: str,
    sequences: list[MtSequenceEvidence],
    counters: dict[str, int],
) -> _SequenceContext:
    existing = next((sequence for sequence in sequences if sequence.path == "ROOT"), None)
    if existing is not None:
        return _SequenceContext(existing.path, None)
    counters["sequence"] += 1
    sequences.append(
        MtSequenceEvidence(
            path="ROOT",
            code="MESSAGE",
            name="Unsequenced message body",
            parent_path=None,
            order=counters["sequence"],
            presence=Presence.UNKNOWN,
            min_occurs=0,
            max_occurs=1,
            repeatable=False,
            source_text="Prowide message scheme without a 16R/16S sequence",
        )
    )
    return _SequenceContext("ROOT", None)


def _parse_fieldset(label: str) -> _ParsedFieldSet:
    match = _FIELDSET.match(label)
    if match is None:
        raise ValueError(f"Unsupported Prowide fieldset label: {label}")
    return _ParsedFieldSet(
        number=match.group("number"),
        presence=_presence(match.group("presence")),
        repeatable=_repeatable(match.group("tail")),
    )


def _parse_field(label: str) -> _ParsedField:
    match = _FIELD.match(label)
    if match is None:
        raise ValueError(f"Unsupported Prowide field label: {label}")
    options = match.group("options")
    return _ParsedField(
        number=match.group("number"),
        options=options.split(",") if options else [],
        presence=_presence(match.group("presence")),
        repeatable=_repeatable(match.group("tail")),
    )


def _presence(value: str) -> Presence:
    return Presence.MANDATORY if value == "M" else Presence.OPTIONAL


def _repeatable(tail: str) -> bool:
    return "repetitive" in tail


def _min_occurs(presence: Presence) -> int:
    return 1 if presence is Presence.MANDATORY else 0


def _max_occurs(repeatable: bool) -> int | None:
    return None if repeatable else 1


def _tags(number: str, options: list[str]) -> list[str]:
    if not options:
        return [number]
    return [number if option == "NONE" else f"{number}{option}" for option in options]

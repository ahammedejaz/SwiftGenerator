"""The Format Specifications table, and the per-field qualifier tables, read as data.

These two tables are the guide's *structural* statement: which sequences exist, whether
each is mandatory and repeatable, which tags sit in which sequence, and which qualifiers
each generic field may carry there. They are authorised documentary structural evidence
for the release the guide declares — and for that release only.

Nothing here writes a structure pack. The model this module builds is read by the
candidate compiler so a rule's reference can be resolved and refused precisely, and by the
reconciliation reports so a difference against another release is named rather than
silently absorbed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum

from app.rule_engine.mt_mrg.document import (
    BLOCK_BY_LABEL,
    FIELD_BLOCKS,
    FIELD_HEADING,
    MrgBlock,
    MrgLine,
    MrgPage,
    MrgSection,
    MrgSectionSpan,
)

# -- Format Specifications ---------------------------------------------------------------

SEQUENCE_OPEN = re.compile(
    r"^(?:---->\s+)?(?P<presence>Mandatory|Optional)\s+(?P<repeat>Repetitive\s+)?"
    r"(?P<kind>Sequence|Subsequence)\s+(?P<path>[A-Z](?:\d+|[a-z]|[A-Z])*)\s+(?P<name>.*)$"
)
SEQUENCE_CLOSE = re.compile(
    r"^(?:----\|\s+)?End of (?:Mandatory|Optional) (?:Repetitive )?"
    r"(?:Sequence|Subsequence) (?P<path>[A-Z](?:\d+|[a-z]|[A-Z])*)\b"
)
#: Rows a guide lists outside any sequence — a flat message (MT103) or the fields before
#: the first sequence opens — sit in the message body, named as the runtime names it.
ROOT_SEQUENCE = "ROOT"
REPEAT_OPEN = "---->"
REPEAT_CLOSE = "----|"
#: Column headings and the legend, which repeat on every page of the table.
TABLE_FURNITURE = frozenset(
    {
        "Status Tag Qualifier Generic",
        "Field Name",
        "Detailed Field Name Content/Options No.",
        "M = Mandatory, O = Optional",
        "Status Tag Qualifier Generic Field",
        "Name",
        # A message without generic fields has no qualifier columns.
        "Status Tag Field Name Content/Options No.",
    }
)
ROW_HEAD = re.compile(r"^(?P<status>[MO])\s+(?P<tag>\d{2}[A-Za-z]?)\s+(?P<rest>.*)$")
DELIMITER_ROW = re.compile(
    r"^M\s+(?P<tag>16[RS])\s+(?P<label>(?:Start|End) of Block)\s+(?P<code>[A-Z0-9]+)"
    r"\s+(?P<number>\d{1,3})$"
)
#: A complete table row ends with its own number; used only to resynchronise after a
#: misnumbered row (see ``parse_format_specification``).
ROW_NUMBER_TAIL = re.compile(r"^[MO]\s+\d{2}[A-Za-z]?\s+.*\s(?P<number>\d{1,3})$")
#: The qualifier column holds either a literal qualifier or ``4!c`` — "any qualifier this
#: field defines", with the actual list given by the field's own qualifier table.
GENERIC_QUALIFIER = "4!c"
QUALIFIER_TOKEN = re.compile(r"^(?P<qualifier>[A-Z]{4}|4!c)(?:\s+(?P<rest>.*))?$")
#: A slash alone is not enough — ``Date/Currency/Amount`` is a field name.
FORMAT_FRAGMENT = re.compile(r"[0-9!\[\]<>*$]")
NO_LETTER_TOKEN = "NOLETTER"
NO_LETTER_OPTION = re.compile(r"No letter option", re.IGNORECASE)
OPTION_LIST = re.compile(rf"^(?:[A-Z]|{NO_LETTER_TOKEN})(?:,\s*(?:[A-Z]|{NO_LETTER_TOKEN}))*$")


def parent_of(path: str) -> str | None:
    """Strip one nesting level: a trailing number run, or a trailing letter."""
    if "_" in path:
        # ``B1_A`` is the repetitive group inside ``B1``; ``_A`` sits in the message body.
        return path.rsplit("_", 1)[0] or None
    if len(path) <= 1:
        return None
    stripped = path.rstrip("0123456789") if path[-1].isdigit() else path[:-1]
    return stripped or None


class SequencePresence(StrEnum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"


class RowStatus(StrEnum):
    MANDATORY = "M"
    OPTIONAL = "O"


@dataclass(frozen=True)
class _OpenRepeat:
    """A ``---->`` arrow waiting for its ``----|``."""

    path: str
    first_row: int
    line: MrgLine


@dataclass(frozen=True)
class MrgSequence:
    path: str
    presence: SequencePresence
    repetitive: bool
    name: str
    order: int
    page: int
    line: int

    @property
    def parent_path(self) -> str | None:
        """``E1``'s parent is ``E``, ``C1a1A1``'s is ``C1a1A``. Derived from the guide's own
        naming convention: each nesting level appends one letter or one number."""
        return parent_of(self.path)


@dataclass(frozen=True)
class MrgFieldRow:
    """One line of the Format Specifications table."""

    number: int
    sequence_path: str
    status: RowStatus
    tag: str
    #: ``None`` where the table shows no qualifier column entry (``16R``, ``23G``, ``35B``).
    qualifier: str | None
    #: ``True`` when the qualifier column reads ``4!c``: the field is generic and its legal
    #: qualifiers come from its own qualifier table, not from this row.
    generic_qualifier: bool
    #: Format options the row lists (``A, C, E``). Empty where the row states a format
    #: string instead, which is what a single-option field does.
    options: tuple[str, ...]
    content: str
    description: str
    repetitive: bool
    page: int
    line: int

    @property
    def field_number(self) -> str:
        """``98`` for ``98a`` — the tag without its option letter."""
        return self.tag[:2]

    @property
    def option(self) -> str | None:
        suffix = self.tag[2:]
        return suffix.upper() if suffix and suffix != "a" else None


@dataclass(frozen=True)
class MrgQualifierRow:
    """One line of a field's qualifier table, inside its Field Specification."""

    field_ordinal: int
    tag: str
    sequence_path: str
    order: int
    status: RowStatus
    qualifier: str
    #: ``R`` (repetitive) or ``N``. The guide's own column.
    repetition: str
    #: Network Validated Rules this qualifier is governed by, as the guide's CR column
    #: names them. A direct, machine-readable cross-check on rule discovery.
    conditional_rules: tuple[str, ...]
    options: tuple[str, ...]
    description: str
    page: int
    line: int


@dataclass(frozen=True)
class MrgFieldSpec:
    """One numbered Field Specification, reduced to what carries authority."""

    ordinal: int
    tag: str
    heading: str
    presence_text: str
    sequence_path: str
    sequence_presence: SequencePresence
    field_status: str
    conditional_rules: tuple[str, ...]
    qualifiers: tuple[MrgQualifierRow, ...]
    #: Codes the CODES block enumerates, keyed by the qualifier the block names.
    codes: tuple[tuple[str, tuple[str, ...]], ...]
    #: Qualifiers (``""`` for a field without one) whose list the guide leaves open — "may
    #: be used", "or bilaterally agreed codes". Their codes are guidance, never a closed set.
    open_code_lists: tuple[str, ...]
    #: The FORMAT block's notation per option letter (``""`` for a field without letter
    #: options): ``Option J 5*40x (Party Identification)`` → ``("J", "5*40x")``. Component
    #: labels are dropped; wrapped lines are joined without the spaces the wrap introduced.
    formats: tuple[tuple[str, str], ...]
    #: Error codes named anywhere in the specification's normative blocks.
    error_codes: tuple[str, ...]
    #: Which labelled blocks the specification actually carries.
    blocks: tuple[MrgBlock, ...]
    first_page: int
    last_page: int


@dataclass(frozen=True)
class MrgStructure:
    """Everything the guide states about the shape of one message in one release."""

    message_type: str
    standards_release: str
    sequences: tuple[MrgSequence, ...] = ()
    rows: tuple[MrgFieldRow, ...] = ()
    field_specs: tuple[MrgFieldSpec, ...] = ()
    problems: tuple[str, ...] = ()

    def sequence(self, path: str) -> MrgSequence | None:
        wanted = path.upper()
        return next((item for item in self.sequences if item.path.upper() == wanted), None)

    def rows_in(self, path: str) -> tuple[MrgFieldRow, ...]:
        wanted = path.upper()
        return tuple(item for item in self.rows if item.sequence_path.upper() == wanted)

    def qualifier_rows(self, path: str, tag: str) -> tuple[MrgQualifierRow, ...]:
        number = tag[:2]
        wanted = path.upper()
        return tuple(
            item
            for spec in self.field_specs
            for item in spec.qualifiers
            if item.sequence_path.upper() == wanted and item.tag[:2] == number
        )

    def checksum(self) -> str:
        """A digest of everything a candidate rule may bind to.

        Descriptions are excluded on purpose: rewording a field's name has no authority
        over a rule, and must not invalidate a candidate derived from the same structure.
        """
        parts = [f"{self.message_type}|{self.standards_release}"]
        for sequence in self.sequences:
            parts.append(
                "|".join(
                    [
                        "SEQ",
                        sequence.path,
                        sequence.presence.value,
                        "R" if sequence.repetitive else "N",
                    ]
                )
            )
        for row in self.rows:
            parts.append(
                "|".join(
                    [
                        "ROW",
                        str(row.number),
                        row.sequence_path,
                        row.status.value,
                        row.tag,
                        row.qualifier or "",
                        "G" if row.generic_qualifier else "L",
                        ",".join(row.options),
                        "R" if row.repetitive else "N",
                    ]
                )
            )
        for spec in self.field_specs:
            for qualifier in spec.qualifiers:
                parts.append(
                    "|".join(
                        [
                            "QUAL",
                            qualifier.sequence_path,
                            qualifier.tag,
                            qualifier.qualifier,
                            qualifier.status.value,
                            qualifier.repetition,
                            ",".join(qualifier.options),
                        ]
                    )
                )
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"


def section_lines(
    pages: tuple[MrgPage, ...],
    span: MrgSectionSpan,
    *,
    message_type: str,
    message_name: str,
    release_text: str,
) -> list[MrgLine]:
    """The lines of one section, with page furniture and table headings removed."""
    from app.rule_engine.mt_mrg.document import body_lines

    return [
        line
        for line in body_lines(pages, message_type, message_name, release_text)
        if span.covers_line(line.number) and line.text.strip() not in TABLE_FURNITURE
    ]


def _split_row(rest: str) -> tuple[str | None, bool, tuple[str, ...], str, str]:
    """Qualifier, genericity, options, content and description from a row's tail."""
    qualifier: str | None = None
    generic = False
    match = QUALIFIER_TOKEN.match(rest)
    if match:
        token = match.group("qualifier")
        if token == GENERIC_QUALIFIER:
            generic = True
        else:
            qualifier = token
        rest = (match.group("rest") or "").strip()
    # The content/options column is the tail. An option list is a comma-separated run of
    # single letters — ``59a`` lists ``No letter option, A, F`` where the bare tag is one of
    # the options; anything else is a format string or a block code, kept verbatim.
    rest = NO_LETTER_OPTION.sub(NO_LETTER_TOKEN, rest)
    words = rest.split()
    for start in range(len(words)):
        tail = " ".join(words[start:])
        if OPTION_LIST.fullmatch(tail):
            return (
                qualifier,
                generic,
                tuple(
                    "" if item.strip() == NO_LETTER_TOKEN else item.strip()
                    for item in tail.split(",")
                ),
                tail.replace(NO_LETTER_TOKEN, "No letter option"),
                " ".join(words[:start]),
            )
    # A format string wraps across lines too (MT940's 61 takes three), and the PDF text
    # then shows it as several words. Trailing words that carry a format marker — a digit,
    # ``!``, a bracket, ``<``, ``*``, ``/`` or ``$`` — are the format, joined back without
    # the spaces the wrap introduced; the words before them are the field name.
    end = len(words)
    while end > 0 and FORMAT_FRAGMENT.search(words[end - 1]):
        end -= 1
    if end == len(words):
        end = max(len(words) - 1, 0)
    content = "".join(words[end:])
    return qualifier, generic, (), content, " ".join(words[:end])


def _joined(lines: list[MrgLine]) -> str:
    return re.sub(r"-\s(?=\S)", "", " ".join(item.text.strip() for item in lines))


def parse_format_specification(
    pages: tuple[MrgPage, ...],
    spans: tuple[MrgSectionSpan, ...],
    *,
    message_type: str,
    message_name: str,
    release_text: str,
) -> tuple[tuple[MrgSequence, ...], tuple[MrgFieldRow, ...], tuple[str, ...]]:
    """Read the Format Specifications table into sequences and rows.

    The table's own ``No.`` column is the anchor. Rows wrap across lines — a long field
    name breaks mid-word — so a row is complete exactly when the text accumulated so far
    ends with the next expected row number. Guessing where a row ends any other way is how
    a wrapped field name becomes a phantom row.
    """
    span = next((item for item in spans if item.section is MrgSection.FORMAT_SPECIFICATION), None)
    if span is None:
        return (), (), ("FORMAT_SPECIFICATION_SECTION_MISSING",)

    sequences: list[MrgSequence] = []
    rows: list[MrgFieldRow] = []
    problems: list[str] = []
    open_paths: list[str] = []
    repeat_stack: list[_OpenRepeat] = []
    group_counts: dict[str, int] = {}
    expected = 1
    buffer: list[MrgLine] = []

    def current_path() -> str:
        if repeat_stack:
            return repeat_stack[-1].path
        return open_paths[-1] if open_paths else ROOT_SEQUENCE

    def flush_unparsed() -> None:
        if buffer:
            problems.append(f"UNPARSED_TABLE_TEXT_AT_LINE_{buffer[0].number}_BEFORE_ROW_{expected}")
            buffer.clear()

    for line in section_lines(
        pages,
        span,
        message_type=message_type,
        message_name=message_name,
        release_text=release_text,
    ):
        stripped = line.text.strip()
        if stripped == span.heading:
            continue
        close = SEQUENCE_CLOSE.match(stripped)
        if close:
            flush_unparsed()
            repeat_stack.clear()
            if open_paths and open_paths[-1] == close.group("path"):
                open_paths.pop()
            continue
        opened = SEQUENCE_OPEN.match(stripped)
        if opened:
            flush_unparsed()
            repeat_stack.clear()
            path = opened.group("path")
            open_paths.append(path)
            sequences.append(
                MrgSequence(
                    path=path,
                    presence=SequencePresence(opened.group("presence").upper()),
                    repetitive=bool(opened.group("repeat")),
                    name=opened.group("name").strip(),
                    order=len(sequences) + 1,
                    page=line.page,
                    line=line.number,
                )
            )
            continue
        if stripped == REPEAT_OPEN:
            # Arrows nest (MT801 repeats a block inside a repeated block), so each opening
            # arrow pushes a group whose rows follow until its closing arrow.
            parent_path = (
                repeat_stack[-1].path if repeat_stack else (open_paths[-1] if open_paths else "")
            )
            ordinal = group_counts.get(parent_path, 0)
            group_counts[parent_path] = ordinal + 1
            repeat_stack.append(
                _OpenRepeat(
                    path=f"{parent_path}_{chr(ord('A') + ordinal)}",
                    first_row=len(rows),
                    line=line,
                )
            )
            continue
        if stripped == REPEAT_CLOSE:
            if not repeat_stack:
                continue
            group = repeat_stack.pop()
            grouped = rows[group.first_row :]
            own_rows = [item for item in grouped if item.sequence_path == group.path]
            child_groups = [item for item in sequences if item.path.startswith(group.path + "_")]
            if len(own_rows) <= 1 and not child_groups:
                # One field repeating on its own: a repetitive row, not a sequence. The row
                # returns to the sequence around it and is marked repetitive.
                outer = (
                    repeat_stack[-1].path
                    if repeat_stack
                    else (open_paths[-1] if open_paths else ROOT_SEQUENCE)
                )
                rows[group.first_row :] = [
                    replace(item, sequence_path=outer, repetitive=True)
                    if item.sequence_path == group.path
                    else item
                    for item in grouped
                ]
                group_counts[outer if outer != ROOT_SEQUENCE else ""] -= 1
                continue
            # Several rows repeat together (MT940's 61 and 86, MT201's transaction block):
            # an unbracketed repetitive group, which the runtime models as a sequence of its
            # own so the rows repeat as a unit rather than severally.
            sequences.append(
                MrgSequence(
                    path=group.path,
                    presence=(
                        SequencePresence.MANDATORY
                        if any(item.status is RowStatus.MANDATORY for item in own_rows)
                        else SequencePresence.OPTIONAL
                    ),
                    repetitive=True,
                    name="Repetitive group",
                    order=len(sequences) + 1,
                    page=group.line.page,
                    line=group.line.number,
                )
            )
            continue

        delimiter = DELIMITER_ROW.match(stripped)
        if delimiter is not None:
            # ``16R``/``16S`` rows are complete on one line and a guide numbers them
            # unreliably (MT548 SR2026 closes GENL as row 14 after row 15). The delimiter
            # is authoritative; the number due is the row's number.
            flush_unparsed()
            read = int(delimiter.group("number"))
            if read != expected:
                problems.append(f"ROW_NUMBER_RESYNC_EXPECTED_{expected}_READ_{read}")
            rows.append(
                MrgFieldRow(
                    number=expected,
                    sequence_path=current_path(),
                    status=RowStatus.MANDATORY,
                    tag=delimiter.group("tag"),
                    qualifier=None,
                    generic_qualifier=False,
                    options=(),
                    content=delimiter.group("code"),
                    description=delimiter.group("label"),
                    repetitive=False,
                    page=line.page,
                    line=line.number,
                )
            )
            expected += 1
            continue
        buffer.append(line)
        joined = _joined(buffer)
        number = expected
        if not joined.endswith(f" {expected}"):
            # A guide occasionally misnumbers one row (MT548 SR2026 closes GENL with
            # ``16S … 14`` where 16 is due). Waiting for the due number would swallow the
            # rest of the table, so a complete row whose number sits within a few of the
            # one due is accepted, the numbering resynchronised and the slip recorded.
            resync = ROW_NUMBER_TAIL.match(joined)
            if resync is None or abs(int(resync.group("number")) - expected) > 3:
                continue
            read = int(resync.group("number"))
            # A number lower than the one due is a misprint of the due number (the table
            # never goes backwards); a higher one means rows were skipped, and the table's
            # own numbering is then the authority.
            number = max(read, expected)
            problems.append(f"ROW_NUMBER_RESYNC_EXPECTED_{expected}_READ_{read}")
        # Prose introducing the table ("The MT 201 consists of two types of sequences …")
        # can sit in the buffer in front of the first row. The row is the shortest tail of
        # the buffer that reads as one; whatever precedes it is recorded as unparsed.
        head = None
        for start in range(len(buffer)):
            candidate = _joined(buffer[start:])
            if not candidate.endswith(f" {number}"):
                continue
            head = ROW_HEAD.match(candidate[: -len(str(number))].strip())
            if head is not None:
                if start:
                    problems.append(
                        f"UNPARSED_TABLE_TEXT_AT_LINE_{buffer[0].number}_BEFORE_ROW_{number}"
                    )
                    del buffer[:start]
                break
        if head is None:
            flush_unparsed()
            expected += 1
            continue
        qualifier, generic, options, content, description = _split_row(head.group("rest").strip())
        rows.append(
            MrgFieldRow(
                number=number,
                sequence_path=current_path(),
                status=RowStatus(head.group("status")),
                tag=head.group("tag"),
                qualifier=qualifier,
                generic_qualifier=generic,
                options=options,
                content=content,
                description=description,
                repetitive=False,
                page=buffer[0].page,
                line=buffer[0].number,
            )
        )
        buffer.clear()
        expected = number + 1
    flush_unparsed()
    if open_paths:
        problems.append("SEQUENCE_NOT_CLOSED_" + "_".join(open_paths))
    return tuple(sequences), tuple(rows), tuple(problems)


# -- Field Specifications ----------------------------------------------------------------

#: ``Mandatory in mandatory sequence A``, ``Conditional (see rules C2, C15)`` (a flat
#: message has no sequence), ``Optional in conditional (see rule ) sequence C``. The
#: sequence part is absent in a guide whose message has no sequences.
PRESENCE_STATEMENT = re.compile(
    r"^(?P<status>Mandatory|Optional|Conditional)"
    r"(?:\s+\(see rules?\s*(?P<rules>C\d+(?:,\s*C\d+)*)?\s*\))?"
    r"(?:\s+in\s+(?P<sequence_presence>mandatory|optional|conditional)"
    r"(?:\s+\(see rules?\s*(?P<sequence_rules>[^)]*)\))?\s+"
    r"(?:sequence|subsequence)\s+(?P<path>[A-Z](?:\d+|[a-z]|[A-Z])*))?$"
)
QUALIFIER_ROW = re.compile(
    r"^(?P<order>\d{1,3})\s+(?P<status>[MO])\s+(?P<qualifier>[A-Z0-9]{4})\s+"
    r"(?P<repetition>[RN])\b(?P<rest>.*)$"
)
#: A generic field lists its qualifiers as one numbered row followed by ``or`` rows. They
#: are alternatives within the same numbered position, so they inherit its order and status
#: and differ only in the qualifier itself.
QUALIFIER_ALTERNATIVE = re.compile(
    r"^or\s+(?P<qualifier>[A-Z0-9]{4})\s+(?P<repetition>[RN])\b(?P<rest>.*)$"
)
#: The tail of a qualifier row: the conditional-rule column, then the option column, then
#: the description. Both leading columns may be empty and the rule list may wrap.
QUALIFIER_TAIL_RULES = re.compile(r"^\s*(?P<rules>C\d{1,2}(?:\s*,\s*C\d{1,2})*)\b")
QUALIFIER_TAIL_OPTIONS = re.compile(r"^\s*(?P<options>[A-Z](?:\s*,\s*[A-Z])*)(?:\s+|$)")
QUALIFIER_HEADER = "Order M/O Qualifier R/N CR Options Qualifier Description"
CONDITIONAL_RULES = re.compile(r"C\d{1,2}")
ERROR_CODES = re.compile(r"\(Error code\(s\):\s*(?P<codes>[^)]+)\)")
#: ``CHQB Cheque``, ``CREDIT Credit transfer(s)``, ``BankOfRussia Central Bank …``: a code is
#: one token of letters and digits, upper case or camel case, followed by a capitalised
#: label. A line that wraps a description starts in lower case and is never an entry.
CODE_ENTRY = re.compile(
    r"^(?P<code>[A-Z][A-Z0-9]{1,11}|[A-Z][a-z]+(?:[A-Z][a-z]+)+)\s+(?P<label>[A-Z].*)$"
)
#: An introduction that closes the list ("must contain one of the following codes") against
#: one that leaves it open ("may be used", "or bilaterally agreed codes"). Only a closed list
#: becomes an allowed-value set: an open one, enforced, would reject codes the guide permits.
CODES_CLOSED = re.compile(r"\bmust\b", re.IGNORECASE)
CODES_OPEN = re.compile(
    r"bilaterally agreed|may be used|may also be used|other codes?", re.IGNORECASE
)
#: Anchored at the start of its own line on purpose. The introduction wraps, so it has to
#: be matched over a small window of following lines — but matching it *anywhere* in that
#: window let the next list's introduction claim the previous list's final code, which is
#: how ``DBNM`` quietly lost ``VEND`` and ``SETR`` lost ``TURN``.
CODES_INTRODUCTION = re.compile(
    r"^If Qualifier is (?P<qualifier>[A-Z0-9]{4})\b.*?(?:must contain|are allowed)"
)


def error_codes_in(text: str) -> tuple[str, ...]:
    """Every SWIFT error code a passage names, in order, without duplicates."""
    found: list[str] = []
    for match in ERROR_CODES.finditer(text):
        for raw in match.group("codes").replace(" or ", ",").split(","):
            code = raw.strip()
            if code and code not in found:
                found.append(code)
    return tuple(found)


def parse_field_specifications(
    pages: tuple[MrgPage, ...],
    spans: tuple[MrgSectionSpan, ...],
    *,
    message_type: str,
    message_name: str,
    release_text: str,
) -> tuple[tuple[MrgFieldSpec, ...], tuple[str, ...]]:
    """Read every numbered Field Specification into its blocks.

    Only the blocks that carry authority are interpreted. ``EXAMPLES`` is recorded as
    present and never read for rules: an example that happens to contain a field says the
    field is possible, never that it is required.
    """
    span = next((item for item in spans if item.section is MrgSection.FIELD_SPECIFICATION), None)
    if span is None:
        return (), ("FIELD_SPECIFICATION_SECTION_MISSING",)

    lines = section_lines(
        pages,
        span,
        message_type=message_type,
        message_name=message_name,
        release_text=release_text,
    )
    starts = [
        (index, FIELD_HEADING.match(line.text.strip()))
        for index, line in enumerate(lines)
        if FIELD_HEADING.match(line.text.strip())
    ]
    specs: list[MrgFieldSpec] = []
    problems: list[str] = []
    for position, (index, heading) in enumerate(starts):
        assert heading is not None  # noqa: S101 - filtered above
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        spec = _one_field_spec(lines[index:end], heading)
        if isinstance(spec, str):
            problems.append(spec)
            continue
        specs.append(spec)
    if not specs:
        problems.append("NO_FIELD_SPECIFICATION_FOUND")
    return tuple(specs), tuple(problems)


def _one_field_spec(lines: list[MrgLine], heading: re.Match[str]) -> MrgFieldSpec | str:
    ordinal = int(heading.group("ordinal"))
    tag = heading.group("tag")
    blocks: dict[MrgBlock, list[MrgLine]] = {}
    current: MrgBlock | None = None
    for line in lines[1:]:
        stripped = line.text.strip()
        if stripped in FIELD_BLOCKS:
            current = BLOCK_BY_LABEL[stripped]
            if current is MrgBlock.PRESENCE and current in blocks:
                # A second PRESENCE inside one numbered specification belongs to a copied
                # sub-part (MT n95's field 79 restates the copied fields). The field's own
                # presence is the first statement; the restatement is not read.
                current = None
                continue
            blocks.setdefault(current, [])
            continue
        if current is not None:
            blocks[current].append(line)

    presence_lines = blocks.get(MrgBlock.PRESENCE, [])
    presence_text = " ".join(item.text.strip() for item in presence_lines).strip()
    statement = PRESENCE_STATEMENT.match(presence_text)
    if statement is None:
        return f"PRESENCE_NOT_UNDERSTOOD_FIELD_{ordinal}_LINE_{lines[0].number}"

    # A flat message's fields sit in the body, ``ROOT`` — the name the runtime pack uses too.
    sequence_path = statement.group("path") or ROOT_SEQUENCE
    sequence_presence_text = (statement.group("sequence_presence") or "mandatory").upper()
    qualifiers = _qualifier_rows(
        blocks.get(MrgBlock.QUALIFIER, []),
        ordinal=ordinal,
        tag=tag,
        sequence_path=sequence_path,
    )
    code_lists = _code_blocks(blocks.get(MrgBlock.CODES, []))
    normative = [
        line
        for block in (
            MrgBlock.QUALIFIER,
            MrgBlock.CODES,
            MrgBlock.NETWORK_VALIDATED_RULES,
        )
        for line in blocks.get(block, [])
    ]
    return MrgFieldSpec(
        ordinal=ordinal,
        tag=tag,
        heading=lines[0].text.strip(),
        presence_text=presence_text,
        sequence_path=sequence_path,
        # A conditional sequence is read as optional: weaker than the guide, never stronger.
        sequence_presence=SequencePresence(
            "OPTIONAL" if sequence_presence_text == "CONDITIONAL" else sequence_presence_text
        ),
        field_status=statement.group("status").upper(),
        conditional_rules=tuple(CONDITIONAL_RULES.findall(statement.group("rules") or "")),
        qualifiers=qualifiers,
        codes=tuple((key, codes) for key, codes, _open in code_lists),
        open_code_lists=tuple(key for key, _codes, is_open in code_lists if is_open),
        formats=_format_block(blocks.get(MrgBlock.FORMAT, [])),
        error_codes=error_codes_in(" ".join(item.text for item in normative)),
        blocks=tuple(sorted(blocks, key=lambda item: item.value)),
        first_page=lines[0].page,
        last_page=lines[-1].page,
    )


FORMAT_OPTION_LINE = re.compile(r"^Option (?P<option>[A-Z])\b\s*(?P<rest>.*)$")
#: ``(Party Identifier)``, ``(D/C Mark)`` — words; never ``(1!n/33x)``, which is a group.
FORMAT_COMPONENT_LABEL = re.compile(r"\([A-Z][A-Za-z/ '’,.-]*\)")
#: Notation never has a run of three lower-case letters or a bare ``or``; prose does.
FORMAT_PROSE = re.compile(r"[a-z]{3,}|^[Oo]r$")


def _format_block(lines: list[MrgLine]) -> tuple[tuple[str, str], ...]:
    """Option letter → notation, from the FORMAT block.

    ``Option A [/1!a][/34x]`` / ``4!a2!a2!c[3!c]`` / ``(Identifier Code)`` is one option
    whose notation wrapped; ``16x (Reference)`` is a field without letter options. A
    ``Line n`` layout (structured narratives) is kept under the bare option as written,
    which leaves it to the format compiler to accept or refuse.
    """
    found: dict[str, list[str]] = {}
    current: str | None = None
    closed = False
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        option = FORMAT_OPTION_LINE.match(text)
        if option is not None:
            current = option.group("option")
            closed = False
            found.setdefault(current, [])
            text = option.group("rest")
        elif current is None:
            current = ""
            found.setdefault(current, [])
        cleaned = FORMAT_COMPONENT_LABEL.sub("", text).strip()
        if closed or not cleaned:
            continue
        if FORMAT_PROSE.search(cleaned):
            # "In option F, the following line formats must be used …" — the notation is
            # complete; what follows is prose about it, read by nothing here.
            closed = True
            continue
        found[current].append(cleaned)
    return tuple((option, "".join(parts)) for option, parts in found.items() if parts)


@dataclass
class _OpenQualifierRow:
    order: int
    status: RowStatus
    qualifier: str
    repetition: str
    first: MrgLine
    tail: list[str]


def _qualifier_rows(
    lines: list[MrgLine], *, ordinal: int, tag: str, sequence_path: str
) -> tuple[MrgQualifierRow, ...]:
    """Read a field's qualifier table.

    A generic field states one numbered row and then a run of ``or`` alternatives sharing
    its position. Both forms carry the same three trailing columns — the conditional rules
    that govern the qualifier, the format options it allows, and its description — and any
    of them may wrap onto the following line, so a row closes only when the next one opens.
    """
    rows: list[MrgQualifierRow] = []
    current: _OpenQualifierRow | None = None

    def close() -> None:
        nonlocal current
        if current is None:
            return
        rest = re.sub(r"-\s(?=\S)", "", " ".join(current.tail)).strip()
        conditional: tuple[str, ...] = ()
        rules = QUALIFIER_TAIL_RULES.match(rest)
        if rules:
            conditional = tuple(CONDITIONAL_RULES.findall(rules.group("rules")))
            rest = rest[rules.end() :]
        options: tuple[str, ...] = ()
        listed = QUALIFIER_TAIL_OPTIONS.match(rest)
        if listed:
            options = tuple(
                item.strip() for item in listed.group("options").split(",") if item.strip()
            )
            rest = rest[listed.end() :]
        rows.append(
            MrgQualifierRow(
                field_ordinal=ordinal,
                tag=tag,
                sequence_path=sequence_path,
                order=current.order,
                status=current.status,
                qualifier=current.qualifier,
                repetition=current.repetition,
                conditional_rules=conditional,
                options=options,
                description=" ".join(rest.split()),
                page=current.first.page,
                line=current.first.number,
            )
        )
        current = None

    for line in lines:
        stripped = line.text.strip()
        if stripped == QUALIFIER_HEADER or ERROR_CODES.fullmatch(stripped):
            continue
        numbered = QUALIFIER_ROW.match(stripped)
        if numbered:
            close()
            current = _OpenQualifierRow(
                order=int(numbered.group("order")),
                status=RowStatus(numbered.group("status")),
                qualifier=numbered.group("qualifier"),
                repetition=numbered.group("repetition"),
                first=line,
                tail=[numbered.group("rest")],
            )
            continue
        alternative = QUALIFIER_ALTERNATIVE.match(stripped)
        if alternative and current is not None:
            order, status = current.order, current.status
            close()
            current = _OpenQualifierRow(
                order=order,
                status=status,
                qualifier=alternative.group("qualifier"),
                repetition=alternative.group("repetition"),
                first=line,
                tail=[alternative.group("rest")],
            )
            continue
        if current is not None:
            current.tail.append(stripped)
    close()
    return tuple(rows)


def _code_blocks(lines: list[MrgLine]) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
    """``(qualifier, codes, open)`` per list the CODES block enumerates.

    A CODES block may introduce several lists, one per qualifier. Attributing all of them
    to the field would hand a qualifier codes that belong to a different one — the exact
    mistake a shared YAML anchor once made in this repository's own configuration.
    """
    collected: dict[str, list[str]] = {}
    openness: dict[str, bool] = {}
    qualifier = ""
    intro: list[str] = []
    text_lines = [line.text.strip() for line in lines]
    for index, stripped in enumerate(text_lines):
        introduction = CODES_INTRODUCTION.match(" ".join(text_lines[index : index + 3]))
        if introduction:
            qualifier = introduction.group("qualifier")
            collected.setdefault(qualifier, [])
            intro = [stripped]
            continue
        entry = CODE_ENTRY.match(stripped)
        if entry:
            collected.setdefault(qualifier, [])
            if qualifier not in openness:
                wording = " ".join(intro)
                openness[qualifier] = bool(CODES_OPEN.search(wording)) or not CODES_CLOSED.search(
                    wording
                )
            code = entry.group("code")
            if code not in collected[qualifier]:
                collected[qualifier].append(code)
            continue
        intro.append(stripped)
    return tuple(
        (key, tuple(value), openness.get(key, True))
        for key, value in collected.items()
        if value
    )


@dataclass
class StructureBuilder:
    """Assembles one :class:`MrgStructure` from the parsed halves."""

    message_type: str
    standards_release: str
    problems: list[str] = field(default_factory=list)

    def build(
        self,
        pages: tuple[MrgPage, ...],
        spans: tuple[MrgSectionSpan, ...],
        *,
        message_name: str,
        release_text: str,
    ) -> MrgStructure:
        sequences, rows, table_problems = parse_format_specification(
            pages,
            spans,
            message_type=self.message_type,
            message_name=message_name,
            release_text=release_text,
        )
        specs, spec_problems = parse_field_specifications(
            pages,
            spans,
            message_type=self.message_type,
            message_name=message_name,
            release_text=release_text,
        )
        return MrgStructure(
            message_type=self.message_type,
            standards_release=self.standards_release,
            sequences=sequences,
            rows=rows,
            field_specs=specs,
            problems=(*self.problems, *table_problems, *spec_problems),
        )

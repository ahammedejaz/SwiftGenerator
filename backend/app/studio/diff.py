"""Compare the message a tester imported with the one the studio regenerated.

The question this answers is narrow and important: *the message that came back is not
byte-identical to the one I pasted — should I care?* Almost always the answer is no, and
almost always the tester cannot tell that at a glance. So every difference is attributed to
a reason, in the product's own words:

``USER_EDIT``
    You changed this value.
``NORMALISATION``
    Same meaning, written the studio's way — specification field order, a header rebuilt
    from the client profile, indentation.
``IMPORT_DROPPED``
    The original held something outside the configured subset. It was reported at import
    and is not in the regenerated message.
``NOT_REPRODUCED``
    Deliberately never written: FIN Block 5 trailers, user-header fields the studio does not
    emit, the MX ``Sgntr`` element. These are allocated by a messaging interface or by the
    network. **A difference here is never an application error** and is never counted as one.
``UNEXPLAINED``
    None of the above fitted. Reported honestly rather than guessed at — an unexplained
    difference is the only kind worth investigating, and mislabelling one as normalisation
    would hide exactly the case this whole comparison exists to surface.

Two comparison bases, because the formats mean different things by "the same message":

``FIN_LINES``
    MT is compared line for line on the FIN text exactly as rendered. Line structure *is*
    the message, so nothing is normalised away first.
``CANONICAL_XML``
    MX is compared on meaning, not layout. Both sides are re-serialised into one
    deterministic form first, so indentation, attribute order, self-closing style and
    whitespace-only text can never show up as a difference. What survives is structure and
    values.

Everything here is `difflib` and string comparison. No model is called, and none could be:
a diff a tester is expected to trust has to be reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from xml.etree import ElementTree

from app.studio.models import (
    DiffBasis,
    DiffKind,
    DiffLine,
    DiffReason,
    DiffSummary,
    ElementInput,
    FieldInput,
    MessageDiff,
    MessageFormat,
    MessageOutputs,
    RenderedLine,
    ValidationIssue,
)

#: FIN blocks the studio reads but never writes back. A difference here is expected.
_TRAILER_BLOCK = re.compile(r"^\{5:")
_USER_HEADER_BLOCK = re.compile(r"^\{3:")
_MT_FIELD_LINE = re.compile(r"^:(?P<tag>\d{2}[A-Z]?):(?::(?P<qualifier>[A-Z0-9]{4})//)?")
_SEQUENCE_LINE = re.compile(r"^:16[RS]:")
_TAG = re.compile(r"^(?:\{(?P<ns>[^}]*)\})?(?P<name>.+)$")

#: Above this many lines on either side, a line-by-line comparison has stopped being
#: something a person reads. It is also where the cost bites: attributing a difference means
#: checking it against the reported import issues, so the work is lines x issues. A 1 MB
#: paste of unmatched lines took over two minutes before this bound existed.
MAX_DIFF_LINES = 3_000

#: Above this many import issues the same applies from the other direction. A message this
#: broken is read from its issue list, not from chips on thousands of lines.
MAX_ATTRIBUTED_ISSUES = 200

#: Import rule ids that mean "the original held something we deliberately do not write".
NOT_REPRODUCED_RULES = frozenset(
    {
        "MT_IMPORT_TRAILER_DROPPED",
        "MT_IMPORT_USER_HEADER_FIELD_DROPPED",
        "MX_IMPORT_SIGNATURE_DROPPED",
    }
)


#: One sentence per reason, shown beside the diff so nobody has to read this module.
REASON_TEXT: dict[DiffReason, str] = {
    DiffReason.USER_EDIT: "You changed this value.",
    DiffReason.NORMALISATION: (
        "Same meaning, written the studio's way — specification order, indentation, or a "
        "header rebuilt from the client profile."
    ),
    DiffReason.IMPORT_DROPPED: (
        "The original held something outside the configured subset. It was reported when "
        "the message was imported and is not in the regenerated message."
    ),
    DiffReason.NOT_REPRODUCED: (
        "Allocated by a messaging interface or by the network, so the studio never writes "
        "it. This is expected and is not an error."
    ),
    DiffReason.UNEXPLAINED: (
        "The studio could not account for this difference. Worth a look — this is the only "
        "kind of difference that usually means something."
    ),
}


# --------------------------------------------------------------------------------------
# Canonical forms
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalLine:
    """One line of the canonical form, and the element path it came from."""

    text: str
    path: str


def canonical_xml(xml: str) -> list[CanonicalLine]:
    """Re-serialise a document into one deterministic form, one element per line.

    This is what makes the MX comparison about meaning. Indentation, attribute order,
    self-closing style, whitespace-only text and redundant namespace declarations are all
    decided here for both sides, so they cannot appear as differences. Element *order* is
    preserved, because in ISO 20022 it is part of the message rather than a presentation
    choice.

    Each line keeps its absolute path, which is how a difference is later matched to the
    business field it belongs to — a diff that says `<TxId>` and nothing else makes the
    tester do the translation the studio exists to do for them.
    """
    text = xml.strip()
    if not text:
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        try:
            body = _strip_declaration(text)
            root = ElementTree.fromstring(f"<CanonicalRoot>{body}</CanonicalRoot>")
        except ElementTree.ParseError:
            # Not parseable: fall back to the raw lines so the tester still sees a
            # comparison rather than an empty panel.
            return [
                CanonicalLine(text=line.rstrip(), path="")
                for line in text.splitlines()
                if line.strip()
            ]
        return _walk(root, 0, "", None, skip_self=True)
    return _walk(root, 0, "", None)


def _strip_declaration(text: str) -> str:
    return re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text, flags=re.IGNORECASE)


def _walk(
    node: ElementTree.Element,
    depth: int,
    parent_path: str,
    inherited_namespace: str | None,
    *,
    skip_self: bool = False,
) -> list[CanonicalLine]:
    if skip_self:
        lines: list[CanonicalLine] = []
        for child in node:
            lines.extend(_walk(child, depth, parent_path, inherited_namespace))
        return lines

    namespace, name = _split_tag(node.tag)
    path = f"{parent_path}/{name}"
    attributes = "".join(
        f' {_split_tag(key)[1]}="{value}"' for key, value in sorted(node.attrib.items())
    )
    # Declare the namespace only where it actually changes, exactly as a serialiser would.
    # Repeating it on every element buries the value the reader is looking for.
    if namespace and namespace != inherited_namespace:
        attributes = f' xmlns="{namespace}"' + attributes
    indent = "  " * depth
    children = list(node)
    text = (node.text or "").strip()
    if not children:
        return [CanonicalLine(text=f"{indent}<{name}{attributes}>{text}</{name}>", path=path)]
    lines = [CanonicalLine(text=f"{indent}<{name}{attributes}>", path=path)]
    for child in children:
        lines.extend(_walk(child, depth + 1, path, namespace or inherited_namespace))
    lines.append(CanonicalLine(text=f"{indent}</{name}>", path=path))
    return lines


def _split_tag(tag: str) -> tuple[str, str]:
    match = _TAG.match(tag)
    if match is None:  # pragma: no cover - ElementTree never yields an empty tag
        return "", tag
    return match.group("ns") or "", match.group("name")


def choose_comparison(
    format_: MessageFormat, original: str, outputs: MessageOutputs
) -> tuple[str, str, DiffBasis, str]:
    """Pick like-for-like sides, so the diff shows differences rather than shape.

    A tester who pasted a bare ``Document`` has not "removed" a business application
    header, and one who pasted a text block has not "removed" Blocks 1 and 2. Comparing the
    wrapped output against either would bury the real differences under the wrapper.
    """
    if format_ is MessageFormat.MT:
        pasted_envelope = "{1:" in original or "{2:" in original
        if pasted_envelope and outputs.fin:
            return original, outputs.fin, DiffBasis.FIN_LINES, "the complete FIN message"
        regenerated = outputs.block4 or outputs.fin or ""
        return _text_block(original), regenerated, DiffBasis.FIN_LINES, "the text block"

    pasted_header = "AppHdr" in original
    if pasted_header and outputs.xml:
        return original, outputs.xml, DiffBasis.CANONICAL_XML, "the header and the document"
    return (
        original,
        outputs.document or outputs.xml or "",
        DiffBasis.CANONICAL_XML,
        "the document, without its business application header",
    )


def _text_block(original: str) -> str:
    """Reduce a full FIN message to its text block, for comparison with Block 4 output."""
    start = original.find("{4:")
    if start == -1:
        return original
    end = original.find("-}", start)
    return original[start : end + 2] if end != -1 else original[start:]


# --------------------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------------------


def _value_key(item: FieldInput | ElementInput) -> tuple[str, int]:
    if isinstance(item, FieldInput):
        return (item.id or f"{item.sequence}:{item.tag}:{item.qualifier}", item.occurrence)
    return (item.path, item.occurrence)


def _edited_values(
    imported: list[FieldInput] | list[ElementInput],
    submitted: list[FieldInput] | list[ElementInput],
) -> set[str]:
    """Locations whose value the caller changed, added or removed since importing."""
    before = {_value_key(item): item.value for item in imported}
    after = {_value_key(item): item.value for item in submitted}
    return {
        key[0]
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    }


def _normalise(text: str) -> str:
    """Everything that is presentation rather than content, removed."""
    return re.sub(r"\s+", "", text).upper()


class _Attributor:
    def __init__(
        self,
        format_: MessageFormat,
        edited: set[str],
        issues: list[ValidationIssue],
        rendered: list[RenderedLine],
        original_lines: list[str],
        regenerated_lines: list[str],
        paths: dict[str, str],
    ) -> None:
        self._format = format_
        self._edited = edited
        self._issues = issues
        self._rendered = {line.text.strip(): line for line in rendered}
        self._by_field_id = {
            line.field_id: line for line in rendered if line.field_id is not None
        }
        self._paths = paths
        self._original_present = {_normalise(line) for line in original_lines}
        self._regenerated_present = {_normalise(line) for line in regenerated_lines}

    # -- what a line is about ---------------------------------------------------------

    def describe(self, text: str) -> tuple[str | None, str | None]:
        """The business field a line carries, and where it lives."""
        rendered = self._rendered.get(text.strip())
        if rendered is not None:
            return rendered.display_name, rendered.field_id
        # MX is compared on a canonical rendering, so the line text never matches the
        # rendered output verbatim. Its element path does, and that is what names the field.
        path = self._paths.get(text.strip())
        if path:
            by_path = self._by_field_id.get(path)
            return (by_path.display_name if by_path else None), path
        if self._format is MessageFormat.MT:
            match = _MT_FIELD_LINE.match(text.strip())
            if match:
                tag = match.group("tag")
                qualifier = match.group("qualifier")
                return None, tag + (f"/{qualifier}" if qualifier else "")
        stripped = text.strip()
        if stripped.startswith("<") and not stripped.startswith("</"):
            name = stripped[1:].split(">")[0].split(" ")[0]
            return None, name
        return None, None

    def _issue_about(self, text: str) -> ValidationIssue | None:
        """Find the import issue that already explained this line.

        Matched on content rather than on a line number: the parser numbers lines within the
        text block it was given, which is not the same numbering as the whole FIN message,
        and quietly comparing the two would attribute the wrong line.
        """
        needle = _normalise(text)
        for issue in self._issues:
            current = _normalise(issue.current_value or "")
            field = _normalise(issue.field or "")
            if current and current in needle:
                return issue
            if field and field.replace("/", "") in needle.replace("/", ""):
                return issue
        return None

    # -- the reasons -------------------------------------------------------------------

    def _is_never_written(self, text: str) -> bool:
        stripped = text.strip()
        if self._format is MessageFormat.MT:
            return bool(_TRAILER_BLOCK.match(stripped) or _USER_HEADER_BLOCK.match(stripped))
        return "Sgntr" in stripped

    def _is_edited(self, location: str | None) -> bool:
        if location is None:
            return False
        return location in self._edited or any(
            location.endswith(item) or item.endswith(location) for item in self._edited
        )

    def removed(self, text: str) -> tuple[DiffReason, str | None, str | None]:
        field, location = self.describe(text)
        if self._is_never_written(text):
            return DiffReason.NOT_REPRODUCED, field, location
        issue = self._issue_about(text)
        if issue is not None:
            return (
                DiffReason.NOT_REPRODUCED
                if issue.rule_id in NOT_REPRODUCED_RULES
                else DiffReason.IMPORT_DROPPED,
                field or issue.field,
                location or issue.location,
            )
        if self._is_edited(location):
            return DiffReason.USER_EDIT, field, location
        if _normalise(text) in self._regenerated_present:
            # The same content is in the regenerated message somewhere else: the composer
            # writes fields in specification order, so a reordered input moves rather than
            # disappears.
            return DiffReason.NORMALISATION, field, location
        return DiffReason.UNEXPLAINED, field, location

    def added(self, text: str) -> tuple[DiffReason, str | None, str | None]:
        field, location = self.describe(text)
        if self._is_edited(location):
            return DiffReason.USER_EDIT, field, location
        if _normalise(text) in self._original_present:
            return DiffReason.NORMALISATION, field, location
        rendered = self._rendered.get(text.strip())
        if rendered is not None and rendered.origin.value != "USER_ENTERED":
            # A header, an envelope value or a sequence marker the studio builds itself.
            return DiffReason.NORMALISATION, field, location
        if self._format is MessageFormat.MT and _SEQUENCE_LINE.match(text.strip()):
            return DiffReason.NORMALISATION, field, location
        return DiffReason.UNEXPLAINED, field, location

    def changed(
        self, before: str, after: str
    ) -> tuple[DiffReason, str | None, str | None]:
        field, location = self.describe(after)
        if location is None:
            field, location = self.describe(before)
        if self._is_edited(location):
            return DiffReason.USER_EDIT, field, location
        if _normalise(before) == _normalise(after):
            return DiffReason.NORMALISATION, field, location
        issue = self._issue_about(before)
        if issue is not None:
            # Same rule as a removed line: a user-header field the studio does not emit is
            # not "dropped on import", it is one of the things it deliberately never writes.
            return (
                DiffReason.NOT_REPRODUCED
                if issue.rule_id in NOT_REPRODUCED_RULES
                else DiffReason.IMPORT_DROPPED
            ), field or issue.field, location
        if self._is_never_written(before) or self._is_never_written(after):
            return DiffReason.NOT_REPRODUCED, field, location
        return DiffReason.UNEXPLAINED, field, location


# --------------------------------------------------------------------------------------
# Building the diff
# --------------------------------------------------------------------------------------


def build_diff(
    *,
    format_: MessageFormat,
    original: str,
    outputs: MessageOutputs,
    imported_fields: list[FieldInput],
    imported_elements: list[ElementInput],
    submitted_fields: list[FieldInput],
    submitted_elements: list[ElementInput],
    issues: list[ValidationIssue],
    rendered_lines: list[RenderedLine],
) -> MessageDiff:
    """Compare an imported message with the one regenerated from it.

    ``issues`` should be the import issues *and* warnings together: a warning that a trailer
    was dropped is exactly what explains the corresponding difference, and separating them
    here would leave that difference unexplained.
    """
    left_text, right_text, basis, compared = choose_comparison(format_, original, outputs)
    paths: dict[str, str] = {}
    if basis is DiffBasis.CANONICAL_XML:
        canonical_left = canonical_xml(left_text)
        canonical_right = canonical_xml(right_text)
        # setdefault keeps the first writer, so the regenerated side is iterated first: its
        # path is the one that resolves against the rendered message and therefore names
        # the business field. A line only the original has still contributes its own.
        for item in (*canonical_right, *canonical_left):
            paths.setdefault(item.text.strip(), item.path)
        left = [item.text for item in canonical_left]
        right = [item.text for item in canonical_right]
    else:
        left = [line.rstrip() for line in left_text.strip().splitlines()]
        right = [line.rstrip() for line in right_text.strip().splitlines()]

    # Refuse to produce a comparison nobody could read, rather than spending minutes
    # building one. The verdict — are these the same message? — is still answered, because
    # that is the part a tester actually needs and it costs nothing.
    oversized = max(len(left), len(right)) > MAX_DIFF_LINES
    too_many_issues = len(issues) > MAX_ATTRIBUTED_ISSUES
    if oversized or too_many_issues:
        identical = left == right
        reason = (
            f"These messages have more than {MAX_DIFF_LINES:,} lines, which is too many to "
            "compare line by line."
            if oversized
            else f"More than {MAX_ATTRIBUTED_ISSUES} parts of the original could not be "
            "imported, so a line-by-line comparison would say little. Fix those first."
        )
        return MessageDiff(
            format=format_,
            basis=basis,
            compared=compared,
            comparable=False,
            not_compared_reason=reason,
            summary=DiffSummary(
                identical=identical,
                unchanged=0,
                added=0,
                removed=0,
                changed=0,
                expected=0,
                dropped=0,
                unexplained=0,
                by_reason={},
            ),
            lines=[],
            notes=[],
        )

    edited = (
        _edited_values(imported_fields, submitted_fields)
        if format_ is MessageFormat.MT
        else _edited_values(imported_elements, submitted_elements)
    )
    attributor = _Attributor(format_, edited, issues, rendered_lines, left, right, paths)

    lines: list[DiffLine] = []
    counts = {kind: 0 for kind in DiffKind}
    reasons: dict[str, int] = {}

    def record(line: DiffLine) -> None:
        counts[line.kind] += 1
        if line.reason is not None:
            reasons[line.reason.value] = reasons.get(line.reason.value, 0) + 1
        lines.append(line)

    matcher = SequenceMatcher(a=left, b=right, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                record(
                    DiffLine(
                        kind=DiffKind.UNCHANGED,
                        original_line=i1 + offset + 1,
                        regenerated_line=j1 + offset + 1,
                        original_text=left[i1 + offset],
                        regenerated_text=right[j1 + offset],
                    )
                )
            continue
        if tag == "replace":
            # Pair them up positionally so a one-value change reads as one changed line
            # rather than as an unrelated removal and addition.
            paired = min(i2 - i1, j2 - j1)
            for offset in range(paired):
                before, after = left[i1 + offset], right[j1 + offset]
                reason, field, location = attributor.changed(before, after)
                record(
                    DiffLine(
                        kind=DiffKind.CHANGED,
                        original_line=i1 + offset + 1,
                        regenerated_line=j1 + offset + 1,
                        original_text=before,
                        regenerated_text=after,
                        reason=reason,
                        explanation=REASON_TEXT[reason],
                        field=field,
                        location=location,
                    )
                )
            i1 += paired
            j1 += paired
            tag = "delete" if i1 < i2 else "insert"
        if tag == "delete" or i1 < i2:
            for offset in range(i2 - i1):
                text = left[i1 + offset]
                reason, field, location = attributor.removed(text)
                record(
                    DiffLine(
                        kind=DiffKind.REMOVED,
                        original_line=i1 + offset + 1,
                        original_text=text,
                        reason=reason,
                        explanation=REASON_TEXT[reason],
                        field=field,
                        location=location,
                    )
                )
        if tag == "insert" or j1 < j2:
            for offset in range(j2 - j1):
                text = right[j1 + offset]
                reason, field, location = attributor.added(text)
                record(
                    DiffLine(
                        kind=DiffKind.ADDED,
                        regenerated_line=j1 + offset + 1,
                        regenerated_text=text,
                        reason=reason,
                        explanation=REASON_TEXT[reason],
                        field=field,
                        location=location,
                    )
                )

    dropped = reasons.get(DiffReason.IMPORT_DROPPED.value, 0)
    unexplained = reasons.get(DiffReason.UNEXPLAINED.value, 0)
    total_differences = counts[DiffKind.ADDED] + counts[DiffKind.REMOVED] + counts[DiffKind.CHANGED]
    summary = DiffSummary(
        identical=total_differences == 0,
        unchanged=counts[DiffKind.UNCHANGED],
        added=counts[DiffKind.ADDED],
        removed=counts[DiffKind.REMOVED],
        changed=counts[DiffKind.CHANGED],
        # Trailer and interface values are counted here, with user edits and normalisation.
        # They are expected differences and must never be presented as application errors.
        expected=total_differences - dropped - unexplained,
        dropped=dropped,
        unexplained=unexplained,
        by_reason=reasons,
    )
    ordered = [reason for reason in DiffReason if reason.value in reasons]
    return MessageDiff(
        format=format_,
        basis=basis,
        compared=compared,
        comparable=True,
        summary=summary,
        lines=lines,
        notes=[REASON_TEXT[reason] for reason in ordered],
    )

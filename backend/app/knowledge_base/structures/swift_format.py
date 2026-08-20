"""SWIFT field format notation → a regular expression for the canonical value.

The notation is the one the Message Reference Guides print and Prowide's field classes
carry (``:4!c//16x``, ``<DATE4>``, ``[<N>]<CUR><AMOUNT>15``, ``35x[$35x]0-3``). It is
compiled once at pack-compile time; nothing here runs per request.

What is deliberately *not* invented: a token this compiler does not know makes the whole
field ``PARTIAL`` — the row keeps a length check and says so — rather than a guessed
pattern that would reject messages SWIFT accepts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The SWIFT ``x`` character set, plus space and the line-break the composer writes.
X_CLASS = r"[A-Za-z0-9/\-?:().,'+ ]"
#: ``y`` is x without lower case; ``z`` adds more punctuation.
Y_CLASS = r"[A-Z0-9/\-?:().,'+= !\"%&*<>;{@#_ ]"
Z_CLASS = r"[A-Za-z0-9/\-?:().,'+=!\"%&*<>;{@#_ \n]"

_MACROS: dict[str, str] = {
    "<DATE1>": r"\d{4}",
    "<DATE2>": r"\d{6}",
    "<DATE3>": r"\d{4}",
    "<DATE4>": r"\d{8}",
    "<YEAR>": r"\d{4}",
    "<TIME2>": r"\d{4}",
    "<TIME3>": r"\d{6}",
    "<HHMM>": r"\d{4}",
    "<UTC>": r"[+-]\d{4}",
    "<CUR>": r"[A-Z]{3}",
    "<BIC>": r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?",
    "<LT>": r"[A-Z0-9]{12}",
    "<N>": r"N",
    "<SIGN>": r"[+-]",
    "<ISIN>": r"ISIN",
    "<SPACE>": r" ",
    "<MIR>": r"\d{6}[A-Z0-9]{12}\d{10}",
    "<MOR>": r"\d{6}[A-Z0-9]{12}\d{10}",
    "<NUMBER>": r"\d+",
    "<VALUE>": r"\d+,\d*",
    "<DC>": r"[CD]",
    "<DM>": r"[DM]",
    "<CC>": r"[A-Z]{2}",
    "<MT>": r"\d{3}",
    "<OFFSET>": r"\d{4}",
    "<BOOL>": r"[YN]",
    "<DDHHMM>": r"\d{6}",
    "<HH>": r"\d{2}",
    "<YYMMDDHHMM>": r"\d{10}",
}

_CHAR_CLASSES: dict[str, str] = {
    "n": r"\d",
    "a": r"[A-Z]",
    "c": r"[A-Z0-9]",
    "x": X_CLASS,
    "y": Y_CLASS,
    "z": Z_CLASS,
    "h": r"[0-9A-F]",
    "e": r" ",
}

_TOKEN = re.compile(
    r"(?P<anglelen><(?P<al_len>\d+)(?P<al_fixed>!)?(?P<al_cls>[nacxyzhe])>)"
    r"|(?P<amount><AMOUNT>(?P<macro_len>\d+)?)"
    r"|(?P<macro><[A-Z0-9-]+>)"
    r"|(?P<lines>\d+)\*(?P<line_len>\d+)(?P<line_cls>[nacxyzhe])"
    r"|(?P<len>\d+)(?P<fixed>!)?(?P<cls>[nacxyzhed])"
    r"|(?P<lit>[A-Z]+|/|:|-|,|\.|\$|\s)"
    r"|(?P<open>\[)|(?P<close>\])(?P<rep>(?P<rep_min>\d+)-(?P<rep_max>\d+))?"
    r"|(?P<annotation>\(\*+\))"
)


class FormatUnsupported(Exception):
    pass


@dataclass(frozen=True)
class CompiledFormat:
    #: The regex for the canonical value — the part after the qualifier separator.
    pattern: str
    #: ``//`` normally; ``/`` where the format carries a mandatory data source scheme.
    qualifier_separator: str
    #: True when the format opens with ``:4!c`` — a qualified, generic field.
    qualified: bool
    #: An optional data source scheme was dropped from the canonical value.
    optional_dss_dropped: bool
    max_length: int | None
    multiline: bool
    #: Human-readable restatement of what is matched.
    description: str
    #: The value pattern with the qualifier and separator removed.
    value_notation: str


def compile_format(notation: str) -> CompiledFormat:
    """Compile one field format. Raises :class:`FormatUnsupported` for unknown notation."""
    cleaned = re.sub(r"\(\*+\)", "", notation.strip())
    qualified = False
    separator = "//"
    optional_dss = False
    value_notation = cleaned
    if cleaned.startswith(":4!c"):
        qualified = True
        rest = cleaned[4:]
        if rest.startswith("//"):
            value_notation = rest[2:]
        elif rest.startswith("/[8c]/"):
            optional_dss = True
            value_notation = rest[len("/[8c]/") :]
        elif rest.startswith("/8c/"):
            separator = "/"
            value_notation = rest[1:]
        elif rest.startswith("/"):
            separator = "/"
            value_notation = rest[1:]
        else:
            raise FormatUnsupported(f"qualified format without a separator: {notation}")
    regex, max_length, multiline = _compile_sequence(value_notation)
    return CompiledFormat(
        pattern=regex,
        qualifier_separator=separator,
        qualified=qualified,
        optional_dss_dropped=optional_dss,
        max_length=max_length,
        multiline=multiline,
        description=_describe(value_notation),
        value_notation=value_notation,
    )


def _compile_sequence(notation: str) -> tuple[str, int | None, bool]:
    parts: list[str] = []
    stack: list[list[str]] = []
    lengths: list[int] = [0]
    multiline = "$" in notation
    position = 0
    unbounded = False
    while position < len(notation):
        match = _TOKEN.match(notation, position)
        if match is None:
            raise FormatUnsupported(f"unknown notation at {position}: {notation!r}")
        position = match.end()
        if match.group("annotation"):
            continue
        if match.group("anglelen"):
            # Prowide writes ``<3!a>`` for a bracketed length token; same meaning as ``3!a``.
            width = int(match.group("al_len"))
            cls = _CHAR_CLASSES[match.group("al_cls")]
            parts.append(f"{cls}{{{width}}}" if match.group("al_fixed") else f"{cls}{{1,{width}}}")
            lengths[0] += width
            continue
        if match.group("open"):
            stack.append(parts)
            parts = []
            continue
        if match.group("close"):
            if not stack:
                raise FormatUnsupported(f"unbalanced bracket in {notation!r}")
            inner = "".join(parts)
            parts = stack.pop()
            if match.group("rep"):
                low = int(match.group("rep_min"))
                high = int(match.group("rep_max"))
                parts.append(f"(?:{inner}){{{low},{high}}}")
                lengths[0] *= 1
                unbounded = unbounded or high > 1
            else:
                parts.append(f"(?:{inner})?")
            continue
        if match.group("amount"):
            width = int(match.group("macro_len") or 15)
            parts.append(_amount(width))
            lengths[0] += width
            continue
        if match.group("macro"):
            name = match.group("macro")
            expansion = _MACROS.get(name)
            if expansion is None:
                raise FormatUnsupported(f"unknown macro {name}")
            parts.append(expansion)
            lengths[0] += _macro_length(name)
            continue
        if match.group("lines"):
            lines = int(match.group("lines"))
            width = int(match.group("line_len"))
            cls = _CHAR_CLASSES[match.group("line_cls")]
            parts.append(f"{cls}{{1,{width}}}(?:\\n{cls}{{1,{width}}}){{0,{lines - 1}}}")
            lengths[0] += lines * width + lines - 1
            multiline = multiline or lines > 1
            continue
        if match.group("len"):
            width = int(match.group("len"))
            cls_name = match.group("cls")
            if cls_name == "d":
                parts.append(_decimal(width))
                lengths[0] += width
                continue
            cls = _CHAR_CLASSES[cls_name]
            if match.group("fixed"):
                parts.append(f"{cls}{{{width}}}")
            else:
                parts.append(f"{cls}{{1,{width}}}")
            lengths[0] += width
            continue
        literal = match.group("lit")
        if literal == "$":
            parts.append(r"\n")
            lengths[0] += 1
        elif literal.isspace():
            parts.append(" ")
            lengths[0] += 1
        else:
            parts.append(re.escape(literal))
            lengths[0] += len(literal)
    if stack:
        raise FormatUnsupported(f"unbalanced bracket in {notation!r}")
    regex = "".join(parts)
    if not regex:
        raise FormatUnsupported("empty format")
    try:
        re.compile(regex)
    except re.error as error:
        raise FormatUnsupported(str(error)) from error
    return regex, (None if unbounded else lengths[0] or None), multiline


def _amount(width: int) -> str:
    """SWIFT amounts: digits, a mandatory decimal comma, at most ``width`` characters in
    total and at least one digit before the comma."""
    return rf"(?=[\d,]{{1,{width}}}$)\d{{1,{width - 1}}},\d{{0,{width - 2}}}"


def _decimal(width: int) -> str:
    return _amount(width)


def _macro_length(name: str) -> int:
    return {
        "<DATE1>": 4,
        "<DATE2>": 6,
        "<DATE3>": 4,
        "<DATE4>": 8,
        "<YEAR>": 4,
        "<TIME2>": 4,
        "<TIME3>": 6,
        "<HHMM>": 4,
        "<UTC>": 5,
        "<CUR>": 3,
        "<BIC>": 11,
        "<LT>": 12,
        "<N>": 1,
        "<SIGN>": 1,
        "<ISIN>": 4,
        "<SPACE>": 1,
        "<MIR>": 28,
        "<MOR>": 28,
        "<NUMBER>": 18,
        "<VALUE>": 18,
        "<DC>": 1,
        "<DM>": 1,
        "<CC>": 2,
        "<MT>": 3,
        "<OFFSET>": 4,
        "<BOOL>": 1,
        "<DDHHMM>": 6,
        "<HH>": 2,
        "<YYMMDDHHMM>": 10,
    }.get(name, 0)


def _describe(notation: str) -> str:
    words = (
        notation.replace("<DATE4>", "YYYYMMDD")
        .replace("<DATE2>", "YYMMDD")
        .replace("<TIME2>", "HHMM")
        .replace("<TIME3>", "HHMMSS")
        .replace("<CUR>", "currency")
        .replace("<AMOUNT>15", "amount (comma decimal, max 15)")
        .replace("<BIC>", "BIC")
        .replace("<N>", "N")
        .replace("$", " newline ")
    )
    return f"SWIFT format {notation}: {words}".strip()


def is_value_less(notation: str) -> bool:
    """``$`` or nothing: a field whose line is its tag alone (``:15A:`` opens a sequence)."""
    cleaned = re.sub(r"\(\*+\)", "", notation.strip())
    return cleaned in {"", "$"}


def input_kind_for(compiled: CompiledFormat, *, codes: bool) -> str:
    """The studio control the format implies. Names match ``InputKind`` values."""
    value = compiled.value_notation
    if codes:
        return "SELECT"
    if value in {"<DATE4>", "<DATE2>"}:
        return "DATE"
    if value.startswith("<DATE4><TIME2>") or value.startswith("<DATE4><TIME3>"):
        return "DATETIME"
    if value == "<BIC>":
        return "PARTY_BIC"
    if "<CUR><AMOUNT>" in value:
        return "AMOUNT"
    if "<AMOUNT>" in value and "4!c/" in value:
        return "QUANTITY"
    if value == "<CUR>":
        return "CURRENCY"
    if value == "1a":
        return "INDICATOR"
    return "TEXT"


# -- synthetic values -------------------------------------------------------------------------


_SYNTHETIC_MACROS: dict[str, str] = {
    "<DATE1>": "0818",
    "<DATE2>": "260818",
    "<DATE3>": "2608",
    "<DATE4>": "20260818",
    "<YEAR>": "2026",
    "<TIME2>": "1200",
    "<TIME3>": "120000",
    "<HHMM>": "1200",
    "<UTC>": "+0100",
    "<CUR>": "USD",
    "<BIC>": "SYNTGB2LXXX",
    "<LT>": "SYNTGB2LAXXX",
    "<N>": "",
    "<SIGN>": "+",
    "<ISIN>": "ISIN",
    "<SPACE>": " ",
    "<MIR>": "260818SYNTGB2LAXXX0001000001",
    "<MOR>": "260818SYNTGB2LAXXX0001000001",
    "<NUMBER>": "1",
    "<VALUE>": "1,",
    "<DC>": "C",
    "<DM>": "D",
    "<CC>": "GB",
    "<MT>": "103",
    "<OFFSET>": "0100",
    "<BOOL>": "Y",
    "<DDHHMM>": "181200",
    "<HH>": "12",
    "<YYMMDDHHMM>": "2608181200",
}


def synthetic_value(notation: str, *, codes: list[str] | None = None, seed: str = "SYNTH") -> str:
    """A structurally valid, clearly synthetic value for one value notation.

    Optional parts are omitted, repeats are taken once, the first allowed code wins where a
    code list exists, and text fields say SYNTHETIC. Nothing here is a real reference,
    institution or instrument.
    """
    compiled = compile_format(notation)
    value_notation = compiled.value_notation
    if codes and re.fullmatch(r"\d!c", value_notation):
        return codes[0]
    out: list[str] = []
    depth = 0
    position = 0
    while position < len(value_notation):
        match = _TOKEN.match(value_notation, position)
        if match is None:
            raise FormatUnsupported(value_notation)
        position = match.end()
        if match.group("annotation"):
            continue
        if match.group("anglelen"):
            width = int(match.group("al_len"))
            fixed = bool(match.group("al_fixed"))
            out.append(_fill(match.group("al_cls"), width if fixed else min(width, 9), seed))
            continue
        if match.group("open"):
            depth += 1
            continue
        if match.group("close"):
            depth -= 1
            continue
        if depth:
            continue  # optional content is left out of a minimal sample
        if match.group("amount"):
            out.append("1000,")
            continue
        if match.group("macro"):
            out.append(_SYNTHETIC_MACROS.get(match.group("macro"), ""))
            continue
        if match.group("lines"):
            width = int(match.group("line_len"))
            out.append(_fill(match.group("line_cls"), min(width, 9), seed))
            continue
        if match.group("len"):
            width = int(match.group("len"))
            cls = match.group("cls")
            fixed = bool(match.group("fixed"))
            if cls == "d":
                out.append("1000,")
            elif cls == "c" and width == 4 and codes:
                out.append(codes[0])
            else:
                out.append(_fill(cls, width if fixed else min(width, 9), seed))
            continue
        literal = match.group("lit")
        if literal == "$":
            out.append("\n")
        else:
            out.append(literal)
    value = "".join(out)
    if "\n" in value:
        value = "\n".join(part for part in value.split("\n") if part)
    if not value and "[" in value_notation:
        # Everything is optional (``[<ISIN> 12!c][$][35x]…``): a sample still needs content,
        # so the first optional group is taken as written.
        opened = value_notation.index("[")
        depth = 0
        for index in range(opened, len(value_notation)):
            if value_notation[index] == "[":
                depth += 1
            elif value_notation[index] == "]":
                depth -= 1
                if depth == 0:
                    unwrapped = (
                        value_notation[:opened]
                        + value_notation[opened + 1 : index]
                        + value_notation[index + 1 :]
                    )
                    return synthetic_value(unwrapped, codes=codes, seed=seed)
    return value


def _fill(cls: str, width: int, seed: str) -> str:
    if cls == "n":
        return ("1234567890" * 3)[:width]
    if cls == "a":
        return (seed.upper() * 8)[:width]
    if cls == "c":
        return ((seed.upper() + "01") * 8)[:width]
    if cls == "h":
        return ("ABCDEF0123" * 3)[:width]
    if cls == "e":
        return " " * width
    return ("SYNTHETIC " * 8).strip()[:width].strip() or "S"

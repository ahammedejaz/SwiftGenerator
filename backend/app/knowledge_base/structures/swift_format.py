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
    r"|(?P<glines>\d+|n)\*\("
    r"|(?P<lines>\d+|n)\*(?P<line_len>\d+)(?P<line_cls>[nacxyzhe])"
    r"|(?P<len>\d+)(?P<fixed>!)?(?P<cls>[nacxyzhed])"
    r"|(?P<lit>[A-Z]+|/|:|-|,|\.|\$|\s)"
    r"|(?P<open>\[)|(?P<close>\])(?P<rep>(?P<rep_min>\d+)-(?P<rep_max>\d+)|\*(?P<rep_times>\d+))?"
    r"|(?P<gopen>\()|(?P<gclose>\))"
    r"|(?P<alt>\|)"
    r"|(?P<annotation>\(\*+\))"
)
#: ``n*78z`` — as many lines as the field allows; the notation states no bound.
UNBOUNDED_LINES = 100


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


@dataclass
class _Frame:
    """An open ``[``, ``(`` or ``N*(`` group while compiling: the alternatives seen so
    far, each a list of regex parts."""

    kind: str
    alternatives: list[list[str]]
    lines: int | None = None

    @property
    def parts(self) -> list[str]:
        return self.alternatives[-1]

    def close(self) -> str:
        inner = "|".join("".join(parts) for parts in self.alternatives)
        return f"(?:{inner})" if len(self.alternatives) > 1 else inner


def _compile_sequence(notation: str) -> tuple[str, int | None, bool]:
    frames: list[_Frame] = [_Frame("top", [[]])]
    lengths: list[int] = [0]
    multiline = "$" in notation
    position = 0
    unbounded = False
    while position < len(notation):
        match = _TOKEN.match(notation, position)
        if match is None:
            raise FormatUnsupported(f"unknown notation at {position}: {notation!r}")
        position = match.end()
        parts = frames[-1].parts
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
            frames.append(_Frame("[", [[]]))
            continue
        if match.group("gopen"):
            frames.append(_Frame("(", [[]]))
            continue
        if match.group("glines"):
            # ``4*(1!n/33x)``: a line layout repeated on up to four lines.
            count = match.group("glines")
            frames.append(
                _Frame("lines", [[]], lines=UNBOUNDED_LINES if count == "n" else int(count))
            )
            multiline = True
            continue
        if match.group("alt"):
            # ``A|B`` inside a group, or at the top level: the next alternative starts here.
            frames[-1].alternatives.append([])
            continue
        if match.group("close") or match.group("gclose"):
            frame = frames.pop() if len(frames) > 1 else None
            if frame is None or frame.kind == "top":
                raise FormatUnsupported(f"unbalanced bracket in {notation!r}")
            closing_square = bool(match.group("close"))
            if closing_square != (frame.kind == "["):
                raise FormatUnsupported(f"mismatched bracket in {notation!r}")
            inner = frame.close()
            parts = frames[-1].parts
            if frame.kind == "lines":
                assert frame.lines is not None  # noqa: S101 - set when the frame opened
                parts.append(f"(?:{inner})(?:\\n(?:{inner})){{0,{frame.lines - 1}}}")
                unbounded = True
            elif frame.kind == "(":
                parts.append(f"(?:{inner})")
            elif match.group("rep_times"):
                times = int(match.group("rep_times"))
                parts.append(f"(?:{inner}){{0,{times}}}")
                unbounded = unbounded or times > 1
            elif match.group("rep"):
                low = int(match.group("rep_min"))
                high = int(match.group("rep_max"))
                parts.append(f"(?:{inner}){{{low},{high}}}")
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
            count = match.group("lines")
            lines = UNBOUNDED_LINES if count == "n" else int(count)
            width = int(match.group("line_len"))
            cls = _CHAR_CLASSES[match.group("line_cls")]
            parts.append(f"{cls}{{1,{width}}}(?:\\n{cls}{{1,{width}}}){{0,{lines - 1}}}")
            lengths[0] += lines * width + lines - 1
            multiline = multiline or lines > 1
            unbounded = unbounded or count == "n"
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
    if len(frames) > 1:
        raise FormatUnsupported(f"unbalanced bracket in {notation!r}")
    regex = frames[0].close()
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
    # The length bound looks ahead over the digit/comma run only, so an amount followed by
    # more notation (MT940's 61: ``15d1!a3!c16x``) is bounded without anchoring at the end.
    return rf"(?=[\d,]{{1,{width}}}(?![\d,]))\d{{1,{width - 1}}},\d{{0,{width - 2}}}"


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


#: What each notation token is, in the words the studio uses everywhere else. Only tokens
#: whose meaning the notation itself states are listed; anything else keeps its notation,
#: so a description never claims to know more than the source does.
_TOKEN_WORDS: dict[str, str] = {
    "<DATE1>": "a month and day (MMDD)",
    "<DATE2>": "a date (YYMMDD)",
    "<DATE3>": "a year and month (YYMM)",
    "<DATE4>": "a date (YYYYMMDD)",
    "<YEAR>": "a year (YYYY)",
    "<TIME2>": "a time (HHMM)",
    "<TIME3>": "a time (HHMMSS)",
    "<HHMM>": "a time (HHMM)",
    "<HH>": "an hour (HH)",
    "<DDHHMM>": "a day and time (DDHHMM)",
    "<YYMMDDHHMM>": "a date and time (YYMMDDHHMM)",
    "<UTC>": "a UTC offset",
    "<CUR>": "a three-letter currency code",
    "<AMOUNT>": "an amount, written with a comma as the decimal separator",
    "<BIC>": "a BIC — eight or eleven characters",
    "<LT>": "a twelve-character logical terminal address",
    "<ISIN>": "the literal ISIN",
    "<SIGN>": "a plus or minus sign",
    "<N>": "an optional N for a negative value",
    "<NUMBER>": "a number",
    "<VALUE>": "a number, written with a comma as the decimal separator",
    "<DC>": "C for credit or D for debit",
    "<DM>": "D or M",
    "<CC>": "a two-letter country code",
    "<MT>": "a three-digit message type",
    "<BOOL>": "Y or N",
    "<OFFSET>": "a four-digit offset from UTC",
    "<SPACE>": "a space",
    "<MIR>": "a message input reference",
    "<MOR>": "a message output reference",
}
#: Plural then singular, so "exactly 1 capital letters" cannot be written.
_CLASS_WORDS: dict[str, tuple[str, str]] = {
    "n": ("digits", "digit"),
    "a": ("capital letters", "capital letter"),
    "c": ("capital letters or digits", "capital letter or digit"),
    "x": ("characters of text", "character of text"),
    "y": ("characters of text", "character of text"),
    "z": ("characters of text", "character of text"),
    "e": ("spaces", "space"),
    "h": ("hexadecimal characters", "hexadecimal character"),
}
_DECIMAL_WORDS = "a number, written with a comma as the decimal separator"


def _sized(width: int, cls: str, *, fixed: bool) -> str:
    plural, singular = _CLASS_WORDS.get(cls, ("characters", "character"))
    noun = singular if width == 1 else plural
    return f"{'exactly' if fixed else 'up to'} {width} {noun}"


_NOTATION_SHAPE = re.compile(r"[0-9A-Za-z!<>\[\]$*/():,.\-]+")
_NOTATION_TOKEN = re.compile(r"\d!?[nacxyzhed]\b|<[A-Z]")


def looks_like_notation(text: str) -> bool:
    """``:4!c//16x`` and ``1a`` are notation; ``Date is rendered as YYYYMMDD`` is prose.

    A configured message's rows carry a hand-authored sentence in the same slot a compiled
    preview row carries its notation, so anything that reads one has to tell them apart.
    """
    stripped = text.strip()
    return bool(
        stripped and _NOTATION_SHAPE.fullmatch(stripped) and _NOTATION_TOKEN.search(stripped)
    )


def describe_format(notation: str) -> str:
    """The notation as a sentence a tester who does not know SWIFT can act on.

    The studio promises that no SWIFT knowledge is required, and then a compiled preview
    row put ``<DATE2><CUR><AMOUNT>15`` under the box as its "expected format". This says
    the same thing in words. The notation is still printed, because an expert reads it
    faster than the sentence and a bug report needs it.
    """
    try:
        compiled = compile_format(notation)
    except FormatUnsupported:
        return f"SWIFT format {notation}."
    value_notation = compiled.value_notation
    if not value_notation.strip():
        return "This field carries no value; its tag alone opens or closes a sequence."
    currency_at = currency_offsets(value_notation)
    parts: list[str] = []
    position = 0
    optional = 0
    while position < len(value_notation):
        match = _TOKEN.match(value_notation, position)
        if match is None:
            return f"SWIFT format {notation}."
        start, position = match.start(), match.end()
        if match.group("annotation") or match.group("alt"):
            continue
        if match.group("open"):
            optional += 1
            continue
        if match.group("close"):
            optional = max(0, optional - 1)
            continue
        if match.group("gopen") or match.group("gclose") or match.group("glines"):
            continue
        word: str | None = None
        if match.group("macro"):
            word = _TOKEN_WORDS.get(match.group("macro"))
        elif match.group("amount"):
            word = _TOKEN_WORDS["<AMOUNT>"]
        elif match.group("len"):
            width, cls = int(match.group("len")), match.group("cls")
            fixed = bool(match.group("fixed"))
            if start in currency_at:
                word = _TOKEN_WORDS["<CUR>"]
            elif cls == "d":
                word = _DECIMAL_WORDS
            else:
                word = _sized(width, cls, fixed=fixed)
        elif match.group("lines") or match.group("anglelen"):
            width = int(match.group("line_len") or match.group("al_len"))
            cls = match.group("line_cls") or match.group("al_cls")
            word = _DECIMAL_WORDS if cls == "d" else _sized(width, cls, fixed=False)
        elif match.group("lit") is not None:
            # Punctuation the composer writes (``/``, ``//``, ``$``). It carries no value
            # for the caller to supply, so it is not part of what the field accepts.
            continue
        if word is None:
            # An unknown token. A sentence that leaves a component out reads as if the field
            # were simpler than it is, which is worse than showing the notation alone.
            return f"SWIFT format {notation}."
        parts.append(f"{word} (optional)" if optional else word)
    if not parts:
        return f"SWIFT format {notation}."
    if len(parts) == 1:
        sentence = parts[0][0].upper() + parts[0][1:] + "."
    else:
        sentence = "In order: " + ", then ".join(parts) + "."
    return f"{sentence} SWIFT format {notation}."


def is_single_code_token(value_notation: str) -> bool:
    """``4!c``, ``10a``, ``16x``, ``3!a``: a value that is one token, so a code list can be
    the whole value. ``8a/4!a2!c4!n4!a2!c`` or ``4!c[/4!c]`` carry more than the code, and
    a list enforced against the whole value would reject what the guide allows."""
    return re.fullmatch(r"\d{1,2}!?[acx]", value_notation.strip()) is not None


def is_value_less(notation: str) -> bool:
    """``$`` or nothing: a field whose line is its tag alone (``:15A:`` opens a sequence)."""
    cleaned = re.sub(r"\(\*+\)", "", notation.strip())
    return cleaned in {"", "$"}


#: ``3!a`` immediately before a decimal is a currency — the same reading
#: ``_COMPONENT_TOKENS`` already applies when a rule names the CURRENCY component of
#: ``6!n3!a15d``. Stating it once here is what stops the guide's own spelling of an amount
#: being sampled as ``SYN`` while Prowide's ``<CUR><AMOUNT>`` samples ``USD``.
#:
#: A ``3!a`` that is *not* followed by a decimal is left alone, however tempting: 71A
#: Details of Charges is ``3!a`` and its codes are BEN, OUR and SHA. Calling that a currency
#: would put a false sentence under the box and sample a value the field does not accept.
_CURRENCY_THEN_AMOUNT = re.compile(r"3!a(?=\[?(?:<AMOUNT>|\d{1,2}!?d))")


def currency_offsets(value_notation: str) -> frozenset[int]:
    """Character offsets in ``value_notation`` where a ``3!a`` token is a currency."""
    return frozenset(match.start() for match in _CURRENCY_THEN_AMOUNT.finditer(value_notation))


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
    # The guide's own spelling of a currency-and-amount pair. Without this the field reaches
    # the tester as a bare text box, and the studio has told them no SWIFT knowledge is
    # needed — so the control has to know what the notation already says it is.
    if currency_offsets(value):
        return "AMOUNT"
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
    if codes and is_single_code_token(value_notation):
        return codes[0]
    currency_at = currency_offsets(value_notation)
    out: list[str] = []
    depth = 0  # inside ``[…]``: optional content, left out of a minimal sample
    skipping = 0  # inside a later ``|`` alternative: the first alternative is the sample
    groups: list[bool] = []  # per open group: whether we are past its first alternative
    position = 0
    while position < len(value_notation):
        match = _TOKEN.match(value_notation, position)
        if match is None:
            raise FormatUnsupported(value_notation)
        position = match.end()
        if match.group("annotation"):
            continue
        if match.group("open"):
            depth += 1
            groups.append(False)
            continue
        if match.group("gopen") or match.group("glines"):
            groups.append(False)
            continue
        if match.group("alt"):
            if groups:
                if not groups[-1]:
                    groups[-1] = True
                    skipping += 1
            else:
                break  # a top-level alternative: the first one is the sample
            continue
        if match.group("close") or match.group("gclose"):
            if groups and groups.pop():
                skipping -= 1
            if match.group("close"):
                depth -= 1
            continue
        if depth or skipping:
            continue
        if match.group("anglelen"):
            width = int(match.group("al_len"))
            fixed = bool(match.group("al_fixed"))
            out.append(_fill(match.group("al_cls"), width if fixed else min(width, 9), seed))
            continue
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
            if match.start() in currency_at:
                out.append(_SYNTHETIC_MACROS["<CUR>"])
            elif cls == "d":
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
                    tail = value_notation[index + 1 :]
                    # ``[3!c]*10`` and ``[35x]0-3``: the repeat count belongs to the
                    # bracket and goes with it.
                    tail = re.sub(r"^(?:\*\d+|\d+-\d+)", "", tail)
                    unwrapped = (
                        value_notation[:opened] + value_notation[opened + 1 : index] + tail
                    )
                    return synthetic_value(unwrapped, codes=codes, seed=seed)
    return value


def _fill(cls: str, width: int, seed: str) -> str:
    repeat = width // 4 + 2  # long enough for any fixed width (MT026's 141 is ``64!h``)
    if cls == "n":
        return ("1234567890" * repeat)[:width]
    if cls == "a":
        return (seed.upper() * repeat)[:width]
    if cls == "c":
        return ((seed.upper() + "01") * repeat)[:width]
    if cls == "h":
        return ("ABCDEF0123" * repeat)[:width]
    if cls == "e":
        return " " * width
    return ("SYNTHETIC " * repeat).strip()[:width].strip() or "S"


# -- components ---------------------------------------------------------------------------


#: Components a rule may name, and the notation tokens that carry them. The first matching
#: token in the value notation is the component; nothing is inferred from the tag.
_COMPONENT_TOKENS: dict[str, tuple[str, ...]] = {
    "CURRENCY": ("<CUR>", "3!a"),
    "AMOUNT": ("<AMOUNT>", "15d", "12d", "18d"),
    "DATE": ("<DATE4>", "<DATE2>", "8!n", "6!n"),
    "SIGN": ("<N>", "[N]", "<SIGN>"),
}


def component_pattern(notation: str, component: str) -> str | None:
    """A regular expression with one named group ``value`` around the component.

    ``6!n3!a15d`` with ``CURRENCY`` → ``^\\d{6}(?P<value>[A-Z]{3})``; ``[N]3!a15d`` →
    ``^(?:N)?(?P<value>[A-Z]{3})``. ``None`` when the notation does not compile or does
    not carry the component — a rule about it is then not expressible, never approximated.
    """
    tokens = _COMPONENT_TOKENS.get(component)
    if not tokens:
        return None
    try:
        compiled = compile_format(notation)
    except FormatUnsupported:
        return None
    value_notation = compiled.value_notation
    position = -1
    chosen = ""
    for token in tokens:
        found = value_notation.find(token)
        if found >= 0 and (position < 0 or found < position):
            position, chosen = found, token
    if position < 0:
        return None
    before = value_notation[:position]
    target = value_notation[position : position + len(chosen)]
    if target == "[N]":
        target = "N"
    try:
        prefix, _length, _multiline = _compile_sequence(before) if before else ("", None, False)
        group, _length, _multiline = _compile_sequence(target)
    except FormatUnsupported:
        return None
    # Optional brackets opened before the component and closed after it cannot be split;
    # such a notation is reported as not expressible rather than mis-grouped.
    if before.count("[") != before.count("]") or before.count("(") != before.count(")"):
        return None
    return f"^{prefix}(?P<value>{group})"

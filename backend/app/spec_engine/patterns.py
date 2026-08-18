"""Deterministic sample values for the regular-expression subset ISO 20022 uses.

ISO 20022 patterns are overwhelmingly concatenations of character classes with counted
quantifiers — ``[A-Z0-9]{4,4}[A-Z]{2,2}`` — plus literals, optional groups and an
occasional top-level alternation. This walks that subset left to right, always choosing
the first alternative, the minimum count and the first usable character of a class, so
one pattern always yields one value.

Anything outside the subset returns ``None``: the caller records a visible
``SAMPLE_VALUE_UNDERIVABLE`` warning instead of shipping a guessed value.
"""

from __future__ import annotations

_PREFERRED = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz"


class _Unsupported(Exception):
    pass


class _Walker:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.pos = 0

    def peek(self) -> str | None:
        return self.pattern[self.pos] if self.pos < len(self.pattern) else None

    def take(self) -> str:
        char = self.pattern[self.pos]
        self.pos += 1
        return char

    # -- pieces ------------------------------------------------------------------

    def _class_char(self) -> str:
        """One character satisfying a [...] class: the first preferred member."""
        assert self.take() == "["
        if self.peek() == "^":
            raise _Unsupported("negated class")
        allowed: set[str] = set()
        previous: str | None = None
        while True:
            char = self.take()
            if char == "]":
                break
            if char == "\\":
                escaped = self.take()
                allowed.add(escaped)
                previous = escaped
                continue
            nxt = self.peek()
            if char == "-" and previous is not None and nxt is not None and nxt != "]":
                end = self.take()
                for code in range(ord(previous), ord(end) + 1):
                    allowed.add(chr(code))
                previous = None
                continue
            allowed.add(char)
            previous = char
        for candidate in _PREFERRED:
            if candidate in allowed:
                return candidate
        if allowed:
            return sorted(allowed)[0]
        raise _Unsupported("empty class")

    def _count(self) -> int:
        """The minimum repetition of a {m}, {m,n} or {m,} quantifier."""
        assert self.take() == "{"
        digits = ""
        while self.peek() is not None and self.peek() not in (",", "}"):
            digits += self.take()
        while self.peek() != "}":
            self.take()
        self.take()
        return int(digits) if digits else 0

    def _atom(self) -> str:
        char = self.peek()
        if char == "[":
            return self._class_char()
        if char == "(":
            return self._group()
        if char == "\\":
            self.take()
            escaped = self.take()
            if escaped == "d":
                return "0"
            if escaped in ".\\+*?()[]{}|/-":
                return escaped
            raise _Unsupported(f"escape \\{escaped}")
        if char is None or char in ")|":
            raise _Unsupported("dangling operator")
        if char == ".":
            self.take()
            return "A"
        return self.take()

    def _group(self) -> str:
        assert self.take() == "("
        # Render the first alternative; skip the rest at this nesting level.
        rendered = self._sequence(stop_at=(")", "|"))
        depth = 1
        while depth:
            char = self.peek()
            if char is None:
                raise _Unsupported("unclosed group")
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                self.take()
                break
            self.take()
        return rendered

    def _sequence(self, stop_at: tuple[str, ...] = ()) -> str:
        out: list[str] = []
        while True:
            char = self.peek()
            if char is None or char in stop_at:
                break
            piece = self._atom()
            nxt = self.peek()
            if nxt == "{":
                out.append(piece * self._count())
            elif nxt == "?":
                self.take()  # optional: choose absence
            elif nxt == "*":
                self.take()
            elif nxt == "+":
                self.take()
                out.append(piece)
            else:
                out.append(piece)
        return "".join(out)


def sample_from_pattern(pattern: str) -> str | None:
    """A deterministic value matching ``pattern``, or None when outside the subset."""
    import re

    walker = _Walker(pattern)
    try:
        candidate = walker._sequence(stop_at=("|",))
    except (_Unsupported, IndexError, AssertionError):
        return None
    try:
        if re.fullmatch(pattern, candidate):
            return candidate
    except re.error:
        return None
    return None

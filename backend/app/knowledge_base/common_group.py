"""``MT n90`` … ``MT n99``: one SWIFT guide that stands for nine messages.

The common-group guides are titled with ``n`` in place of the category digit, because the
same message exists in every category (MT 190, MT 290 … MT 990). The knowledge base keeps
the guide under the ``MTn90`` identity its cover states, and resolves it to concrete
message types only where another source models the member — the guide itself is not
evidence that every category uses it.

Runtime-safe: imported by the catalogue and the structure compiler alike.
"""

from __future__ import annotations

import re

COMMON_GROUP_NUMBER = re.compile(r"^n(?P<suffix>9\d)$")


def is_common_group(message_type: str) -> bool:
    return COMMON_GROUP_NUMBER.fullmatch(message_type.removeprefix("MT")) is not None


def common_group_members(message_type: str) -> tuple[str, ...]:
    """``MTn90`` → ``MT190`` … ``MT990``; any other type → itself."""
    match = COMMON_GROUP_NUMBER.fullmatch(message_type.removeprefix("MT"))
    if match is None:
        return (message_type,)
    return tuple(f"MT{category}{match.group('suffix')}" for category in range(1, 10))


def common_group_of(message_type: str) -> str | None:
    """``MT190`` → ``MTn90``; a message outside the common group → ``None``."""
    number = message_type.removeprefix("MT")
    if len(number) == 3 and number[0].isdigit() and number[1] == "9":
        return f"MTn{number[1:]}"
    return None

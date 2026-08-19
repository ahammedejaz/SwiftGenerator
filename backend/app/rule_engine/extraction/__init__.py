"""Turning source evidence into *candidate* rules — never into active ones.

Nothing in this package can affect a running validation. It writes candidate files; a
human reviews them; the reviewed pack goes through git and CI; only then does the
registry load it.
"""

from __future__ import annotations

#: Bump when the extraction instructions change: it is part of the cache key, so a
#: reworded prompt cannot silently reuse answers produced by the old one.
PROMPT_VERSION = "rule-extraction-v1"
#: Bump when the candidate or refuter schema changes, for the same reason.
SCHEMA_VERSION = "rule-candidate-v1"

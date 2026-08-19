"""Turning source evidence into *candidate* rules — never into active ones.

Nothing in this package can affect a running validation. It writes candidate files; a
human reviews them; the reviewed pack goes through git and CI; only then does the
registry load it.
"""

from __future__ import annotations

#: Bump when the extraction instructions change: it is part of the cache key, so a reworded
#: prompt cannot silently reuse answers produced by the old one. v2: REQUIRED and FORBIDDEN
#: now take several fields, as their conditional twins always did — a live run showed a
#: model reading "must carry the ISIN, the quantity and the account" as one rule, which is
#: what the sentence says, and the vocabulary rejecting it was the asymmetry.
PROMPT_VERSION = "rule-extraction-v2"
#: Bump when the candidate or refuter schema changes, for the same reason. v2: the strict
#: schema was silently dropping the candidate's `title` property, because the normaliser
#: stripped every dict key called `title` — schema keyword or field name alike. Answers
#: produced under v1 were missing a field the application required, so none of them may be
#: reused.
SCHEMA_VERSION = "rule-candidate-v2"

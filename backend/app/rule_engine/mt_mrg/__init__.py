"""Reading a SWIFT MyStandards MT Message Reference Guide as *evidence*.

This package is offline developer tooling. It never runs inside the application, and
nothing it produces is loaded by the runtime registry.

The reading is deliberately deterministic end to end. A Message Reference Guide states its
own structure — the section headings name the Format Specifications, the Network Validated
Rules, the Usage Rules and each Field Specification — so asking a model which page holds
the rules would replace a fact with a guess. The same unchanged bytes therefore always
yield the same sections, the same rule identifiers and the same candidate references.

Three boundaries hold everywhere below:

1. **The guide is evidence, not authority.** A candidate rule derived from it carries the
   source rule number, the SWIFT error code and the page, and stays ``REVIEW_REQUIRED``
   until a person who can read that page approves it.
2. **A release never leaks into another release.** Everything here is stamped with the
   release the document declares. A candidate compiled for one release does not resolve
   against another, and that failure is the point rather than an inconvenience.
3. **The source text stays local.** Only derived metadata — identifiers, hashes, page
   numbers, resolved references — is ever written anywhere this repository commits.
"""

from __future__ import annotations

#: Bumped when the deterministic reading changes in a way that could move a segment id, a
#: candidate rule id or a resolved reference. Recorded on every candidate pack.
MRG_READER_VERSION = "mt-mrg-reader/1"

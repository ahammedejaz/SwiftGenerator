# Sample Messages Guide

`/samples` lists one composer-generated synthetic scenario for each of MT530, MT537, MT540–MT548,
and MT564–MT568. Samples share the production deterministic composers—there is no separately
maintained raw-message source.

Each annotation maps a rendered line to its sequence occurrence, specification row, tag,
qualifier, entered value, business meaning, why-used text, presence rule, standards release, and
source status. The view can load a sample into the secure builder, where all values remain marked
`SAMPLE_DATA` and `confirmed=false`.

Sample field coverage is reported in [MESSAGE_COVERAGE_REPORT.md](MESSAGE_COVERAGE_REPORT.md).
A golden-path sample may omit optional rows, so sample coverage below 100% is not a composer gap.
All identifiers are synthetic and must not be sent to a client or network.

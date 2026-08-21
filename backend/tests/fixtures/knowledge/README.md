# Synthetic knowledge fixtures

Invented documents owned by this repository. They imitate the *layout* of standards
material so the knowledge sync, the chunker, retrieval, the pack compilers and the AI
authoring paths can be tested on a machine that holds no licensed document. Every file
declares `KNOWLEDGE-SOURCE-CLASSIFICATION: SYNTHETIC_FIXTURE` in its own body (classification
is content-derived, like every identity here), which is what permits excerpts and external
processing for these files alone.

- `guides/mt999-synthetic-guide-sr2026.txt` — an invented MT 999 guide, SR2026 layout
- `guides/mt999-synthetic-guide-sr2027.txt` — the same invented message one release later,
  with one rule and one qualifier changed (release isolation tests)
- `notes/mt998-usage-note.md` — an invented usage note containing the prompt-injection text
  the tests assert is treated as data
- `schemas/test.001.001.01.xsd` — the synthetic ISO 20022 schema the compiler tests use

Nothing here is a SWIFT or ISO rule, message or code.

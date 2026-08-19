"""Measuring the extraction pipeline — and being precise about what is measured.

Two runs, two different claims:

* **Offline** (``--live`` absent) stages scripted answers that stand in for realistic model
  behaviours — a correct reading, a wrong field, an over-broad reading, a hallucinated
  code, an answer that followed an injected instruction, a no-rule answer. It measures the
  **deterministic half**: diff classification, reference validation, the injection
  boundary, and no-rule handling. It cannot measure how good a model is, and nothing it
  produces may be reported as model precision or recall.
* **Live** calls the configured models and compares what they produce with the corpus's
  expected readings. That, and only that, measures extraction quality.
"""

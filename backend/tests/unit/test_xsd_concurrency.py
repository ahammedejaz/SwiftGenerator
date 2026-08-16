"""Schema validation must never attribute one document's errors to another.

`XMLSchema.validate()` writes its findings onto the schema object — `error_log` is instance
state, and libxml2 keeps a validation context there too. Those objects are shared by every
caller through an `lru_cache`, and FastAPI runs sync endpoints in a threadpool, so two
requests validating at the same time interleave on one object.

CI caught it: a lifecycle test failed about one run in three with *"No matching global
declaration available for the validation root"* against a document whose root the schema
plainly declares — an error belonging to some other document. It does not reproduce on macOS,
whose lxml wheel bundles a different libxml2, so this test is a guard on the invariant rather
than a reproduction of the race. It asserts the two things that must stay true: every verdict
is right under concurrency, and the verdict and its error log are read as one atomic step.
"""

from __future__ import annotations

import threading

import pytest

from app.profiles.loader import profiles
from app.studio.models import MessageFormat
from app.studio.mx import xsd as xsd_module
from app.studio.mx.generator import mx_generator
from app.studio.mx.registry import mx_registry
from app.studio.samples import available_variants, build_sample

PROFILE = "BASE_DEMO_V1"


def _document(message_type: str) -> str:
    variant = available_variants(MessageFormat.MX, message_type)[0]
    sample = build_sample(MessageFormat.MX, message_type, variant)
    built = mx_generator.build(message_type, profiles.get(PROFILE), list(sample.elements))
    return built.document


def test_validation_is_serialised_against_the_shared_schema() -> None:
    """The compiled schemas are cached and therefore shared; validating on them is not safe
    to do concurrently, so it must be behind a lock."""
    assert isinstance(xsd_module._VALIDATION_LOCK, type(threading.Lock()))  # noqa: SLF001


@pytest.mark.parametrize("message_type", [s.message_type for s in mx_registry.all_specs()])
def test_a_valid_document_is_valid_on_its_own(message_type: str) -> None:
    """The baseline the concurrent test below compares against."""
    spec = mx_registry.get(message_type)

    outcome = xsd_module.validate_document(spec, _document(message_type))

    assert outcome.performed is True
    assert outcome.passed is True, [issue.message for issue in outcome.issues]


def test_concurrent_validation_never_reports_another_document_s_errors() -> None:
    every = [spec.message_type for spec in mx_registry.all_specs()]
    documents = {message_type: _document(message_type) for message_type in every}
    # A cold cache, as a freshly started server has: schemas compile while others validate.
    xsd_module._compiled.cache_clear()  # noqa: SLF001

    wrong: list[str] = []

    def hammer(message_type: str) -> None:
        spec = mx_registry.get(message_type)
        for _ in range(30):
            outcome = xsd_module.validate_document(spec, documents[message_type])
            if not outcome.passed:
                wrong.append(
                    f"{message_type}: "
                    + "; ".join(issue.message for issue in outcome.issues)[:120]
                )
                return

    threads = [
        threading.Thread(target=hammer, args=(message_type,))
        for message_type in every
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert wrong == []

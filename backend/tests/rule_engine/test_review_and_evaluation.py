"""The review gate, and the corpus that measures the pipeline.

Two things are pinned here. A reviewer's decision is recorded in the file, hashes and all,
so a later reader can tell an approved-unchanged rule from an edited one. And the offline
corpus run measures the deterministic half of extraction — never the models, which only a
live run can measure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.rule_engine.compiler import compile_pack
from app.rule_engine.diagnostics import RuleEngineError
from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.evaluation.corpus import (
    CorpusCategory,
    ScriptedBehaviour,
    load_corpus,
    scripted_answer,
)
from app.rule_engine.evaluation.runner import run_evaluation
from app.rule_engine.extraction.review import (
    ReviewAction,
    apply_review,
    candidate_hashes,
    pack_yaml,
)
from app.rule_engine.models import RulePack, RuleReviewStatus
from app.rule_engine.refs import StructureIndex
from tests.rule_engine.conftest import AMT, CMONID, mx, pack, rule


def candidate_pack(index: StructureIndex):  # type: ignore[no-untyped-def]
    return pack(
        index,
        rules=(
            rule("CAND-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS), reviewed=False),
        ),
        reviewed=False,
    )


# -- review --------------------------------------------------------------------------------


def test_approving_records_who_did_it_and_what_they_approved(index: StructureIndex) -> None:
    original = candidate_pack(index)
    approved = apply_review(
        original,
        ReviewAction.APPROVE,
        reviewer="A. Reviewer",
        candidate_hashes=candidate_hashes(original),
    )
    assert approved.fully_reviewed()
    review = approved.rules[0].review
    assert review.status is RuleReviewStatus.REVIEWED
    assert review.reviewed_by == "A. Reviewer"
    # Equal hashes are themselves the evidence that nothing was edited.
    assert review.candidate_hash == review.rule_hash
    compile_pack(approved, index, require_reviewed=True)


def test_approving_an_edited_candidate_records_both_hashes(index: StructureIndex) -> None:
    original = candidate_pack(index)
    edited = original.model_copy(
        update={
            "rules": (
                rule(
                    "CAND-ONE",
                    Predicate(field=mx(CMONID), operator=Operator.EXISTS),
                    reviewed=False,
                ),
            )
        }
    )
    approved = apply_review(
        edited,
        ReviewAction.APPROVE,
        reviewer="A. Reviewer",
        candidate_hashes=candidate_hashes(original),
    )
    review = approved.rules[0].review
    assert review.candidate_hash != review.rule_hash


def test_approving_without_naming_a_reviewer_is_refused(index: StructureIndex) -> None:
    with pytest.raises(ValueError):
        apply_review(candidate_pack(index), ReviewAction.APPROVE, reviewer="  ")


def test_rejecting_and_deferring_leave_a_pack_unloadable(index: StructureIndex) -> None:
    rejected = apply_review(
        candidate_pack(index), ReviewAction.REJECT, reviewer="A. Reviewer", reason="over-broad"
    )
    assert rejected.rules[0].review.status is RuleReviewStatus.REJECTED
    assert rejected.review.rejection_reason == "over-broad"
    with pytest.raises(RuleEngineError):
        compile_pack(rejected, index, require_reviewed=True)

    deferred = apply_review(candidate_pack(index), ReviewAction.DEFER)
    assert deferred.rules[0].review.status is RuleReviewStatus.REVIEW_REQUIRED
    with pytest.raises(RuleEngineError):
        compile_pack(deferred, index, require_reviewed=True)


def test_a_reviewed_pack_round_trips_through_yaml_unchanged(index: StructureIndex) -> None:
    approved = apply_review(candidate_pack(index), ReviewAction.APPROVE, reviewer="A. Reviewer")
    text = pack_yaml(approved)
    reloaded = RulePack.model_validate(yaml.safe_load(text))
    assert reloaded == approved
    # Deterministic: the same pack always writes the same bytes.
    assert pack_yaml(reloaded) == text


def test_a_reviewed_file_carries_no_clock(index: StructureIndex) -> None:
    # A timestamp would make two reviews of the same decision differ byte for byte. The
    # commit is the timestamp, which is also what the compiled structure packs do.
    approved = apply_review(candidate_pack(index), ReviewAction.APPROVE, reviewer="A. Reviewer")
    assert approved.review.reviewed_at == "SOURCE_CONTROLLED"
    assert all(item.reviewed_at == "SOURCE_CONTROLLED" for item in approved.all_reviews())


def test_the_shipped_packs_are_byte_stable_under_a_rewrite() -> None:
    from app.rule_engine.registry import rule_pack_registry

    for compiled in rule_pack_registry.packs():
        path = rule_pack_registry.directory / compiled.pack.file_name()
        assert pack_yaml(compiled.pack) == path.read_text(encoding="utf-8")


# -- the corpus ------------------------------------------------------------------------------


def test_the_corpus_is_synthetic_and_says_so() -> None:
    corpus = load_corpus()
    document = corpus.document()
    assert "SYNTHETIC MATERIAL" in document
    assert "not a standard" in document
    assert len(corpus.cases) >= 40


def test_the_corpus_covers_the_categories_the_measurement_needs() -> None:
    corpus = load_corpus()
    present = {case.category for case in corpus.cases}
    assert present == set(CorpusCategory)
    # False positives matter more than coverage, so the no-rule cases are not a token few.
    no_rule = [case for case in corpus.cases if case.category is CorpusCategory.NO_RULE]
    assert len(no_rule) >= 5
    assert all(not case.expected_rules for case in no_rule)


def test_every_case_produces_exactly_one_segment() -> None:
    from app.rule_engine.evaluation.runner import corpus_source

    corpus = load_corpus()
    headings = [segment.heading for segment in corpus_source(corpus).segments]
    for case in corpus.cases:
        assert headings.count(case.heading) == 1, case.case_id


def test_a_staged_behaviour_that_does_nothing_would_be_caught() -> None:
    # `model_copy(update=...)` silently accepts an unknown key, so a camelCase typo would
    # make a "wrong field" pass identical to a correct one and the corpus would pass while
    # measuring nothing. The helper checks its keys; this proves it.
    from app.rule_engine.evaluation.corpus import _revised

    corpus = load_corpus()
    case = next(item for item in corpus.cases if item.expected_rules)
    original = case.expected_rules[0].as_candidate(case.case_id, "X#S0001")
    with pytest.raises(KeyError):
        _revised(original, ruleType="REQUIRED")
    assert _revised(original, targets=["/x"]).targets == ["/x"]


@pytest.mark.parametrize("behaviour", list(ScriptedBehaviour))
def test_every_staged_behaviour_produces_valid_model_output(
    behaviour: ScriptedBehaviour,
) -> None:
    from app.rule_engine.extraction.schemas import CandidateExtraction

    corpus = load_corpus()
    case = next(item for item in corpus.cases if item.expected_rules)
    CandidateExtraction.model_validate(scripted_answer(case, behaviour, "X#S0001"))


def test_the_offline_run_passes_and_measures_the_deterministic_half() -> None:
    report = run_evaluation()
    assert report.mode == "offline"
    assert report.passed, report.render()
    rendered = report.render()
    assert "does not and" in rendered and "cannot measure model precision" in rendered
    for metric in (
        "diff classification accuracy",
        "reference validation",
        "no-rule handling",
        "injection boundary held",
    ):
        assert metric in report.metrics


def test_the_offline_run_never_reaches_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # `make check` must not require a credential, and must not be able to spend one.
    import app.rule_engine.evaluation.runner as runner

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline evaluation must never construct a live client")

    monkeypatch.setattr(runner, "live_client", refuse)
    assert run_evaluation().passed


def test_a_live_run_without_a_credential_reports_a_missing_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.rule_engine.evaluation.runner as runner

    monkeypatch.setattr(runner, "live_client", lambda *args, **kwargs: None)
    report = run_evaluation(live=True)
    assert not report.passed
    assert "LIVE_EXTRACTION_NOT_VERIFIED" in report.render()
    assert "not a passing one" in report.render()


def test_the_corpus_file_is_committed_where_the_runner_looks_for_it() -> None:
    from app.rule_engine.evaluation.corpus import corpus_directory

    assert (corpus_directory() / "corpus.yaml").is_file()
    assert Path("config/rule_evaluation/corpus.yaml").is_file()


# -- the strict provider schema -------------------------------------------------------------


def test_every_candidate_field_survives_into_the_strict_schema() -> None:
    """The schema the provider is given must ask for exactly what the application requires.

    It did not: the normaliser stripped every dict key called ``title`` — schema keyword
    and *field name* alike — so the model was never asked for the candidate's title, never
    sent one, and every response was then rejected for a missing required field. Offline
    runs could not see it, because a scripted answer always includes every field. This is
    the guard that would have caught it.
    """
    from app.rule_engine.extraction.schemas import (
        CandidateExtraction,
        CandidateRule,
        Refutation,
        candidate_schema,
        refutation_schema,
    )

    for model, schema, definition in (
        (CandidateRule, candidate_schema(), "CandidateRule"),
        (CandidateExtraction, candidate_schema(), None),
        (Refutation, refutation_schema(), None),
    ):
        node = schema["$defs"][definition] if definition else schema
        published = set(node["properties"])
        required = {field.alias or name for name, field in model.model_fields.items()}
        assert required == published, f"{model.__name__}: {sorted(required ^ published)}"
        # Strict mode: every property is required and nothing else is accepted.
        assert set(node["required"]) == published
        assert node["additionalProperties"] is False


def test_a_property_named_like_a_schema_keyword_is_not_stripped() -> None:
    from pydantic import BaseModel, ConfigDict

    from app.agents.schemas import normalise_provider_schema

    class Awkward(BaseModel):
        model_config = ConfigDict(extra="forbid")

        title: str
        default: str

    normalised = normalise_provider_schema(Awkward.model_json_schema())
    assert isinstance(normalised, dict)
    assert set(normalised["properties"]) == {"title", "default"}
    # …while the schema's own `title` keyword is still removed from the object itself.
    assert "title" not in {key for key in normalised if key != "properties"}


def test_the_interpretation_schema_is_unchanged_by_that_fix() -> None:
    # The normaliser is shared with the settlement-intent path. Its published schema must
    # be byte-identical, because nothing there is named after a schema keyword.
    import hashlib
    import json

    from app.agents.schemas import strict_interpretation_schema

    digest = hashlib.sha256(
        json.dumps(strict_interpretation_schema(), sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert digest.startswith("6ea14edb65cc8b7d")

"""What loads, what does not, and the one invariant that guards everything else.

Only reviewed, source-controlled packs are ever loaded. The registry refuses rather than
skips when it meets an unreviewed pack, because a silent skip is exactly how that
invariant would eventually erode: a candidate file dropped in by accident would simply do
nothing, nobody would notice, and one day a change would make it do something.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.knowledge.models import RuleLayer
from app.profiles.loader import ProfileRepository
from app.rule_engine.diagnostics import RuleEngineError, RuleFindingCode
from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.extraction.review import pack_yaml
from app.rule_engine.refs import StructureIndex
from app.rule_engine.registry import RulePackRegistry, rule_pack_registry
from app.studio.models import MessageFormat
from tests.rule_engine.conftest import AMT, CMONID, MESSAGE, TXCOND, mx, pack, restriction, rule


def write(directory: Path, *packs) -> None:  # type: ignore[no-untyped-def]
    directory.mkdir(parents=True, exist_ok=True)
    for item in packs:
        (directory / item.file_name()).write_text(pack_yaml(item), encoding="utf-8")


def codes_of(error: RuleEngineError) -> set[RuleFindingCode]:
    return {finding.code for finding in error.findings}


# -- the invariant --------------------------------------------------------------------------


def test_an_unreviewed_pack_makes_the_registry_refuse_to_load(
    tmp_path: Path, index: StructureIndex
) -> None:
    candidate = pack(
        index,
        rules=(
            rule("CAND-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS), reviewed=False),
        ),
        reviewed=False,
    )
    write(tmp_path, candidate)
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(tmp_path, index=index)
    assert RuleFindingCode.RULE_REVIEW_REQUIRED in codes_of(caught.value)


def test_one_unreviewed_rule_is_enough_to_stop_a_pack(
    tmp_path: Path, index: StructureIndex
) -> None:
    mixed = pack(
        index,
        rules=(
            rule("GOOD-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),
            rule("SNEAKY", Predicate(field=mx(CMONID), operator=Operator.EXISTS), reviewed=False),
        ),
    )
    write(tmp_path, mixed)
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(tmp_path, index=index)
    assert RuleFindingCode.RULE_REVIEW_REQUIRED in codes_of(caught.value)


def test_a_reviewed_pack_loads(tmp_path: Path, index: StructureIndex) -> None:
    write(
        tmp_path,
        pack(index, rules=(rule("BASE-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)),
    )
    registry = RulePackRegistry(tmp_path, index=index)
    assert len(registry.packs()) == 1
    assert registry.layers_for(MessageFormat.MX, MESSAGE) == {RuleLayer.BASE_STANDARD}


# -- refusals and tolerances -----------------------------------------------------------------


def test_two_packs_may_not_share_an_identity(tmp_path: Path, index: StructureIndex) -> None:
    first = pack(index, rules=(rule("A-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),))
    write(tmp_path, first)
    (tmp_path / "duplicate.yaml").write_text(pack_yaml(first), encoding="utf-8")
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(tmp_path, index=index)
    assert RuleFindingCode.RULE_PACK_ID_INVALID in codes_of(caught.value)


def test_a_malformed_pack_file_is_refused_by_name(tmp_path: Path, index: StructureIndex) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.yaml").write_text("packId: nonsense\nformat: MX\n", encoding="utf-8")
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(tmp_path, index=index)
    assert RuleFindingCode.RULE_PACK_ID_INVALID in codes_of(caught.value)


def test_a_pack_for_a_message_this_deployment_lacks_is_inactive_not_fatal(
    tmp_path: Path, index: StructureIndex
) -> None:
    # Pointing the specification directory at a different drop should not stop the
    # application starting. The pack is inapplicable, which is not the same as unsafe.
    good = pack(index, rules=(rule("A-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),))
    payload = yaml.safe_load(pack_yaml(good))
    payload["messageType"] = "pacs.008"
    payload["messageVersion"] = "pacs.008.001.13"
    payload["packId"] = "MX:pacs.008.001.13:BASE_STANDARD:v1"
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "elsewhere.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    registry = RulePackRegistry(tmp_path, index=index)
    assert registry.packs() == []
    assert any(
        item.code is RuleFindingCode.RULE_MESSAGE_UNKNOWN for item in registry.warnings
    )


def test_a_pack_no_profile_selects_warns_that_it_never_runs(
    tmp_path: Path, index: StructureIndex
) -> None:
    orphan = pack(
        index,
        layer=RuleLayer.CLIENT_PROFILE,
        profile_id="NOBODY_USES_THIS",
        rules=(rule("ORPHAN", Predicate(field=mx(AMT), operator=Operator.EXISTS)),),
    )
    write(tmp_path, orphan)
    registry = RulePackRegistry(tmp_path, index=index)
    assert any(
        item.code is RuleFindingCode.RULE_PROFILE_UNKNOWN for item in registry.warnings
    )


def test_an_empty_or_absent_rules_directory_is_normal(
    tmp_path: Path, index: StructureIndex
) -> None:
    assert RulePackRegistry(tmp_path / "nothing-here", index=index).packs() == []
    (tmp_path / "empty").mkdir()
    assert RulePackRegistry(tmp_path / "empty", index=index).packs() == []


# -- selection ------------------------------------------------------------------------------


def test_a_profile_gets_the_base_layer_plus_only_the_overlays_that_name_it(
    tmp_path: Path, index: StructureIndex
) -> None:
    profiles = ProfileRepository()
    write(
        tmp_path,
        pack(index, rules=(rule("BASE-ONE", Predicate(field=mx(AMT), operator=Operator.EXISTS)),)),
        pack(
            index,
            layer=RuleLayer.MARKET_PRACTICE,
            profile_id="DEMO_MARKET_V1",
            restrictions=(restriction("MKT-COND", TXCOND, ("NOMC", "PART")),),
        ),
        pack(
            index,
            layer=RuleLayer.CLIENT_PROFILE,
            profile_id="DEMO_MARKET_CLIENT_V1",
            rules=(rule("CLI-ONE", Predicate(field=mx(CMONID), operator=Operator.EXISTS)),),
        ),
    )
    registry = RulePackRegistry(tmp_path, index=index, profiles=profiles)

    overlaid = registry.effective(MessageFormat.MX, MESSAGE, "DEMO_MARKET_CLIENT_V1")
    assert {item.rule.rule_id for item in overlaid.rules} == {"BASE-ONE", "CLI-ONE"}
    assert len(overlaid.restrictions) == 1

    plain = registry.effective(MessageFormat.MX, MESSAGE, "BASE_DEMO_V1")
    assert {item.rule.rule_id for item in plain.rules} == {"BASE-ONE"}
    assert plain.restrictions == ()


def test_an_impossible_profile_is_found_at_installation_not_at_use(
    tmp_path: Path, index: StructureIndex
) -> None:
    write(
        tmp_path,
        pack(
            index,
            layer=RuleLayer.MARKET_PRACTICE,
            profile_id="DEMO_MARKET_V1",
            rules=(rule("MKT-NEEDS", Predicate(field=mx(CMONID), operator=Operator.EXISTS)),),
        ),
        pack(
            index,
            layer=RuleLayer.CLIENT_PROFILE,
            profile_id="DEMO_MARKET_CLIENT_V1",
            rules=(rule("CLI-BANS", Predicate(field=mx(CMONID), operator=Operator.ABSENT)),),
        ),
    )
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(tmp_path, index=index, profiles=ProfileRepository())
    assert RuleFindingCode.RULE_OVERLAY_CONFLICT in codes_of(caught.value)


def test_an_unknown_message_or_profile_gets_an_empty_effective_set() -> None:
    empty = rule_pack_registry.effective(MessageFormat.MX, "sese.999", "NO_SUCH_PROFILE")
    assert empty.empty
    assert empty.layers_present() == ()


# -- what actually ships -----------------------------------------------------------------------


def test_the_installed_packs_are_reviewed_and_synthetic() -> None:
    from app.rule_engine.models import RuleReviewStatus, RuleSourceType

    packs = rule_pack_registry.packs()
    assert packs, "the demonstration overlays should be installed"
    for compiled in packs:
        assert compiled.pack.fully_reviewed()
        assert all(
            item.status is RuleReviewStatus.REVIEWED for item in compiled.pack.all_reviews()
        )
        assert not compiled.pack.authoritative_completeness_known
        for source in compiled.pack.sources:
            assert source.source_type is RuleSourceType.SYNTHETIC_FIXTURE


def test_no_base_business_pack_ships(index: StructureIndex) -> None:
    # Deriving "the base business rules of sese.023" from a synthetic document and
    # installing them would claim knowledge of the real message's rules. Only clearly
    # synthetic market and client overlays ship; the base layer is proven in tests.
    layers = {compiled.pack.layer for compiled in rule_pack_registry.packs()}
    assert RuleLayer.BASE_STANDARD not in layers
    assert layers == {RuleLayer.MARKET_PRACTICE, RuleLayer.CLIENT_PROFILE}

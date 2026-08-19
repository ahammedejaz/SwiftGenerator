"""Loading installed Rule Packs — and refusing everything that is not reviewed.

This is the single place the "no candidate ever affects normal validation" invariant is
enforced. It refuses rather than skips: a candidate file dropped into the rules directory
by accident fails the load loudly instead of quietly activating, because a silent skip is
exactly how this invariant would eventually break.

One thing *is* skipped, with a warning: a pack targeting a message this deployment has not
installed. That is not unsafe, only inapplicable — an operator pointing the specification
directory at their own drop should not be unable to start.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.config import get_settings, source_path
from app.knowledge.models import RuleLayer
from app.profiles.loader import ClientProfile, ProfileRepository
from app.profiles.loader import profiles as default_profiles
from app.rule_engine.compiler import CompiledRulePack, compile_pack
from app.rule_engine.diagnostics import (
    RuleEngineError,
    RuleFinding,
    RuleFindingCode,
    RuleFindingLog,
    RuleSeverity,
)
from app.rule_engine.layers import EffectiveRules, build_effective
from app.rule_engine.models import RulePack
from app.rule_engine.refs import StructureIndex
from app.studio.models import MessageFormat


def rule_pack_directory() -> Path:
    return source_path(get_settings().rule_pack_directory, "rules")


@dataclass(frozen=True)
class FieldRuleFact:
    """What Message Intelligence is told about a rule that names a field."""

    layer: RuleLayer
    rule_id: str
    title: str
    meaning: str
    source_reference: str


@dataclass(frozen=True)
class _Target:
    format: MessageFormat
    message_type: str
    profile_id: str


class RulePackRegistry:
    """Every installed rule pack, compiled, conflict-checked and ready to evaluate."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        index: StructureIndex | None = None,
        profiles: ProfileRepository | None = None,
    ) -> None:
        self._directory = directory or rule_pack_directory()
        self._index = index or StructureIndex()
        self._profiles = profiles or default_profiles
        self._packs: list[CompiledRulePack] = []
        self._effective: dict[_Target, EffectiveRules] = {}
        self._warnings: list[RuleFinding] = []
        self._load()

    # -- loading -----------------------------------------------------------------------

    def _read(self, path: Path, log: RuleFindingLog) -> RulePack | None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            log.error(
                RuleFindingCode.RULE_PACK_ID_INVALID,
                f"{path.name} could not be read: {error}.",
                "Correct the file, or remove it from the rules directory.",
                subject=path.name,
            )
            return None
        try:
            return RulePack.model_validate(raw)
        except ValidationError as error:
            log.error(
                RuleFindingCode.RULE_PACK_ID_INVALID,
                f"{path.name} is not a valid rule pack: "
                f"{'; '.join(item['msg'] for item in error.errors()[:4])}.",
                "Correct the pack, or keep it in the candidate directory until it is.",
                subject=path.name,
            )
            return None

    def _load(self) -> None:
        log = RuleFindingLog()
        if not self._directory.is_dir():
            return
        seen: dict[str, str] = {}
        for path in sorted(self._directory.glob("*.yaml")):
            pack = self._read(path, log)
            if pack is None:
                continue
            if pack.pack_id in seen:
                log.error(
                    RuleFindingCode.RULE_PACK_ID_INVALID,
                    f"{pack.pack_id} is declared by both {seen[pack.pack_id]} and "
                    f"{path.name}.",
                    "Two packs may never share an identity.",
                    subject=path.name,
                )
                continue
            seen[pack.pack_id] = path.name
            if path.name != pack.file_name():
                log.warning(
                    RuleFindingCode.RULE_PACK_ID_INVALID,
                    f"{path.name} declares {pack.pack_id}, whose conventional file name is "
                    f"{pack.file_name()}.",
                    "Rename the file so the directory listing reads like the identities.",
                    subject=path.name,
                )
            if not self._index.known(pack.format, pack.message_type):
                self._warnings.append(
                    RuleFinding(
                        code=RuleFindingCode.RULE_MESSAGE_UNKNOWN,
                        severity=RuleSeverity.WARNING,
                        message=(
                            f"{pack.pack_id} targets {pack.message_type}, which this "
                            "deployment has not installed; the pack is inactive."
                        ),
                        suggestion=(
                            "Install the structure pack, or remove the rule pack from this "
                            "deployment."
                        ),
                        subject=path.name,
                    )
                )
                continue
            try:
                self._packs.append(compile_pack(pack, self._index, require_reviewed=True))
            except RuleEngineError as error:
                log.findings.extend(error.findings)

        if log.blocked:
            raise RuleEngineError(log.findings)
        self._warnings.extend(log.findings)
        self._build_effective_sets()

    def _build_effective_sets(self) -> None:
        """Compose every installed combination now, so an impossible profile cannot ship.

        Conflict analysis at *installation* is the whole point: a market rule that requires
        a field the client forbids must be found here, not when a tester eventually sends a
        message that trips over it.
        """
        targets = {(pack.pack.format, pack.pack.message_type) for pack in self._packs}
        referenced_profiles: set[str] = set()
        for format_, message_type in sorted(targets, key=lambda item: (item[0], item[1])):
            for profile in self._profiles.list():
                selected = self._select(format_, message_type, profile)
                referenced_profiles.update(pack.pack.profile_id or "" for pack in selected)
                self._effective[_Target(format_, message_type, profile.profile_id)] = (
                    build_effective(
                        selected,
                        format_=format_,
                        message_type=message_type,
                        profile_id=profile.profile_id,
                    )
                )
        for pack in self._packs:
            if pack.pack.profile_id and pack.pack.profile_id not in referenced_profiles:
                self._warnings.append(
                    RuleFinding(
                        code=RuleFindingCode.RULE_PROFILE_UNKNOWN,
                        severity=RuleSeverity.WARNING,
                        message=(
                            f"{pack.pack_id} serves {pack.pack.profile_id}, which no "
                            "configured profile selects, so none of its rules ever run."
                        ),
                        suggestion=(
                            "Point a client profile at it — profileId for a client pack, "
                            "marketProfileId for a market pack."
                        ),
                        subject=pack.pack_id,
                    )
                )

    def _select(
        self, format_: MessageFormat, message_type: str, profile: ClientProfile
    ) -> list[CompiledRulePack]:
        selected: list[CompiledRulePack] = []
        for compiled in self._packs:
            pack = compiled.pack
            if pack.format is not format_ or pack.message_type != message_type:
                continue
            match pack.layer:
                case RuleLayer.BASE_STANDARD:
                    selected.append(compiled)
                case RuleLayer.MARKET_PRACTICE:
                    if pack.profile_id == profile.market_profile_id:
                        selected.append(compiled)
                case RuleLayer.CLIENT_PROFILE:
                    if pack.profile_id == profile.profile_id:
                        selected.append(compiled)
                case _:
                    pass
        return selected

    # -- reading -----------------------------------------------------------------------

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def warnings(self) -> list[RuleFinding]:
        return list(self._warnings)

    def packs(self) -> list[CompiledRulePack]:
        return list(self._packs)

    def effective(
        self, format_: MessageFormat, message_type: str, profile_id: str
    ) -> EffectiveRules:
        """The rules that apply to one message under one profile. Never raises."""
        found = self._effective.get(_Target(format_, message_type, profile_id))
        if found is not None:
            return found
        return EffectiveRules(
            format=format_, message_type=message_type, profile_id=profile_id
        )

    def layers_for(self, format_: MessageFormat, message_type: str) -> set[RuleLayer]:
        """Which authority layers have an installed pack for this message.

        Used by the capability model. It answers *what configuration exists*, exactly as
        the client-profile dimension already does — not *what applies to your request*.
        """
        return {
            pack.pack.layer
            for pack in self._packs
            if pack.pack.format is format_ and pack.pack.message_type == message_type
        }

    def rules_for_field(
        self, format_: MessageFormat, message_type: str, location: str
    ) -> list[FieldRuleFact]:
        """Every installed rule that names a field, in layer order.

        Only reviewed packs are loaded, so this can never surface a candidate — which is
        the same reason a candidate never produces a validation finding.
        """
        from app.rule_engine.evaluator import source_reference
        from app.rule_engine.layers import LAYER_ORDER

        found: list[FieldRuleFact] = []
        for pack in sorted(self._packs, key=lambda item: LAYER_ORDER.index(item.pack.layer)):
            if pack.pack.format is not format_ or pack.pack.message_type != message_type:
                continue
            for rule in pack.rules:
                if any(item.location == location for item in rule.bindings.values()):
                    found.append(
                        FieldRuleFact(
                            layer=pack.pack.layer,
                            rule_id=rule.rule.rule_id,
                            title=rule.rule.title,
                            meaning=rule.rule.finding.message,
                            source_reference=source_reference(rule.rule.evidence) or "",
                        )
                    )
            for restriction in pack.restrictions:
                if restriction.field.location == location:
                    item = restriction.restriction
                    found.append(
                        FieldRuleFact(
                            layer=pack.pack.layer,
                            rule_id=item.restriction_id,
                            title=f"{restriction.field.display_name} is restricted",
                            meaning=item.finding.message,
                            source_reference=source_reference(item.evidence) or "",
                        )
                    )
        return found


rule_pack_registry = RulePackRegistry()

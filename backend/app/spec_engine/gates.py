"""The pack gates: what must be true before a compiled pack may be called compiled.

These run against a *private* registry built from the pack file — never against the
application's installed configuration — so validating a candidate cannot disturb the
running platform, and a pack is proven through exactly the code paths the platform uses:
the ordinary registry loads it, the ordinary generator composes it, the ordinary parser
reads it back, and lxml validates the result against the **source** schema. Passing the
derived schema alone would only prove the compiler agrees with itself.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from app.spec_engine.diagnostics import (
    CompilerFinding,
    FindingCode,
    FindingLog,
)
from app.studio.models import ElementInput, Presence
from app.studio.mx.generator import MxGenerator
from app.studio.mx.parser import parse_message
from app.studio.mx.registry import MxRegistry


@dataclass
class GateResult:
    passed: bool
    detail: str


@dataclass
class PackValidation:
    registry_load: GateResult
    sample: GateResult
    compose: GateResult
    source_xsd: GateResult
    invalid_variants: GateResult
    round_trip: GateResult
    findings: list[CompilerFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            item.passed
            for item in (
                self.registry_load,
                self.sample,
                self.compose,
                self.source_xsd,
                self.invalid_variants,
                self.round_trip,
            )
        )

    def render(self) -> str:
        rows = [
            ("registry load", self.registry_load),
            ("sample derivation", self.sample),
            ("compose", self.compose),
            ("source-XSD validation", self.source_xsd),
            ("invalid variants rejected", self.invalid_variants),
            ("round trip", self.round_trip),
        ]
        lines = [
            f"  {'PASS' if item.passed else 'FAIL'}  {name}: {item.detail}"
            for name, item in rows
        ]
        return "\n".join(lines)


def _skip(reason: str) -> GateResult:
    return GateResult(passed=False, detail=reason)


def _sample_inputs(registry: MxRegistry, message_type: str) -> list[ElementInput]:
    """A minimal valid instance: every mandatory-chain leaf, first branch per choice.

    Values come from the pack's own examples, which the compiler derived from the schema
    facets. A leaf without an example simply is not filled — and the compose or source
    gate then fails visibly, which is the honest outcome for an underivable value.
    """
    by_path = registry.by_path(message_type)
    chosen_branch: dict[str, str] = {}
    inputs: list[ElementInput] = []
    for flat in registry.flat(message_type):
        element = flat.element
        if not element.is_leaf:
            continue
        required = element.presence is Presence.MANDATORY and flat.mandatory_chain
        in_choice = flat.choice_group is not None
        if in_choice:
            group = flat.choice_group or ""
            branch = flat.choice_branch or flat.path
            first_branch = chosen_branch.setdefault(group, branch)
            if branch != first_branch:
                continue
            # Inside the chosen branch, fill every leaf that is mandatory within it, or
            # the branch's own leaf when the branch is itself the leaf.
            choice_parent = by_path.get(group)
            required = element.presence is Presence.MANDATORY or (
                flat.path == branch and element.is_leaf
            )
            if choice_parent is not None and not (
                choice_parent.element.presence is Presence.MANDATORY
                and choice_parent.mandatory_chain
            ):
                required = False
        if not required:
            continue
        if not element.examples:
            continue
        inputs.append(ElementInput(path=flat.path, value=element.examples[0].value))
    return inputs


def _mutations(document: str, spec, registry: MxRegistry):  # type: ignore[no-untyped-def]
    """Deliberately broken variants the source schema must reject."""
    import re

    variants: dict[str, str | None] = {
        "missing mandatory element": None,
        "invalid enumeration": None,
        "invalid datatype": None,
        "wrong element order": None,
    }
    leaves = [item for item in registry.flat(spec.message_type) if item.element.is_leaf]

    mandatory = next(
        (item for item in leaves if item.element.presence is Presence.MANDATORY), None
    )
    if mandatory is not None:
        pattern = f"<{mandatory.element.name}[^>]*>.*?</{mandatory.element.name}>"
        broken = re.sub(pattern, "", document, count=1, flags=re.DOTALL)
        if broken != document:
            variants["missing mandatory element"] = broken

    coded = next((item for item in leaves if item.element.codes), None)
    if coded is not None and coded.element.codes:
        good = coded.element.codes[0]
        broken = document.replace(f">{good}<", ">ZZZZINVALID<", 1)
        if broken != document:
            variants["invalid enumeration"] = broken

    dated = next(
        (
            item
            for item in leaves
            if (item.element.data_type and "Date" in item.element.data_type.value)
            or (item.element.restriction and item.element.restriction.base.value == "DATE")
        ),
        None,
    )
    if dated is not None:
        broken = re.sub(
            f"(<{dated.element.name}>)[^<]+(</{dated.element.name}>)",
            r"\g<1>NOT-A-DATE\g<2>",
            document,
            count=1,
        )
        if broken != document:
            variants["invalid datatype"] = broken

    # Swap the first two sibling leaves under the root to break sequence order.
    match = re.search(r"(<(\w+)>[^<]*</\2>)\s*(<(\w+)>[^<]*</\4>)", document)
    if match and match.group(2) != match.group(4):
        broken = (
            document[: match.start()]
            + match.group(3)
            + match.group(1)
            + document[match.end() :]
        )
        variants["wrong element order"] = broken

    return variants


def validate_pack(
    pack_yaml: str, version: str, source_xsd: Path
) -> PackValidation:
    """Run every gate over a pack candidate. Never touches installed configuration."""
    from lxml import etree

    log = FindingLog()
    schema = etree.XMLSchema(etree.parse(str(source_xsd)))

    with tempfile.TemporaryDirectory() as tmp:
        pack_path = Path(tmp) / f"{version}.yaml"
        pack_path.write_text(pack_yaml, encoding="utf-8")

        # Gate 1 — the ordinary registry loads it.
        try:
            registry = MxRegistry(Path(tmp))
        except Exception as error:  # noqa: BLE001 - reported, not raised
            log.error(
                FindingCode.PACK_VALIDATION_FAILED,
                f"The MX registry refused the pack: {error}",
                "Fix the pack; the registry's message names the field.",
            )
            failed = _skip("registry refused the pack")
            return PackValidation(
                registry_load=GateResult(False, str(error)),
                sample=failed,
                compose=failed,
                source_xsd=failed,
                invalid_variants=failed,
                round_trip=failed,
                findings=log.findings,
            )
        spec = registry.all_specs()[0]
        registry_gate = GateResult(True, f"{spec.message_type} ({spec.version})")

        # Gate 2 — a sample derives from the pack's own examples.
        inputs = _sample_inputs(registry, spec.message_type)
        mandatory_leaves = [
            item
            for item in registry.flat(spec.message_type)
            if item.element.is_leaf
            and item.element.presence is Presence.MANDATORY
            and item.mandatory_chain
        ]
        missing = {item.path for item in mandatory_leaves} - {item.path for item in inputs}
        sample_gate = (
            GateResult(True, f"{len(inputs)} element(s), all mandatory paths covered")
            if not missing
            else GateResult(False, "no example value for: " + ", ".join(sorted(missing)))
        )

        # Gate 3 — the ordinary generator composes and its own validation passes.
        generator = MxGenerator(registry)
        resolved, issues = generator.resolve(spec, inputs)
        structural = generator.validate_structure(spec, resolved)
        blocking = [item for item in (*issues, *structural) if item.severity.value == "ERROR"]
        if blocking:
            compose_gate = GateResult(
                False,
                "; ".join(f"{item.rule_id}: {item.message}" for item in blocking[:5]),
            )
            document = None
        else:
            document = generator.compose_document(spec, resolved)
            compose_gate = GateResult(True, f"{len(document)} bytes of XML")

        # Gate 4 — the source schema accepts the composed document.
        if document is None:
            source_gate = _skip("not composed")
            variants_gate = _skip("not composed")
            round_trip_gate = _skip("not composed")
        else:
            tree = etree.fromstring(document.encode())
            if schema.validate(tree):
                source_gate = GateResult(True, f"valid against {source_xsd.name}")
            else:
                error_log = cast("Any", schema.error_log)
                messages = [str(entry) for entry in error_log]
                source_gate = GateResult(False, "; ".join(messages[:5]))

            # Gate 5 — broken variants must be *rejected* by the source schema.
            rejected, accepted = [], []
            for label, variant in _mutations(document, spec, registry).items():
                if variant is None:
                    continue
                try:
                    variant_tree = etree.fromstring(variant.encode())
                except etree.XMLSyntaxError:
                    rejected.append(label)
                    continue
                if schema.validate(variant_tree):
                    accepted.append(label)
                else:
                    rejected.append(label)
            variants_gate = (
                GateResult(True, f"rejected: {', '.join(rejected)}")
                if rejected and not accepted
                else GateResult(
                    False,
                    "source schema accepted broken variant(s): " + ", ".join(accepted)
                    if accepted
                    else "no mutation could be derived",
                )
            )

            # Gate 6 — parse back through the ordinary parser and recompose identically.
            try:
                parsed = parse_message(document, registry)
            except Exception as error:  # noqa: BLE001
                round_trip_gate = GateResult(False, f"parser refused its own output: {error}")
            else:
                if parsed.errors:
                    round_trip_gate = GateResult(
                        False,
                        "; ".join(item.message for item in parsed.errors[:3]),
                    )
                else:
                    again_resolved, again_issues = generator.resolve(spec, parsed.elements)
                    recomposed = generator.compose_document(spec, again_resolved)
                    same = etree.tostring(
                        etree.fromstring(document.encode()), method="c14n2"
                    ) == etree.tostring(etree.fromstring(recomposed.encode()), method="c14n2")
                    round_trip_gate = (
                        GateResult(True, "canonically identical")
                        if same
                        else GateResult(False, "recomposed document differs canonically")
                    )

        return PackValidation(
            registry_load=registry_gate,
            sample=sample_gate,
            compose=compose_gate,
            source_xsd=source_gate,
            invalid_variants=variants_gate,
            round_trip=round_trip_gate,
            findings=log.findings,
        )

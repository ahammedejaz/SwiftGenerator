"""Deterministic Rule Pack compilation: everything checkable, checked before review.

A candidate that fails here never reaches a reviewer looking like a valid rule — it
reaches them as a rejected candidate with the reason attached. The same checks run again
when a reviewed pack is loaded, so a pack edited by hand after review cannot slip through.

Compilation only ever *reads* structure. There is no writer anywhere in this package, which
is what makes "a Rule Pack cannot mutate a Structure Pack" architectural rather than
aspirational.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal, InvalidOperation

from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
from app.rule_engine.diagnostics import (
    RuleEngineError,
    RuleFinding,
    RuleFindingCode,
    RuleFindingLog,
)
from app.rule_engine.dsl import (
    DATE_OPERATORS,
    MAX_EXPRESSION_DEPTH,
    MEMBERSHIP_OPERATORS,
    NUMERIC_OPERATORS,
    AtLeastOne,
    AtMostOne,
    ExactlyOne,
    Expression,
    Operator,
    Predicate,
    Subject,
    depth,
    walk,
)
from app.rule_engine.models import (
    CodeRestriction,
    Rule,
    RulePack,
    RuleReviewStatus,
)
from app.rule_engine.refs import (
    DATE_KINDS,
    NUMERIC_KINDS,
    FieldKind,
    FieldRef,
    ResolvedFieldRef,
    StructureIndex,
)
from app.studio.models import MessageFormat

#: Substrings that have no business in declarative configuration. The pack model already
#: makes executable content unrepresentable; this is the second, cheap line of defence
#: against a model or an author smuggling something into a free-text field.
EXECUTABLE_MARKERS: tuple[str, ...] = (
    "eval(",
    "exec(",
    "__import__",
    "subprocess",
    "os.system",
    "os.popen",
    "importlib",
    "{{",
    "}}",
    "{%",
    "%}",
    "<script",
    "javascript:",
    "data:text/html",
    "$(",
    "${",
    "<%",
    "%>",
    "://",
    "drop table",
    "union select",
    "--;",
)

#: A group containing an unbounded quantifier that is itself quantified — the classic
#: catastrophic-backtracking shape. A screen, not a proof; the length cap does the rest.
NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*]|\([^)]*[+*][^)]*\)\{")
BACKREFERENCE = re.compile(r"\\[1-9]")


@dataclass(frozen=True)
class CompiledRule:
    rule: Rule
    pack_id: str
    #: Canonical field reference -> what the structure says. The evaluator's lookup table.
    bindings: dict[str, ResolvedFieldRef]
    #: The field a finding points at, so "go to this field" keeps working.
    primary: ResolvedFieldRef


@dataclass(frozen=True)
class CompiledRestriction:
    restriction: CodeRestriction
    pack_id: str
    field: ResolvedFieldRef


@dataclass(frozen=True)
class CompiledRulePack:
    pack: RulePack
    rules: tuple[CompiledRule, ...] = ()
    restrictions: tuple[CompiledRestriction, ...] = ()
    warnings: tuple[RuleFinding, ...] = dataclass_field(default=())

    @property
    def pack_id(self) -> str:
        return self.pack.pack_id


def screen_for_executable_content(payload: object, log: RuleFindingLog, subject: str) -> None:
    """Refuse anything that looks like it wants to be executed, anywhere in the pack."""

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                visit(value, f"{path}.{key}")
            return
        if isinstance(node, list | tuple):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")
            return
        if not isinstance(node, str):
            return
        lowered = node.casefold()
        for marker in EXECUTABLE_MARKERS:
            if marker in lowered:
                log.error(
                    RuleFindingCode.RULE_EXECUTABLE_CONTENT_REJECTED,
                    f"{path} contains {marker!r}, which declarative configuration never needs.",
                    "Remove it. Rules are data; nothing here is ever interpreted as code.",
                    subject=subject,
                    location=path,
                )

    visit(payload, "$")


def _screen_pattern(pattern: str, log: RuleFindingLog, subject: str, location: str) -> None:
    if BACKREFERENCE.search(pattern):
        log.error(
            RuleFindingCode.RULE_REGEX_REJECTED,
            f"The pattern {pattern!r} uses a backreference.",
            "Write a pattern the source states literally, without backreferences.",
            subject=subject,
            location=location,
        )
        return
    if NESTED_QUANTIFIER.search(pattern):
        log.error(
            RuleFindingCode.RULE_REGEX_REJECTED,
            f"The pattern {pattern!r} nests unbounded quantifiers.",
            "Rewrite it without a quantified group that itself repeats.",
            subject=subject,
            location=location,
        )
        return
    try:
        re.compile(pattern)
    except re.error as error:
        log.error(
            RuleFindingCode.RULE_REGEX_REJECTED,
            f"The pattern {pattern!r} does not compile: {error}.",
            "Correct the pattern.",
            subject=subject,
            location=location,
        )


def _required_occurrences(predicate: Predicate) -> int | None:
    """How many occurrences a COUNT comparison demands, when it demands a minimum."""
    if predicate.value is None:
        return None
    threshold = int(predicate.value)
    match predicate.operator:
        case Operator.EQUALS:
            return threshold
        case Operator.GREATER_OR_EQUAL:
            return threshold
        case Operator.GREATER_THAN:
            return threshold + 1
        case _:
            return None


def _check_predicate(
    predicate: Predicate,
    bindings: dict[str, ResolvedFieldRef],
    log: RuleFindingLog,
    subject: str,
    location: str,
) -> None:
    binding = bindings.get(predicate.field.canonical())
    if binding is None:
        return
    where = f"{location}:{predicate.field.describe()}"

    if predicate.subject is Subject.COUNT:
        needed = _required_occurrences(predicate)
        if needed is not None and needed > binding.max_occurs:
            log.error(
                RuleFindingCode.RULE_COUNT_NOT_REPEATABLE,
                f"{binding.display_name} can occur at most {binding.max_occurs} time(s), "
                f"so a rule demanding {needed} can never be satisfied.",
                "Target repeatable content, or lower the count.",
                subject=subject,
                location=where,
            )
        return

    other = (
        bindings.get(predicate.other_field.canonical())
        if predicate.other_field is not None
        else None
    )

    if predicate.operator is Operator.MATCHES:
        if binding.kind not in {FieldKind.TEXT, FieldKind.IDENTIFIER}:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"MATCHES needs a text field; {binding.display_name} holds "
                f"{binding.kind.value.lower()} content.",
                "Compare a code with IN, a number with a numeric operator, a date with a "
                "date operator.",
                subject=subject,
                location=where,
            )
        elif predicate.value is not None:
            _screen_pattern(predicate.value, log, subject, where)
        return

    if predicate.operator in NUMERIC_OPERATORS:
        if binding.kind not in NUMERIC_KINDS:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"{predicate.operator} needs a numeric field; {binding.display_name} holds "
                f"{binding.kind.value.lower()} content.",
                "Use a numeric element, or compare with a different operator.",
                subject=subject,
                location=where,
            )
        if predicate.value is not None:
            try:
                Decimal(predicate.value)
            except (InvalidOperation, ValueError):
                log.error(
                    RuleFindingCode.RULE_TYPE_MISMATCH,
                    f"{predicate.value!r} is not a number.",
                    "Supply a decimal value.",
                    subject=subject,
                    location=where,
                )
        if other is not None and other.kind not in NUMERIC_KINDS:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"{other.display_name} is not numeric, so it cannot be compared with "
                f"{binding.display_name}.",
                "Compare two numeric fields.",
                subject=subject,
                location=where,
            )
        return

    if predicate.operator in DATE_OPERATORS:
        if binding.kind not in DATE_KINDS:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"{predicate.operator} needs a date field; {binding.display_name} holds "
                f"{binding.kind.value.lower()} content.",
                "Use a date element, or compare with a different operator.",
                subject=subject,
                location=where,
            )
        if other is not None and other.kind is not binding.kind:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"{binding.display_name} and {other.display_name} are not the same kind of "
                "date, so comparing them is not meaningful.",
                "Compare a date with a date and a date-time with a date-time.",
                subject=subject,
                location=where,
            )
        return

    # Equality and membership. The only structural check that applies is the code set.
    if other is not None and other.kind is not binding.kind:
        log.error(
            RuleFindingCode.RULE_TYPE_MISMATCH,
            f"{binding.display_name} holds {binding.kind.value.lower()} content and "
            f"{other.display_name} holds {other.kind.value.lower()}; comparing them is not "
            "meaningful.",
            "Compare fields of the same kind.",
            subject=subject,
            location=where,
        )
        return
    if binding.kind is not FieldKind.CODE or not binding.codes:
        return
    literals = list(predicate.values) if predicate.operator in MEMBERSHIP_OPERATORS else (
        [predicate.value] if predicate.value is not None else []
    )
    unknown = [item for item in literals if item not in binding.codes]
    if unknown:
        log.error(
            RuleFindingCode.RULE_CODE_UNKNOWN,
            f"{binding.display_name} does not allow {', '.join(unknown)}; the structure "
            f"declares {', '.join(binding.codes)}.",
            "A rule may restrict the codes a structure allows, never invent one.",
            subject=subject,
            location=where,
        )


def _bind(
    references: list[FieldRef],
    index: StructureIndex,
    pack: RulePack,
    log: RuleFindingLog,
    location: str,
) -> dict[str, ResolvedFieldRef]:
    bindings: dict[str, ResolvedFieldRef] = {}
    for ref in references:
        if ref.format is not pack.format:
            log.error(
                RuleFindingCode.RULE_REFERENCE_INVALID,
                f"{location} references a {ref.format} field in an {pack.format} pack.",
                "A pack targets one message in one format.",
                subject=pack.pack_id,
                location=location,
            )
            continue
        if ref.canonical() in bindings:
            continue
        resolved = index.resolve(ref, pack.message_type)
        if resolved is None:
            log.error(
                RuleFindingCode.RULE_REFERENCE_INVALID,
                f"{pack.message_type} has no field {ref.describe()}, or the reference "
                "matches more than one.",
                "Name a field the installed structure declares, precisely enough to be "
                "unambiguous.",
                subject=pack.pack_id,
                location=location,
            )
            continue
        bindings[ref.canonical()] = resolved
    return bindings


def _check_expression(
    expression: Expression,
    bindings: dict[str, ResolvedFieldRef],
    log: RuleFindingLog,
    subject: str,
    location: str,
) -> None:
    if depth(expression) > MAX_EXPRESSION_DEPTH:
        log.error(
            RuleFindingCode.RULE_OPERATOR_INVALID,
            f"{location} nests expressions {depth(expression)} deep; the limit is "
            f"{MAX_EXPRESSION_DEPTH}.",
            "Split the rule in two.",
            subject=subject,
            location=location,
        )
        return
    for node in walk(expression):
        match node:
            case Predicate():
                _check_predicate(node, bindings, log, subject, location)
            case ExactlyOne() | AtLeastOne() | AtMostOne():
                fields = (
                    node.exactly_one
                    if isinstance(node, ExactlyOne)
                    else node.at_least_one
                    if isinstance(node, AtLeastOne)
                    else node.at_most_one
                )
                seen = {ref.canonical() for ref in fields}
                if len(seen) != len(fields):
                    log.error(
                        RuleFindingCode.RULE_OPERATOR_INVALID,
                        f"{location} names the same field twice in a group operator.",
                        "List each field once.",
                        subject=subject,
                        location=location,
                    )
            case _:
                pass


def compile_pack(
    pack: RulePack,
    index: StructureIndex,
    *,
    require_reviewed: bool = False,
) -> CompiledRulePack:
    """Compile one pack against installed structure. Raises on any error finding."""
    log = RuleFindingLog()
    subject = pack.pack_id

    if pack.engine_version != RULE_ENGINE_VERSION or pack.dsl_version != DSL_VERSION:
        log.error(
            RuleFindingCode.RULE_PACK_ID_INVALID,
            f"{subject} was written for {pack.engine_version}/{pack.dsl_version}; this "
            f"engine is {RULE_ENGINE_VERSION}/{DSL_VERSION}.",
            "Recompile or re-review the pack against this engine.",
            subject=subject,
        )

    screen_for_executable_content(
        json.loads(pack.model_dump_json(by_alias=True, exclude_none=True)), log, subject
    )

    if not index.known(pack.format, pack.message_type):
        log.error(
            RuleFindingCode.RULE_MESSAGE_UNKNOWN,
            f"No {pack.format} message {pack.message_type} is installed.",
            "Install the structure pack first, or correct the messageType.",
            subject=subject,
        )
        raise RuleEngineError(log.findings)

    installed_version = index.version(pack.format, pack.message_type)
    if pack.message_version and installed_version != pack.message_version:
        log.error(
            RuleFindingCode.RULE_STRUCTURE_VERSION_MISMATCH,
            f"{subject} targets {pack.message_version}; {installed_version} is installed.",
            "Re-review the pack against the installed version.",
            subject=subject,
        )

    checksum = index.structure_checksum(pack.format, pack.message_type)
    if pack.structure_compatibility.structure_checksum != checksum:
        log.error(
            RuleFindingCode.RULE_STRUCTURE_VERSION_MISMATCH,
            f"{subject} was written against a different structure "
            f"({pack.structure_compatibility.structure_checksum[:19]}…); the installed "
            f"structure digests to {checksum[:19]}….",
            "Re-check the rules against the current structure and update "
            "structureCompatibility.",
            subject=subject,
        )

    identifiers = [item.rule_id for item in pack.rules] + [
        item.restriction_id for item in pack.code_restrictions
    ]
    for identifier in sorted({item for item in identifiers if identifiers.count(item) > 1}):
        log.error(
            RuleFindingCode.RULE_ID_DUPLICATE,
            f"{subject} declares {identifier} more than once.",
            "Rule and restriction identifiers share one namespace; make each unique.",
            subject=subject,
            location=identifier,
        )

    if require_reviewed and not pack.fully_reviewed():
        unreviewed = [
            item.rule_id
            for item in pack.rules
            if item.review.status is not RuleReviewStatus.REVIEWED
        ] + [
            item.restriction_id
            for item in pack.code_restrictions
            if item.review.status is not RuleReviewStatus.REVIEWED
        ]
        log.error(
            RuleFindingCode.RULE_REVIEW_REQUIRED,
            f"{subject} is not fully reviewed"
            + (f" ({', '.join(unreviewed)})" if unreviewed else "")
            + ".",
            "Only reviewed, source-controlled packs are ever loaded. Review it, or keep it "
            "in the candidate directory.",
            subject=subject,
        )

    compiled_rules: list[CompiledRule] = []
    for rule in pack.rules:
        from app.rule_engine.dsl import references as expression_references

        refs = list(expression_references(rule.assert_))
        if rule.when is not None:
            refs = list(expression_references(rule.when)) + refs
        bindings = _bind(refs, index, pack, log, rule.rule_id)
        if rule.when is not None:
            _check_expression(rule.when, bindings, log, subject, rule.rule_id)
        _check_expression(rule.assert_, bindings, log, subject, rule.rule_id)
        primary = next(
            (bindings[ref.canonical()] for ref in refs if ref.canonical() in bindings),
            None,
        )
        if primary is not None:
            compiled_rules.append(
                CompiledRule(
                    rule=rule, pack_id=pack.pack_id, bindings=bindings, primary=primary
                )
            )

    compiled_restrictions: list[CompiledRestriction] = []
    for restriction in pack.code_restrictions:
        bindings = _bind([restriction.field], index, pack, log, restriction.restriction_id)
        resolved = bindings.get(restriction.field.canonical())
        if resolved is None:
            continue
        if resolved.kind is not FieldKind.CODE or not resolved.codes:
            log.error(
                RuleFindingCode.RULE_TYPE_MISMATCH,
                f"{resolved.display_name} is not a code element, so its values cannot be "
                "narrowed to a code list.",
                "Restrict a code element, or express the rule with a pattern or a "
                "comparison.",
                subject=subject,
                location=restriction.restriction_id,
            )
            continue
        unknown = [code for code in restriction.codes if code not in resolved.codes]
        if unknown:
            log.error(
                RuleFindingCode.RULE_CODE_UNKNOWN,
                f"{resolved.display_name} does not allow {', '.join(unknown)}; the "
                f"structure declares {', '.join(resolved.codes)}.",
                "An overlay narrows the codes a structure allows; it never invents one.",
                subject=subject,
                location=restriction.restriction_id,
            )
            continue
        if set(restriction.codes) == set(resolved.codes):
            log.warning(
                RuleFindingCode.RULE_OVERLAY_WIDENING,
                f"{restriction.restriction_id} allows every code the structure already "
                "allows, so it restricts nothing.",
                "Remove it, or narrow the list.",
                subject=subject,
                location=restriction.restriction_id,
            )
        compiled_restrictions.append(
            CompiledRestriction(
                restriction=restriction, pack_id=pack.pack_id, field=resolved
            )
        )

    if log.blocked:
        raise RuleEngineError(log.findings)
    return CompiledRulePack(
        pack=pack,
        rules=tuple(compiled_rules),
        restrictions=tuple(compiled_restrictions),
        warnings=tuple(log.findings),
    )


def structure_compatibility_for(
    index: StructureIndex, format_: MessageFormat, message_type: str
) -> dict[str, str]:
    """The compatibility block a new pack should record. Used by the CLI and the tests."""
    return {
        "structureVersion": index.version(format_, message_type) or message_type,
        "structureChecksum": index.structure_checksum(format_, message_type),
    }

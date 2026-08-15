from __future__ import annotations

import argparse
from pathlib import Path

from app.samples.service import sample_service
from app.specifications.registry import specification_registry


def render_coverage_markdown() -> str:
    sample_rows = sample_service.coverage()
    report = specification_registry.report(
        sample_coverage=sample_rows,
        golden_coverage=sample_rows,
    )
    lines = [
        "# Message Coverage Report",
        "",
        "Generated from the source-bounded specification registry and production-composer "
        "sample annotations. This is configured-subset coverage, not a claim of complete "
        "ISO 15022 or SWIFT Standards coverage.",
        "",
        f"- Registry version: `{report.registry_version}`",
        f"- Configured rows: **{report.total_configured_rows}**",
        "- Authoritative completeness denominator available: **No**",
        "- Production-capable messages: **0**",
        "",
        "| Message | Capability | Configured rows | Knowledge | Form | Composer | Parser | "
        "Validator | Sample | Golden |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.messages:
        metrics = (
            item.knowledge_records,
            item.form_supported_fields,
            item.composer_supported_fields,
            item.parser_supported_fields,
            item.validator_supported_fields,
            item.sample_covered_fields,
            item.golden_tested_fields,
        )
        rendered_metrics = [
            f"{metric.covered}/{metric.configured} ({metric.percentage:.2f}%)" for metric in metrics
        ]
        lines.append(
            "| "
            + " | ".join(
                [
                    item.message_type.value,
                    item.capability.value,
                    str(item.configured_format_rows),
                    *rendered_metrics,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Coverage-gate interpretation",
            "",
            "Knowledge, form, composer, parser, and validator percentages measure only the "
            "200 rows configured in this repository. Sample and golden percentages measure "
            "which configured rows occur in the generated golden-path sample; optional rows "
            "not used by that scenario reduce those values.",
            "",
            "Every target message remains `PARTIAL` because the repository does not contain a "
            "current authorised full format-row denominator, complete network/usage validation "
            "rules, approved market practice, or institution client rule pack. The production "
            "gate therefore fails closed regardless of configured-subset percentages.",
            "",
            "## Required evidence before promotion",
            "",
            "1. Import a licensed, approved release-specific specification and preserve its "
            "provenance.",
            "2. Reconcile every official format row, sequence, option, qualifier, code list, "
            "usage rule, and network rule.",
            "3. Obtain institution and market-profile review and external validation evidence.",
            "4. Expand samples and golden tests to cover every supported conditional and "
            "repeatable path.",
            "5. Re-run the coverage compiler; only a passing evidence-backed gate may change "
            "capability state.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or verify the message coverage report")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[3] / "MESSAGE_COVERAGE_REPORT.md"
    expected = render_coverage_markdown()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            print("MESSAGE_COVERAGE_REPORT.md is stale")
            return 1
        print("MESSAGE_COVERAGE_REPORT.md is current")
        return 0
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Message Coverage Report

Generated from the source-bounded specification registry and production-composer sample annotations. This is configured-subset coverage, not a claim of complete ISO 15022 or SWIFT Standards coverage.

- Registry version: `ISO15022_CONFIGURED_SUBSET_V1`
- Configured rows: **200**
- Authoritative completeness denominator available: **No**
- Production-capable messages: **0**

| Message | Capability | Configured rows | Knowledge | Form | Composer | Parser | Validator | Sample | Golden |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MT530 | PARTIAL | 5 | 5/5 (100.00%) | 5/5 (100.00%) | 5/5 (100.00%) | 5/5 (100.00%) | 5/5 (100.00%) | 5/5 (100.00%) | 5/5 (100.00%) |
| MT537 | PARTIAL | 23 | 23/23 (100.00%) | 23/23 (100.00%) | 23/23 (100.00%) | 23/23 (100.00%) | 23/23 (100.00%) | 22/23 (95.65%) | 22/23 (95.65%) |
| MT540 | PARTIAL | 14 | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 12/14 (85.71%) | 12/14 (85.71%) |
| MT541 | PARTIAL | 15 | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 13/15 (86.67%) | 13/15 (86.67%) |
| MT542 | PARTIAL | 14 | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 12/14 (85.71%) | 12/14 (85.71%) |
| MT543 | PARTIAL | 15 | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 15/15 (100.00%) | 13/15 (86.67%) | 13/15 (86.67%) |
| MT544 | PARTIAL | 12 | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 11/12 (91.67%) | 11/12 (91.67%) |
| MT545 | PARTIAL | 13 | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 12/13 (92.31%) | 12/13 (92.31%) |
| MT546 | PARTIAL | 12 | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 11/12 (91.67%) | 11/12 (91.67%) |
| MT547 | PARTIAL | 13 | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 12/13 (92.31%) | 12/13 (92.31%) |
| MT548 | PARTIAL | 12 | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 12/12 (100.00%) | 7/12 (58.33%) | 7/12 (58.33%) |
| MT564 | PARTIAL | 14 | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) |
| MT565 | PARTIAL | 10 | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) | 10/10 (100.00%) |
| MT566 | PARTIAL | 13 | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) | 13/13 (100.00%) |
| MT567 | PARTIAL | 9 | 9/9 (100.00%) | 9/9 (100.00%) | 9/9 (100.00%) | 9/9 (100.00%) | 9/9 (100.00%) | 6/9 (66.67%) | 6/9 (66.67%) |
| MT568 | PARTIAL | 6 | 6/6 (100.00%) | 6/6 (100.00%) | 6/6 (100.00%) | 6/6 (100.00%) | 6/6 (100.00%) | 6/6 (100.00%) | 6/6 (100.00%) |

## Coverage-gate interpretation

Knowledge, form, composer, parser, and validator percentages measure only the 200 rows configured in this repository. Sample and golden percentages measure which configured rows occur in the generated golden-path sample; optional rows not used by that scenario reduce those values.

Every target message remains `PARTIAL` because the repository does not contain a current authorised full format-row denominator, complete network/usage validation rules, approved market practice, or institution client rule pack. The production gate therefore fails closed regardless of configured-subset percentages.

## Required evidence before promotion

1. Import a licensed, approved release-specific specification and preserve its provenance.
2. Reconcile every official format row, sequence, option, qualifier, code list, usage rule, and network rule.
3. Obtain institution and market-profile review and external validation evidence.
4. Expand samples and golden tests to cover every supported conditional and repeatable path.
5. Re-run the coverage compiler; only a passing evidence-backed gate may change capability state.

# Excel bulk guide

## Client-usable authoring boundary

The current Excel endpoints remain bounded configured-subset generation/test utilities. They retain
row-level validation, formula-injection protection, safe filenames, row continuation, ZIP reports,
and workflow type metadata. They do **not** yet provide the required multi-sheet encrypted real-data
draft import for nested MT537 and MT564–MT568 structures, nor do they submit messages automatically.

Until the secure parent/child workbook importer is implemented and externally validated, use the
authenticated Message Builder for actual values. Existing templates and all shipped workbook data
are synthetic. This limitation is intentional and recorded in the final report.

## Download the template

Use the Bulk Generator screen or:

```bash
curl -fS http://localhost:8000/api/bulk/template -o securities-message-studio-template.xlsx
```

The workbook contains synthetic examples only.

## Columns

Required headers are Scenario ID, Profile ID, Lifecycle, Direction, Payment Type, Function, Sender Reference, Related Reference, Transaction Type, ISIN, Quantity, Trade Date, Settlement Date, Safekeeping Account, Place of Settlement, Delivering Agent, Receiving Agent, Currency, Amount, Status Category, Status Code, Reason Code, Reason Narrative, Generation Mode, and Negative Mutation.

Optional headers are Client Reference, Settlement Result, and Actual Settlement Date. “Required header” means the column must exist; whether a row value is required is calculated by message type and profile.

## Row behavior

- Instructions resolve from Direction and Payment Type.
- Status/confirmation rows must occur after and reference an earlier instruction row by Sender Reference.
- FOP rows should leave Currency and Amount blank.
- DVP rows require Currency and Amount unless the row explicitly selects the matching negative mutation.
- Dates use `YYYY-MM-DD` or native Excel dates.
- Enum text is case-normalized with spaces converted to underscores.
- Blank rows are ignored.
- An invalid row is recorded as failed while later valid rows continue.

Limits default to 5 MiB and 1,000 data rows. Only a valid `.xlsx` OOXML ZIP is accepted. Filenames containing path components, other extensions, executables, and malformed archives are rejected.

## Upload

```bash
curl -fS http://localhost:8000/api/bulk/generate \
  -F 'file=@securities-message-studio-template.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
```

The result gives row status, message type, filename, profile/version, validation outcome, counts, and report ID.

## ZIP contents

- One `.txt` raw demonstration message per generated row.
- One `.validation.json` report per message.
- `summary.xlsx` with resolved type, filename, profile/version, expected negative status, counts, and actual outcome.
- `execution-report.json` with overall and row-level results.

Downloads are resolved by server-held report IDs; client filenames cannot select server paths. Formula-like output cells beginning with `=`, `+`, `-`, or `@` are escaped to reduce spreadsheet formula injection risk.

## Workflow workbook

The original settlement workbook remains compatible. `/api/bulk/workflow-template` supports `SETTLEMENT_COMMAND`, `PENALTY`, and `CORPORATE_*` rows. Corporate rows link to earlier valid rows by **Related Message Reference**. Invalid rows are reported while independent valid rows continue. The ZIP contains text messages, JSON validation files, `summary.xlsx`, and `execution-report.json`.

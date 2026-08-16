# curl examples

Every request below is a file in [`requests/`](requests), so the examples and the pack cannot
drift apart. The API is open when `APP_ENV` is `development`; elsewhere add
`-H "X-API-Key: <your service key>"`.

```bash
API=http://127.0.0.1:8000
```

## Generate

```bash
# MT541 — receive against payment, returns a complete FIN message
curl -s -X POST "$API/api/v1/messages/generate" \
  -H 'Content-Type: application/json' \
  --data @demo/requests/MT541-generate.json | jq -r '.outputs.fin'

# sese.023 — the ISO 20022 equivalent, AppHdr plus Document
curl -s -X POST "$API/api/v1/messages/generate" \
  -H 'Content-Type: application/json' \
  --data @demo/requests/sese023-generate.json | jq -r '.outputs.xml'
```

Both should match the corresponding file in [`expected/`](expected) byte for byte.

## Validate without generating

```bash
curl -s -X POST "$API/api/v1/messages/validate" \
  -H 'Content-Type: application/json' \
  --data @demo/requests/MT548-generate.json | jq '.validation.summary, .validation.errors'
```

## Import an existing message

```bash
curl -s -X POST "$API/api/v1/messages/import" \
  -H 'Content-Type: application/json' \
  --data @demo/requests/MT541-import.json \
  | jq '{messageType, elementCount, importIssues, identical: .diff.summary.identical}'
```

The format and the message type come from the message itself. `identical: true` means the
studio rebuilt exactly what you sent.

## Compare original with regenerated

```bash
curl -s -X POST "$API/api/v1/messages/diff" \
  -H 'Content-Type: application/json' \
  --data @demo/requests/MT541-diff.json \
  | jq '.diff.summary, [.diff.lines[] | select(.kind != "UNCHANGED") | {kind, reason, field}]'
```

One changed line, `reason: "USER_EDIT"`, `field: "Sender'\''s Message Reference"`.
`summary.unexplained` is the only figure worth failing a pipeline on.

## Excel in, messages out

```bash
curl -s "$API/api/v1/templates/MT.xlsx" -o /tmp/MT.xlsx     # or use demo/excel/demo-MT.xlsx

curl -s -X POST "$API/api/v1/messages/generate-from-excel" \
  -F "file=@demo/excel/demo-MT.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  | jq '{generated, failed, first: .results[0].outputs.fin}'
```

## Look a field up

```bash
curl -s "$API/api/v1/intelligence/search?q=PSET" | jq '.hits[0] | {address, displayName, businessMeaning}'
```

## What the platform claims, and from what

```bash
curl -s "$API/api/v1/coverage" | jq '{messages: (.messages | length), authoritativeCompletenessKnown}'
curl -s "$API/api/v1/sources"  | jq '.sources[] | {id, state, present}'
```

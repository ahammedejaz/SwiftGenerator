# Official ISO 20022 schemas

Drop authoritative `.xsd` files here to upgrade MX validation from
`SUBSET_DERIVED` to `OFFICIAL`. No code change is needed — the schema is picked up on the
next request. Set `MX_OFFICIAL_XSD_DIRECTORY` to read them from somewhere outside the
checkout instead.

The full procedure for all four classes of authoritative artifact is in
[docs/authoritative-sources.md](../../../../../docs/authoritative-sources.md).

## Naming

One file per message version, named exactly after the version:

```
sese.023.001.11.xsd
sese.024.001.13.xsd
sese.025.001.12.xsd
```

The lookup is `config/mx/xsd/official/<version>.xsd`, where `<version>` is the `version`
field of the matching file in `backend/config/mx/`. A name that does not match is silently
not found, so check the spelling against the YAML rather than against the ISO catalogue.

## What changes when you add one

| | Without a file here | With a file here |
|---|---|---|
| `schemaSource` in the API response | `SUBSET_DERIVED` | `OFFICIAL` |
| What validation proves | the document matches *this repository's configured subset* | the document conforms to the official message definition |

Both are compiled and enforced by libxml2 — the derived schema is a real XSD, not a
formality — but only the official one is conformance. The response always reports which was
used, and the tool never claims the derived schema is authoritative.

## Why the directory is empty

ISO 20022 schemas are licensed artifacts. They are deliberately not vendored into this
repository. Obtain them from your own ISO 20022 or SWIFT MyStandards entitlement and copy
them in locally; `.gitignore` keeps `.xsd` files here out of version control so a licensed
file is never committed by accident.

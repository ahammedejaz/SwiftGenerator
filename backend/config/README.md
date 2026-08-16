# Configuration is the source of truth

A message is a specification plus values. The specification lives here, in YAML, and nothing
in this directory is code. Adding a field, a message or a client profile is an edit here.

| Directory | Holds | Read by |
| --- | --- | --- |
| `knowledge/` | MT, per tag: meaning, format, examples, common mistakes | `app/knowledge/loader.py` |
| `specifications/` | MT, per message: sequences and row order | `app/specifications/registry.py` |
| `mx/` | MX, per message: the complete nested element tree | `app/studio/mx/registry.py` |
| `mx/xsd/official/` | Licensed ISO 20022 schemas, dropped in locally | `app/studio/mx/xsd.py` |
| `profiles/` | Client profiles: currencies, rules, envelope values | `app/profiles/loader.py` |

Each location has a setting that redirects it, so an authorised artifact can be read from
outside the checkout without touching code: `MT_SPECIFICATION_MANIFEST`,
`MX_SPECIFICATION_DIRECTORY`, `MX_OFFICIAL_XSD_DIRECTORY`, `CLIENT_PROFILE_DIRECTORY`. An
unset setting means "the configuration committed here", which is what keeps a clean clone
working with no environment at all.

Nothing licensed is committed. The procedure for importing an authoritative source — and
what each one changes — is in [docs/authoritative-sources.md](../../docs/authoritative-sources.md).
`GET /api/v1/sources` reports what is present right now.

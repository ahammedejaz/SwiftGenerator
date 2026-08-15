# Client profiles

Profiles are versioned YAML rule packs under `backend/config/profiles`. They are demonstration configuration, not learned from historical messages and not institution-approved. The loader uses a strict Pydantic schema, rejects duplicate profile IDs, and exposes requirements/defaults through one repository.

## Visible profile behavior

| Behavior | Base Demo V1 | BFS Client Demo V1 |
| --- | --- | --- |
| Client reference | Optional | Required for MT540–MT547 |
| Place of settlement default | None | `SYNTHPSET01` |
| Allowed currencies | USD, EUR, GBP | USD, EUR |
| Sender reference max | 16 | 12 |
| Function default | NEWM | NEWM |
| Quantity type default | UNIT | UNIT |

This gives the demonstration one required-field change, one default change, and at least one validation-rule change when the profile switches. Reports and messages record profile ID and version.

## Configuration shape

- Identity: `profileId`, semantic `version`, standards release label, demo status.
- `supportedMessageTypes`: explicit MT allowlist.
- `defaults`: canonical field paths only.
- `allowedCurrencies`: controlled DVP list.
- `requiredFields`: base requirement list per MT type.
- `clientRequiredFields`: profile additions per MT type.
- `enabledNegativeMutations`: controlled allowlist.
- `validation.senderReference`: length and uppercase/alphanumeric format.

## Adding a profile safely

1. Copy an existing demo YAML under a new unique ID/version.
2. Use canonical snake_case paths exactly as the loader expects.
3. Use synthetic defaults only; never add production accounts, BICs, counterparties, or messages.
4. Add profile-loader, missing-field, validation, and message golden/regression tests.
5. Review supported statuses and negative mutations.
6. Restart the API because profiles are loaded at process startup.

Profile inheritance/merging is intentionally not implicit in this MVP; each file is a reviewable complete rule pack.

Profiles explicitly enable MT530, MT537, and MT564–MT568. Their dedicated typed services own required workflow fields. Knowledge overlays may strengthen presence, narrow codes/options, and add client wording; they cannot weaken mandatory presence or broaden a base allowlist. Profile, standards, and knowledge versions participate in cache identity and reporting.

## Secure authoring behaviour

Profile defaults are never silently inserted into a real-data draft. The builder displays each
default and its `PROFILE_DEFAULT` source before composition. Switching profile increments the
draft revision, clears validation/checksum, and invalidates approval while preserving entered data
for explicit reconciliation. Current Base/BFS profiles are demonstration rule packs, not approved
production client packs; production requires a `CLIENT_VERIFIED` imported profile.

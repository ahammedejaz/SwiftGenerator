# Message Builder Guide

The `/message-builder` workspace is the secure entry point for the configured MT530, MT537,
MT540–MT548, and MT564–MT568 subsets.

1. Sign in through the explicitly labelled development identity picker (development only).
2. Select a message and profile, then create an empty draft. No sample or business value is
   inserted automatically.
3. Add configured optional sequences or repeatable sequence occurrences. Child occurrences must
   be attached to an eligible parent and cardinality limits are enforced.
4. Add fields from the sequence browser. The builder displays tag, qualifier, presence,
   deterministic condition, format, provenance, and Tag Intelligence link.
5. Enter actual values. Each field retains its source (`USER_ENTERED`, profile default, imported,
   derived, or sample). Formula-like and FIN-block injection values are rejected.
6. Compose and inspect Block 4, line mappings, checksum, findings, and each validation level.
7. Download evidence or request review. Edits after approval create a new revision and invalidate
   the approval.

`Load Sample` is explicit. Loaded fields remain `SAMPLE_DATA` and unconfirmed until replaced or
confirmed. Profile changes preserve values but invalidate the previous validation and approval.

The builder exposes every row in the **configured subset**, not every field in the current
official standard. An unavailable row cannot be invented in Raw mode; import shows unknown fields
as unsupported rather than treating them as valid.

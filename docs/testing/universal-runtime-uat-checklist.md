# Universal runtime UAT checklist

Record environment, commit SHA, browser, knowledge mode and AI provider with the result.

## Startup and catalogue

- [ ] `make quickstart` succeeds from a clean clone with no AI key and no knowledge bundle.
- [ ] `/api/health/live` is alive and `/api/health/ready` is ready with optional services labeled.
- [ ] Create Message exposes configured MT/MX choices before preview enrichment finishes.
- [ ] Direct load, refresh and leave/return issue one configured and one preview catalogue request per browser runtime.
- [ ] A preview failure leaves configured messages usable and names the optional failure.

## Dynamic runtime and AI

- [ ] A generation-ready preview MT and MX can be selected only with explicit lane/release.
- [ ] Generated preview MT and MX use ordinary validation, provenance and download paths.
- [ ] AI sample output is synthetic, cited where evidence exists, and deterministically valid.
- [ ] A cache hit says zero live calls; deterministic fallback does not present as a model call.
- [ ] AI & Knowledge Usage shows overview, RAG, embeddings, knowledge, cache and bounded operations.
- [ ] Inspect the telemetry response for absence of prompts, values, excerpts, credentials and endpoints.

## Conversion

- [ ] `/convert` labels the bundled pack `SYNTHETIC_TEST_ONLY` and production-ineligible.
- [ ] Conversion without explicit preview opt-in returns `BLOCKED_BY_MAPPING_EVIDENCE`.
- [ ] The synthetic MT541 proof reports mapped, derived, missing and not-represented fields.
- [ ] Removing a required mapped source value returns `NEEDS_INPUT`; no target XML is produced.
- [ ] Supplying missing target data reruns ordinary MX validation and yields XML only when valid.
- [ ] A target version mismatch fails without fallback.

## Distribution and security

- [ ] `make knowledge-fetch` rejects HTTP, bad checksum, traversal, links and devices.
- [ ] `git ls-files` contains no raw operator PDF/XSD/ZIP, source index, secret or `.env`.
- [ ] `make check`, `make e2e`, `make audit`, `make secret-scan` and Docker build pass.

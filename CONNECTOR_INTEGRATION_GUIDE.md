# Connector Integration Guide

The server-side registry models download-only, HTTPS UAT, SFTP/file drop, MQ, Alliance Access
file/MQ/SOAP, Lite2 AutoClient file, and custom adapters. Only `DOWNLOAD_ONLY` is a normal
operational capability. `MOCK_UAT` is available only under explicit development/test configuration
and emits clearly marked mock acknowledgements; it never contacts a real endpoint.

A real adapter must implement the provider-neutral connector contract, obtain destinations and
credentials exclusively from a server-side secret/configuration store, enforce an allowlist,
provide bounded timeout/retry semantics and idempotency, and return safe response metadata. It
must never accept a browser-supplied host.

Production is disabled unless both `SUBMISSION_MODE=production` and
`PRODUCTION_SUBMISSION_ENABLED=true` are present and all approval/validation policies pass. No
client connector contract or Alliance library is included, so no live connectivity is claimed.

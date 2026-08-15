# Authentication and RBAC Guide

Roles are `VIEWER`, `AUTHOR`, `REVIEWER`, `APPROVER`, `SUBMITTER`, `PROFILE_ADMIN`,
`SECURITY_ADMIN`, and `AUDITOR`. Routes apply least-privilege checks and every draft lookup is
tenant-scoped.

The development provider issues server-side sessions with opaque HMAC-protected cookies, CSRF
double-submit tokens, expiry, and explicit identities. It is rejected in production. The
provider-neutral identity protocol is ready for an OIDC or SAML adapter, but no production IdP
contract or credentials exist in this repository; production authentication is therefore not
operational.

Maker-checker rules prohibit authors approving their own draft. Approval binds a tenant, revision,
and checksum. Any field, sequence, or profile edit increments the revision, resets validation,
and invalidates active approval. Production submission additionally requires a submitter role,
immutable approval, external validation when configured, an allowlisted connector, and the dual
production gate.
